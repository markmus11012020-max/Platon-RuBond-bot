from __future__ import annotations

from datetime import datetime

from bondbot.analytics.bonds import normalize_rating, rating_rank
from bondbot.models import Bond, utcnow
from bondbot.strategy.types import StabilityScore

_RATING_MAX = len(
    [
        "D", "C", "CC", "CCC-", "CCC", "CCC+", "B-", "B", "B+", "BB-", "BB", "BB+",
        "BBB-", "BBB", "BBB+", "A-", "A", "A+", "AA-", "AA", "AA+", "AAA",
    ]
) - 1

WEIGHTS = {
    "rating": 30.0,
    "liquidity": 20.0,
    "duration": 15.0,
    "issue_size": 10.0,
    "price": 10.0,
    "yield_position": 10.0,
    "data_quality": 5.0,
}

_PENALTIES = {
    "qual_only": -100.0,
    "no_volume": -20.0,
    "no_rating": -20.0,
    "no_issue_size": -3.0,
    "amortized": -8.0,
    "offer_within_365d": -10.0,
    "price_below_95": -5.0,
    "ytm_near_high": -5.0,
    "no_g_spread": -3.0,
    "stale_data_over_7d": -5.0,
}

_FRESH_DAYS = 7.0
_SEMI_DAYS = 30.0


def _rating_component(bond: Bond) -> float:
    rank = rating_rank(bond.rating)
    if rank < 0:
        return 0.0
    return rank / max(1, _RATING_MAX)


def _liquidity_component(bond: Bond, required_volume_mn: float | None) -> float:
    if bond.volume_mn_rub is None or bond.volume_mn_rub <= 0:
        return 0.0
    target = (required_volume_mn or 20.0) * 5.0
    return min(1.0, bond.volume_mn_rub / target)


def _duration_component(bond: Bond, max_duration_years: float) -> float:
    if bond.duration_years is None:
        return 0.0
    if max_duration_years <= 0:
        return 0.0
    return max(0.0, 1.0 - bond.duration_years / max_duration_years)


def _issue_size_component(bond: Bond) -> float:
    if bond.issue_size_rub is None or bond.issue_size_rub <= 0:
        return 0.0
    target = 20_000_000_000.0  # 20 млрд ₽ = полный балл
    return min(1.0, bond.issue_size_rub / target)


def _price_component(bond: Bond) -> float:
    if bond.price_pct is None:
        return 0.0
    return max(0.0, 1.0 - abs(bond.price_pct - 100.0) / 10.0)


def _yield_position_component(bond: Bond, low_pct: float, high_pct: float) -> float:
    if bond.ytm_pct is None or high_pct <= low_pct:
        return 0.0
    share = (bond.ytm_pct - low_pct) / (high_pct - low_pct)
    return max(0.0, min(1.0, 1.0 - share))


def _data_quality_component(bond: Bond, now: datetime) -> float:
    fields = (
        bond.ytm_pct,
        bond.duration_years,
        bond.rating,
        bond.price_pct,
        bond.volume_mn_rub,
        bond.issue_size_rub,
    )
    completeness = sum(1 for value in fields if value is not None) / len(fields)
    fetched = bond.fetched_at
    if fetched is None:
        freshness = 0.0
    else:
        age_days = (now - fetched).total_seconds() / 86400.0
        if age_days <= _FRESH_DAYS:
            freshness = 1.0
        elif age_days <= _SEMI_DAYS:
            freshness = 0.5
        else:
            freshness = 0.0
    return freshness * completeness


