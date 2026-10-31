from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from bondbot.models import Bond, Coupon
from bondbot.strategy.liquidity import liquidity_plan
from bondbot.strategy.stability import stability_score
from bondbot.strategy.valuation import (
    after_tax_ytm,
    carry_yield,
    g_spread_bp,
    modified_duration,
    value_bond,
    z_spread_bp,
)

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def make_bond(**kwargs) -> Bond:
    base = dict(
        isin="TEST",
        name="Test Bond",
        ytm_pct=20.0,
        current_coupon_yield_pct=18.0,
        duration_years=2.0,
        rating="AAA",
        price_pct=100.0,
        g_spread_bp=210.0,
        volume_mn_rub=100.0,
        issue_size_rub=30_000_000_000,
        face_value=1000.0,
        nkd_rub=0.0,
        amortized=False,
        qual_only=False,
        fetched_at=NOW,
    )
    base.update(kwargs)
    return Bond(**base)


def test_after_tax_ytm() -> None:
    assert after_tax_ytm(20.0) == pytest.approx(17.4)
    assert after_tax_ytm(None) is None


def test_modified_duration() -> None:
    assert modified_duration(2.0, 20.0) == pytest.approx(1.6667, abs=1e-3)
    assert modified_duration(None, 20.0) is None


def test_carry_and_g_spread() -> None:
    bond = make_bond()
    assert carry_yield(bond, 14.0) == pytest.approx(4.0)
    assert g_spread_bp(bond, 14.0) == (210.0, False)
    assert carry_yield(make_bond(current_coupon_yield_pct=None), 14.0) == pytest.approx(6.0)


def test_liquidity_plan_values() -> None:
    bond = make_bond(volume_mn_rub=8.0)
    plan = liquidity_plan(
        bond,
        1_575_900.0,
        max_pct_daily_volume=0.05,
        horizon_days=5,
    )
    assert plan.max_position_rub == pytest.approx(2_000_000.0)
    assert plan.days_to_exit == pytest.approx(3.93975, abs=1e-4)
    assert plan.allowed_topup_rub == pytest.approx(424_100.0, abs=1.0)
    assert plan.formulas


def test_liquidity_plan_missing_volume() -> None:
    plan = liquidity_plan(
        make_bond(volume_mn_rub=None),
        1_000_000.0,
        max_pct_daily_volume=0.05,
        horizon_days=5,
    )
    assert plan.max_position_rub is None
    assert plan.days_to_exit is None
    assert plan.warnings


def test_valuation_basics() -> None:
    bond = make_bond()
    valuation = value_bond(bond, key_rate_pct=14.0, now=NOW.date())
    assert valuation.after_tax_ytm_pct == pytest.approx(17.4)
    assert valuation.modified_duration == pytest.approx(1.6667, abs=1e-3)
    assert valuation.carry_pct == pytest.approx(4.0)
    assert valuation.g_spread_bp == pytest.approx(210.0)
    assert valuation.z_spread_bp is None  # нет купонов в календаре
    assert any("Z-спред" in warning for warning in valuation.warnings)


def test_z_spread_positive() -> None:
    bond = make_bond(
        price_pct=98.8,
        nkd_rub=0.0,
        maturity_date=date.today() + timedelta(days=30),
        volume_mn_rub=50.0,
    )
    value = z_spread_bp(bond, [], 14.0, today=date.today())
    # (1000 / 988) ^ (365 / 30) - 1 = 15.82%, то есть 182 б.п. к ставке 14%
    assert value == pytest.approx(182.19, abs=1.0)


def test_value_bond_amortized_warning() -> None:
    bond = make_bond(amortized=True)
    valuation = value_bond(bond, key_rate_pct=14.0, now=NOW.date())
    assert valuation.amortized is True
    assert any("амортизация" in warning for warning in valuation.warnings)


def test_value_bond_offer_warning() -> None:
    bond = make_bond(offer_date=date.today() + timedelta(days=100))
    valuation = value_bond(bond, key_rate_pct=14.0, now=date.today())
    assert any("оферта" in warning for warning in valuation.warnings)


def test_stability_high_beats_low() -> None:
    high = make_bond(isin="H", name="High")
    low = make_bond(
        isin="L",
        name="Low",
        ytm_pct=23.9,
        duration_years=4.9,
        rating="A-",
        price_pct=94.0,
        volume_mn_rub=20.0,
        issue_size_rub=5_000_000_000,
        g_spread_bp=None,
        amortized=True,
        offer_date=NOW.date() + timedelta(days=300),
        fetched_at=NOW - timedelta(days=90),
    )
    high_score = stability_score(high, low_pct=19.0, high_pct=24.0, now=NOW)
    low_score = stability_score(low, low_pct=19.0, high_pct=24.0, now=NOW)
    assert high_score.score > low_score.score
    assert low_score.penalties


def test_stability_qual_only_zero() -> None:
    bond = make_bond(qual_only=True)
    score = stability_score(bond, low_pct=19.0, high_pct=24.0, now=NOW)
    assert score.score == 0.0
    assert any("квалы" in penalty for penalty in score.penalties)


def test_stability_no_rating_penalty() -> None:
    bond = make_bond(rating=None)
    score = stability_score(bond, low_pct=19.0, high_pct=24.0, now=NOW)
    assert any("нет рейтинга" in penalty for penalty in score.penalties)
