from __future__ import annotations

import pickle
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from bondbot.analytics.bonds import rating_rank
from bondbot.config import load_settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import PortfolioPosition
from bondbot.strategy.allocation import AllocationConstraints, build_allocation
from bondbot.strategy.exit import build_exit_plan
from bondbot.strategy.render import render_allocation, render_exit_plan, render_safe_list
from bondbot.strategy.safe import build_safe_list

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
SNAPSHOT = KeyRateSnapshot(value_pct=14.0, as_of=NOW.date())


def _bond(isin: str, name: str, **kwargs):
    base = dict(
        isin=isin,
        name=name,
        ytm_pct=20.0,
        current_coupon_yield_pct=18.0,
        duration_years=2.0,
        rating="AAA",
        price_pct=100.0,
        volume_mn_rub=100.0,
        issue_size_rub=30_000_000_000,
        g_spread_bp=200.0,
        face_value=1000.0,
        nkd_rub=0.0,
        qual_only=False,
        amortized=False,
        fetched_at=NOW,
    )
    base.update(kwargs)
    return __import__("bondbot.models", fromlist=["Bond"]).Bond(**base)


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "strategy.db"))
    database.upsert_bonds(
        [
            _bond("AAA1", "Elite High", ytm_pct=20.0, duration_years=2.0, rating="AAA",
                  price_pct=100.0, volume_mn_rub=100.0, issue_size_rub=30_000_000_000,
                  g_spread_bp=200.0),
            _bond("A1", "Solid Mid", ytm_pct=21.0, duration_years=3.0, rating="A",
                  price_pct=100.0, volume_mn_rub=30.0, issue_size_rub=5_000_000_000,
                  g_spread_bp=300.0),
            _bond("BBB1", "Risky", ytm_pct=23.0, duration_years=4.9, rating="BBB-",
                  price_pct=95.0, volume_mn_rub=20.0, issue_size_rub=5_000_000_000,
                  g_spread_bp=400.0),
            _bond("HIGH1", "Too High Yield", ytm_pct=30.0, duration_years=5.0, rating="A",
                  price_pct=95.0, volume_mn_rub=40.0, issue_size_rub=5_000_000_000,
                  g_spread_bp=500.0),
            _bond("LOW1", "Too Low Yield", ytm_pct=18.5, duration_years=3.0, rating="AA",
                  price_pct=100.0, volume_mn_rub=40.0, issue_size_rub=5_000_000_000,
                  g_spread_bp=150.0),
            _bond("QUAL1", "Qual Only", ytm_pct=21.0, duration_years=3.0, rating="A",
                  price_pct=100.0, volume_mn_rub=40.0, issue_size_rub=5_000_000_000,
                  g_spread_bp=200.0, qual_only=True),
        ]
    )
    database.upsert_positions(
        [
            PortfolioPosition(
                isin="BBB1",
                name="Risky",
                qty=1000,
                buy_price_pct=100.0,
                current_value_rub=400_000.0,
                annual_coupon_rub=4_000.0,
            )
        ]
    )
    yield database
    database.close()


def test_safe_list_only_in_range(db) -> None:
    settings = replace(load_settings())
    result = build_safe_list(settings, db, SNAPSHOT, now=NOW)
    isins = [item.bond.isin for item in result.items]
    assert isins
    assert all(19.0 <= item.bond.ytm_pct <= 24.0 for item in result.items)
    assert "QUAL1" not in isins
    assert result.range.low_pct == pytest.approx(19.0)
    assert result.range.high_pct == pytest.approx(24.0)
    assert result.audit_id


def test_safe_list_respects_rating_and_duration(db) -> None:
    settings = replace(load_settings())
    result = build_safe_list(settings, db, SNAPSHOT, now=NOW)
    for item in result.items:
        bond = item.bond
        assert bond.duration_years <= settings.max_duration_years
        assert rating_rank(bond.rating) >= rating_rank(settings.min_rating)
        assert bond.price_pct is not None


def test_safe_list_audit_record(db) -> None:
    settings = replace(load_settings())
    result = build_safe_list(settings, db, SNAPSHOT, now=NOW)
    records = db.audits(limit=5)
    assert records
    assert records[0]["id"] == result.audit_id
    assert records[0]["kind"] == "safe_list"
    assert "range = ЦБ 14.00%" in records[0]["formulas"][0]


def test_allocation_targets_and_sells(db) -> None:
    settings = replace(load_settings())
    result = build_allocation(settings, db, SNAPSHOT, now=NOW)
    assert result.total_value_rub == pytest.approx(400_000.0)
    assert result.cash_reserve_rub >= 0
    targets = {t.bond.isin: t for t in result.targets}
    assert "BBB1" in targets
    assert targets["BBB1"].action == "sell"
    assert set(targets).issubset({"AAA1", "A1", "BBB1"})
    for target in result.targets:
        assert target.target_weight <= result.constraints.max_position_share + 1e-6
        assert target.target_value_rub >= 0
    assert result.audit_id


def test_allocation_liquidity_cap(db) -> None:
    settings = replace(load_settings())
    result = build_allocation(
        settings,
        db,
        SNAPSHOT,
        constraints=AllocationConstraints(max_positions=2, min_position_rub=0),
        now=NOW,
    )
    for target in result.targets:
        if target.liquidity and target.liquidity.max_position_rub:
            cap = target.liquidity.max_position_rub
            assert target.target_value_rub <= cap + 1.0


def test_exit_plan(db) -> None:
    settings = replace(load_settings())
    image_result = build_exit_plan(settings, db, now=NOW)
    assert image_result.audit_id
    plan = next(p for p in image_result.plans if p.isin == "BBB1")
    assert plan.position_value_rub == pytest.approx(400_000.0)
    assert not plan.warnings  # 400k при лимите 1 млн ₽ в день выходят за 0.4 дня
    assert plan.days_to_exit == pytest.approx(0.4, abs=1e-6)


def test_exit_plan_warns_when_position_too_large(db) -> None:
    settings = replace(load_settings())
    db.upsert_positions(
        [
            PortfolioPosition(
                isin="BBB1",
                name="Risky",
                qty=8000,
                buy_price_pct=100.0,
                current_value_rub=8_000_000.0,
            )
        ]
    )
    result = build_exit_plan(settings, db, now=NOW)
    plan = next(p for p in result.plans if p.isin == "BBB1")
    assert plan.days_to_exit == pytest.approx(8.0)
    assert plan.warnings
    assert any("выход" in warning for warning in plan.warnings)


def test_render_helpers(db) -> None:
    settings = replace(load_settings())
    safe_result = build_safe_list(settings, db, SNAPSHOT, now=NOW)
    text = render_safe_list(safe_result)
    assert "Стабильные бумаги" in text
    assert "19.00–24.00%" in text
    alloc_result = build_allocation(settings, db, SNAPSHOT, now=NOW)
    alloc_text = render_allocation(alloc_result)
    assert "Целевая аллокация" in alloc_text
    exit_result = build_exit_plan(settings, db, now=NOW)
    exit_text = render_exit_plan(exit_result)
    assert "Ликвидность и выход" in exit_text
