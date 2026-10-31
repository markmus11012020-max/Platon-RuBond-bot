from __future__ import annotations

from bondbot.models import Bond
from bondbot.strategy.types import LiquidityPlan


def liquidity_plan(
    bond: Bond,
    position_value_rub: float | None,
    *,
    max_pct_daily_volume: float,
    horizon_days: int,
) -> LiquidityPlan:
    """Deterministic liquidity and exit plan for one position.

    max_position_rub = daily_volume * max_pct_daily_volume * horizon_days
    days_to_exit      = position_value / (daily_volume * max_pct_daily_volume)
    allowed_topup_rub = max(0, max_position_rub - position_value_rub)
    """
    max_pct = max(0.0, min(float(max_pct_daily_volume), 1.0))
    horizon = max(1, int(horizon_days))
    warnings: list[str] = []
    formulas: list[str] = []

    daily_volume_rub: float | None = None
    if bond.volume_mn_rub is not None and bond.volume_mn_rub > 0:
        daily_volume_rub = bond.volume_mn_rub * 1_000_000

    position = position_value_rub if position_value_rub and position_value_rub > 0 else None

    max_position_rub: float | None = None
    days_to_exit: float | None = None
    share: float | None = None
    allowed_topup: float | None = None

    if daily_volume_rub is None:
        warnings.append(f"{bond.isin}: нет данных о дневном объёме — ликвидность не рассчитана")
    else:
        max_position_rub = daily_volume_rub * max_pct * horizon
        formulas.append(
            f"max_position = {daily_volume_rub:.0f} ₽ × {max_pct:.0%} × {horizon} дн. "
            f"= {max_position_rub:.0f} ₽"
        )
        if position is not None:
            days_to_exit = position / (daily_volume_rub * max_pct) if max_pct > 0 else None
            share = position / daily_volume_rub
            formulas.append(
                f"days_to_exit = {position:.0f} ₽ / ({daily_volume_rub:.0f} ₽ × {max_pct:.0%}) "
                f"= {days_to_exit:.2f} дн."
            )
            if days_to_exit is not None and days_to_exit > horizon:
                warnings.append(
                    f"{bond.isin}: выход {days_to_exit:.1f} дн. при лимите {horizon} дн. — позиция слишком велика"
                )
            if share > max_pct:
                warnings.append(
                    f"{bond.isin}: позиция {share:.1%} дневного объёма (лимит {max_pct:.0%})"
                )
        allowed_topup = max(0.0, max_position_rub - (position or 0.0))
        formulas.append(
            f"allowed_topup = max(0, {max_position_rub:.0f} ₽ − {position or 0.0:.0f} ₽) "
            f"= {allowed_topup:.0f} ₽"
        )

    return LiquidityPlan(
        isin=bond.isin,
        name=bond.name,
        position_value_rub=position,
        daily_volume_rub=daily_volume_rub,
        max_pct_daily_volume=max_pct,
        horizon_days=horizon,
        max_position_rub=max_position_rub,
        allowed_topup_rub=allowed_topup,
        days_to_exit=days_to_exit,
        share_of_daily_volume=share,
        warnings=tuple(warnings),
        formulas=tuple(formulas),
    )
