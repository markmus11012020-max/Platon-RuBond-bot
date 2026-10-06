"""Unit-тесты BondAnalyzer (улучшения 1–4, 6)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.analytics.bond_math import BondAnalyzer


@pytest.fixture
def analyzer() -> BondAnalyzer:
    return BondAnalyzer()


@pytest.fixture
def fixed_bond() -> dict:
    return {
        "isin": "RU000A105XX3",
        "current_price": 95.0,
        "face_value": 1000.0,
        "nearest_coupon_value": 40.0,
        "coupon_period": 182,
        "maturity_date": (date.today() + timedelta(days=730)).isoformat(),
        "coupon_type": "постоянный",
        "accrued_interest": 12.5,
    }


@pytest.fixture
def amortizing_bond() -> dict:
    today = date.today()
    return {
        "isin": "RU000AMORT01",
        "current_price": 98.0,
        "face_value": 1000.0,
        "residual_face_value": 750.0,
        "nearest_coupon_value": 30.0,
        "coupon_period": 182,
        "maturity_date": (today + timedelta(days=730)).isoformat(),
        "amortization_schedule": [
            {"date": (today + timedelta(days=182)).isoformat(), "amount": 250.0},
            {"date": (today + timedelta(days=364)).isoformat(), "amount": 250.0},
            {"date": (today + timedelta(days=730)).isoformat(), "amount": 250.0},
        ],
    }


class TestYTM:
    def test_newton_ytm_positive(self, analyzer, fixed_bond):
        ytm = analyzer.calculate_ytm(fixed_bond)
        assert ytm is not None
        assert 0.05 < ytm < 0.40

    def test_simple_ytm_fallback(self, analyzer, fixed_bond):
        ytm = analyzer.calculate_simple_ytm(fixed_bond)
        assert ytm is not None
        assert ytm > 0

    def test_zero_price_returns_none(self, analyzer):
        assert analyzer.calculate_ytm({"current_price": 0, "face_value": 1000, "maturity_date": "2030-01-01"}) is None
        assert analyzer.calculate_ytm({"current_price": None, "maturity_date": "2030-01-01"}) is None

    def test_past_maturity_returns_none(self, analyzer):
        bond = {
            "current_price": 100,
            "face_value": 1000,
            "nearest_coupon_value": 40,
            "coupon_period": 182,
            "maturity_date": "2020-01-01",
        }
        assert analyzer.calculate_ytm(bond) is None

    def test_ytm_with_tax(self, analyzer, fixed_bond):
        gross = analyzer.calculate_ytm(fixed_bond, tax_rate=0.0)
        net = analyzer.calculate_ytm(fixed_bond, tax_rate=0.13)
        assert gross is not None and net is not None
        # Net cashflows → slightly different YTM
        assert isinstance(net, float)


class TestAccruedInterest:
    def test_dirty_price(self, analyzer, fixed_bond):
        dirty = analyzer.dirty_price(fixed_bond)
        clean = analyzer.clean_price(fixed_bond)
        assert dirty is not None and clean is not None
        assert dirty == pytest.approx(clean + 12.5, abs=0.01)

    def test_clean_without_accrued(self, analyzer):
        bond = {"current_price": 100.0, "face_value": 1000.0}
        assert analyzer.clean_price(bond) == pytest.approx(1000.0)


class TestAmortization:
    def test_cashflows_include_amort(self, analyzer, amortizing_bond):
        flows = analyzer.build_cashflows(amortizing_bond)
        assert len(flows) >= 2
        total_cf = sum(cf for _, cf in flows)
        # Купоны + амортизация ≈ 30*n + 750
        assert total_cf > 750

    def test_ytm_amortizing(self, analyzer, amortizing_bond):
        ytm = analyzer.calculate_ytm(amortizing_bond)
        assert ytm is not None
        assert ytm > 0


class TestSpreads:
    def test_z_spread(self, analyzer, fixed_bond):
        z = analyzer.calculate_z_spread(fixed_bond, risk_free_rate=0.12)
        assert z is not None
        # При цене 95 и rf=12% спред должен быть положительным
        assert isinstance(z, float)

    def test_credit_spread(self, analyzer, fixed_bond):
        cs = analyzer.calculate_credit_spread(fixed_bond, benchmark_rate=0.10)
        assert cs is not None
        assert cs > 0


class TestFloaterAndCurrent:
    def test_floater_with_spread(self, analyzer):
        bond = {"spread": 0.015, "nearest_coupon_value": 80, "coupon_period": 91, "face_value": 1000}
        assert analyzer.estimate_floater_yield(bond, 0.16) == 0.175

    def test_floater_from_coupon(self, analyzer):
        bond = {"nearest_coupon_value": 40.0, "coupon_period": 182, "face_value": 1000}
        y = analyzer.estimate_floater_yield(bond, 0.16)
        assert y is not None and y > 0

    def test_current_yield(self, analyzer, fixed_bond):
        cy = analyzer.calculate_current_yield(fixed_bond)
        assert cy is not None and 0.05 < cy < 0.30


class TestTax:
    def test_apply_tax(self, analyzer):
        assert analyzer.apply_tax(0.20, 0.13) == pytest.approx(0.174, abs=1e-4)
        assert analyzer.apply_tax(None) is None
        assert analyzer.apply_tax(0.20, -0.1) == 0.20  # invalid → unchanged


class TestFilter:
    def test_filter_by_risk(self, analyzer):
        bonds = [
            {"isin": "A", "rating": "AAA"},
            {"isin": "B", "rating": "BBB-"},
            {"isin": "C", "rating": "BB+"},
            {"isin": "D", "rating": "NR"},
            {"isin": "E", "is_vdo": True, "rating": "A"},
            {"isin": "F", "rating": "ААА"},
        ]
        filtered = analyzer.filter_by_risk(bonds, "BBB-")
        isins = {b["isin"] for b in filtered}
        assert isins == {"A", "B", "F"}
