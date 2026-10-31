from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from bondbot.config import load_settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import Bond, PortfolioPosition, utcnow
from bondbot.services.alerts import (
    build_alerts,
    format_alert,
    save_alerts,
    send_pending_alerts,
)
from bondbot.services.backup import backup_database
from bondbot.services.digest import build_digest
from bondbot.services.refresh import merge_bonds, refresh_market
from bondbot.services.scheduler import BotScheduler


class FakeVk:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, peer_id: int, message: str, **kwargs) -> int:
        self.sent.append({"peer_id": peer_id, "message": message})
        return 1


class FakeSmartLab:
    bonds: list[Bond] = []

    def __init__(self, settings) -> None:
        self.settings = settings

    async def __aenter__(self) -> "FakeSmartLab":
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def fetch_screener(self) -> list[Bond]:
        return list(self.bonds)


def _bond(isin: str = "X", **kwargs) -> Bond:
    base = dict(
        isin=isin,
        name="Test",
        ytm_pct=20.0,
        duration_years=2.0,
        rating="AAA",
        price_pct=100.0,
        volume_mn_rub=100.0,
        issue_size_rub=30_000_000_000.0,
        maturity_date=date.today() + timedelta(days=400),
        fetched_at=utcnow(),
    )
    base.update(kwargs)
    return Bond(**base)


def test_merge_bonds_keeps_smartlab_rating_and_official_price() -> None:
    base = _bond(price_pct=99.0, g_spread_bp=200.0)
    official = _bond(price_pct=101.0, ytm_pct=21.0, rating=None, g_spread_bp=None)
    merged = merge_bonds([base], [official])[0]
    assert merged.rating == "AAA"
    assert merged.g_spread_bp == 200.0
    assert merged.price_pct == 101.0
    assert merged.ytm_pct == 21.0


def test_refresh_market_detects_new_isins(tmp_path, monkeypatch) -> None:
    db = Database(str(tmp_path / "refresh.db"))
    settings = replace(load_settings(), moex_enabled=False)
    try:
        FakeSmartLab.bonds = [_bond("FIRST")]
        monkeypatch.setattr("bondbot.services.refresh.SmartLabClient", FakeSmartLab)
        first = asyncio.run(refresh_market(settings, db))
        assert first.upserted == 1
        assert db.count_bonds() == 1
        assert "FIRST" in first.new_isins

        FakeSmartLab.bonds = [_bond("FIRST"), _bond("SECOND")]
        second = asyncio.run(refresh_market(settings, db))
        assert second.upserted == 2
        assert second.new_isins == ("SECOND",)
        recent = db.recent_new_issues(days=7)
        assert [row["isin"] for row in recent] == ["SECOND"]
    finally:
        db.close()


def _alert_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "alerts.db"))
    db.upsert_bonds(
        [
            _bond(
                "RISKY",
                name="Risky",
                ytm_pct=30.0,
                rating="BBB",
                volume_mn_rub=1.0,
                offer_date=date.today() + timedelta(days=20),
            )
        ]
    )
    db.upsert_positions(
        [
            PortfolioPosition(
                isin="RISKY",
                name="Risky",
                qty=1,
                current_value_rub=400_000.0,
            )
        ]
    )
    return db


def test_build_alerts_and_dedupe(tmp_path) -> None:
    db = _alert_db(tmp_path)
    settings = replace(load_settings(), owner_peer_id=12345)
    snapshot = KeyRateSnapshot(value_pct=14.0, as_of=date.today())
    try:
        alerts = build_alerts(settings, db, snapshot)
        kinds = {alert.kind for alert in alerts}
        assert {"yield_high", "rating", "offer", "liquidity", "concentration"} <= kinds
        assert save_alerts(db, alerts) == len(alerts)
        assert save_alerts(db, alerts) == 0
        assert format_alert({"severity": "critical", "message": "test"}).startswith("🚨")
    finally:
        db.close()


def test_send_pending_alerts(tmp_path) -> None:
    db = _alert_db(tmp_path)
    settings = replace(
        load_settings(),
        owner_peer_id=12345,
        alerts_enabled=True,
        alert_quiet_start=23,
        alert_quiet_end=8,
    )
    vk = FakeVk()
    try:
        db.save_alert(
            kind="test",
            severity="warning",
            message="Проверка",
            dedupe_key="test:1",
        )
        sent = asyncio.run(
            send_pending_alerts(
                settings,
                db,
                vk,
                now=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
            )
        )
        assert sent == 1
        assert vk.sent and vk.sent[0]["peer_id"] == 12345
        assert db.unsent_alerts() == []
    finally:
        db.close()


def test_build_digest(tmp_path) -> None:
    db = _alert_db(tmp_path)
    db.upsert_bonds(
        [
            _bond(
                "SAFE",
                name="Safe",
                ytm_pct=20.0,
                rating="AAA",
                volume_mn_rub=100.0,
                issue_size_rub=30_000_000_000.0,
            )
        ]
    )
    settings = replace(load_settings())
    snapshot = KeyRateSnapshot(value_pct=14.0, as_of=date.today())
    try:
        text = build_digest(settings, db, snapshot)
        assert "Дайджест" in text
        assert "Ставка ЦБ" in text
        assert "Идеи в коридоре" in text
    finally:
        db.close()


def test_backup_database(tmp_path) -> None:
    db = Database(str(tmp_path / "source.db"))
    db.upsert_bonds([_bond("BACKUP")])
    db.close()
    target = backup_database(tmp_path / "source.db", tmp_path / "backups")
    assert target.exists()
    assert target.stat().st_size > 0


def test_scheduler_records_job(tmp_path) -> None:
    db = Database(str(tmp_path / "jobs.db"))
    settings = replace(load_settings(), scheduler_enabled=False, alerts_enabled=False)
    scheduler = BotScheduler(settings, db, FakeVk())  # type: ignore[arg-type]

    async def work() -> dict:
        return {"ok": True}

    try:
        asyncio.run(scheduler._run("demo", work))
        job = db.last_jobs(1)[0]
        assert job["name"] == "demo"
        assert job["status"] == "ok"
        assert job["details"] == {"ok": True}
    finally:
        db.close()
