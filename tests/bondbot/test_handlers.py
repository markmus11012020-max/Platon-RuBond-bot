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
from bondbot.models import Bond, PortfolioPosition, utcnow
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
        self.members = {ADMIN_ID}
        self.downloaded: bytes = b""

    async def send_message(self, peer_id: int, message: str, **kwargs) -> int:
        self.sent.append({"peer_id": peer_id, "message": message, **kwargs})
        return 1

    async def is_group_member(self, user_id: int, group_id: int | None = None) -> bool:
        return user_id in self.members

    async def download(self, url: str, limit: int = 8_000_000) -> bytes:
        return self.downloaded


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


def test_non_member_is_denied(db: Database) -> None:
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
    assert vk.sent
    assert "участникам сообщества" in vk.sent[-1]["message"]


def test_public_member_gets_help_without_admin_commands(db: Database) -> None:
    handlers, vk = _owner_handlers(db)
    member_id = ADMIN_ID + 5
    vk.members.add(member_id)
    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": member_id,
                        "text": "/help",
                    }
                },
            }
        )
    )
    message = vk.sent[-1]["message"]
    assert "Platon Bond Bot" in message
    assert "/screen" in message
    assert "/portfolio" not in message
    assert "Админ-команды" not in message


def test_public_member_cannot_use_admin_command(db: Database) -> None:
    handlers, vk = _owner_handlers(db)
    member_id = ADMIN_ID + 6
    vk.members.add(member_id)
    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": member_id,
                        "text": "/portfolio",
                    }
                },
            }
        )
    )
    assert "администратору" in vk.sent[-1]["message"]


def test_tax_and_iis_reference(db: Database) -> None:
    handlers, vk = _owner_handlers(db)
    for command, expected in (("/iis", "ИИС-3"), ("/tax", "НДФЛ")):
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
        assert expected in vk.sent[-1]["message"]
        assert "не налоговая консультация" in vk.sent[-1]["message"]


def test_free_text_goes_to_dialog(db: Database) -> None:
    settings = replace(
        load_settings(),
        vk_admin_user_id=ADMIN_ID,
        vk_group_token="test",
        vk_group_id=1,
        openai_api_key="",
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
                        "text": "Техдефолт МГКЛ, расскажи про эту новость",
                    }
                },
            }
        )
    )
    assert "LLM не настроен" in vk.sent[-1]["message"]


def test_long_reply_is_split_not_truncated(db: Database) -> None:
    handlers, vk = _owner_handlers(db)
    text = "\n".join(f"Строка {index}: " + ("данные " * 30) for index in range(100))
    asyncio.run(handlers._reply(CHAT_PEER, text))
    assert len(vk.sent) > 1
    combined = "\n".join(item["message"] for item in vk.sent)
    assert "Строка 0" in combined
    assert "Строка 99" in combined
    assert all(len(item["message"]) <= 3500 for item in vk.sent)


def test_document_import_replaces_portfolio(db: Database, monkeypatch) -> None:
    handlers, vk = _owner_handlers(db)
    html = (FIXTURES / "portfolio_synthetic.html").read_text(encoding="utf-8")
    vk.downloaded = html.encode("utf-8")
    db.upsert_positions(
        [
            PortfolioPosition(
                isin="STALE",
                name="Stale position",
                qty=1,
                current_value_rub=1.0,
            )
        ]
    )

    async def fake_refresh(*args, **kwargs):
        return 0, []

    monkeypatch.setattr("bondbot.vk.handlers.refresh_details", fake_refresh)
    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": ADMIN_ID,
                        "text": "",
                        "attachments": [
                            {
                                "type": "doc",
                                "doc": {
                                    "title": "portfolio.html",
                                    "ext": "html",
                                    "url": "https://example.com/portfolio.html",
                                },
                            }
                        ],
                    }
                },
            }
        )
    )
    assert "Портфель обновлён: 2 позиций" in vk.sent[-2]["message"]
    assert "1 517 400 ₽" in vk.sent[-1]["message"]
    assert len(db.positions()) == 2
    assert all(position.isin != "STALE" for position in db.positions())


