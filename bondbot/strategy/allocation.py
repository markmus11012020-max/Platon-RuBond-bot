from __future__ import annotations

import logging
from dataclasses import asdict, replace
from datetime import datetime, timezone

from bondbot.analytics.bonds import meets_min_rating
from bondbot.config import Settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import Bond, PortfolioPosition
from bondbot.strategy.safe import required_daily_volume_mn_from, safe_range
from bondbot.strategy.stability import stability_score
from bondbot.strategy.types import (
    AllocationConstraints,
    AllocationResult,
    AllocationTarget,
    LiquidityPlan,
)

log = logging.getLogger(__name__)

_TOLERANCE = 1e-9


def _eligible_for_constraints(
    bond: Bond,
    low_pct: float,
    high_pct: float,
    constraints: AllocationConstraints,
    required_volume_mn: float,
) -> tuple[bool, str]:
    if bond.qual_only:
        return False, "только для квалов"
    if bond.ytm_pct is None or bond.duration_years is None:
        return False, "нет YTM или дюрации"
    if not (low_pct <= bond.ytm_pct <= high_pct):
        return False, f"YTM {bond.ytm_pct:.2f}% вне диапазона {low_pct:.2f}–{high_pct:.2f}%"
    if bond.duration_years > constraints.max_duration_years:
        return False, f"дюрация {bond.duration_years:.2f} г выше лимита {constraints.max_duration_years:.0f}"
    if not meets_min_rating(bond.rating, constraints.min_rating):
        return False, f"рейтинг {bond.rating or '—'} ниже минимума {constraints.min_rating}"
    if bond.price_pct is None or not (
        constraints.min_price_pct <= bond.price_pct <= constraints.max_price_pct
    ):
        price = f"{bond.price_pct:.2f}%" if bond.price_pct is not None else "н/д"
        return False, f"цена {price} вне {constraints.min_price_pct:.0f}–{constraints.max_price_pct:.0f}%"
    if bond.volume_mn_rub is None or bond.volume_mn_rub < required_volume_mn:
        volume = f"{bond.volume_mn_rub:.1f}" if bond.volume_mn_rub is not None else "н/д"
        return False, f"оборот {volume} млн ₽ ниже минимума {required_volume_mn:.0f}"
    return True, ""


def _position_value(position: PortfolioPosition) -> float:
    if position.current_value_rub is not None:
        return position.current_value_rub
    if position.buy_price_pct is not None and position.qty is not None:
        return position.qty * position.buy_price_pct / 100 * 1000
    return 0.0


def _caps_for(
    bond: Bond,
    investable_rub: float,
    constraints: AllocationConstraints,
    required_volume_mn: float,
) -> tuple[float, str | None]:
    """Индивидуальный потолок доли: общий лимит и ликвидность."""
    cap = constraints.max_position_share
    note: str | None = None
    if bond.volume_mn_rub and bond.volume_mn_rub > 0:
        daily = bond.volume_mn_rub * 1_000_000
        max_position = daily * constraints.max_pct_daily_volume * constraints.exit_horizon_days
        if investable_rub > 0:
            liquidity_cap = max_position / investable_rub
            if liquidity_cap < cap:
                cap = liquidity_cap
                note = "лимит по ликвидности"
    else:
        note = "нет данных об объёме"
    if bond.volume_mn_rub is not None and bond.volume_mn_rub < required_volume_mn:
        note = "оборот ниже минимума"
    return max(0.0, cap), note


def _waterfill(
    scores: dict[str, float],
    caps: dict[str, float],
    rating_caps: dict[str, float],
    rating_of: dict[str, str],
) -> dict[str, float]:
    weights: dict[str, float] = {isin: score for isin, score in scores.items()}
    total = sum(weights.values())
    if total <= 0:
        return {isin: 0.0 for isin in weights}
    weights = {isin: score / total for isin, score in weights.items()}

    for _ in range(40):
        excess = 0.0

        for isin, weight in list(weights.items()):
            cap = caps.get(isin, 1.0)
            if weight > cap + _TOLERANCE:
                excess += weight - cap
                weights[isin] = cap

        groups: dict[str, float] = {}
        for isin, rating in rating_of.items():
            groups[rating] = groups.get(rating, 0.0) + weights[isin]
        for rating, group_weight in list(groups.items()):
            cap = rating_caps.get(rating, 1.0)
            if group_weight > cap + _TOLERANCE:
                scale = cap / group_weight
                for isin in rating_of:
                    if rating_of[isin] != rating:
                        continue
                    before = weights[isin]
                    after = before * scale
                    excess += before - after
                    weights[isin] = after

        if excess <= 1e-7:
            break

        recipients = [
            isin
            for isin, weight in weights.items()
            if weight < caps.get(isin, 1.0) - _TOLERANCE
        ]
        if not recipients:
            break

        total_score = sum(scores[isin] for isin in recipients)
        if total_score <= 0:
            step = excess / len(recipients)
            for isin in recipients:
                weights[isin] += step
        else:
            for isin in recipients:
                weights[isin] += excess * scores[isin] / total_score

    return weights


