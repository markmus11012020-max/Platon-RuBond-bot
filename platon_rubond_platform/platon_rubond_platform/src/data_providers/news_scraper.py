"""
Класс NewsParser — парсинг новостных лент и раскрытий информации
о корпоративных событиях эмитентов (облигации, оферты, выпуски).

Источники (бесплатные, без API-ключей):
  1. RSS Интерфакс
  2. DuckDuckGo Search (библиотека duckduckgo-search / ddgs)
"""

from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import requests

from src.data_providers.base_parser import BaseParser
from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.news")

TIMEOUT = 15
DEFAULT_QUERY = "облигации выпуск оферта"
INTERFAX_RSS = "https://www.interfax.ru/rss.asp"


class NewsParser(BaseParser):
    """
    Парсер новостей рынка облигаций.
    Наследуется от BaseParser.
    """

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; Platon-RuBond-bot/1.0; "
                    "+https://github.com/local)"
                ),
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            }
        )

    def fetch_data(self, query: str = DEFAULT_QUERY) -> Dict[str, Any]:  # type: ignore[override]
        """
        Собирает свежие новости из RSS и/или DuckDuckGo Search.

        Возвращает словарь:
          {
            "rss_items": [...],   # сырые элементы RSS
            "ddg_items": [...],   # результаты поиска DDG
            "query": str
          }
        При сетевых ошибках возвращает пустые списки и логирует предупреждения.
        """
        result: Dict[str, Any] = {
            "query": query,
            "rss_items": [],
            "ddg_items": [],
        }

        # --- 1. RSS Интерфакс ---
        try:
            resp = self._session.get(INTERFAX_RSS, timeout=TIMEOUT)
            if resp.status_code >= 400:
                logger.warning(
                    "NewsParser RSS: HTTP %s для %s", resp.status_code, INTERFAX_RSS
                )
            else:
                result["rss_items"] = self._parse_rss_raw(resp.content)
                logger.info("NewsParser RSS: получено %d элементов", len(result["rss_items"]))
        except requests.exceptions.Timeout:
            logger.warning("NewsParser RSS: таймаут (%s с)", TIMEOUT)
        except requests.exceptions.ConnectionError as exc:
            logger.warning("NewsParser RSS: ошибка сети — %s", exc)
        except requests.exceptions.RequestException as exc:
            logger.warning("NewsParser RSS: ошибка запроса — %s", exc)
        except Exception as exc:
            logger.warning("NewsParser RSS: неожиданная ошибка — %s", exc)

        # --- 2. DuckDuckGo Search (опционально, если установлен пакет) ---
        try:
            result["ddg_items"] = self._fetch_ddg(query)
            logger.info("NewsParser DDG: получено %d результатов", len(result["ddg_items"]))
        except Exception as exc:
            logger.warning("NewsParser DDG: ошибка — %s", exc)

        return result

    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        Очищает тексты от HTML-тегов и приводит к единому формату:
        [{"title": ..., "text": ..., "date": ..., "source": ...}, ...]
        """
        if not raw_data or not isinstance(raw_data, dict):
            logger.warning("NewsParser.parse_data: пустые данные")
            return []

        news: List[Dict[str, Any]] = []

        # RSS
        for item in raw_data.get("rss_items") or []:
            title = self._clean_text(item.get("title", ""))
            text = self._clean_text(item.get("description", "") or item.get("summary", ""))
            date = item.get("pubDate") or item.get("published") or ""
            if title:
                news.append(
                    {
                        "title": title,
                        "text": text,
                        "date": date,
                        "source": "interfax_rss",
                        "link": item.get("link", ""),
                    }
                )

        # DDG
        for item in raw_data.get("ddg_items") or []:
            title = self._clean_text(item.get("title", ""))
            text = self._clean_text(item.get("body", "") or item.get("snippet", ""))
            date = item.get("date") or ""
            if title:
                news.append(
                    {
                        "title": title,
                        "text": text,
                        "date": date,
                        "source": "duckduckgo",
                        "link": item.get("href", "") or item.get("link", ""),
                    }
                )

        # Фильтруем по ключевым словам, связанным с облигациями (если есть RSS-шум)
        keywords = (
            "облигац",
            "оферт",
            "выпуск",
            "купон",
            "погашен",
            "isin",
            "bond",
            "эмисси",
            "рейтинг",
            "дефолт",
            "реструкт",
        )
        filtered = [
            n
            for n in news
            if any(k in (n["title"] + " " + n["text"]).lower() for k in keywords)
        ]

        # Если после фильтра ничего не осталось — возвращаем всё (лучше шум, чем пусто)
        result = filtered if filtered else news
        logger.info("NewsParser.parse_data: итого %d новостей", len(result))
        return result

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _parse_rss_raw(self, content: bytes) -> List[Dict[str, str]]:
        """Разбор RSS/Atom без внешних зависимостей (ElementTree)."""
        items: List[Dict[str, str]] = []
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            logger.warning("NewsParser: ошибка разбора RSS XML — %s", exc)
            return items

        # RSS 2.0
        for item in root.findall(".//item"):
            entry = {
                "title": (item.findtext("title") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "pubDate": (item.findtext("pubDate") or "").strip(),
            }
            if entry["title"]:
                items.append(entry)

        # Atom fallback
        if not items:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                title = entry.findtext("{http://www.w3.org/2005/Atom}title") or ""
                summary = (
                    entry.findtext("{http://www.w3.org/2005/Atom}summary")
                    or entry.findtext("{http://www.w3.org/2005/Atom}content")
                    or ""
                )
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                link = link_el.get("href", "") if link_el is not None else ""
                published = (
                    entry.findtext("{http://www.w3.org/2005/Atom}published")
                    or entry.findtext("{http://www.w3.org/2005/Atom}updated")
                    or ""
                )
                if title.strip():
                    items.append(
                        {
                            "title": title.strip(),
                            "description": summary.strip(),
                            "link": link,
                            "pubDate": published,
                        }
                    )

        return items

    def _fetch_ddg(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Поиск через duckduckgo-search (если установлен)."""
        try:
            from duckduckgo_search import DDGS  # type: ignore
        except ImportError:
            logger.info(
                "NewsParser: пакет duckduckgo-search не установлен — пропускаем DDG"
            )
            return []

        results: List[Dict[str, Any]] = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.news(query, max_results=max_results, region="ru-ru"):
                    results.append(
                        {
                            "title": r.get("title", ""),
                            "body": r.get("body", ""),
                            "href": r.get("url", "") or r.get("href", ""),
                            "date": r.get("date", ""),
                        }
                    )
        except Exception as exc:
            logger.warning("NewsParser DDG search failed: %s", exc)
        return results

    @staticmethod
    def _clean_text(text: str) -> str:
        """Удаляет HTML-теги, декодирует сущности, нормализует пробелы."""
        if not text:
            return ""
        # Удаляем теги
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
