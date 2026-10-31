from __future__ import annotations

from dataclasses import replace
from datetime import date

from bondbot.config import load_settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import Bond, utcnow
from bondbot.services.relative import build_relative_value


def _bond(isin: str, ytm: float, **kwargs) -> Bond:
    base = dict(
        isin=isin,
        name=f"Bond {isin}",
        ytm_pct=ytm,
        duration_years=2.0,
        rating="AAA",
        price_pct=100.0,
        volume_mn_rub=100.0,
        fetched_at=utcnow(),
    )
    base.update(kwargs)
    return Bond(**base)


def test_relative_value_for_bond_and_list(tmp_path) -> None:
    db = Database(str(tmp_path / "relative.db"))
    settings = replace(load_settings())
    snapshot = KeyRateSnapshot(value_pct=14.0, as_of=date.today())
    try:
        db.upsert_bonds(
            [
                _bond("A", 19.0),
                _bond("B", 20.0),
                _bond("C", 21.0),
                _bond("D", 24.0),
            ]
        )
        text = build_relative_value(settings, db, snapshot)
        assert "Relative value" in text
        assert "Дешевле peers" in text
        target = build_relative_value(settings, db, snapshot, isin="D")
        assert "D" in target
        assert "премия" in target
    finally:
        db.close()
