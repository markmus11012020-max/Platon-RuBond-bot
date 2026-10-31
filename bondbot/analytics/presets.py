from __future__ import annotations

from bondbot.analytics.rates import MaxYield
from bondbot.config import Settings
from bondbot.models import ScreenFilters

PRESET_LABELS = {
    "conservative": "консервативный",
    "balanced": "сбалансированный",
    "max_yield": "максимальная доходность",
}

PRESET_ALIASES = {
    "консервативный": "conservative",
    "сбалансированный": "balanced",
    "баланс": "balanced",
    "максимальная доходность": "max_yield",
    "доходность": "max_yield",
    "max": "max_yield",
}


def preset_name(value: str) -> str | None:
    key = value.strip().lower()
    return key if key in PRESET_LABELS else PRESET_ALIASES.get(key)


def preset_filters(
    settings: Settings,
    name: str,
    max_yield: MaxYield,
) -> ScreenFilters:
    key = preset_name(name) or "balanced"
    base = dict(
        min_yield_pct=settings.min_yield_pct,
        max_yield_pct=max_yield.value_pct,
        position_size_rub=settings.position_size_rub,
        exclude_qual_only=True,
        only_complete_data=True,
    )
    if key == "conservative":
        return ScreenFilters(
            **base,
            max_duration_years=2.5,
            min_rating="A-",
            min_volume_mn_rub=20.0,
            min_price_pct=95.0,
            max_price_pct=105.0,
            coupon_type="fixed",
            exclude_amortized=True,
            sort_by="score",
            sort_order="desc",
        )
    if key == "max_yield":
        return ScreenFilters(
            **base,
            max_duration_years=5.0,
            min_rating="BB-",
            min_volume_mn_rub=20.0,
            min_price_pct=90.0,
            max_price_pct=110.0,
            sort_by="yield",
            sort_order="desc",
        )
    return ScreenFilters(
        **base,
        max_duration_years=3.0,
        min_rating="BBB-",
        min_volume_mn_rub=20.0,
        min_price_pct=90.0,
        max_price_pct=110.0,
        sort_by="score",
        sort_order="desc",
    )


__all__ = ["PRESET_LABELS", "preset_filters", "preset_name"]
