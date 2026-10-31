from __future__ import annotations

from bondbot.analytics.bonds import (
    coupon_type_matches,
    meets_min_rating,
    normalize_rating,
    position_share_of_volume,
    rating_rank,
    required_daily_volume_mn,
    screen_bonds,
)
from bondbot.analytics.presets import preset_filters
from bondbot.analytics.query import parse_screen_query
from bondbot.analytics.rates import MaxYield
from bondbot.config import load_settings
from bondbot.models import Bond, ScreenFilters


def test_rating_order() -> None:
    assert normalize_rating("AAA") == "AAA"
    assert normalize_rating("aa+") == "AA+"
    assert rating_rank("AAA") > rating_rank("AA+") > rating_rank("A-") > rating_rank("BBB")
    assert rating_rank(None) == -1
    assert meets_min_rating("A", "A-")
    assert not meets_min_rating("BBB+", "A-")


def test_liquidity_requirements() -> None:
    assert required_daily_volume_mn(1_000_000, 0.05) == 20.0
    assert required_daily_volume_mn(500_000, 0.05) == 10.0
    assert position_share_of_volume(1_000_000, 40.0) == 0.025


def test_coupon_type_aliases() -> None:
    assert coupon_type_matches("fixed", "постоянный")
    assert coupon_type_matches("floating", "плавающий")
    assert not coupon_type_matches("floating", "fixed")
    assert coupon_type_matches(None, "any")


def test_screen_coupon_filters() -> None:
    bonds = [
        Bond(
            isin="FIX2",
            name="Fixed 2",
            ytm_pct=18.0,
            duration_years=1.0,
            rating="AAA",
            coupon_type="fixed",
            coupon_freq=2.0,
            volume_mn_rub=100.0,
        ),
        Bond(
            isin="FIX12",
            name="Fixed 12",
            ytm_pct=18.0,
            duration_years=1.0,
            rating="AAA",
            coupon_type="fixed",
            coupon_freq=12.0,
            volume_mn_rub=100.0,
        ),
        Bond(
            isin="FLOAT",
            name="Floating",
            ytm_pct=18.0,
            duration_years=1.0,
            rating="AAA",
            coupon_type="floating",
            coupon_freq=4.0,
            volume_mn_rub=100.0,
        ),
    ]
    filters = ScreenFilters(
        min_yield_pct=15.0,
        coupon_type="fixed",
        coupon_freqs=(2.0, 12.0),
        position_size_rub=1_000_000,
    )
    results = screen_bonds(bonds, filters, required_volume_mn=20.0)
    assert [item.bond.isin for item in results] == ["FIX2", "FIX12"]


def test_parse_screen_query_and_sort() -> None:
    settings = load_settings()
    cap = MaxYield(value_pct=24.0)
    filters = parse_screen_query(
        settings,
        "постоянный 12 погашение до 2028-12-31 сортировка доходность по убыванию",
        cap,
    )
    assert filters.coupon_type == "fixed"
    assert filters.coupon_freqs == (12.0,)
    assert filters.maturity_to is not None
    assert filters.sort_by == "yield"
    assert filters.sort_order == "desc"


def test_preset_filters() -> None:
    settings = load_settings()
    cap = MaxYield(value_pct=24.0)
    conservative = preset_filters(settings, "консервативный", cap)
    assert conservative.coupon_type == "fixed"
    assert conservative.max_duration_years == 2.5
    assert conservative.min_rating == "A-"
    assert conservative.only_complete_data


def test_screen_sorting() -> None:
    bonds = [
        Bond(isin="LOW", name="Low", ytm_pct=15.0, duration_years=1.0, rating="AAA", volume_mn_rub=100.0),
        Bond(isin="HIGH", name="High", ytm_pct=20.0, duration_years=1.0, rating="AAA", volume_mn_rub=100.0),
        Bond(isin="MID", name="Mid", ytm_pct=17.0, duration_years=1.0, rating="AAA", volume_mn_rub=100.0),
    ]
    filters = ScreenFilters(sort_by="yield", sort_order="asc")
    results = screen_bonds(bonds, filters, required_volume_mn=20.0)
    assert [item.bond.isin for item in results] == ["LOW", "MID", "HIGH"]


def test_ofz_passes_corporate_rating_filter() -> None:
    bond = Bond(
        isin="SU26207RMFS9",
        name="ОФЗ 26207",
        ytm_pct=15.0,
        duration_years=2.0,
        rating=None,
        price_pct=100.0,
        volume_mn_rub=100.0,
        coupon_type="fixed",
        coupon_freq=2.0,
    )
    filters = ScreenFilters(min_rating="A-", position_size_rub=1_000_000)
    results = screen_bonds([bond], filters, required_volume_mn=20.0)
    assert [item.bond.isin for item in results] == ["SU26207RMFS9"]


def test_parse_unlimited_filters() -> None:
    settings = load_settings()
    cap = MaxYield(value_pct=24.0)
    filters = parse_screen_query(
        settings,
        "без ограничения по доходности без ограничения по дюрации сортировка дюрация",
        cap,
    )
    assert filters.min_yield_pct == 0.0
    assert filters.max_yield_pct == 100.0
    assert filters.max_duration_years is None
    assert filters.sort_by == "duration"


def test_screen_filters() -> None:
    bonds = [
        Bond(isin="A", name="Good", ytm_pct=17.0, duration_years=1.5, rating="AAA", volume_mn_rub=300),
        Bond(isin="B", name="Low volume", ytm_pct=18.0, duration_years=1.0, rating="AA", volume_mn_rub=5),
        Bond(isin="C", name="Low rating", ytm_pct=20.0, duration_years=1.0, rating="BBB", volume_mn_rub=300),
        Bond(isin="D", name="Long", ytm_pct=19.0, duration_years=8.0, rating="AAA", volume_mn_rub=300),
        Bond(isin="E", name="Qual only", ytm_pct=19.0, duration_years=2.0, rating="AAA", volume_mn_rub=300, qual_only=True),
    ]
    filters = ScreenFilters(
        min_yield_pct=15.0,
        max_duration_years=3.0,
        min_rating="A-",
        exclude_qual_only=True,
        position_size_rub=1_000_000,
    )
    results = screen_bonds(bonds, filters, required_volume_mn=20.0)
    assert [item.bond.isin for item in results] == ["A"]
