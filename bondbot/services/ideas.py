from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bondbot.analytics.portfolio import analyze_portfolio
from bondbot.config import Settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import utcnow
from bondbot.strategy.safe import build_safe_list, safe_range


@dataclass(frozen=True, slots=True)
class Idea:
    isin: str
    name: str
    ytm_pct: float | None
    price_pct: float | None
    rating: str | None
    duration_years: float | None
    score: float
    thesis: str
    risks: str


def build_ideas(
    settings: Settings,
    db: Database,
    snapshot: KeyRateSnapshot,
    *,
    limit: int = 3,
    now: datetime | None = None,
) -> list[Idea]:
    result = build_safe_list(
        settings,
        db,
        snapshot,
        limit=max(1, limit),
        save_audit=False,
        now=now,
    )
    ideas: list[Idea] = []
    for item in result.items:
        bond = item.bond
        thesis = (
            f"YTM {bond.ytm_pct:.2f}% в коридоре {result.range.low_pct:.2f}–"
            f"{result.range.high_pct:.2f}%, рейтинг {bond.rating or '—'}, "
            f"дюрация {bond.duration_years:.2f} г, оборот {bond.volume_mn_rub:.1f} млн ₽."
        )
        risks = "; ".join(item.score.penalties[:4]) or "явных штрафов скоринга нет"
        ideas.append(
            Idea(
                isin=bond.isin,
                name=bond.name,
                ytm_pct=bond.ytm_pct,
                price_pct=bond.price_pct,
                rating=bond.rating,
                duration_years=bond.duration_years,
                score=item.score.score,
                thesis=thesis,
                risks=risks,
            )
        )
    return ideas


def save_ideas(db: Database, ideas: list[Idea]) -> int:
    open_ideas = db.ideas(limit=200, status="open")
    existing = {str(item["isin"]) for item in open_ideas}
    saved = 0
    for idea in ideas:
        if idea.isin in existing:
            continue
        db.create_idea(
            isin=idea.isin,
            name=idea.name,
            thesis=idea.thesis,
            action="watch",
            price_pct=idea.price_pct,
            ytm_pct=idea.ytm_pct,
            risks=idea.risks,
        )
        saved += 1
    return saved


def render_ideas(ideas: list[Idea], snapshot: KeyRateSnapshot) -> str:
    lines = [
        "💡 Идеи в коридоре",
        f"Диапазон: {safe_range(snapshot).describe()}",
        "",
    ]
    if not ideas:
        lines.append("Под текущие фильтры идей нет. Проверь /safe и профиль риска.")
        return "\n".join(lines)
    for index, idea in enumerate(ideas, start=1):
        lines.append(f"{index}. {idea.name} ({idea.isin}) — score {idea.score:.0f}/100")
        lines.append(
            f"   YTM {idea.ytm_pct:.2f}% · цена {idea.price_pct:.2f}% · "
            f"{idea.rating or '—'} · дюр. {idea.duration_years:.2f} г"
            if idea.ytm_pct is not None
            and idea.price_pct is not None
            and idea.duration_years is not None
            else f"   score {idea.score:.0f}/100"
        )
        lines.append(f"   Тезис: {idea.thesis}")
        lines.append(f"   Риски: {idea.risks}")
    lines.append("")
    lines.append("Это идеи для самостоятельной проверки, не индивидуальная рекомендация.")
    return "\n".join(lines)


def render_journal(db: Database, limit: int = 10) -> str:
    ideas = db.ideas(limit=limit)
    if not ideas:
        return "📓 Журнал идей пуст. Сгенерируй идеи командой /idea."
    bonds = {bond.isin: bond for bond in db.list_bonds()}
    lines = ["📓 Журнал идей", ""]
    for item in ideas:
        bond = bonds.get(str(item["isin"]))
        current = bond.price_pct if bond else None
        outcome = None
        if current is not None and item.get("price_pct"):
            outcome = (current / float(item["price_pct"]) - 1.0) * 100.0
        outcome_text = f"{outcome:+.2f}%" if outcome is not None else "—"
        lines.append(
            f"#{item['id']} {item.get('name') or item['isin']} ({item['isin']}) · "
            f"{item['status']} · {outcome_text}"
        )
        lines.append(f"   {item['thesis']}")
        if item.get("risks"):
            lines.append(f"   Риски: {item['risks']}")
    lines.append("")
    lines.append("Доходность идеи считается по изменению цены; купоны не включены.")
    return "\n".join(lines)


def build_strategy_note(
    settings: Settings,
    db: Database,
    snapshot: KeyRateSnapshot,
    *,
    now: datetime | None = None,
) -> str:
    current = now or utcnow()
    positions = db.positions()
    bonds = {bond.isin: bond for bond in db.list_bonds()}
    metrics = analyze_portfolio(
        positions,
        bonds,
        max_pct_daily_volume=settings.max_pct_daily_volume,
    )
    range_ = safe_range(snapshot)
    ideas = build_ideas(settings, db, snapshot, limit=3, now=current)
    lines = [
        f"🧭 Стратегия на {current:%d.%m.%Y}",
        f"Ключевая ставка: {snapshot.value_pct:.2f}% на {snapshot.as_of:%d.%m.%Y}",
        f"Рабочий коридор YTM: {range_.low_pct:.2f}–{range_.high_pct:.2f}%",
        f"Портфель: {metrics.total_value_rub:,.0f} ₽ · средняя YTM "
        f"{metrics.weighted_ytm_pct:.2f}% · дюрация {metrics.weighted_duration_years:.2f} г"
        if metrics.weighted_ytm_pct is not None and metrics.weighted_duration_years is not None
        else f"Портфель: {metrics.total_value_rub:,.0f} ₽",
        "",
        "Что смотреть:",
        "• Дюрация: при ожидании снижения ставки длиннее, при росте — короче.",
        "• Кредит: не поднимать долю ВДО выше лимита; следить за офертами.",
        "• Ликвидность: позиция должна выходить за горизонт, а не за один день.",
    ]
    if ideas:
        lines.append("")
        lines.append("Идеи:")
        for idea in ideas:
            lines.append(f"• {idea.name} ({idea.isin}) — YTM {idea.ytm_pct:.2f}%, score {idea.score:.0f}")
    if metrics.warnings:
        lines.append("")
        lines.append("Риски портфеля:")
        lines.extend(f"• {warning}" for warning in metrics.warnings[:8])
    lines.append("")
    lines.append("Сценарии: снижение ставки поддерживает цену и длинную дюрацию; "
                 "рост ставки давит на цену, но повышает доходность новых вложений.")
    lines.append("Не индивидуальная инвестиционная рекомендация.")
    return "\n".join(lines)


__all__ = [
    "Idea",
    "build_ideas",
    "build_strategy_note",
    "render_ideas",
    "render_journal",
    "save_ideas",
]
