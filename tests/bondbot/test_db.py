from __future__ import annotations

from datetime import date

from bondbot.db import Database
from bondbot.models import Bond


def test_upsert_and_watchlist(tmp_path) -> None:
    db = Database(str(tmp_path / "test.db"))
    try:
        bond = Bond(
            isin="RU000A10G1T5",
            name="Test bond",
            ytm_pct=17.4,
            duration_years=0.66,
            rating="AAA",
            volume_mn_rub=341.2,
            maturity_date=date(2035, 9, 26),
        )
        assert db.upsert_bonds([bond]) == 1
        assert db.upsert_bonds([bond]) == 1
        loaded = db.get_bond("RU000A10G1T5")
        assert loaded is not None
        assert loaded.ytm_pct == 17.4
        assert loaded.maturity_date == date(2035, 9, 26)

        db.add_watch("RU000A10G1T5", "бумажный портфель")
        rows = db.watchlist()
        assert len(rows) == 1
        assert rows[0]["isin"] == "RU000A10G1T5"
        assert rows[0]["name"] == "Test bond"
    finally:
        db.close()
