from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from bondbot.db import SCHEMA_VERSION, Database
from bondbot.models import Bond, utcnow


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


def test_schema_version_is_set(tmp_path) -> None:
    db = Database(str(tmp_path / "version.db"))
    try:
        version = db.conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
    finally:
        db.close()


def test_repair_bond_data_clears_legacy_outliers(tmp_path) -> None:
    db = Database(str(tmp_path / "repair.db"))
    try:
        db.upsert_bonds([Bond(isin="OLD", name="Legacy", ytm_pct=17.0)])
        with db.conn:
            db.conn.execute(
                "UPDATE bonds SET ytm_pct = 415.8, price_pct = 500, "
                "g_spread_bp = 28352 WHERE isin = 'OLD'"
            )
        assert db.repair_bond_data() == 1
        loaded = db.get_bond("OLD")
        assert loaded is not None
        assert loaded.ytm_pct is None
        assert loaded.price_pct is None
        assert loaded.g_spread_bp is None
        assert db.repair_bond_data() == 0
    finally:
        db.close()


def test_llm_usage_quota(tmp_path) -> None:
    db = Database(str(tmp_path / "usage.db"))
    try:
        assert db.llm_tokens_today(7) == 0
        db.add_llm_usage(7, 1200)
        db.add_llm_usage(7, 800)
        assert db.llm_tokens_today(7) == 2000
        assert db.llm_tokens_today(8) == 0
    finally:
        db.close()


def test_old_unsent_alerts_expire(tmp_path) -> None:
    db = Database(str(tmp_path / "alerts.db"))
    try:
        db.save_alert(
            kind="test",
            severity="info",
            message="old",
            dedupe_key="old:1",
            created_at=utcnow() - timedelta(days=3),
        )
        assert db.unsent_alerts()
        assert db.expire_alerts(hours=48) == 1
        assert db.unsent_alerts() == []
    finally:
        db.close()


def test_legacy_positions_table_is_migrated(tmp_path) -> None:
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE positions (
            isin TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            qty REAL NOT NULL,
            buy_price_pct REAL
        );
        PRAGMA user_version = 0;
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    try:
        columns = {
            row[1]
            for row in db.conn.execute("PRAGMA table_info(positions)").fetchall()
        }
        assert "annual_coupon_rub" in columns
        bond_columns = {
            row[1]
            for row in db.conn.execute("PRAGMA table_info(bonds)").fetchall()
        }
        assert "coupon_type" in bond_columns
        version = db.conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
    finally:
        db.close()
