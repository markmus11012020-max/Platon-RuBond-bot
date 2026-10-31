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
