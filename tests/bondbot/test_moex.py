from __future__ import annotations

import pytest

from bondbot.data.moex import parse_moex_bonds

SECURITIES = {
    "columns": [
        "SECID",
        "BOARDID",
        "SHORTNAME",
        "PREVPRICE",
        "YIELDATPREVWAPRICE",
        "COUPONVALUE",
        "NEXTCOUPON",
        "ACCRUEDINT",
        "FACEVALUE",
        "MATDATE",
        "OFFERDATE",
        "COUPONPERIOD",
        "ISSUESIZE",
        "FACEUNIT",
        "COUPONPERCENT",
        "BONDTYPE",
        "BONDSUBTYPE",
        "COUPON_DETAILS",
    ],
    "data": [
        [
            "SEC1",
            "TQCB",
            "Test bond",
            100.5,
            18.0,
            40.0,
            "2026-12-01",
            10.0,
            1000.0,
            "2029-01-01",
            None,
            182,
            100_000,
            "SUR",
            16.0,
            "",
            "",
            "",
        ],
        [
            "USD1",
            "TQCB",
            "USD bond",
            100.0,
            5.0,
            10.0,
            None,
            0.0,
            1000.0,
            "2029-01-01",
            None,
            182,
            100_000,
            "USD",
            5.0,
            "",
            "",
            "",
        ],
    ],
}

MARKET = {
    "columns": ["SECID", "BOARDID", "LAST", "WAPRICE", "YIELD", "DURATION", "VALTODAY"],
    "data": [
        ["SEC1", "TQCB", None, 101.0, 19.5, 730, 50_000_000.0],
        ["USD1", "TQCB", 100.0, 100.0, 5.0, 365, 10_000_000.0],
    ],
}


def test_parse_moex_bonds() -> None:
    bonds = parse_moex_bonds({"securities": SECURITIES, "marketdata": MARKET})
    assert len(bonds) == 1
    bond = bonds[0]
    assert bond.isin == "SEC1"
    assert bond.name == "Test bond"
    assert bond.price_pct == pytest.approx(101.0)
    assert bond.ytm_pct == pytest.approx(19.5)
    assert bond.duration_years == pytest.approx(2.0)
    assert bond.volume_mn_rub == pytest.approx(50.0)
    assert bond.coupon_rub == pytest.approx(40.0)
    assert bond.coupon_freq == pytest.approx(2.0)
    assert bond.issue_size_rub == pytest.approx(100_000_000.0)
    assert bond.maturity_date is not None
    assert bond.next_coupon_date is not None


def test_parse_moex_skips_currency_and_bad_boards() -> None:
    payload = {
        "securities": {
            "columns": SECURITIES["columns"],
            "data": [SECURITIES["data"][1]],
        },
        "marketdata": MARKET,
    }
    assert parse_moex_bonds(payload) == []
