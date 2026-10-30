from __future__ import annotations

from pathlib import Path

from bondbot.data.smartlab import parse_detail, parse_screener

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_screener() -> None:
    html = (FIXTURES / "smartlab_screener.html").read_text(encoding="utf-8")
    bonds = parse_screener(html, source_url="https://smart-lab.ru/q/bonds/")
    assert len(bonds) >= 99
    first = bonds[0]
    assert first.isin == "RU000A10G1T5"
    assert first.name
    assert first.ytm_pct == 17.4
    assert first.rating == "AAA"
    assert first.volume_mn_rub == 341.2
    assert first.duration_years == 0.66
    assert first.next_coupon_date is not None
    assert first.maturity_date is not None
    assert first.source_url == "https://smart-lab.ru/q/bonds/"


def test_parse_detail_and_coupons() -> None:
    html = (FIXTURES / "smartlab_bond.html").read_text(encoding="utf-8")
    bond, coupons = parse_detail(html, "RU000A10G1T5")
    assert bond is not None
    assert bond.isin == "RU000A10G1T5"
    assert bond.price_pct == 99.86
    assert bond.ytm_pct == 17.45
    assert bond.rating == "AAA"
    assert bond.face_value == 1000
    assert bond.issue_size_rub == 52_200_000_000
    assert bond.qual_only is False
    assert bond.amortized is True
    assert bond.duration_years is not None and 0.6 < bond.duration_years < 0.7
    assert len(coupons) > 100
    assert coupons[0].coupon_date.isoformat() == "2026-11-26"
    assert coupons[0].value_rub == 25.42
