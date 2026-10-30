from __future__ import annotations

from pathlib import Path

from bondbot.db import Database
from bondbot.importers.smartlab_portfolio import import_portfolio_file, parse_portfolio_html

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_portfolio_html() -> None:
    html = (FIXTURES / "portfolio_synthetic.html").read_text(encoding="utf-8")
    positions = parse_portfolio_html(html, source_url="portfolio_synthetic.html")
    assert len(positions) == 2
    first = positions[0]
    assert first.isin == "RU000TEST0001"
    assert first.qty == 500
    assert first.buy_price_pct == 99.99
    assert first.current_price_pct == 99.52
    assert first.current_value_rub == 497_600
    assert first.profit_rub == -2_350
    assert first.annual_coupon_rub == 118_380
    assert first.ytm_pct == 18.5
    assert first.rating == "BBB"

    assert sum(item.current_value_rub or 0 for item in positions) == 1_517_400
    assert sum(item.profit_rub or 0 for item in positions) == 1_450
    assert sum(item.annual_coupon_rub or 0 for item in positions) == 305_820


def test_import_portfolio(tmp_path) -> None:
    db = Database(str(tmp_path / "portfolio.db"))
    try:
        positions = import_portfolio_file(db, FIXTURES / "portfolio_synthetic.html")
        assert len(positions) == 2
        assert len(db.positions()) == 2
        totals = db.portfolio_totals()
        assert totals["total_value_rub"] == 1_517_400
        assert totals["profit_rub"] == 1_450
        assert totals["annual_coupon_rub"] == 305_820
    finally:
        db.close()
