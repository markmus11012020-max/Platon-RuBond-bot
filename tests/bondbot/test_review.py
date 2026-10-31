from __future__ import annotations

from dataclasses import replace
from datetime import date

from bondbot.config import load_settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import Bond, PortfolioPosition, utcnow
from bondbot.services.review import (
    build_portfolio_review,
    build_what_changed,
    save_portfolio_snapshot,
)


def _setup(tmp_path) -> Database:
    db = Database(str(tmp_path / "review.db"))
    db.upsert_bonds(
        [
            Bond(
                isin="REV",
                name="Review Bond",
                ytm_pct=20.0,
                duration_years=2.0,
                rating="AAA",
                price_pct=100.0,
                volume_mn_rub=100.0,
                issue_size_rub=30_000_000_000.0,
                fetched_at=utcnow(),
            )
        ]
    )
    db.upsert_positions(
        [
            PortfolioPosition(
                isin="REV",
                name="Review Bond",
                qty=100,
                current_value_rub=100_000.0,
                annual_coupon_rub=20_000.0,
            )
        ]
    )
    return db


def test_what_changed_and_snapshot(tmp_path) -> None:
    db = _setup(tmp_path)
    settings = replace(load_settings())
    snapshot = KeyRateSnapshot(value_pct=14.0, as_of=date.today())
    try:
        first = build_what_changed(settings, db)
        assert "Что изменилось" in first
        save_portfolio_snapshot(settings, db)
        db.upsert_positions(
            [
                PortfolioPosition(
                    isin="REV",
                    name="Review Bond",
                    qty=100,
                    current_value_rub=110_000.0,
                    annual_coupon_rub=20_000.0,
                )
            ]
        )
        second = build_what_changed(settings, db)
        assert "100 000 ₽" in second
        assert "110 000 ₽" in second
        review = build_portfolio_review(settings, db, snapshot)
        assert "Риск-скор" in review
        assert "стресс" in review.lower()
    finally:
        db.close()
