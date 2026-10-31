from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from bondbot.analytics.rates import MaxYield
from bondbot.config import load_settings
from bondbot.data.cbr import CACHE_KEY, KeyRateSnapshot
from bondbot.data.smartlab import parse_screener
from bondbot.db import Database
from bondbot.models import utcnow
from bondbot.importers.smartlab_portfolio import import_portfolio_file
from bondbot.vk.handlers import (
    BotHandlers,
    format_portfolio,
    format_screen,
    format_status,
)

FIXTURES = Path(__file__).parent / "fixtures"
CHAT_PEER = 2_000_000_777
ADMIN_ID = 42


class FakeVk:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, peer_id: int, message: str, **kwargs) -> int:
        self.sent.append({"peer_id": peer_id, "message": message, **kwargs})
        return 1


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(str(tmp_path / "handlers.db"))
    screener = (FIXTURES / "smartlab_screener.html").read_text(encoding="utf-8")
    database.upsert_bonds(parse_screener(screener, source_url="fixture"))
    import_portfolio_file(database, FIXTURES / "portfolio_synthetic.html")
    yield database
    database.close()


def test_format_portfolio(db: Database) -> None:
    text = format_portfolio(load_settings(), db)
    assert "Бумажный портфель" in text
    assert "1 517 400 ₽" in text
    assert "P&L: 1 450 ₽" in text
    assert "RU000TEST0001" in text
    assert "Test Bond 1" in text


def test_format_screen(db: Database) -> None:
    text = format_screen(load_settings(), db, limit=3)
    assert "Кандидаты" in text
    assert "YTM" in text
    assert "Лимит:" in text


def test_format_screen_with_dynamic_cap(db: Database) -> None:
    cap = MaxYield(
        value_pct=35.0,
        source="key_rate",
        key_rate_pct=25.0,
        margin_pct=10.0,
        as_of=date(2026, 10, 30),
    )
    text = format_screen(load_settings(), db, limit=3, max_yield=cap)
    assert "ставка ЦБ 25.00%" in text
    assert "35.00%" in text


def test_format_status_shows_cap(db: Database) -> None:
    cap = MaxYield(
        value_pct=24.0,
        source="key_rate",
        key_rate_pct=14.0,
        margin_pct=10.0,
        as_of=date(2026, 10, 30),
    )
    text = format_status(load_settings(), db, max_yield=cap)
    assert "Лимит доходности" in text
    assert "ставка ЦБ 14.00%" in text


def test_connect_and_portfolio_command(db: Database) -> None:
    settings = replace(
        load_settings(),
        vk_admin_user_id=ADMIN_ID,
        vk_group_token="test",
        vk_group_id=1,
    )
    vk = FakeVk()
    handlers = BotHandlers(settings, db, vk)  # type: ignore[arg-type]

    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": ADMIN_ID,
                        "text": "/connect",
                    }
                },
            }
        )
    )
    assert db.kv_get("chat_peer_id") == str(CHAT_PEER)
    assert "подключена" in vk.sent[-1]["message"].lower()

    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": ADMIN_ID,
                        "text": "/portfolio",
                    }
                },
            }
        )
    )
    assert "Бумажный портфель" in vk.sent[-1]["message"]


def _owner_handlers(db: Database) -> tuple[BotHandlers, FakeVk]:
    settings = replace(
        load_settings(),
        vk_admin_user_id=ADMIN_ID,
        vk_group_token="test",
        vk_group_id=1,
    )
    vk = FakeVk()
    return BotHandlers(settings, db, vk), vk  # type: ignore[arg-type]


def test_private_start_stores_owner_peer(db: Database) -> None:
    handlers, vk = _owner_handlers(db)
    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": ADMIN_ID,
                        "from_id": ADMIN_ID,
                        "text": "/start",
                    }
                },
            }
        )
    )
    assert db.kv_get("owner_peer_id") == str(ADMIN_ID)
    assert "аналитик" in vk.sent[-1]["message"].lower()


def test_stranger_is_ignored(db: Database) -> None:
    handlers, vk = _owner_handlers(db)
    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": ADMIN_ID + 1,
                        "text": "/portfolio",
                    }
                },
            }
        )
    )
    assert vk.sent == []


def test_strategy_commands_reply(db: Database) -> None:
    handlers, vk = _owner_handlers(db)
    db.kv_set(
        CACHE_KEY,
        KeyRateSnapshot(
            value_pct=14.0,
            as_of=date(2026, 10, 30),
            fetched_at=utcnow(),
        ).to_json(),
    )
    expected = {
        "/safe": "Стабильные бумаги",
        "/exit": "Ликвидность и выход",
        "/alloc": "Целевая аллокация",
    }
    for command, header in expected.items():
        asyncio.run(
            handlers.handle_update(
                {
                    "type": "message_new",
                    "object": {
                        "message": {
                            "peer_id": CHAT_PEER,
                            "from_id": ADMIN_ID,
                            "text": command,
                        }
                    },
                }
            )
        )
        assert header in vk.sent[-1]["message"]
    assert db.audits(limit=10)
