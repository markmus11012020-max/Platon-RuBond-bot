from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from bondbot.models import Bond, utcnow


@dataclass(frozen=True, slots=True)
class YieldRange:
    low_pct: float
    high_pct: float
    key_rate_pct: float
    margin_low_pct: float = 5.0
    margin_high_pct: float = 10.0
    as_of: date | None = None
    stale: bool = False

    def describe(self) -> str:
        suffix = " (кэш, ЦБ недоступен)" if self.stale else ""
        date_suffix = f" на {self.as_of:%d.%m.%Y}" if self.as_of else ""
        return (
            f"ставка ЦБ {self.key_rate_pct:.2f}% + {self.margin_low_pct:.0f}–"
            f"{self.margin_high_pct:.0f} п.п. = {self.low_pct:.2f}–{self.high_pct:.2f}%"
            f"{date_suffix}{suffix}"
        )


@dataclass(frozen=True, slots=True)
class LiquidityPlan:
    isin: str
    name: str
    position_value_rub: float | None
    daily_volume_rub: float | None
    max_pct_daily_volume: float
    horizon_days: int
    max_position_rub: float | None
    allowed_topup_rub: float | None
    days_to_exit: float | None
    share_of_daily_volume: float | None
    warnings: tuple[str, ...] = ()
    formulas: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BondValuation:
    isin: str
    name: str
    ytm_pct: float | None
    after_tax_ytm_pct: float | None
    duration_years: float | None
    modified_duration: float | None
    g_spread_bp: float | None
    z_spread_bp: float | None
    carry_pct: float | None
    tax_rate: float
    amortized: bool
    warnings: tuple[str, ...] = ()
    formulas: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StabilityScore:
    isin: str
    score: float
    components: dict[str, float]
    penalties: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SafeBond:
    bond: Bond
    score: StabilityScore


@dataclass(frozen=True, slots=True)
class SafeListResult:
    range: YieldRange
    items: tuple[SafeBond, ...]
    universe_size: int
    eligible_size: int
    audit_id: int | None = None
    generated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, slots=True)
class ExitPlanResult:
    total_value_rub: float
    plans: tuple[LiquidityPlan, ...]
    warnings: tuple[str, ...] = ()
    audit_id: int | None = None
    generated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, slots=True)
class AllocationConstraints:
    min_rating: str = "A-"
    max_duration_years: float = 5.0
    max_position_share: float = 0.25
    max_rating_share: float = 0.40
    max_pct_daily_volume: float = 0.05
    exit_horizon_days: int = 5
    max_positions: int = 10
    min_position_rub: float = 50_000.0
    cash_reserve_pct: float = 0.05
    min_price_pct: float = 90.0
    max_price_pct: float = 110.0
    exclude_qual_only: bool = True


@dataclass(frozen=True, slots=True)
class AllocationTarget:
    bond: Bond
    score: float
    target_weight: float
    target_value_rub: float
    current_value_rub: float
    current_weight: float
    action: str
    delta_value_rub: float
    liquidity: LiquidityPlan | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class AllocationResult:
    total_value_rub: float
    investable_rub: float
    cash_reserve_rub: float
    targets: tuple[AllocationTarget, ...]
    constraints: AllocationConstraints
    warnings: tuple[str, ...] = ()
    audit_id: int | None = None
    generated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, slots=True)
class AuditRecord:
    kind: str
    inputs: dict[str, Any]
    formulas: tuple[str, ...]
    result: dict[str, Any]
    version: str = "strategy-1.0"
    created_at: datetime = field(default_factory=utcnow)
