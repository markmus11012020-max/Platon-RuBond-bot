from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date

import pytest

from bondbot.brokers.base import (
    BrokerAccount,
    BrokerPortfolio,
    BrokerPosition,
    BrokerUnsupportedError,
)
from bondbot.brokers.tinvest import (
    money,
    parse_accounts,
    parse_portfolio,
    quotation,
)
from bondbot.config import load_settings
from bondbot.db import Database
from bondbot.models import Bond, PortfolioPosition
from bondbot.services.broker_sync import sync_broker


def _settings():
    return replace(load_settings(), tinvest_token="test-token", tinvest_account_id="")


def test_quotation_and_money() -> None:
    assert quotation({"units": "12", "nano": 500_000_000}) == 12.5
    assert quotation({"units": -3, "nano": -250_000_000}) == -3.25
    assert quotation("7.5") == 7.5
    assert quotation(None) is None
    assert money({"units": 1000, "nano": 0, "currency": "rub"}) == 1000.0


def test_bond_info_normalizes_tinvest_response() -> None:
    from bondbot.brokers.tinvest import TInvestClient

    class FakeClient(TInvestClient):
        async def _post(self, method: str, payload: dict[str, object]):
            assert method == "InstrumentsService/BondBy"
            assert payload == {
                "idType": "INSTRUMENT_ID_TYPE_UID",
                "id": "UID1",
            }
            return {
                "instrument": {
                    "isin": "ru000test0001",
                    "name": "Test Bond",
                    "nominal": {"units": "1000", "nano": 0},
                    "couponQuantityPerYear": 12,
                    "floatingCouponFlag": False,
                    "amortizationFlag": True,
                    "maturityDate": "2027-06-01T00:00:00Z",
                }
            }

    info = asyncio.run(FakeClient(_settings())._bond_info("FIGI1", "UID1"))
    assert info["isin"] == "RU000TEST0001"
    assert info["nominal"] == 1000.0
    assert info["coupon_freq"] == 12
    assert info["floating"] is False
    assert info["amortized"] is True


def test_parse_accounts() -> None:
    accounts = parse_accounts(
        {
            "accounts": [
                {
                    "id": "ACC1",
                    "name": "Брокерский счёт",
                    "type": "ACCOUNT_TYPE_TINKOFF",
                    "status": "ACCOUNT_STATUS_OPEN",
                    "openedDate": "2024-05-01T10:00:00Z",
                },
                {"id": "", "name": "skip"},
            ]
        }
    )
    assert len(accounts) == 1
    assert accounts[0].id == "ACC1"
    assert accounts[0].opened_date == date(2024, 5, 1)


def test_parse_portfolio_keeps_only_bonds() -> None:
    payload = {
        "accountId": "ACC1",
        "totalAmountBonds": {"units": "15000", "nano": 0},
        "positions": [
            {
                "figi": "FIGI1",
                "instrumentUid": "UID1",
                "instrumentType": "bond",
                "quantity": {"units": "10", "nano": 0},
                "averagePositionPrice": {"units": "990", "nano": 0, "currency": "rub"},
                "currentPrice": {"units": "1000", "nano": 0, "currency": "rub"},
                "currentNkd": {"units": "10", "nano": 0, "currency": "rub"},
            },
            {
                "figi": "FIGI2",
                "instrumentUid": "UID2",
                "instrumentType": "currency",
                "quantity": {"units": "100", "nano": 0},
            },
        ],
    }
    infos = {
        "UID1": {
            "isin": "RU000TEST0001",
            "name": "Test Bond",
            "nominal": 1000.0,
            "coupon_freq": 12,
            "floating": False,
            "amortized": True,
            "maturity_date": "2027-06-01",
        }
    }
    portfolio = parse_portfolio(payload, infos)

    assert portfolio.total_value_rub == 15000
    assert len(portfolio.positions) == 1
    position = portfolio.positions[0]
    assert position.isin == "RU000TEST0001"
    assert position.name == "Test Bond"
    assert position.quantity == 10
    assert position.average_price_rub == 990
    assert position.current_price_rub == 1000
    assert position.current_nkd_rub == 10
    assert position.current_value_rub == 10_100
    assert position.face_value == 1000
    assert position.coupon_freq == 12
    assert position.coupon_type == "fixed"
    assert position.amortized is True
    assert position.maturity_date == date(2027, 6, 1)


