"""
Класс MacroParser — мониторинг макроэкономических показателей РФ.

Основной источник: ключевая ставка ЦБ РФ.
Бесплатные эндпоинты без API-ключей (с fallback на кэш/значение по умолчанию).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from src.data_providers.base_parser import BaseParser
from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.macro")

TIMEOUT = 15
# Публичная страница ЦБ с ключевой ставкой
CBR_KEY_RATE_URL = "https://www.cbr.ru/hd_base/KeyRate/"
# Альтернатива: XML ежедневных показателей
CBR_DAILY_XML = "https://www.cbr.ru/scripts/XML_daily.asp"
# Fallback, если сеть недоступна (обновлять вручную при необходимости)
DEFAULT_KEY_RATE = 0.16  # 16 %


class MacroParser(BaseParser):
    """
    Парсер макропоказателей (ключевая ставка ЦБ, инфляционные ожидания и т.п.).
    """

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        default_key_rate: float = DEFAULT_KEY_RATE,
    ) -> None:
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "Platon-RuBond-bot/1.0 (research)",
                "Accept": "text/html, application/xml, */*",
            }
        )
        self.default_key_rate = default_key_rate
        self._cache: Dict[str, Any] = {}

    def fetch_data(self, indicator: str = "key_rate") -> Dict[str, Any]:  # type: ignore[override]
        """
        Получение сырых данных по макропоказателю.

        indicator:
          - "key_rate" — ключевая ставка ЦБ РФ
        """
        result: Dict[str, Any] = {
            "indicator": indicator,
            "raw_html": None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        if indicator != "key_rate":
            logger.warning("MacroParser: неизвестный indicator '%s'", indicator)
            return result

        try:
            resp = self._session.get(CBR_KEY_RATE_URL, timeout=TIMEOUT)
            if resp.status_code >= 400:
                logger.warning(
                    "MacroParser: HTTP %s при запросе ключевой ставки",
                    resp.status_code,
                )
                return result
            result["raw_html"] = resp.text
            logger.info("MacroParser: страница ключевой ставки получена (%d байт)", len(resp.text))
        except requests.exceptions.Timeout:
            logger.warning("MacroParser: таймаут при запросе ЦБ")
        except requests.exceptions.ConnectionError as exc:
            logger.warning("MacroParser: ошибка сети — %s", exc)
        except requests.exceptions.RequestException as exc:
            logger.warning("MacroParser: ошибка запроса — %s", exc)

        return result

    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        Извлекает ключевую ставку из HTML/сырых данных ЦБ.

        Returns
        -------
        list[dict]
            [{"indicator": "key_rate", "value": 0.16, "unit": "share",
              "as_of": "YYYY-MM-DD", "source": "cbr"}]
        """
        if not raw_data or not isinstance(raw_data, dict):
            return [self._fallback()]

        html = raw_data.get("raw_html") or ""
        rate = self._extract_key_rate_from_html(html)

        if rate is None:
            logger.warning(
                "MacroParser: не удалось извлечь ставку — используем fallback %.2f%%",
                self.default_key_rate * 100,
            )
            return [self._fallback()]

        self._cache["key_rate"] = rate
        return [
            {
                "indicator": "key_rate",
                "value": rate,
                "unit": "share",
                "as_of": date.today().isoformat(),
                "source": "cbr",
            }
        ]

    def get_key_rate(self) -> float:
        """
        Удобный метод: возвращает текущую ключевую ставку в долях.

        Порядок:
          1. Кэш сессии
          2. Живой запрос к ЦБ
          3. default_key_rate
        """
        if "key_rate" in self._cache:
            return float(self._cache["key_rate"])

        raw = self.fetch_data("key_rate")
        parsed = self.parse_data(raw)
        if parsed and parsed[0].get("value") is not None:
            return float(parsed[0]["value"])
        return self.default_key_rate

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fallback(self) -> Dict[str, Any]:
        return {
            "indicator": "key_rate",
            "value": self.default_key_rate,
            "unit": "share",
            "as_of": date.today().isoformat(),
            "source": "fallback",
        }

    @staticmethod
    def _extract_key_rate_from_html(html: str) -> Optional[float]:
        """
        Эвристический разбор страницы cbr.ru/hd_base/KeyRate/.

        Ищет паттерны вида «16,00» / «16.00» рядом со словами
        «ключевая» / «Key rate» / в таблице.
        """
        if not html:
            return None

        # Типичные паттерны: <td>16,50</td> или >16,00<
        patterns = [
            r"[Кк]лючевая\s+ставка[^0-9]{0,80}?(\d{1,2}[.,]\d{1,2})",
            r"Key\s*rate[^0-9]{0,80}?(\d{1,2}[.,]\d{1,2})",
            r"<td[^>]*>\s*(\d{1,2}[.,]\d{2})\s*</td>",
            r"rate[^0-9]{0,40}?(\d{1,2}[.,]\d{2})\s*%",
        ]
        for pat in patterns:
            m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
            if m:
                try:
                    val = float(m.group(1).replace(",", "."))
                    # Ключевая ставка обычно 5–25 %
                    if 1.0 <= val <= 30.0:
                        return round(val / 100.0, 4)
                except ValueError:
                    continue
        return None
