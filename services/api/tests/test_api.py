from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.risk.moex import MarketSnapshot
from app.services.bond_lookup import BondLookup

client = TestClient(app)


@pytest.fixture(autouse=True)
def fake_market(monkeypatch):
    async def snapshot(isin: str, days: int = 45) -> MarketSnapshot:
        return MarketSnapshot(
            isin=isin,
            last_price_pct=100.0,
            last_value_rub=25_000_000,
            drawdown_7d_pct=0.0,
            drawdown_30d_pct=0.0,
            volume_ratio_30d=1.0,
            bid_pct=99.9,
            offer_pct=100.1,
            spread_pct=0.2,
            available_buy_rub=2_000_000,
            available_sell_rub=2_000_000,
            data_date=date.today().isoformat(),
            quote_time="10:00:00",
            history_points=20,
        )

    monkeypatch.setattr("app.services.risk_service.fetch_snapshot", snapshot)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["demo_mode"] is True


def test_bots_list() -> None:
    response = client.get("/api/bots")
    assert response.status_code == 200
    payload = response.json()
    assert {item["id"] for item in payload} == {"bond", "freelance"}


def test_bond_overview() -> None:
    response = client.get("/api/bots/bond/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_value_rub"] == 5_768_810
    assert len(payload["positions"]) == 6
    assert len(payload["allocation"]) == 6
    assert payload["candidates"] == []
    assert len(payload["excluded"]) == 3
    assert {item["name"] for item in payload["excluded"]} >= {
        "МГКЛ 2Р9",
        "БалтЛизП12",
    }
    assert payload["events"]


def test_bond_chat_and_confirm() -> None:
    response = client.post(
        "/api/bots/bond/chat",
        json={"message": "Предложи замену", "history": []},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"]
    assert payload["action"]["kind"] == "review"
    assert payload["action"]["legs"] == []
    assert "технический дефолт" in payload["message"].lower()
    action_id = payload["action"]["id"]
    assert payload["action"]["status"] == "proposed"

    confirmed = client.post(f"/api/bots/bond/actions/{action_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert "сделка не выставлялась" in confirmed.json()["message"].lower()
    assert confirmed.json()["audit_id"].startswith("PRE-")


def test_unknown_action_returns_404() -> None:
    response = client.post("/api/bots/bond/actions/missing/confirm")
    assert response.status_code == 404


def test_unknown_isin_without_card(monkeypatch) -> None:
    async def no_card(isin: str):
        return None

    monkeypatch.setattr("app.services.bond_service.lookup_bond", no_card)
    response = client.post(
        "/api/bots/bond/chat",
        json={"message": "Что думаешь про RU000A10E4Y1?", "history": []},
    )
    assert response.status_code == 200
    message = response.json()["message"]
    assert "не нашлось" in message.lower()
    assert "Не индивидуальная инвестиционная рекомендация" in message
    assert len(message) < 500


def test_unknown_isin_lookup_card(monkeypatch) -> None:
    async def card(isin: str):
        return BondLookup(
            isin=isin,
            name="Аэрофьюэлз003Р-01",
            rating="A",
            price_pct=101.65,
            ytm_pct=20.22,
            duration_years=1.49,
            coupon_rub=49.86,
            coupon_freq=4,
            maturity_date=date(2028, 7, 21),
            bid_pct=101.55,
            offer_pct=101.64,
            spread_pct=0.09,
            available_buy_rub=500_000,
            data_date=date.today().isoformat(),
        )

    monkeypatch.setattr("app.services.bond_service.lookup_bond", card)
    response = client.post(
        "/api/bots/bond/chat",
        json={"message": "Что думаешь про RU000A10E4Y1?", "history": []},
    )
    assert response.status_code == 200
    message = response.json()["message"]
    assert "Аэрофьюэлз003Р-01" in message
    assert "Рейтинг: A" in message
    assert "Риск-проверка" in message

    followup = client.post(
        "/api/bots/bond/chat",
        json={
            "message": "эмитент и рейтинг, кредитные события за 6-12 месяцев",
            "history": [
                {"role": "user", "content": "Что думаешь про RU000A10E4Y1?"},
                {"role": "assistant", "content": message},
            ],
        },
    )
    assert followup.status_code == 200
    followup_message = followup.json()["message"]
    assert "карточка уже в диалоге" in followup_message
    assert followup_message.count("Аэрофьюэлз003Р-01") == 0


def test_premarket_briefing() -> None:
    response = client.post(
        "/api/bots/bond/chat",
        json={"message": "Утренний брифинг", "history": []},
    )
    assert response.status_code == 200
    assert "брифинг" in response.json()["message"].lower()


def test_freelance_feed() -> None:
    response = client.get("/api/bots/freelance/orders")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["source"] == "demo"
    assert len(payload["orders"]) >= 3


def test_mcp_tools_unavailable_without_token() -> None:
    response = client.get("/api/mcp/tools")
    assert response.status_code == 503


def test_risk_summary_and_candidates() -> None:
    summary = client.get("/api/risk/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["credit_events"] >= 1
    assert payload["blocklist"] >= 1
    assert payload["checks"]["total"] == 3
    assert payload["checks"]["passed"] == 0
    assert payload["checks"]["blocked"] >= 1

    candidates = client.get("/api/risk/candidates")
    assert candidates.status_code == 200
    items = {item["isin"]: item for item in candidates.json()}
    assert items["RU000A10G1Q1"]["status"] == "blocked"
    assert items["RU000A10FWC7"]["status"] == "blocked"
    assert items["RU000A10G1T5"]["status"] == "review"


def test_risk_admin_endpoints_require_token() -> None:
    response = client.post(
        "/api/risk/blocklist",
        json={
            "isin": "RU000TEST0001",
            "reason": "test",
            "source": "test",
        },
    )
    assert response.status_code == 503