def test_sync_broker_replaces_positions_and_enriches_new_bonds(
    tmp_path,
    monkeypatch,
) -> None:
    db = Database(str(tmp_path / "broker.db"))
    db.upsert_bonds(
        [
            Bond(
                isin="RU000TEST0001",
                name="Test Bond",
                face_value=1000,
                coupon_rub=35,
                coupon_freq=12,
                rating="A+",
                ytm_pct=20.0,
                maturity_date=date(2027, 6, 1),
            )
        ]
    )
    db.upsert_positions(
        [
            PortfolioPosition(
                isin="RU000OLD00001",
                name="Old Bond",
                qty=1,
                current_value_rub=1000,
            )
        ]
    )

    class FakeClient:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def accounts(self):
            return [
                BrokerAccount(
                    id="ACC1",
                    name="Основной",
                    type="ACCOUNT_TYPE_TINKOFF",
                    status="ACCOUNT_STATUS_OPEN",
                )
            ]

        async def portfolio(self, account_id: str):
            return BrokerPortfolio(
                account=BrokerAccount(
                    id=account_id,
                    name="Основной",
                    type="ACCOUNT_TYPE_TINKOFF",
                    status="ACCOUNT_STATUS_OPEN",
                ),
                positions=(
                    BrokerPosition(
                        figi="FIGI1",
                        isin="RU000TEST0001",
                        name="Test Bond",
                        instrument_type="bond",
                        quantity=10,
                        average_price_rub=990,
                        current_price_rub=1000,
                        current_nkd_rub=10,
                        current_value_rub=10_100,
                        face_value=1000,
                        coupon_freq=12,
                        coupon_type="fixed",
                        maturity_date=date(2027, 6, 1),
                    ),
                    BrokerPosition(
                        figi="FIGI2",
                        isin="RU000NEW00002",
                        name="New Bond",
                        instrument_type="bond",
                        quantity=5,
                        average_price_rub=1000,
                        current_price_rub=1010,
                        current_nkd_rub=0,
                        current_value_rub=5050,
                        face_value=1000,
                        coupon_freq=4,
                        coupon_type="fixed",
                        maturity_date=date(2028, 1, 15),
                    ),
                ),
                total_value_rub=15_150,
            )

        async def close(self) -> None:
            return None

    class FakeSmartLab:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def fetch_detail(self, isin: str):
            return None, []

    monkeypatch.setattr("bondbot.services.broker_sync.TInvestClient", FakeClient)
    monkeypatch.setattr("bondbot.services.broker_sync.SmartLabClient", FakeSmartLab)

    try:
        result = asyncio.run(sync_broker(_settings(), db))
        assert result.positions == 2
        assert result.account_id == "ACC1"
        assert result.warnings == ()

        positions = {position.isin: position for position in db.positions()}
        assert set(positions) == {"RU000TEST0001", "RU000NEW00002"}
        old = positions["RU000TEST0001"]
        assert old.buy_price_pct == 99.0
        assert old.current_price_pct == 100.0
        assert old.annual_coupon_rub == pytest.approx(4200.0)
        assert old.current_value_rub == 10_100
        assert old.source_url == "broker:tinvest"

        new = positions["RU000NEW00002"]
        assert new.name == "New Bond"
        assert new.current_price_pct == 101.0
        assert new.annual_coupon_rub is None

        new_bond = db.get_bond("RU000NEW00002")
        assert new_bond is not None
        assert new_bond.name == "New Bond"
        assert new_bond.maturity_date == date(2028, 1, 15)
        assert db.kv_get("portfolio_snapshot")
        assert {row["isin"] for row in db.watchlist()} >= {
            "RU000TEST0001",
            "RU000NEW00002",
        }
    finally:
        db.close()


def test_sync_sber_reports_missing_public_api(tmp_path) -> None:
    db = Database(str(tmp_path / "sber.db"))
    try:
        with pytest.raises(BrokerUnsupportedError, match="публичного API"):
            asyncio.run(sync_broker(_settings(), db, "sber"))
    finally:
        db.close()


def test_sync_keeps_portfolio_when_bond_has_no_isin(tmp_path, monkeypatch) -> None:
    db = Database(str(tmp_path / "no-isin.db"))
    db.upsert_positions(
        [
            PortfolioPosition(
                isin="RU000OLD00001",
                name="Old Bond",
                qty=1,
                current_value_rub=1000,
            )
        ]
    )

    class FakeClient:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def accounts(self):
            return [
                BrokerAccount(
                    id="ACC1",
                    name="Основной",
                    type="ACCOUNT_TYPE_TINKOFF",
                    status="ACCOUNT_STATUS_OPEN",
                )
            ]

        async def portfolio(self, account_id: str):
            return BrokerPortfolio(
                account=BrokerAccount(
                    id=account_id,
                    name="Основной",
                    type="ACCOUNT_TYPE_TINKOFF",
                    status="ACCOUNT_STATUS_OPEN",
                ),
                positions=(
                    BrokerPosition(
                        figi="FIGI1",
                        isin=None,
                        name="Unknown Bond",
                        instrument_type="bond",
                        quantity=1,
                        current_price_rub=1000,
                        current_value_rub=1000,
                    ),
                ),
            )

        async def close(self) -> None:
            return None

    monkeypatch.setattr("bondbot.services.broker_sync.TInvestClient", FakeClient)
    try:
        result = asyncio.run(sync_broker(_settings(), db))
        assert result.positions == 0
        assert "состав портфеля не изменён" in " ".join(result.warnings)
        assert [position.isin for position in db.positions()] == ["RU000OLD00001"]
    finally:
        db.close()