def stability_score(
    bond: Bond,
    *,
    low_pct: float,
    high_pct: float,
    max_duration_years: float = 5.0,
    required_volume_mn: float | None = None,
    now: datetime | None = None,
) -> StabilityScore:
    """Чистый расчёт «насколько бумага финансово стабильна и безопасна».

    Компоненты (сумма весов 100 п.):
    - рейтинг 30
    - ликвидность 20
    - дюрация 15
    - объём выпуска 10
    - цена от номинала 10
    - положение YTM внутри диапазона 10
    - свежесть и полнота данных 5
    Штрафы за амортизацию, оферту, дешёвую цену, кваловый статус и пр."""
    now = now or utcnow()
    components: dict[str, float] = {
        "rating": _rating_component(bond) * WEIGHTS["rating"],
        "liquidity": _liquidity_component(bond, required_volume_mn) * WEIGHTS["liquidity"],
        "duration": _duration_component(bond, max_duration_years) * WEIGHTS["duration"],
        "issue_size": _issue_size_component(bond) * WEIGHTS["issue_size"],
        "price": _price_component(bond) * WEIGHTS["price"],
        "yield_position": _yield_position_component(bond, low_pct, high_pct) * WEIGHTS["yield_position"],
        "data_quality": _data_quality_component(bond, now) * WEIGHTS["data_quality"],
    }

    penalties: list[str] = []
    penalty_points = 0.0

    def apply(key: str, note: str) -> None:
        nonlocal penalty_points
        penalty_points += _PENALTIES[key]
        penalties.append(f"{note} ({_PENALTIES[key]:+.0f})")

    if bond.qual_only:
        apply("qual_only", "только квалы")
    if bond.volume_mn_rub is None or bond.volume_mn_rub <= 0:
        apply("no_volume", "нет данных об объёме")
    if not bond.rating:
        apply("no_rating", "нет рейтинга")
    if bond.issue_size_rub is None or bond.issue_size_rub <= 0:
        apply("no_issue_size", "нет данных о выпуске")
    if bond.amortized:
        apply("amortized", "амортизация")
    if bond.offer_date is not None:
        delta = (bond.offer_date - now.date()).days
        if 0 <= delta <= 365:
            apply("offer_within_365d", f"оферта через {delta} дн.")
    if bond.price_pct is not None and bond.price_pct < 95.0:
        apply("price_below_95", f"цена {bond.price_pct:.2f}%")
    if bond.ytm_pct is not None and bond.ytm_pct > high_pct - 0.5:
        apply("ytm_near_high", f"YTM {bond.ytm_pct:.2f}% у верхней границы")
    if bond.g_spread_bp is None and bond.ytm_pct is not None:
        apply("no_g_spread", "нет G-спреда")
    fetched = bond.fetched_at
    if fetched is not None:
        age_days = (now - fetched).total_seconds() / 86400.0
        if age_days > _FRESH_DAYS:
            apply("stale_data_over_7d", f"данные от {fetched:%d.%m.%Y}")

    raw = sum(components.values()) + penalty_points
    score = round(max(0.0, min(100.0, raw)), 1)

    reasons: list[str] = []
    if bond.rating:
        normalize = normalize_rating(bond.rating)
        rank = rating_rank(bond.rating)
        reasons.append(f"рейтинг {normalize or bond.rating} ({rank}/{_RATING_MAX})")
    if bond.duration_years is not None:
        reasons.append(f"дюрация {bond.duration_years:.2f} г")
    if bond.volume_mn_rub is not None and bond.volume_mn_rub > 0:
        reasons.append(f"оборот {bond.volume_mn_rub:.1f} млн ₽")
    if bond.issue_size_rub is not None and bond.issue_size_rub > 0:
        reasons.append(f"выпуск {bond.issue_size_rub / 1_000_000:.0f} млн ₽")
    if bond.price_pct is not None:
        reasons.append(f"цена {bond.price_pct:.2f}%")
    if bond.ytm_pct is not None:
        reasons.append(f"YTM {bond.ytm_pct:.2f}%")
    reasons.extend(penalties)

    return StabilityScore(
        isin=bond.isin,
        score=score,
        components=components,
        penalties=tuple(penalties),
        reasons=tuple(reasons),
    )
