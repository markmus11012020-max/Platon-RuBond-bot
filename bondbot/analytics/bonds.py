from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

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


COUPON_TYPE_LABELS = {
    "fixed": "постоянный",
    "floating": "плавающий",
    "structured": "структурный",
}

COUPON_TYPE_ALIASES = {
    "fixed": "fixed",
    "постоянный": "fixed",
    "фиксированный": "fixed",
    "fixed_unknown": "fixed",
    "floating": "floating",
    "плавающий": "floating",
    "переменный": "floating",
    "ruonia": "floating",
    "ключевая": "floating",
    "структурный": "structured",
    "structured": "structured",
}


def is_ofz(bond: Bond) -> bool:
    name = (bond.name or "").upper().replace("Ё", "Е")
    return name.startswith("ОФЗ") or "ОФЗ " in name


def bond_rating_rank(bond: Bond) -> int:
    return rating_rank("AAA") if is_ofz(bond) else rating_rank(bond.rating)


def bond_rating_label(bond: Bond) -> str:
    if is_ofz(bond):
        return "ОФЗ (суверен)"
    return bond.rating or "—"


def coupon_type_label(value: str | None) -> str:
    return COUPON_TYPE_LABELS.get(value or "", value or "—")


def coupon_type_matches(value: str | None, requested: str | None) -> bool:
    if not requested or requested == "any":
        return True
    normalized = COUPON_TYPE_ALIASES.get(requested.lower(), requested.lower())
    return (value or "").lower() == normalized


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


def _complete_data(bond: Bond) -> bool:
    return all(
        value is not None
        for value in (
            bond.ytm_pct,
            bond.duration_years,
            bond.price_pct,
            bond.volume_mn_rub,
            bond.coupon_type,
            bond.coupon_freq,
            bond.maturity_date,
        )
    ) and (bond.rating is not None or is_ofz(bond))


def _sort_value(item: ScreenResult, sort_by: str) -> Any:
    bond = item.bond
    values = {
        "yield": bond.ytm_pct,
        "duration": bond.duration_years,
        "maturity": bond.maturity_date,
        "offer": bond.offer_date,
        "coupon_freq": bond.coupon_freq,
        "coupon_type": coupon_type_label(bond.coupon_type),
        "rating": bond_rating_rank(bond),
        "price": bond.price_pct,
        "volume": bond.volume_mn_rub,
        "issue_size": bond.issue_size_rub,
        "updated": bond.fetched_at,
        "score": item.score,
    }
    return values.get(sort_by, item.score)


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
        if filters.min_duration_years is not None and bond.duration_years < filters.min_duration_years:
            continue
        if filters.max_duration_years is not None and bond.duration_years > filters.max_duration_years:
            continue
        if filters.maturity_from is not None:
            if bond.maturity_date is None or bond.maturity_date < filters.maturity_from:
                continue
        if filters.maturity_to is not None:
            if bond.maturity_date is None or bond.maturity_date > filters.maturity_to:
                continue
        if filters.offer_from is not None:
            if bond.offer_date is None or bond.offer_date < filters.offer_from:
                continue
        if filters.offer_to is not None:
            if bond.offer_date is None or bond.offer_date > filters.offer_to:
                continue
        if not coupon_type_matches(bond.coupon_type, filters.coupon_type):
            continue
        if filters.coupon_freqs:
            if bond.coupon_freq is None or not any(
                abs(bond.coupon_freq - float(freq)) <= 0.5
                for freq in filters.coupon_freqs
            ):
                continue
        if not is_ofz(bond) and not meets_min_rating(bond.rating, filters.min_rating):
            continue
        if filters.min_price_pct is not None and bond.price_pct is not None:
            if bond.price_pct < filters.min_price_pct:
                continue
        if filters.max_price_pct is not None and bond.price_pct is not None:
            if bond.price_pct > filters.max_price_pct:
                continue
        if filters.exclude_qual_only and bond.qual_only:
            continue
        if filters.exclude_amortized and bond.amortized:
            continue
        if filters.only_complete_data and not _complete_data(bond):
            continue
        if filters.issuer:
            needle = filters.issuer.lower()
            if needle not in f"{bond.name} {bond.issuer or ''}".lower():
                continue
        if filters.min_issue_size_rub is not None:
            if bond.issue_size_rub is None or bond.issue_size_rub < filters.min_issue_size_rub:
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
        rating_bonus = (bond_rating_rank(bond) - 10) * 0.05
        liquidity_bonus = min((bond.volume_mn_rub or 0) / 200, 1.0)
        score = bond.ytm_pct + rating_bonus + liquidity_bonus
        results.append(ScreenResult(bond=bond, score=round(score, 4), liquidity_share=share))

    present = [item for item in results if _sort_value(item, filters.sort_by) is not None]
    missing = [item for item in results if _sort_value(item, filters.sort_by) is None]
    present.sort(
        key=lambda item: _sort_value(item, filters.sort_by),
        reverse=filters.sort_order.lower() == "desc",
    )
    missing.sort(key=lambda item: item.score, reverse=True)
    ordered = present + missing
    offset = max(0, filters.offset)
    if filters.limit is not None:
        return ordered[offset : offset + max(1, filters.limit)]
    return ordered[offset:]
