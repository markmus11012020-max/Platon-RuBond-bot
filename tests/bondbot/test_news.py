from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from bondbot.config import load_settings
from bondbot.db import Database
from bondbot.models import Bond, PortfolioPosition, utcnow
from bondbot.services.news import (
    build_news_digest,
    configured_feeds,
    enrich_news,
    parse_feed,
)

def _rss() -> str:
    first = datetime.now(timezone.utc) - timedelta(hours=2)
    second = datetime.now(timezone.utc) - timedelta(hours=1)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Test</title>
<item>
  <title>Тестовая облигация: ЦБ сохранил ставку</title>
  <link>https://example.com/news/1</link>
  <pubDate>{first:%a, %d %b %Y %H:%M:%S +0000}</pubDate>
  <description>Ключевая ставка сохранена. Рынок облигаций реагирует.</description>
</item>
<item>
  <title>Погода в Москве</title>
  <link>https://example.com/news/2</link>
  <pubDate>{second:%a, %d %b %Y %H:%M:%S +0000}</pubDate>
  <description>Без экономических новостей.</description>
</item>
</channel></rss>
"""


def test_parse_and_enrich_feed() -> None:
    items = parse_feed(_rss(), "Test")
    assert len(items) == 2
    assert items[0]["source"] == "Test"
    assert items[0]["url"] == "https://example.com/news/1"
    assert items[0]["published_at"]
    bond = Bond(isin="RU000TEST", name="Тестовая облигация", fetched_at=utcnow())
    enriched = enrich_news(items, [bond], {"RU000TEST"}, set())
    assert enriched[0]["entities"] == ["RU000TEST"]
    assert enriched[0]["relevance"] == 3
    assert enriched[1]["relevance"] == 0


def test_configured_feeds_default_and_override() -> None:
    settings = replace(load_settings(), news_feeds="")
    assert len(configured_feeds(settings)) >= 5
    settings = replace(
        load_settings(),
        news_feeds="Custom=https://example.com/rss.xml",
    )
    assert configured_feeds(settings) == {"Custom": "https://example.com/rss.xml"}


def test_news_storage_and_digest(tmp_path) -> None:
    db = Database(str(tmp_path / "news.db"))
    settings = replace(load_settings(), news_hours=24)
    try:
        db.upsert_bonds(
            [Bond(isin="RU000TEST", name="Тестовая облигация", fetched_at=utcnow())]
        )
        db.upsert_positions(
            [
                PortfolioPosition(
                    isin="RU000TEST",
                    name="Тестовая облигация",
                    qty=1,
                    current_value_rub=1000.0,
                )
            ]
        )
        items = enrich_news(
            parse_feed(_rss(), "Test"),
            db.list_bonds(),
            {"RU000TEST"},
            set(),
        )
        assert db.save_news(items) == 2
        assert db.save_news(items) == 0
        assert db.news_count() == 2
        db.save_news(
            [
                {
                    "source": "Test",
                    "title": "Техдефолт МГКЛ: что известно",
                    "url": "https://example.com/news/3",
                    "published_at": utcnow().isoformat(),
                    "summary": "Эмитент допустил технический дефолт.",
                    "hash": "tech-default-1",
                }
            ]
        )
        found = db.search_news("Техдефолт МГКЛ")
        assert found
        assert "МГКЛ" in found[0]["title"]
        digest = build_news_digest(settings, db, limit=1)
        assert "ЦБ сохранил ставку" in digest
        assert "портфель" in digest
        assert "https://example.com/news/1" in digest
    finally:
        db.close()
