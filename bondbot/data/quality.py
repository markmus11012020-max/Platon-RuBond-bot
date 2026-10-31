from __future__ import annotations

import logging
from dataclasses import replace

from bondbot.models import Bond, PortfolioPosition

log = logging.getLogger(__name__)

# (min, max) для числовых полей. None допустим и означает «нет данных».
BOND_LIMITS: dict[str, tuple[float, float]] = {
    "ytm_pct": (0.0, 60.0),
    "current_coupon_yield_pct": (0.0, 100.0),
    "annual_coupon_yield_pct": (0.0, 100.0),
    "price_pct": (1.0, 200.0),
    "volume_mn_rub": (0.0, 1_000_000.0),
    "coupon_rub": (0.0, 100_000.0),
    "coupon_freq": (0.0, 12.0),
    "nkd_rub": (0.0, 100_000.0),
    "duration_years": (0.0, 50.0),
    "years_to_maturity": (0.0, 50.0),
    "face_value": (1.0, 1_000_000.0),
    "issue_size_rub": (0.0, 1e15),
    "g_spread_bp": (-10_000.0, 10_000.0),
}

POSITION_LIMITS: dict[str, tuple[float, float]] = {
    "buy_price_pct": (1.0, 200.0),
    "current_price_pct": (1.0, 200.0),
    "ytm_pct": (0.0, 60.0),
    "coupon_rub": (0.0, 100_000.0),
    "coupon_freq": (0.0, 12.0),
    "annual_coupon_rub": (0.0, 1e12),
    "current_value_rub": (0.0, 1e15),
    "g_spread_bp": (-10_000.0, 10_000.0),
}


def _sanitize(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    if low <= value <= high:
        return value
    return None


def sanitize_bond(bond: Bond) -> Bond:
    """Обнуляет заведомо битые числа, чтобы они не попадали в скрининг и рейтинги."""
    updates: dict[str, float | None] = {}
    for field, (low, high) in BOND_LIMITS.items():
        value = getattr(bond, field)
        cleaned = _sanitize(value, low, high)
        if cleaned != value:
            log.warning(
                "bond %s: %s=%s вне диапазона %s..%s — поле очищено",
                bond.isin,
                field,
                value,
                low,
                high,
            )
            updates[field] = cleaned
    return replace(bond, **updates) if updates else bond


def sanitize_position(position: PortfolioPosition) -> PortfolioPosition:
    updates: dict[str, float | None] = {}
    for field, (low, high) in POSITION_LIMITS.items():
        value = getattr(position, field)
        cleaned = _sanitize(value, low, high)
        if cleaned != value:
            log.warning(
                "position %s: %s=%s вне диапазона %s..%s — поле очищено",
                position.isin,
                field,
                value,
                low,
                high,
            )
            updates[field] = cleaned
    return replace(position, **updates) if updates else position


__all__ = [
    "BOND_LIMITS",
    "POSITION_LIMITS",
    "sanitize_bond",
    "sanitize_position",
]
