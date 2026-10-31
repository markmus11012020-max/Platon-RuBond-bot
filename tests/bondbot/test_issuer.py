from __future__ import annotations

import asyncio
from dataclasses import replace

from bondbot.config import load_settings
from bondbot.db import Database
from bondbot.models import Bond, utcnow
from bondbot.services.issuer import enrich_issuer_payload, issuer_payload, render_issuer


def _bond(isin: str, name: str, ytm: float = 20.0, **kwargs) -> Bond:
    base = dict(
        isin=isin,
        name=name,
        ytm_pct=ytm,
        duration_years=1.5,
        rating="A+",
        price_pct=99.0,
        volume_mn_rub=50.0,
        fetched_at=utcnow(),
    )
    base.update(kwargs)
    return Bond(**base)


def test_search_bonds_by_issuer_alias(tmp_path) -> None:
    db = Database(str(tmp_path / "issuer.db"))
    try:
        db.upsert_bonds(
            [
                _bond("BALT1", "БалтЛизП15"),
                _bond("LEAS1", "МКЛизинг1"),
                _bond("MGKL1", "МГКЛ 1P7", ytm=30.0),
            ]
        )
        found = db.search_bonds_by_name("Балтийский лизинг")
        assert [bond.isin for bond in found] == ["BALT1"]
        assert db.search_bonds_by_name("МГКЛ")[0].isin == "MGKL1"
    finally:
        db.close()


def test_issuer_payload_and_render(tmp_path) -> None:
    db = Database(str(tmp_path / "issuer2.db"))
    try:
        db.upsert_bonds([_bond("BALT1", "БалтЛизП15")])
        db.save_news(
            [
                {
                    "source": "Ведомости",
                    "title": "БалтЛиз: что известно",
                    "url": "https://example.com/balt",
                    "published_at": utcnow().isoformat(),
                    "summary": "Лизинговая компания в фокусе.",
                    "hash": "balt-news",
                }
            ]
        )
        payload = issuer_payload(db, "Балтийский лизинг", key_rate_pct=14.0)
        assert payload["bonds"][0]["isin"] == "BALT1"
        assert payload["news"]
        text = render_issuer(payload)
        assert "обзор эмитента" in text
        assert "БалтЛизП15" in text
        assert "БалтЛиз: что известно" in text
    finally:
        db.close()


def test_enrich_issuer_payload_adds_live_results(tmp_path, monkeypatch) -> None:
    db = Database(str(tmp_path / "issuer3.db"))
    settings = replace(load_settings(), live_search_enabled=True)
    try:
        db.upsert_bonds([_bond("BALT1", "БалтЛизП15")])
        payload = issuer_payload(db, "Балтийский лизинг", key_rate_pct=14.0)
        assert not payload["news"]

        async def fake_search(*args, **kwargs):
            return [
                {
                    "source": "smart-lab",
                    "title": "БалтЛиз: обзор",
                    "url": "https://smart-lab.ru/blog/1.php",
                    "snippet": "Свежий материал",
                    "published_at": None,
                    "live": True,
                }
            ]

        monkeypatch.setattr("bondbot.services.issuer.live_search", fake_search)
        enriched = asyncio.run(
            enrich_issuer_payload(settings, db, payload, "Балтийский лизинг")
        )
        assert enriched["live_search"] is True
        assert enriched["news"][0]["source"] == "smart-lab"
        assert "живой поиск" in render_issuer(enriched)
    finally:
        db.close()
