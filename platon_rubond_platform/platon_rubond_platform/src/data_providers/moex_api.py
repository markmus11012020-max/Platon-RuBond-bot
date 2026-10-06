"""
Класс MoexParser — сбор данных по API Московской Биржи (ISS MOEX).
Получение спецификации облигации, рыночных данных и календаря купонов.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from src.data_providers.base_parser import BaseParser
from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.moex")

# Официальные эндпоинты ISS MOEX
BASE_ISS = "https://iss.moex.com/iss"
TIMEOUT = 20


class MoexParser(BaseParser):
    """
    Парсер данных облигаций с Московской Биржи.
    Наследуется от BaseParser и реализует fetch_data / parse_data.
    """

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "Platon-RuBond-bot/1.0 (research; contact@local)",
                "Accept": "application/json",
            }
        )

    def fetch_data(self, secid: str = "") -> Dict[str, Any]:  # type: ignore[override]
        """
        Выполняет GET-запросы к ISS MOEX API.

        Эндпоинты:
          - /securities/{secid}.json — описание инструмента
          - /engines/stock/markets/bonds/securities/{secid}.json — рыночные данные
          - /securities/{secid}/bondcoupons.json — календарь купонов

        Возвращает словарь с сырыми JSON-ответами или пустой dict при ошибке.
        """
        if not secid or not isinstance(secid, str):
            logger.warning("MoexParser.fetch_data: пустой или некорректный secid")
            return {}

        secid = secid.strip().upper()
        result: Dict[str, Any] = {
            "secid": secid,
            "description": None,
            "market": None,
            "coupons": None,
        }

        endpoints = {
            "description": f"{BASE_ISS}/securities/{secid}.json?iss.meta=off",
            "market": (
                f"{BASE_ISS}/engines/stock/markets/bonds/securities/{secid}.json"
                "?iss.meta=off"
            ),
            "coupons": f"{BASE_ISS}/securities/{secid}/bondcoupons.json?iss.meta=off",
        }

        for key, url in endpoints.items():
            try:
                resp = self._session.get(url, timeout=TIMEOUT)
                if resp.status_code >= 400:
                    logger.warning(
                        "MOEX %s [%s]: HTTP %s — %s",
                        key,
                        secid,
                        resp.status_code,
                        url,
                    )
                    continue
                result[key] = resp.json()
            except requests.exceptions.Timeout:
                logger.warning("MOEX %s [%s]: таймаут запроса (%s с)", key, secid, TIMEOUT)
            except requests.exceptions.ConnectionError as exc:
                logger.warning("MOEX %s [%s]: ошибка сети — %s", key, secid, exc)
            except requests.exceptions.RequestException as exc:
                logger.warning("MOEX %s [%s]: ошибка запроса — %s", key, secid, exc)
            except ValueError as exc:
                logger.warning("MOEX %s [%s]: некорректный JSON — %s", key, secid, exc)

        return result

    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        Преобразует сырой JSON в структурированный словарь облигации.

        Возвращаемые поля:
          isin, shortname, maturity_date, offer_date, face_value,
          current_price, coupon_period, coupon_type, nearest_coupon_value
        """
        if not raw_data or not isinstance(raw_data, dict):
            logger.warning("MoexParser.parse_data: пустые или некорректные данные")
            return []

        try:
            desc_map = self._extract_description(raw_data.get("description"))
            market_sec, market_md = self._extract_market(raw_data.get("market"))
            nearest_coupon = self._extract_nearest_coupon(raw_data.get("coupons"))

            isin = (
                desc_map.get("ISIN")
                or market_sec.get("ISIN")
                or raw_data.get("secid")
                or ""
            )
            shortname = (
                desc_map.get("SHORTNAME")
                or market_sec.get("SHORTNAME")
                or desc_map.get("NAME")
                or ""
            )
            maturity = (
                desc_map.get("MATDATE")
                or market_sec.get("MATDATE")
                or ""
            )
            offer_date = (
                market_sec.get("OFFERDATE")
                or desc_map.get("OFFERDATE")
                or market_sec.get("BUYBACKDATE")
                or desc_map.get("BUYBACKDATE")
                or None
            )
            # Фильтруем «пустые» даты
            if offer_date in ("0000-00-00", "", None):
                offer_date = None

            face_value = self._to_float(
                market_sec.get("FACEVALUE")
                or desc_map.get("FACEVALUE")
                or desc_map.get("INITIALFACEVALUE")
                or 1000.0
            )
            current_price = self._to_float(
                market_md.get("LAST")
                or market_md.get("LCURRENTPRICE")
                or market_sec.get("PREVPRICE")
                or market_sec.get("PREVWAPRICE")
                or market_md.get("WAPRICE")
            )
            coupon_period = self._to_int(
                market_sec.get("COUPONPERIOD")
                or desc_map.get("COUPONPERIOD")
                or 0
            )

            coupon_type = self._detect_coupon_type(desc_map, market_sec)

            nearest_coupon_value = nearest_coupon
            if nearest_coupon_value is None:
                nearest_coupon_value = self._to_float(
                    market_sec.get("COUPONVALUE")
                )

            bond: Dict[str, Any] = {
                "isin": isin,
                "secid": raw_data.get("secid") or isin,
                "shortname": shortname,
                "maturity_date": maturity,
                "offer_date": offer_date,
                "face_value": face_value,
                "current_price": current_price,
                "coupon_period": coupon_period,
                "coupon_type": coupon_type,
                "nearest_coupon_value": nearest_coupon_value,
            }
            return [bond]
        except Exception as exc:
            logger.exception("MoexParser.parse_data: ошибка разбора — %s", exc)
            return []

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    @staticmethod
    def _table_to_dicts(block: Optional[Dict]) -> List[Dict[str, Any]]:
        """Преобразует блок ISS (columns + data) в список словарей."""
        if not block or "columns" not in block or "data" not in block:
            return []
        cols = block["columns"]
        return [dict(zip(cols, row)) for row in block["data"]]

    def _extract_description(self, desc_json: Optional[Dict]) -> Dict[str, str]:
        """Описание инструмента: name → value."""
        if not desc_json:
            return {}
        rows = self._table_to_dicts(desc_json.get("description"))
        result: Dict[str, str] = {}
        for row in rows:
            name = row.get("name") or row.get("NAME")
            value = row.get("value") or row.get("VALUE")
            if name is not None:
                result[str(name).upper()] = value
        return result

    def _extract_market(
        self, market_json: Optional[Dict]
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Рыночные данные: securities + marketdata."""
        if not market_json:
            return {}, {}
        secs = self._table_to_dicts(market_json.get("securities"))
        mds = self._table_to_dicts(market_json.get("marketdata"))
        sec = secs[0] if secs else {}
        md = mds[0] if mds else {}
        return sec, md

    def _extract_nearest_coupon(self, coupons_json: Optional[Dict]) -> Optional[float]:
        """Берёт ближайший будущий (или последний известный) купон в рублях."""
        if not coupons_json:
            return None
        # Возможные имена блоков
        for key in ("coupons", "bondcoupons", "coupon"):
            rows = self._table_to_dicts(coupons_json.get(key))
            if rows:
                break
        else:
            rows = []

        if not rows:
            return None

        # Ищем запись с value / couponvalue
        for row in rows:
            val = (
                row.get("value")
                or row.get("VALUE")
                or row.get("couponvalue")
                or row.get("COUPONVALUE")
            )
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _detect_coupon_type(
        desc: Dict[str, str], market_sec: Dict[str, Any]
    ) -> str:
        """Определяет тип купона: постоянный / флоатер / переменный."""
        candidates = [
            desc.get("COUPONTYPE"),
            desc.get("TYPENAME"),
            desc.get("TYPE"),
            market_sec.get("BONDTYPE"),
            market_sec.get("BONDSUBTYPE"),
            str(desc.get("NAME", "")),
            str(desc.get("SECNAME", "")),
        ]
        text = " ".join(str(c) for c in candidates if c).lower()

        floater_markers = (
            "флoатер",
            "флоатер",
            "float",
            "переменн",
            "floating",
            "ключ",
            "ruonia",
            "ключевой",
            "пересм",
        )
        if any(m in text for m in floater_markers):
            return "флоатер"
        return "постоянный"

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: Any) -> int:
        if value is None or value == "":
            return 0
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
