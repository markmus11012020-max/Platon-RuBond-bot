from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3), name="MSK")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now_msk() -> datetime:
    return datetime.now(MSK)


def to_msk(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MSK)


@dataclass(slots=True)
class Bond:
    isin: str
    name: str
    issuer: str | None = None
    price_pct: float | None = None
    ytm_pct: float | None = None
    current_coupon_yield_pct: float | None = None
    annual_coupon_yield_pct: float | None = None
    rating: str | None = None
    g_spread_bp: float | None = None
    volume_mn_rub: float | None = None
    coupon_rub: float | None = None
    coupon_freq: float | None = None
    nkd_rub: float | None = None
    duration_years: float | None = None
    next_coupon_date: date | None = None
    placement_date: date | None = None
    maturity_date: date | None = None
    offer_date: date | None = None
    years_to_maturity: float | None = None
    face_value: float | None = None
    issue_size_rub: float | None = None
    qual_only: bool | None = None
    amortized: bool | None = None
    source_url: str = ""
    fetched_at: datetime = field(default_factory=utcnow)

    @property
    def is_liquid(self) -> bool:
        return bool(self.volume_mn_rub and self.volume_mn_rub > 0)


@dataclass(slots=True)
class Coupon:
    isin: str
    coupon_date: date
    value_rub: float | None = None
    yield_pct: float | None = None


@dataclass(slots=True)
class PortfolioPosition:
    isin: str
    name: str
    qty: float
    buy_price_pct: float | None = None
    current_price_pct: float | None = None
    ytm_pct: float | None = None
    maturity_date: date | None = None
    rating: str | None = None
    g_spread_bp: float | None = None
    coupon_rub: float | None = None
    coupon_freq: float | None = None
    annual_coupon_rub: float | None = None
    current_value_rub: float | None = None
    next_coupon_date: date | None = None
    source_url: str = ""

    @property
    def buy_value_rub(self) -> float | None:
        if self.buy_price_pct is None:
            return None
        return self.qty * self.buy_price_pct / 100 * 1000

    @property
    def profit_rub(self) -> float | None:
        if self.current_value_rub is None or self.buy_value_rub is None:
            return None
        return self.current_value_rub - self.buy_value_rub

    @property
    def estimated_annual_coupon_rub(self) -> float | None:
        if self.coupon_rub is None or self.coupon_freq is None:
            return None
        return self.coupon_rub * self.coupon_freq * self.qty


@dataclass(slots=True)
class ScreenFilters:
    min_yield_pct: float | None = None
    max_yield_pct: float | None = None
    max_duration_years: float | None = None
    min_rating: str | None = None
    min_volume_mn_rub: float | None = None
    min_price_pct: float | None = None
    max_price_pct: float | None = None
    exclude_qual_only: bool = True
    position_size_rub: float | None = None
