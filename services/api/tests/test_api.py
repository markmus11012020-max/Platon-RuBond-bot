from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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
    assert payload["allocation"][0]["share_pct"] > 0
    assert payload["events"]


def test_bond_chat_and_confirm() -> None:
    response = client.post(
        "/api/bots/bond/chat",
        json={"message": "Предложи замену", "history": []},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"]
    action_id = payload["action"]["id"]
    assert payload["action"]["status"] == "proposed"

    confirmed = client.post(f"/api/bots/bond/actions/{action_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["audit_id"].startswith("PRE-")


def test_unknown_action_returns_404() -> None:
    response = client.post("/api/bots/bond/actions/missing/confirm")
    assert response.status_code == 404


def test_freelance_feed() -> None:
    response = client.get("/api/bots/freelance/orders")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["source"] == "demo"
    assert len(payload["orders"]) >= 3
