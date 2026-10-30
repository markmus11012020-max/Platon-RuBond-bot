from __future__ import annotations

import re
from dataclasses import dataclass

from bondbot.models import Bond, ScreenFilters

RATING_SCALE = [
    "D",
    "C",
    "CC",
    "CCC-",
    "CCC",
    "CCC+",
    "B-",
    "B",
    "B+",
    "BB-",
    "BB",
    "BB+",
    "BBB-",
    "BBB",
    "BBB+",
    "A-",
    "A",
    "A+",
    "AA-",
    "AA",
    "AA+",
    "AAA",
]
_RATING_INDEX = {rating: index for index, rating in enumerate(RATING_SCALE)}


def normalize_rating(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(AAA|AA|A|BBB|BB|B|CCC|CC|C|D)[+-]?", value.upper())
    return match.group(0) if match else None


def rating_rank(value: str | None) -> int:
    rating = normalize_rating(value)
    return _RATING_INDEX.get(rating, -1) if rating else -1


def meets_min_rating(value: str | None, minimum: str | None) -> bool:
    if not minimum:
        return True
    return rating_rank(value) >= rating_rank(minimum)


def required_daily_volume_mn(position_size_rub: float, max_pct: float) -> float:
    if max_pct <= 0:
        return 0.0
    return position_size_rub / max_pct / 1_000_000


def position_share_of_volume(position_size_rub: float, volume_mn_rub: float | None) -> float | None:
    if not volume_mn_rub or volume_mn_rub <= 0:
        return None
    return position_size_rub / (volume_mn_rub * 1_000_000)


@dataclass(slots=True)
class ScreenResult:
    bond: Bond
    score: float
    liquidity_share: float | None


def screen_bonds(
    bonds: list[Bond],
    filters: ScreenFilters,
    *,
    required_volume_mn: float | None = None,
) -> list[ScreenResult]:
    results: list[ScreenResult] = []
    for bond in bonds:
        if bond.ytm_pct is None or bond.duration_years is None:
            continue
        if filters.min_yield_pct is not None and bond.ytm_pct < filters.min_yield_pct:
            continue
        if filters.max_yield_pct is not None and bond.ytm_pct > filters.max_yield_pct:
            continue
        if filters.max_duration_years is not None and bond.duration_years > filters.max_duration_years:
            continue
        if not meets_min_rating(bond.rating, filters.min_rating):
            continue
        if filters.min_price_pct is not None and bond.price_pct is not None:
            if bond.price_pct < filters.min_price_pct:
                continue
        if filters.max_price_pct is not None and bond.price_pct is not None:
            if bond.price_pct > filters.max_price_pct:
                continue
        if filters.exclude_qual_only and bond.qual_only:
            continue

        min_volume = filters.min_volume_mn_rub
        if min_volume is None:
            min_volume = required_volume_mn
        if min_volume is not None:
            if bond.volume_mn_rub is None or bond.volume_mn_rub < min_volume:
                continue

        share = position_share_of_volume(
            filters.position_size_rub or 1_000_000, bond.volume_mn_rub
        )
        rating_bonus = (rating_rank(bond.rating) - 10) * 0.05
        liquidity_bonus = min((bond.volume_mn_rub or 0) / 200, 1.0)
        score = bond.ytm_pct + rating_bonus + liquidity_bonus
        results.append(ScreenResult(bond=bond, score=round(score, 4), liquidity_share=share))

    results.sort(key=lambda item: (item.score, item.bond.volume_mn_rub or 0), reverse=True)
    return results
