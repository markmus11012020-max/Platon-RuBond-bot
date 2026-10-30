from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, timedelta
from unittest.mock import patch

from bondbot.analytics.rates import MaxYield, resolve_max_yield
from bondbot.config import load_settings
from bondbot.data.cbr import CACHE_KEY, KeyRateSnapshot, parse_key_rate
from bondbot.db import Database
from bondbot.models import utcnow

CBR_HTML = """
<html><body>
<table class="data">
  <tr><th>Дата</th><th>Ставка</th></tr>
  <tr><td>29.10.2026</td><td>14,00</td></tr>
  <tr><td>30.10.2026</td><td>14,00</td></tr>
  <tr><td>23.10.2026</td><td>14,00</td></tr>
</table>
</body></html>
"""


def test_parse_key_rate_picks_latest() -> None:
    snapshot = parse_key_rate(CBR_HTML)
    assert snapshot is not None
    assert snapshot.value_pct == 14.0
    assert snapshot.as_of == date(2026, 10, 30)


def test_parse_key_rate_no_table() -> None:
    assert parse_key_rate("<html><body>no data</body></html>") is None


def test_max_yield_describe() -> None:
    cap = MaxYield(
        value_pct=24.0,
        source="key_rate",
        key_rate_pct=14.0,
        margin_pct=10.0,
        as_of=date(2026, 10, 30),
    )
    text = cap.describe()
    assert "ставка ЦБ 14.00%" in text
    assert "24.00%" in text
    assert "30.10.2026" in text


def test_resolve_fixed_cap(tmp_path) -> None:
    db = Database(str(tmp_path / "rates.db"))
    try:
        settings = replace(
            load_settings(),
            dynamic_max_yield=False,
            max_yield_pct=35.0,
        )
        cap = asyncio.run(resolve_max_yield(settings, db))
        assert cap.value_pct == 35.0
        assert cap.source == "fixed"
    finally:
        db.close()


def test_resolve_uses_fresh_cache(tmp_path) -> None:
    db = Database(str(tmp_path / "rates.db"))
    try:
        db.kv_set(
            CACHE_KEY,
            KeyRateSnapshot(
                value_pct=14.0,
                as_of=date(2026, 10, 30),
                fetched_at=utcnow(),
            ).to_json(),
        )
        settings = replace(load_settings(), dynamic_max_yield=True, key_rate_margin_pct=10.0)
        cap = asyncio.run(resolve_max_yield(settings, db))
        assert cap.value_pct == 24.0
        assert cap.source == "key_rate"
        assert cap.key_rate_pct == 14.0
        assert cap.stale is False
    finally:
        db.close()


def test_resolve_fetches_and_saves(tmp_path) -> None:
    db = Database(str(tmp_path / "rates.db"))
    snapshot = KeyRateSnapshot(value_pct=15.5, as_of=date(2026, 10, 30))
    try:
        settings = replace(load_settings(), dynamic_max_yield=True, key_rate_margin_pct=10.0)

        async def fake_fetch(self):
            return snapshot

        with patch("bondbot.data.cbr.CbrKeyRateClient.fetch", new=fake_fetch):
            cap = asyncio.run(resolve_max_yield(settings, db))

        assert cap.value_pct == 25.5
        assert cap.source == "key_rate"
        assert db.kv_get(CACHE_KEY)
    finally:
        db.close()


def test_resolve_falls_back_without_key_rate(tmp_path) -> None:
    db = Database(str(tmp_path / "rates.db"))
    try:
        settings = replace(
            load_settings(),
            dynamic_max_yield=True,
            max_yield_pct=35.0,
        )

        async def fail_fetch(self):
            raise RuntimeError("CBR unavailable")

        with patch("bondbot.data.cbr.CbrKeyRateClient.fetch", new=fail_fetch):
            cap = asyncio.run(resolve_max_yield(settings, db))

        assert cap.value_pct == 35.0
        assert cap.source == "fallback"
    finally:
        db.close()


def test_resolve_uses_stale_cache_on_failure(tmp_path) -> None:
    db = Database(str(tmp_path / "rates.db"))
    try:
        old = KeyRateSnapshot(
            value_pct=14.0,
            as_of=date(2026, 10, 30),
            fetched_at=utcnow() - timedelta(days=2),
        )
        db.kv_set(CACHE_KEY, old.to_json())
        settings = replace(load_settings(), dynamic_max_yield=True, key_rate_margin_pct=10.0)

        async def fail_fetch(self):
            raise RuntimeError("CBR unavailable")

        with patch("bondbot.data.cbr.CbrKeyRateClient.fetch", new=fail_fetch):
            cap = asyncio.run(resolve_max_yield(settings, db))

        assert cap.value_pct == 24.0
        assert cap.source == "key_rate"
        assert cap.stale is True
    finally:
        db.close()
