from __future__ import annotations

from datetime import datetime

from bondbot.analytics.portfolio import analyze_portfolio
from bondbot.config import Settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import to_msk, utcnow
from bondbot.services.news import build_news_digest
from bondbot.strategy.safe import build_safe_list, safe_range
from bondbot.strategy.types import SafeListResult


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def _pct(value: float | None) -> str:
    return f"{value:.2f}%" if value is not None else "—"


def _num(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "—"


def _short(text: str, limit: int = 3900) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_digest(
    settings: Settings,
    db: Database,
    snapshot: KeyRateSnapshot,
    *,
    now: datetime | None = None,
) -> str:
    current = now or utcnow()
    today = current.date()
    positions = db.positions()
    bonds = {bond.isin: bond for bond in db.list_bonds()}
    metrics = analyze_portfolio(
        positions,
        bonds,
        max_pct_daily_volume=settings.max_pct_daily_volume,
    )
    range_ = safe_range(snapshot)
    safe: SafeListResult = build_safe_list(
        settings,
        db,
        snapshot,
        limit=3,
        save_audit=False,
        now=current,
    )

    lines = [
        f"📬 Дайджест {to_msk(current):%d.%m.%Y}",
        f"Ставка ЦБ: {range_.describe()}",
        f"Портфель: {_money(metrics.total_value_rub)} · P&L {_money(metrics.profit_rub)} · "
        f"купон {_money(metrics.annual_coupon_rub)}",
        f"Средняя YTM: {_pct(metrics.weighted_ytm_pct)} · "
        f"дюрация {_num(metrics.weighted_duration_years)} лет",
    ]

    if metrics.warnings:
        lines.append("")
        lines.append("Риски портфеля:")
        for warning in metrics.warnings[:5]:
            lines.append(f"• {warning}")

    if safe.items:
        lines.append("")
        lines.append("Идеи в коридоре:")
        for item in safe.items:
            bond = item.bond
            lines.append(
                f"• {bond.name} ({bond.isin}) — YTM {_pct(bond.ytm_pct)}, "
                f"дюр. {bond.duration_years:.2f} г, {bond.rating or '—'}, score {item.score.score:.0f}"
            )

    new_issues = db.recent_new_issues(days=7, limit=3)
    if new_issues:
        lines.append("")
        lines.append("Новые выпуски:")
        for row in new_issues:
            lines.append(
                f"• {row.get('name') or row['isin']} ({row['isin']}) — "
                f"YTM {_pct(row.get('ytm_pct'))}, рейтинг {row.get('rating') or '—'}"
            )

    events: list[str] = []
    for position in positions:
        bond = bonds.get(position.isin)
        if bond is None:
            continue
        if bond.offer_date and 0 <= (bond.offer_date - today).days <= 30:
            events.append(f"{bond.name}: оферта {(bond.offer_date - today).days} дн.")
        if bond.maturity_date and 0 <= (bond.maturity_date - today).days <= 30:
            events.append(f"{bond.name}: погашение {(bond.maturity_date - today).days} дн.")
    if events:
        lines.append("")
        lines.append("Календарь:")
        lines.extend(f"• {event}" for event in events[:8])

    news = build_news_digest(settings, db, limit=3)
    if "не найдено" not in news:
        lines.append("")
        lines.append(news)

    lines.append("")
    lines.append("Не индивидуальная инвестиционная рекомендация.")
    return _short("\n".join(lines))


__all__ = ["build_digest"]
