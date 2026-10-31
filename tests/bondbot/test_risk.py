from __future__ import annotations

from datetime import date, timedelta

import pytest

from bondbot.analytics.risk import (
    assess_bond_risk,
    assess_portfolio_risk,
    stress_portfolio,
)
from bondbot.models import Bond, PortfolioPosition, utcnow


def _bond(isin: str = "RISK", **kwargs) -> Bond:
    base = dict(
        isin=isin,
        name="Risk Bond",
        ytm_pct=18.0,
        duration_years=1.0,
        rating="AAA",
        price_pct=100.0,
        volume_mn_rub=100.0,
        issue_size_rub=30_000_000_000.0,
        fetched_at=utcnow(),
    )
    base.update(kwargs)
    return Bond(**base)


def test_healthy_bond_has_low_risk() -> None:
    assessment = assess_bond_risk(_bond(), 14.0)
    assert assessment.level in {"LOW", "MEDIUM"}
    assert assessment.score < 50


def test_risky_bond_has_warnings() -> None:
    assessment = assess_bond_risk(
        _bond(
            ytm_pct=30.0,
            duration_years=5.0,
            rating="BBB-",
            price_pct=88.0,
            volume_mn_rub=1.0,
            offer_date=date.today() + timedelta(days=20),
            fetched_at=utcnow() - timedelta(days=90),
        ),
        14.0,
    )
    assert assessment.level in {"HIGH", "CRITICAL"}
    assert assessment.warnings
    assert any("оферта" in warning for warning in assessment.warnings)


def test_portfolio_risk_uses_weights_and_concentration() -> None:
    bonds = {
        "A": _bond("A", ytm_pct=17.0),
        "B": _bond("B", ytm_pct=30.0, rating="BB", volume_mn_rub=1.0),
    }
    positions = [
        PortfolioPosition(isin="A", name="A", qty=1, current_value_rub=900_000.0),
        PortfolioPosition(isin="B", name="B", qty=1, current_value_rub=100_000.0),
    ]
    assessment = assess_portfolio_risk(positions, bonds, 14.0)
    assert assessment.isin == "PORTFOLIO"
    assert assessment.score > 0
    assert any("90.0%" in warning or "Risk Bond" in warning for warning in assessment.warnings)


def test_stress_portfolio_duration_impact() -> None:
    bond = _bond("S", ytm_pct=20.0, duration_years=2.0)
    position = PortfolioPosition(
        isin="S",
        name="S",
        qty=1000,
        current_value_rub=1_000_000.0,
        annual_coupon_rub=80_000.0,
    )
    result = stress_portfolio([position], {"S": bond}, 100.0)
    # modified duration = 2 / 1.2 = 1.6667; 1% move -> -16 666.67 ₽
    assert result.impact_rub == pytest.approx(-16_666.67, abs=1.0)
    assert result.new_value_rub == pytest.approx(983_333.33, abs=1.0)
    assert result.annual_income_rub == pytest.approx(80_000.0)
