from __future__ import annotations

from datetime import datetime, timezone

from bondbot.config import Settings
from bondbot.db import Database
from bondbot.models import PortfolioPosition
from bondbot.strategy.liquidity import liquidity_plan
from bondbot.strategy.types import ExitPlanResult, LiquidityPlan


def _position_value(position: PortfolioPosition) -> float:
    if position.current_value_rub is not None:
        return position.current_value_rub
    if position.buy_price_pct is not None and position.qty is not None:
        return position.qty * position.buy_price_pct / 100 * 1000
    return 0.0


def build_exit_plan(
    settings: Settings,
    db: Database,
    *,
    save_audit: bool = True,
    now: datetime | None = None,
) -> ExitPlanResult:
    """Ликвидность и план выхода по каждой позиции портфеля.

    Максимальная позиция на горизонт: объём × 5% × горизонт.
    Дни до выхода: позиция / (объём × лимит)."""
    now = now or datetime.now(timezone.utc)
    positions = db.positions()
    bonds = {bond.isin: bond for bond in db.list_bonds()}
    total_value_rub = sum(_position_value(p) for p in positions)

    plans = []
    warnings: list[str] = []
    for position in positions:
        bond = bonds.get(position.isin)
        if bond is None:
            warnings.append(
                f"{position.isin}: нет данных о бумаге — добавь через /bond {position.isin}"
            )
            continue
        plan = liquidity_plan(
            bond,
            _position_value(position),
            max_pct_daily_volume=settings.max_pct_daily_volume,
            horizon_days=settings.exit_horizon_days,
        )
        plans.append(plan)
        warnings.extend(plan.warnings)

    audit_id: int | None = None
    if save_audit:
        audit_id = db.save_audit(
            kind="exit_plan",
            inputs={
                "positions": len(positions),
                "total_value_rub": total_value_rub,
                "exit_horizon_days": settings.exit_horizon_days,
                "max_pct_daily_volume": settings.max_pct_daily_volume,
                "position_size_rub": settings.position_size_rub,
            },
            formulas=(
                "max_position = дневной объём × 5% × горизонт",
                "days_to_exit = позиция / (объём × 5%)",
                "allowed_topup = max(0, max_position − текущая позиция)",
            ),
            result={
                "total_value_rub": total_value_rub,
                "warnings": warnings,
                "plans": [
                    {
                        "isin": plan.isin,
                        "position_value_rub": plan.position_value_rub,
                        "daily_volume_rub": plan.daily_volume_rub,
                        "max_position_rub": plan.max_position_rub,
                        "allowed_topup_rub": plan.allowed_topup_rub,
                        "days_to_exit": plan.days_to_exit,
                        "share": plan.share_of_daily_volume,
                    }
                    for plan in plans
                ],
            },
            created_at=now,
        )

    return ExitPlanResult(
        total_value_rub=total_value_rub,
        plans=tuple(plans),
        warnings=tuple(warnings),
        audit_id=audit_id,
        generated_at=now,
    )