def test_dialog_history_roundtrip(db: Database) -> None:
    handlers, _ = _owner_handlers(db)
    handlers._save_dialog(ADMIN_ID, "вопрос", "ответ")
    history = handlers._load_dialog(ADMIN_ID)
    assert history[-2]["role"] == "user"
    assert history[-1]["role"] == "assistant"
    asyncio.run(handlers._clear_dialog(ADMIN_ID))
    assert handlers._load_dialog(ADMIN_ID) == []


def test_screen_coupon_filter(db: Database) -> None:
    handlers, vk = _owner_handlers(db)
    db.kv_set(
        CACHE_KEY,
        KeyRateSnapshot(
            value_pct=14.0,
            as_of=date(2026, 10, 30),
            fetched_at=utcnow(),
        ).to_json(),
    )
    db.upsert_bonds(
        [
            Bond(
                isin="FIX2",
                name="Постоянный купон 2",
                ytm_pct=18.0,
                duration_years=1.0,
                rating="AAA",
                price_pct=100.0,
                volume_mn_rub=100.0,
                coupon_type="fixed",
                coupon_freq=2.0,
            )
        ]
    )
    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": ADMIN_ID,
                        "text": "/screen постоянный 2",
                    }
                },
            }
        )
    )
    message = vk.sent[-1]["message"]
    assert "купон постоянный" in message
    assert "выплат в год: 2" in message
    assert "FIX2" in message


def test_keyboard_mention_prefix_is_parsed(db: Database) -> None:
    handlers, vk = _owner_handlers(db)
    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": ADMIN_ID,
                        "text": "[club242762834|@club242762834] /help",
                    }
                },
            }
        )
    )
    assert "Platon Bond Bot" in vk.sent[-1]["message"]
    assert vk.sent[-1].get("keyboard") is not None


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


def test_smart_commands_reply(db: Database) -> None:
    handlers, vk = _owner_handlers(db)
    db.kv_set(
        CACHE_KEY,
        KeyRateSnapshot(
            value_pct=14.0,
            as_of=date(2026, 10, 30),
            fetched_at=utcnow(),
        ).to_json(),
    )
    cases = {
        "/value RU000A10G1T5": "📐",
        "/risk": "Риск",
        "/risk RU000A10G1T5": "Риск",
        "/stress 100": "Стресс-тест",
        "/news": "За последние",
        "/new": "Новых выпусков",
        "/journal": "Журнал идей",
        "/strategy": "Стратегия",
        "/idea": "Идеи в коридоре",
        "/relative": "Relative value",
        "/doctor": "Портфель",
        "/whatsnew": "Что изменилось",
        "/keyboard": "Кнопки",
        "/position list": "Бумажный портфель",
        "/ask": "Напиши вопрос",
    }
    for command, header in cases.items():
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
        assert header in vk.sent[-1]["message"], command

    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": ADMIN_ID,
                        "text": "/position add RU000A10G1T5 1 99",
                    }
                },
            }
        )
    )
    assert "Позиция добавлена" in vk.sent[-1]["message"]
    db.upsert_bonds(
        [
            Bond(
                isin="BALT1",
                name="БалтЛизП15",
                ytm_pct=20.0,
                duration_years=1.5,
                rating="A+",
                price_pct=99.0,
                volume_mn_rub=50.0,
            )
        ]
    )
    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": ADMIN_ID,
                        "text": "/issuer Балтийский лизинг",
                    }
                },
            }
        )
    )
    assert "обзор эмитента" in vk.sent[-1]["message"]
    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": ADMIN_ID,
                        "text": "/calendar 90",
                    }
                },
            }
        )
    )
    assert "Календарь" in vk.sent[-1]["message"] or "Событий" in vk.sent[-1]["message"]
    asyncio.run(
        handlers.handle_update(
            {
                "type": "message_new",
                "object": {
                    "message": {
                        "peer_id": CHAT_PEER,
                        "from_id": ADMIN_ID,
                        "text": "/position remove RU000A10G1T5",
                    }
                },
            }
        )
    )
    assert "удалена" in vk.sent[-1]["message"]
