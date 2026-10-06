"""Unit-тесты MacroParser (улучшение 7)."""

from __future__ import annotations

from src.data_providers.macro_parser import MacroParser


def test_fallback_key_rate():
    mp = MacroParser(default_key_rate=0.15)
    # Без сети / при пустом HTML должен вернуть fallback
    parsed = mp.parse_data({"raw_html": "", "indicator": "key_rate"})
    assert len(parsed) == 1
    assert parsed[0]["value"] == 0.15
    assert parsed[0]["source"] == "fallback"


def test_extract_from_html():
    mp = MacroParser()
    html = """
    <html><body>
    <h1>Ключевая ставка Банка России</h1>
    <table><tr><td>16,50</td></tr></table>
    </body></html>
    """
    rate = mp._extract_key_rate_from_html(html)
    assert rate == 0.1650


def test_get_key_rate_cached():
    mp = MacroParser(default_key_rate=0.16)
    mp._cache["key_rate"] = 0.175
    assert mp.get_key_rate() == 0.175


def test_integration_floater_with_macro():
    """Связка MacroParser → BondAnalyzer.estimate_floater_yield."""
    from src.analytics.bond_math import BondAnalyzer

    mp = MacroParser(default_key_rate=0.16)
    key_rate = mp.get_key_rate()  # fallback, т.к. ЦБ может быть недоступен
    ba = BondAnalyzer()
    bond = {"spread": 0.02, "nearest_coupon_value": 50, "coupon_period": 91, "face_value": 1000}
    y = ba.estimate_floater_yield(bond, key_rate)
    assert y == round(key_rate + 0.02, 4)
