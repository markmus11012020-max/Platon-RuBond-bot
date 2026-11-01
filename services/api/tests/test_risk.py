from __future__ import annotations

import asyncio
from datetime import date

from app.config import Settings
from app.risk.moex import MarketSnapshot
from app.risk.repository import RiskRepository
from app.services.fundamentals_csv import parse_fundamentals_csv, template_csv
from app.services.risk_service import evaluate_candidate


def _candidate() -> dict:
    return {
        "isin": "RU000A10G1T5",
        "name": "Аэрофьюэл 2Р4",
        "issuer": "Аэрофьюэл",
        "ytm_pct": 17.4,
        "duration_years": 0.86,
        "rating": "AA-",
    }


async def _good_snapshot(isin: str, days: int = 45) -> MarketSnapshot:
    return MarketSnapshot(
        isin=isin,
        last_price_pct=100.0,
        last_value_rub=30_000_000,
        drawdown_7d_pct=0.2,
        drawdown_30d_pct=1.0,
        volume_ratio_30d=1.4,
        bid_pct=99.9,
        offer_pct=100.1,
        spread_pct=0.2,
        available_buy_rub=5_000_000,
        available_sell_rub=5_000_000,
        data_date=date.today().isoformat(),
        history_points=20,
    )


def test_risk_gate_blocks_drawdown_and_spread(tmp_path, monkeypatch) -> None:
    repo = RiskRepository(str(tmp_path / "risk.db"))
    settings = Settings(
        demo_mode=True,
        risk_db_path=str(tmp_path / "risk.db"),
        bond_db_path=str(tmp_path / "missing-news.db"),
    )

    async def bad_snapshot(isin: str, days: int = 45) -> MarketSnapshot:
        return MarketSnapshot(
            isin=isin,
            last_price_pct=80.0,
            last_value_rub=1_000_000,
            drawdown_7d_pct=-12.0,
            drawdown_30d_pct=-20.0,
            volume_ratio_30d=0.1,
            bid_pct=95.0,
            offer_pct=100.0,
            spread_pct=5.3,
            available_buy_rub=10_000,
            available_sell_rub=10_000,
            data_date=date.today().isoformat(),
            history_points=20,
        )

    monkeypatch.setattr("app.services.risk_service.fetch_snapshot", bad_snapshot)
    assessment = asyncio.run(evaluate_candidate(settings, repo, _candidate()))
    names = {item["name"]: item["status"] for item in assessment.checks}
    assert assessment.status == "blocked"
    assert names["drawdown_7d"] == "fail"
    assert names["drawdown_30d"] == "fail"
    assert names["spread"] == "warn"


def test_risk_gate_allows_after_credit_check(tmp_path, monkeypatch) -> None:
    import sqlite3

    news_db = tmp_path / "news.db"
    connection = sqlite3.connect(news_db)
    connection.execute(
        "CREATE TABLE news (source TEXT, title TEXT, url TEXT, published_at TEXT, summary TEXT)"
    )
    connection.commit()
    connection.close()

    repo = RiskRepository(str(tmp_path / "risk-ok.db"))
    repo.set_credit_check(
        "RU000A10G1T5",
        status="passed",
        source="manual review",
    )
    settings = Settings(
        demo_mode=True,
        risk_db_path=str(tmp_path / "risk-ok.db"),
        bond_db_path=str(news_db),
    )
    monkeypatch.setattr("app.services.risk_service.fetch_snapshot", _good_snapshot)
    assessment = asyncio.run(evaluate_candidate(settings, repo, _candidate()))
    assert assessment.status == "ok"


def test_fundamentals_roundtrip(tmp_path) -> None:
    repo = RiskRepository(str(tmp_path / "fundamentals.db"))
    repo.upsert_fundamentals(
        isin="RU000A10G1T5",
        issuer="Аэрофьюэлз",
        period="2025FY",
        revenue_rub=12_500_000_000,
        net_profit_rub=1_200_000_000,
        ebitda_rub=2_100_000_000,
        net_debt_rub=3_400_000_000,
        equity_rub=5_000_000_000,
        current_ratio=1.4,
        source="manual/report",
    )
    items = repo.fundamentals_for(isin="RU000A10G1T5")
    assert len(items) == 1
    assert items[0]["revenue_rub"] == 12_500_000_000
    assert items[0]["period"] == "2025FY"
    assert items[0]["source"] == "manual/report"


def test_fundamentals_csv_parser() -> None:
    raw = (
        "isin;issuer;period;revenue_rub;net_profit_rub;ebitda_rub;"
        "net_debt_rub;equity_rub;current_ratio;source\n"
        "RU000A10E4Y1;Аэрофьюэлз;2025FY;12 500 000 000;1 200 000 000;"
        "2 100 000 000;3 400 000 000;5 000 000 000;1,4;e-disclosure\n"
        "BAD;Без периода;;;;;;;manual\n"
    ).encode("utf-8")
    parsed = parse_fundamentals_csv(raw)
    assert len(parsed.rows) == 2
    assert parsed.rows[0].error == ""
    assert parsed.rows[0].data["revenue_rub"] == 12_500_000_000
    assert parsed.rows[0].data["current_ratio"] == 1.4
    assert "нужны period и source" in parsed.rows[1].error


def test_fundamentals_csv_template() -> None:
    assert "revenue_rub" in template_csv()
    assert "RU000A10E4Y1" in template_csv()
