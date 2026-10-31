from __future__ import annotations

from datetime import datetime

from bondbot.analytics.risk import RiskAssessment, StressResult
from bondbot.models import to_msk
from bondbot.strategy.types import (
    AllocationResult,
    BondValuation,
    ExitPlanResult,
    SafeListResult,
)

_MAX_MESSAGE = 3800


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def _num(value: float | None, suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}{suffix}"


def _pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}%"


def _short(text: str, limit: int = _MAX_MESSAGE) -> str:
    # Длинные сообщения разбивает VK-слой; здесь ничего не обрезаем.
    return (text or "").strip()


def _share(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1%}"


def _dt(value: datetime | None) -> str:
    localized = to_msk(value)
    return localized.strftime("%d.%m.%Y %H:%M") if localized else "—"


def render_safe_list(result: SafeListResult, limit: int = 8) -> str:
    lines = [
        "🛡 Стабильные бумаги",
        f"Диапазон: {result.range.describe()}",
        f"Обзор {result.universe_size}, подходит {result.eligible_size}, показано {min(limit, len(result.items))}",
        "",
    ]
    for index, item in enumerate(result.items[:limit], start=1):
        bond = item.bond
        score = item.score
        reasons = " · ".join(score.reasons[:3]) or "—"
        lines.append(
            f"{index}. {bond.name} ({bond.isin}) — {score.score:.0f}/100"
        )
        lines.append(
            f"   YTM {_pct(bond.ytm_pct, 2)} · дюр. {_num(bond.duration_years)} г · "
            f"{bond.rating or '—'} · цена {_pct(bond.price_pct, 2)}"
        )
        lines.append(
            f"   объём {_num(bond.volume_mn_rub, ' млн ₽', 1)} · "
            f"выпуск {_num(bond.issue_size_rub / 1_000_000 if bond.issue_size_rub else None, ' млн ₽', 0)} · "
            f"G-спред {_num(bond.g_spread_bp if bond.g_spread_bp is not None else None, ' б.п.', 0)}"
        )
        lines.append(f"   почему: {reasons}")
    lines.append("")
    lines.append("Оценка: рейтинг 30% · ликвидность 20% · дюрация 15% · выпуск 10% · цена 10% · YTM в диапазоне 10% · данные 5%")
    lines.append(f"Аудит: id {result.audit_id} · {_dt(result.generated_at)}")
    lines.append("Не рекомендация. Проверяй офера, амортизацию и рейтинги.")
    return _short("\n".join(lines))


def render_exit_plan(result: ExitPlanResult) -> str:
    lines = [
        "💧 Ликвидность и выход",
        f"Портфель: {_money(result.total_value_rub)} · горизонт {result.plans[0].horizon_days if result.plans else '—'} дн.",
        "",
    ]
    for plan in result.plans:
        lines.append(
            f"• {plan.name} ({plan.isin}) — {_money(plan.position_value_rub)}"
        )
        lines.append(
            f"   объём {_num(plan.daily_volume_rub / 1_000_000 if plan.daily_volume_rub else None, ' млн ₽', 1)} · "
            f"доля {_share(plan.share_of_daily_volume)} · "
            f"выход {_num(plan.days_to_exit, ' дн.', 2)}"
        )
        lines.append(
            f"   макс. на {plan.horizon_days} дн. {_money(plan.max_position_rub)} · "
            f"докупка {_money(plan.allowed_topup_rub)}"
        )
    if result.warnings:
        lines.append("")
        lines.append("Предупреждения:")
        for warning in result.warnings[:10]:
            lines.append(f"• {warning}")
    lines.append("")
    lines.append(f"Аудит: id {result.audit_id} · {_dt(result.generated_at)}")
    lines.append("Не рекомендация.")
    return _short("\n".join(lines))


def render_risk(result: RiskAssessment) -> str:
    icons = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
    lines = [
        f"{icons.get(result.level, '•')} Риск: {result.name} ({result.isin})",
        f"Оценка: {result.score:.0f}/100 · уровень {result.level}",
    ]
    if result.factors:
        lines.append("")
        lines.append("Факторы:")
        for factor in sorted(result.factors, key=lambda item: item.score, reverse=True):
            lines.append(
                f"• {factor.name}: {factor.score:.0f}/100 (вес {factor.weight:.0%}) — {factor.note}"
            )
    if result.warnings:
        lines.append("")
        lines.append("Предупреждения:")
        lines.extend(f"• {warning}" for warning in result.warnings[:10])
    lines.append("")
    lines.append("Оценка выше = риск выше. Это аналитика, не рекомендация.")
    return _short("\n".join(lines))


