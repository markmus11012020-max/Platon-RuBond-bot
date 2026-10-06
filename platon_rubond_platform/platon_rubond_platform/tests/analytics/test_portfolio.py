"""Unit-тесты PortfolioManager (улучшения 5–6)."""

from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

import pytest

from src.analytics.portfolio import PortfolioManager


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_portfolio.db")


@pytest.fixture
def pm(tmp_db):
    manager = PortfolioManager(db_path=tmp_db, tax_rate=0.13, auto_load=True)
    yield manager
    manager.close()


@pytest.fixture
def market_data():
    return [
        {
            "isin": "RU000A105XX3",
            "current_price": 99.0,
            "face_value": 1000,
            "ytm": 0.12,
            "nearest_coupon_value": 45.0,
            "coupon_period": 182,
            "next_coupon_date": (date.today() + timedelta(days=30)).isoformat(),
        },
        {
            "isin": "SU26238RMFS7",
            "current_price": 96.0,
            "face_value": 1000,
            "ytm": 0.14,
            "nearest_coupon_value": 30.0,
            "coupon_period": 182,
        },
    ]


class TestAddRemove:
    def test_add_and_average(self, pm):
        assert pm.add_to_portfolio("RU000A105XX3", 10, 98.5, issuer="Gazprom", sector="Energy")
        assert pm.add_to_portfolio("RU000A105XX3", 5, 99.0)
        pos = pm.get_positions()
        assert len(pos) == 1
        assert pos[0]["quantity"] == 15.0
        # средневзвешенная цена
        expected = (10 * 98.5 + 5 * 99.0) / 15
        assert pos[0]["purchase_price"] == pytest.approx(expected, abs=0.01)

    def test_invalid_inputs(self, pm):
        assert not pm.add_to_portfolio("", 1, 100)
        assert not pm.add_to_portfolio("X", -1, 100)
        assert not pm.add_to_portfolio("X", 1, 0)

    def test_remove(self, pm):
        pm.add_to_portfolio("RU000A105XX3", 10, 98.5)
        assert pm.remove_from_portfolio("RU000A105XX3", 3)
        assert pm.get_positions()[0]["quantity"] == 7.0
        assert pm.remove_from_portfolio("RU000A105XX3")
        assert pm.get_positions() == []


class TestPersistence:
    def test_save_and_reload(self, tmp_db):
        pm1 = PortfolioManager(db_path=tmp_db, auto_load=False)
        pm1.add_to_portfolio("RU000A105XX3", 10, 98.5, issuer="Gazprom")
        pm1.add_to_portfolio("SU26238RMFS7", 5, 95.0, issuer="Minfin")
        pm1.close()

        pm2 = PortfolioManager(db_path=tmp_db, auto_load=True)
        positions = pm2.get_positions()
        assert len(positions) == 2
        isins = {p["isin"] for p in positions}
        assert isins == {"RU000A105XX3", "SU26238RMFS7"}
        pm2.close()

    def test_clear_persists(self, pm):
        pm.add_to_portfolio("RU000A105XX3", 10, 98.5)
        pm.clear()
        assert pm.get_positions() == []
        # reload
        pm.load_from_db()
        assert pm.get_positions() == []


class TestMetrics:
    def test_metrics_with_tax(self, pm, market_data):
        pm.add_to_portfolio("RU000A105XX3", 10, 98.5, issuer="Gazprom", sector="Energy")
        pm.add_to_portfolio("SU26238RMFS7", 5, 95.0, issuer="Minfin", sector="Gov")
        m = pm.calculate_portfolio_metrics(market_data, tax_rate=0.13)
        assert m["total_market_value"] > 0
        assert m["weighted_ytm"] is not None
        assert m["weighted_ytm_net"] is not None
        assert m["weighted_ytm_net"] < m["weighted_ytm"]
        assert m["tax_rate"] == 0.13
        assert "coupon_calendar" in m
        assert "coupon_calendar_net" in m
        assert m["positions_count"] == 2

    def test_diversification_warning(self, pm, market_data):
        pm.add_to_portfolio("RU000A105XX3", 100, 98.5)
        pm.add_to_portfolio("SU26238RMFS7", 1, 95.0)
        m = pm.calculate_portfolio_metrics(market_data)
        assert m["diversification_ok"] is False
        assert len(m["concentration_warnings"]) > 0

    def test_empty_portfolio(self, pm):
        m = pm.calculate_portfolio_metrics([])
        assert m["total_market_value"] == 0.0
        assert m["positions_count"] == 0
