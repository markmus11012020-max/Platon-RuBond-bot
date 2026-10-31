from __future__ import annotations

from dataclasses import replace
from datetime import date

from bondbot.config import load_settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import Bond, PortfolioPosition, utcnow
from bondbot.services.ideas import (
    build_ideas,
    build_strategy_note,
    render_ideas,
    render_journal,
    save_ideas,
)


def test_ideas_and_journal(tmp_path) -> None:
    db = Database(str(tmp_path / "ideas.db"))
    settings = replace(load_settings())
    snapshot = KeyRateSnapshot(value_pct=14.0, as_of=date.today())
    try:
        db.upsert_bonds(
            [
                Bond(
                    isin="IDEA",
                    name="Idea Bond",
                    ytm_pct=20.0,
                    duration_years=2.0,
                    rating="AAA",
                    price_pct=100.0,
                    volume_mn_rub=100.0,
                    issue_size_rub=30_000_000_000.0,
                    g_spread_bp=200.0,
                    fetched_at=utcnow(),
                )
            ]
        )
        db.upsert_positions(
            [
                PortfolioPosition(
                    isin="IDEA",
                    name="Idea Bond",
                    qty=1,
                    current_value_rub=100_000.0,
                    annual_coupon_rub=20_000.0,
                )
            ]
        )
        ideas = build_ideas(settings, db, snapshot, limit=3)
        assert ideas
        assert ideas[0].isin == "IDEA"
        assert save_ideas(db, ideas) == 1
        assert save_ideas(db, ideas) == 0
        assert "Идеи в коридоре" in render_ideas(ideas, snapshot)
        assert "Журнал идей" in render_journal(db)
        note = build_strategy_note(settings, db, snapshot)
        assert "Стратегия" in note
        assert "Рабочий коридор" in note
    finally:
        db.close()
