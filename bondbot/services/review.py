from __future__ import annotations

import json
from datetime import datetime

from bondbot.analytics.portfolio import analyze_portfolio
from bondbot.analytics.risk import assess_portfolio_risk, stress_portfolio
from bondbot.config import Settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import to_msk, utcnow
from bondbot.strategy.safe import safe_range

SNAPSHOT_KEY = "portfolio_snapshot"


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def _pct(value: float | None) -> str:
    return f"{value:.2f}%" if value is not None else "—"


def _num(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "—"


def portfolio_metrics(settings: Settings, db: Database):
    positions = db.positions()
    bonds = {bond.isin: bond for bond in db.list_bonds()}
    metrics = analyze_portfolio(
        positions,
        bonds,
        max_pct_daily_volume=settings.max_pct_daily_volume,
    )
    return positions, bonds, metrics


def save_portfolio_snapshot(
    settings: Settings,
    db: Database,
    *,
    now: datetime | None = None,
) -> dict:
    current = now or utcnow()
    positions, _, metrics = portfolio_metrics(settings, db)
    payload = {
        "date": to_msk(current).date().isoformat(),
        "created_at": current.isoformat(),
        "total_value_rub": metrics.total_value_rub,
        "total_cost_rub": metrics.total_cost_rub,
        "profit_rub": metrics.profit_rub,
        "annual_coupon_rub": metrics.annual_coupon_rub,
        "weighted_ytm_pct": metrics.weighted_ytm_pct,
        "weighted_duration_years": metrics.weighted_duration_years,
        "positions": [
            {
                "isin": position.isin,
                "name": position.name,
                "value_rub": position.current_value_rub,
                "ytm_pct": position.ytm_pct,
            }
            for position in positions
        ],
    }
    db.kv_set(SNAPSHOT_KEY, json.dumps(payload, ensure_ascii=False))
    return payload


def load_portfolio_snapshot(db: Database) -> dict | None:
    raw = db.kv_get(SNAPSHOT_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def build_what_changed(
    settings: Settings,
    db: Database,
    *,
    now: datetime | None = None,
) -> str:
    current = now or utcnow()
    positions, _, metrics = portfolio_metrics(settings, db)
    previous = load_portfolio_snapshot(db)
    lines = [f"🔄 Что изменилось · {to_msk(current):%d.%m.%Y}", ""]
    if previous is None:
        lines.append("Предыдущего снимка нет. Текущий срез сохранён.")
        lines.append(f"Стоимость: {_money(metrics.total_value_rub)}")
        lines.append(f"P&L: {_money(metrics.profit_rub)}")
        lines.append(f"Средняя YTM: {_pct(metrics.weighted_ytm_pct)}")
        save_portfolio_snapshot(settings, db, now=current)
        return "\n".join(lines)

    lines.append(
        f"Стоимость: {_money(previous.get('total_value_rub'))} → "
        f"{_money(metrics.total_value_rub)} "
        f"({_money(metrics.total_value_rub - float(previous.get('total_value_rub') or 0))})"
    )
    lines.append(
        f"P&L: {_money(previous.get('profit_rub'))} → {_money(metrics.profit_rub)}"
    )
    prev_ytm = previous.get("weighted_ytm_pct")
    if prev_ytm is not None and metrics.weighted_ytm_pct is not None:
        lines.append(
            f"Средняя YTM: {_pct(float(prev_ytm))} → {_pct(metrics.weighted_ytm_pct)}"
        )
    prev_duration = previous.get("weighted_duration_years")
    if prev_duration is not None and metrics.weighted_duration_years is not None:
        lines.append(
            f"Дюрация: {_num(float(prev_duration))} → "
            f"{_num(metrics.weighted_duration_years)} лет"
        )

    previous_positions = {
        str(item.get("isin")): float(item.get("value_rub") or 0)
        for item in previous.get("positions") or []
    }
    changes: list[str] = []
    for position in positions:
        before = previous_positions.get(position.isin)
        after = position.current_value_rub or 0.0
        if before is None:
            changes.append(f"• {position.name}: новая позиция {_money(after)}")
        elif abs(after - before) >= 1:
            changes.append(
                f"• {position.name}: {_money(before)} → {_money(after)} "
                f"({_money(after - before)})"
            )
    if changes:
        lines.append("")
        lines.append("Позиции:")
        lines.extend(changes[:10])
    if not changes:
        lines.append("")
        lines.append("Существенных изменений по позициям нет.")
    prev_date = previous.get("date")
    if prev_date:
        lines.append("")
        lines.append(f"Сравнение со снимком {prev_date}.")
    lines.append("Не индивидуальная инвестиционная рекомендация.")
    return "\n".join(lines)


def build_portfolio_review(
    settings: Settings,
    db: Database,
    snapshot: KeyRateSnapshot,
    *,
    now: datetime | None = None,
) -> str:
    current = now or utcnow()
    positions, bonds, metrics = portfolio_metrics(settings, db)
    risk = assess_portfolio_risk(positions, bonds, snapshot.value_pct, now=current)
    stress = stress_portfolio(positions, bonds, 100.0)
    range_ = safe_range(snapshot)
    lines = [
        f"🩺 Портфель · {to_msk(current):%d.%m.%Y}",
        f"Стоимость: {_money(metrics.total_value_rub)} · P&L {_money(metrics.profit_rub)}",
        f"Купон: {_money(metrics.annual_coupon_rub)} · YTM {_pct(metrics.weighted_ytm_pct)} · "
        f"дюрация {_num(metrics.weighted_duration_years)} лет",
        f"Риск-скор: {risk.score:.0f}/100 ({risk.level})",
        f"Коридор: {range_.low_pct:.2f}–{range_.high_pct:.2f}% · "
        f"стресс +100 б.п.: {_money(stress.impact_rub)}",
    ]
    if metrics.rating_mix:
        ratings = " · ".join(
            f"{rating} {share:.0%}" for rating, share in sorted(metrics.rating_mix.items())
        )
        lines.append(f"Рейтинги: {ratings}")
    if risk.warnings:
        lines.append("")
        lines.append("Что требует внимания:")
        lines.extend(f"• {warning}" for warning in risk.warnings[:8])
    checklist: list[str] = []
    if (metrics.weighted_duration_years or 0) > 3:
        checklist.append("дюрация выше 3 лет — проверить чувствительность к ставке")
    if metrics.weighted_ytm_pct is not None and metrics.weighted_ytm_pct > 22:
        checklist.append("средняя YTM выше 22% — проверить кредитный риск")
    if not checklist:
        checklist.append("критичных отклонений по профилю нет")
    lines.append("")
    lines.append("Чек-лист:")
    lines.extend(f"• {item}" for item in checklist)
    if metrics.warnings:
        lines.append("")
        lines.append("Лимиты и ликвидность:")
        lines.extend(f"• {warning}" for warning in metrics.warnings[:8])
    lines.append("")
    lines.append("Не индивидуальная инвестиционная рекомендация.")
    return "\n".join(lines)


__all__ = [
    "SNAPSHOT_KEY",
    "build_portfolio_review",
    "build_what_changed",
    "load_portfolio_snapshot",
    "portfolio_metrics",
    "save_portfolio_snapshot",
]
