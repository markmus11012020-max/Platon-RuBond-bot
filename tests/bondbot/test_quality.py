from __future__ import annotations

from bondbot.data.quality import sanitize_bond, sanitize_position
from bondbot.db import Database
from bondbot.models import Bond, PortfolioPosition


def test_sanitize_bond_drops_outliers() -> None:
    bond = Bond(
        isin="BAD",
        name="Broken bond",
        ytm_pct=415.8,
        price_pct=500.0,
        duration_years=-1.0,
        volume_mn_rub=-5.0,
        issue_size_rub=-1.0,
        face_value=0.0,
        coupon_freq=99.0,
    )
    cleaned = sanitize_bond(bond)
    assert cleaned.ytm_pct is None
    assert cleaned.price_pct is None
    assert cleaned.duration_years is None
    assert cleaned.volume_mn_rub is None
    assert cleaned.issue_size_rub is None
    assert cleaned.face_value is None
    assert cleaned.coupon_freq is None


def test_sanitize_bond_keeps_valid_values() -> None:
    bond = Bond(
        isin="GOOD",
        name="Good bond",
        ytm_pct=18.5,
        price_pct=99.5,
        duration_years=2.5,
        volume_mn_rub=40.0,
        issue_size_rub=5_000_000_000.0,
        face_value=1000.0,
        coupon_freq=2.0,
    )
    assert sanitize_bond(bond) == bond


def test_database_sanitizes_bonds(tmp_path) -> None:
    db = Database(str(tmp_path / "quality.db"))
    try:
        db.upsert_bonds([Bond(isin="BAD", name="Broken", ytm_pct=415.8, price_pct=500.0)])
        loaded = db.get_bond("BAD")
        assert loaded is not None
        assert loaded.ytm_pct is None
        assert loaded.price_pct is None
    finally:
        db.close()


def test_sanitize_position_drops_outliers() -> None:
    position = PortfolioPosition(
        isin="BAD",
        name="Broken",
        qty=1,
        buy_price_pct=500.0,
        current_value_rub=-100.0,
    )
    cleaned = sanitize_position(position)
    assert cleaned.qty == 1
    assert cleaned.buy_price_pct is None
    assert cleaned.current_value_rub is None