def build_allocation(
    settings: Settings,
    db: Database,
    snapshot: KeyRateSnapshot,
    *,
    constraints: AllocationConstraints | None = None,
    save_audit: bool = True,
    now: datetime | None = None,
) -> AllocationResult:
    """Детерминированная целевая аллокация портфеля.

    Диапазон: ключевая ставка + 5..10 п.п. (по умолчанию).
    Ограничения: максимальная доля позиции, доля на группу рейтинга,
    ликвидность по объёму, минимальный рейтинг, дюрация.
    LLM не участвует — только формулы."""
    from bondbot.analytics.portfolio import analyze_portfolio

    now = now or datetime.now(timezone.utc)
    range = safe_range(snapshot)
    cons = constraints or AllocationConstraints()
    required_volume_mn = required_daily_volume_mn_from(settings)

    bonds: dict[str, Bond] = {}
    for bond in db.list_bonds():
        bonds[bond.isin] = bond

    positions: list[PortfolioPosition] = db.positions()
    current_total = sum(_position_value(p) for p in positions)
    total_value_rub = current_total if current_total > 0 else settings.portfolio_size_rub
    investable_rub = total_value_rub * (1.0 - cons.cash_reserve_pct)
    cash_reserve_rub = total_value_rub - investable_rub

    scores: dict[str, float] = {}
    caps: dict[str, float] = {}
    liquidity_cap_notes: dict[str, str | None] = {}
    eligibility: dict[str, tuple[bool, str]] = {}

    selected_isins: list[str] = []
    for bond in db.list_bonds():
        eligible, reason = _eligible_for_constraints(
            bond,
            range.low_pct,
            range.high_pct,
            cons,
            required_volume_mn,
        )
        eligibility[bond.isin] = (eligible, reason)
        if not eligible:
            continue
        score = stability_score(
            bond,
            low_pct=range.low_pct,
            high_pct=range.high_pct,
            max_duration_years=cons.max_duration_years,
            required_volume_mn=required_volume_mn,
            now=now,
        )
        scores[bond.isin] = score.score

    top_scores = sorted(scores.values(), reverse=True)[: cons.max_positions]
    min_selected_score = min(top_scores) if top_scores else 0.0
    selected_isins = [
        isin for isin, score_value in scores.items() if score_value >= min_selected_score
    ]

    selected_isins = sorted(
        selected_isins,
        key=lambda isin: scores.get(isin, 0.0),
        reverse=True,
    )[: cons.max_positions]

    scores_for_weights = {isin: scores[isin] for isin in selected_isins}
    for isin in selected_isins:
        bond = bonds.get(isin)
        if bond is None:
            continue
        cap, note = _caps_for(bond, investable_rub, cons, required_volume_mn)
        caps[isin] = cap
        liquidity_cap_notes[isin] = note
        if note == "нет данных об объёме":
            caps[isin] = cons.max_position_share

    rating_of = {isin: bonds[isin].rating or "н/д" for isin in selected_isins if isin in bonds}
    rating_caps = {rating: cons.max_rating_share for rating in rating_of.values()}

    weights = _waterfill(scores_for_weights, caps, rating_caps, rating_of)

    targets: list[AllocationTarget] = []
    current_by_isin: dict[str, PortfolioPosition] = {p.isin: p for p in positions}

    for isin in selected_isins:
        bond = bonds.get(isin)
        if bond is None:
            continue
        position = current_by_isin.get(isin)
        target_value = (weights.get(isin, 0.0) or 0.0) * investable_rub
        current_value = _position_value(position) if position else 0.0
        delta = target_value - current_value
        action = "hold"
        threshold = max(50_000.0, total_value_rub * 0.01)
        if delta > threshold:
            action = "buy"
        elif delta < -threshold:
            action = "sell"
        liquidity = None
        if bond is not None:
            liquidity = build_liquidity_plan_from_bond(
                bond,
                position_value_rub=current_value,
                constraints=cons,
                settings=settings,
            )
        targets.append(
            AllocationTarget(
                bond=bond,
                score=scores.get(isin, 0.0),
                target_weight=target_value / total_value_rub if total_value_rub else 0.0,
                target_value_rub=target_value,
                current_value_rub=current_value,
                current_weight=current_value / total_value_rub if total_value_rub else 0.0,
                action=action,
                delta_value_rub=delta,
                liquidity=liquidity,
                note=liquidity_cap_notes.get(isin),
            )
        )

    # позиции вне стратегии: либо не вошли в топ, либо не прошли фильтры
    for isin, position in current_by_isin.items():
        if isin in selected_isins:
            continue
        bond = bonds.get(isin) or Bond(isin=isin, name=position.name)
        eligible, reason = eligibility.get(isin, (False, "нет данных"))
        if not eligible:
            note = reason
        else:
            note = "вне топ-N по стабильности"
        current_value = _position_value(position)
        targets.append(
            AllocationTarget(
                bond=bond,
                score=0.0,
                target_weight=0.0,
                target_value_rub=0.0,
                current_value_rub=current_value,
                current_weight=current_value / total_value_rub if total_value_rub else 0.0,
                action="sell" if current_value > 0 else "hold",
                delta_value_rub=-current_value,
                liquidity=build_liquidity_plan_from_bond(
                    bond,
                    position_value_rub=current_value,
                    constraints=cons,
                    settings=settings,
                ),
                note=note,
            )
        )

    warnings: list[str] = []
    sum_target = sum(t.target_value_rub for t in targets)
    investable_final = min(investable_rub, sum_target)
    cash_reserve_final = total_value_rub - investable_final
    if sum_target > investable_rub + 1.0:
        warnings.append(
            f"суммарная цель {sum_target:.0f} ₽ выше бюджета {investable_rub:.0f} ₽"
        )
    for target in targets:
        if target.liquidity and target.liquidity.warnings:
            warnings.extend(target.liquidity.warnings)
        if target.note and target.action != "hold":
            warnings.append(f"{target.bond.isin}: {target.note}")

    result = AllocationResult(
        total_value_rub=total_value_rub,
        investable_rub=investable_final,
        cash_reserve_rub=cash_reserve_final,
        targets=tuple(targets),
        constraints=cons,
        warnings=tuple(warnings),
        generated_at=now,
    )

    if save_audit:
        audit_id = db.save_audit(
            kind="allocation",
            inputs={
                "key_rate_pct": snapshot.value_pct,
                "key_rate_as_of": str(snapshot.as_of),
                "range_low_pct": range.low_pct,
                "range_high_pct": range.high_pct,
                "total_value_rub": result.total_value_rub,
                "cash_reserve_pct": cons.cash_reserve_pct,
                "max_position_share": cons.max_position_share,
                "max_rating_share": cons.max_rating_share,
                "max_pct_daily_volume": cons.max_pct_daily_volume,
                "exit_horizon_days": cons.exit_horizon_days,
                "max_positions": cons.max_positions,
                "min_rating": cons.min_rating,
            },
            formulas=(
                f"range = ЦБ {snapshot.value_pct:.2f}% + 5–10 п.п. "
                f"= {range.low_pct:.2f}–{range.high_pct:.2f}%",
                "weight = score / sum(scores), далее caps: доля ≤ "
                f"{cons.max_position_share:.0%}, группа рейтинга ≤ {cons.max_rating_share:.0%}, "
                "ликвидность = объём × 5% × горизонт",
                f"cash_reserve = {cons.cash_reserve_pct:.0%} от портфеля",
            ),
            result={
                "targets": [asdict(t) for t in result.targets],
                "warnings": list(result.warnings),
            },
            created_at=now,
        )
        result = replace(result, audit_id=audit_id)

    return result


def build_liquidity_plan_from_bond(
    bond: Bond,
    *,
    position_value_rub: float | None,
    constraints: AllocationConstraints,
    settings: Settings,
) -> LiquidityPlan | None:
    """Локальный помощник: расчёт ликвидности для бумаг вне портфеля и входа в новые."""
    from bondbot.strategy.liquidity import liquidity_plan

    return liquidity_plan(
        bond,
        position_value_rub,
        max_pct_daily_volume=constraints.max_pct_daily_volume,
        horizon_days=constraints.exit_horizon_days,
    )