def render_stress(result: StressResult) -> str:
    lines = [
        f"📉 Стресс-тест: ставка {result.delta_bp:+.0f} б.п.",
        f"Текущая стоимость: {_money(result.current_value_rub)}",
        f"Влияние: {_money(result.impact_rub)}",
        f"Новая стоимость: {_money(result.new_value_rub)}",
        f"Годовой купон: {_money(result.annual_income_rub)}",
    ]
    if result.notes:
        lines.append("")
        lines.append("Заметки:")
        lines.extend(f"• {note}" for note in result.notes[:8])
    lines.append("")
    lines.append("Оценка по модифицированной дюрации; фактический результат может отличаться.")
    return _short("\n".join(lines))


def render_valuation(result: BondValuation) -> str:
    lines = [
        f"📐 {result.name} ({result.isin})",
        f"YTM: {_pct(result.ytm_pct, 2)} · после налога: {_pct(result.after_tax_ytm_pct, 2)}",
        f"Дюрация: {_num(result.duration_years)} лет · модифицированная: {_num(result.modified_duration)}",
        f"G-спред: {_num(result.g_spread_bp, ' б.п.', 0)} · Z-спред: {_num(result.z_spread_bp, ' б.п.', 1)}",
        f"Carry: {_num(result.carry_pct, ' п.п.')}",
        f"Налог: {result.tax_rate:.0%}",
    ]
    if result.warnings:
        lines.append("")
        lines.append("Предупреждения:")
        lines.extend(f"• {warning}" for warning in result.warnings[:8])
    if result.formulas:
        lines.append("")
        lines.append("Формулы:")
        lines.extend(f"• {formula}" for formula in result.formulas[:6])
    lines.append("")
    lines.append("Не индивидуальная инвестиционная рекомендация.")
    return _short("\n".join(lines))


def render_allocation(result: AllocationResult) -> str:
    lines = [
        "🧮 Целевая аллокация",
        f"Капитал {_money(result.total_value_rub)} · "
        f"резерв {_money(result.cash_reserve_rub)} · под цели {_money(result.investable_rub)}",
        "",
        "Покупка/удержание:",
    ]
    buys = [t for t in result.targets if t.action == "buy"]
    holds = [t for t in result.targets if t.action == "hold"]
    sells = [t for t in result.targets if t.action == "sell"]

    for target in buys + holds:
        lines.append(
            f"• {target.bond.name} ({target.bond.isin}) — "
            f"{_share(target.current_weight)} → {_share(target.target_weight)} · "
            f"{target.action.upper()} {_money(abs(target.delta_value_rub))} · "
            f"score {target.score:.0f}"
        )
    if sells:
        lines.append("")
        lines.append("Продажи:")
        for target in sells:
            exit_days = None
            if target.liquidity:
                exit_days = target.liquidity.days_to_exit
            lines.append(
                f"• {target.bond.name} ({target.bond.isin}) — "
                f"{_share(target.current_weight)} → 0 · "
                f"{_money(abs(target.delta_value_rub))} · выход {_num(exit_days, ' дн.', 2)} · {target.note or ''}"
            )
    lines.append("")
    lines.append(
        f"Ограничения: позиция ≤ {result.constraints.max_position_share:.0%} · "
        f"группа рейтинга ≤ {result.constraints.max_rating_share:.0%} · "
        f"ликвидность {result.constraints.max_pct_daily_volume:.0%} · "
        f"горизонт {result.constraints.exit_horizon_days} дн."
    )
    if result.warnings:
        lines.append("")
        lines.append("Предупреждения:")
        for warning in result.warnings[:10]:
            lines.append(f"• {warning}")
    lines.append("")
    lines.append(f"Аудит: id {result.audit_id} · {_dt(result.generated_at)}")
    lines.append("Не рекомендация.")
    return _short("\n".join(lines))
