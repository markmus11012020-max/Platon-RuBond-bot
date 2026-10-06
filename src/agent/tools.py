"""
Инструменты LangChain для агента Platon-RuBond-bot.

Оборачивают MoexParser, BondAnalyzer, NewsParser и PineconeMemoryManager
в стандартные @tool-функции, которые агент вызывает самостоятельно.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.agent.tools")

def _cache_get(tool_name: str, **kwargs):
    try:
        from src.agent.cache import get_tool_cache
        return get_tool_cache().get(tool_name, **kwargs)
    except Exception:
        return None

def _cache_set(tool_name: str, value: str, **kwargs):
    try:
        from src.agent.cache import get_tool_cache
        get_tool_cache().set(tool_name, value, **kwargs)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Ленивые синглтоны (избегаем повторной инициализации в Streamlit)
# ---------------------------------------------------------------------------
_moex_parser = None
_news_parser = None
_bond_analyzer = None
_macro_parser = None
_pinecone_manager = None


def _get_moex():
    global _moex_parser
    if _moex_parser is None:
        from src.data_providers.moex_api import MoexParser
        _moex_parser = MoexParser()
    return _moex_parser


def _get_news():
    global _news_parser
    if _news_parser is None:
        from src.data_providers.news_scraper import NewsParser
        _news_parser = NewsParser()
    return _news_parser


def _get_analyzer():
    global _bond_analyzer
    if _bond_analyzer is None:
        from src.analytics.bond_math import BondAnalyzer
        _bond_analyzer = BondAnalyzer()
    return _bond_analyzer


def _get_macro():
    global _macro_parser
    if _macro_parser is None:
        from src.data_providers.macro_parser import MacroParser
        _macro_parser = MacroParser()
    return _macro_parser


def _get_pinecone():
    global _pinecone_manager
    if _pinecone_manager is None:
        try:
            from src.memory.pinecone_store import PineconeMemoryManager
            from src.config import Config
            cfg = Config()
            _pinecone_manager = PineconeMemoryManager(
                api_key=cfg.pinecone_api_key,
                environment=cfg.pinecone_env,
                index_name=getattr(cfg, "pinecone_index", None) or "platon-rubond",
            )
        except Exception as exc:
            logger.warning("Pinecone init failed: %s", exc)
            _pinecone_manager = None
    return _pinecone_manager


def _safe_json(obj: Any) -> str:
    """Сериализация результата инструмента в JSON-строку для LLM."""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str, indent=None)
    except Exception:
        return str(obj)


# ---------------------------------------------------------------------------
# Попытка использовать langchain @tool; fallback — plain functions + Tool wrapper
# ---------------------------------------------------------------------------
try:
    from langchain_core.tools import tool as _lc_tool

    def tool(fn=None, **kwargs):
        if fn is not None:
            return _lc_tool(fn)
        return lambda f: _lc_tool(f, **kwargs)

except ImportError:
    try:
        from langchain.tools import tool as _lc_tool

        def tool(fn=None, **kwargs):
            if fn is not None:
                return _lc_tool(fn)
            return lambda f: _lc_tool(f, **kwargs)

    except ImportError:
        # Fallback: plain decorator that just marks the function
        def tool(fn=None, *, description: str = ""):
            def decorator(f):
                f.description = description or (f.__doc__ or "")
                f.name = f.__name__
                return f
            if fn is not None:
                return decorator(fn)
            return decorator


@tool
def get_bond_info_tool(secid: str) -> str:
    """
    Собирает сырые и нормализованные данные по облигации с Московской Биржи (ISS MOEX).

    Аргументы:
        secid: тикер или ISIN бумаги (например SU26238RMFS7 или RU000A105XX3).

    Возвращает JSON со спецификацией: isin, shortname, maturity_date, offer_date,
    face_value, current_price, coupon_period, coupon_type, nearest_coupon_value.
    """
    try:
        if not secid or not str(secid).strip():
            return _safe_json({"error": "secid is required"})
        secid = str(secid).strip()
        cached = _cache_get("get_bond_info_tool", secid=secid)
        if cached is not None:
            return cached
        parser = _get_moex()
        raw = parser.fetch_data(secid)
        parsed = parser.parse_data(raw)
        if not parsed:
            return _safe_json({"error": f"No data for secid={secid}", "raw_keys": list(raw.keys()) if raw else []})
        out = _safe_json(parsed[0])
        _cache_set("get_bond_info_tool", out, secid=secid)
        return out
    except Exception as exc:
        logger.exception("get_bond_info_tool failed")
        return _safe_json({"error": str(exc)})


@tool
def analyze_bond_finance_tool(secid: str, current_key_rate: float = 0.16) -> str:
    """
    Полный финансовый анализ облигации: данные с Мосбиржи + YTM + доходность флоатера + оценка риска.

    Аргументы:
        secid: тикер или ISIN бумаги.
        current_key_rate: текущая ключевая ставка ЦБ РФ в долях (например 0.16 = 16%).
                          Если не указана, используется значение по умолчанию 0.16.

    Возвращает JSON: рыночные данные, ytm, estimated_floater_yield / current_yield,
    coupon_type, credit risk flags.
    """
    try:
        if not secid or not str(secid).strip():
            return _safe_json({"error": "secid is required"})
        secid = str(secid).strip()
        key_rate = float(current_key_rate) if current_key_rate is not None else 0.16
        cached = _cache_get("analyze_bond_finance_tool", secid=secid, current_key_rate=key_rate)
        if cached is not None:
            return cached

        parser = _get_moex()
        analyzer = _get_analyzer()

        raw = parser.fetch_data(secid)
        parsed_list = parser.parse_data(raw)
        if not parsed_list:
            return _safe_json({"error": f"No bond data for secid={secid}"})

        bond = dict(parsed_list[0])

        # YTM (точная)
        ytm = analyzer.calculate_ytm(bond)
        bond["ytm"] = ytm
        bond["ytm_simple"] = analyzer.calculate_simple_ytm(bond)
        bond["current_yield"] = analyzer.calculate_current_yield(bond)

        coupon_type = (bond.get("coupon_type") or "").lower()
        if "флоат" in coupon_type or "float" in coupon_type or "перемен" in coupon_type:
            bond["estimated_floater_yield"] = analyzer.estimate_floater_yield(bond, key_rate)
        else:
            bond["estimated_floater_yield"] = None

        # Спреды
        bond["credit_spread"] = analyzer.calculate_credit_spread(bond, key_rate)
        bond["z_spread"] = analyzer.calculate_z_spread(bond, risk_free_rate=key_rate)

        # Риск: без рейтинга в данных MOEX — помечаем
        if not bond.get("rating") and not bond.get("credit_rating"):
            bond["risk_note"] = "Рейтинг отсутствует в данных MOEX; требуется ручная проверка"

        bond["key_rate_used"] = key_rate
        out = _safe_json(bond)
        _cache_set("analyze_bond_finance_tool", out, secid=secid, current_key_rate=key_rate)
        return out
    except Exception as exc:
        logger.exception("analyze_bond_finance_tool failed")
        return _safe_json({"error": str(exc)})


@tool
def search_bond_news_tool(query: str = "облигации выпуск оферта") -> str:
    """
    Поиск свежих новостей рынка облигаций РФ (RSS Интерфакс + DuckDuckGo)
    и семантический поиск по векторной памяти Pinecone (если настроена).

    Аргументы:
        query: поисковый запрос (например "оферта Газпром" или "ключевая ставка ЦБ").

    Возвращает JSON-список новостей: title, text, date, source, link.
    """
    try:
        q = (query or "облигации выпуск оферта").strip()
        cached = _cache_get("search_bond_news_tool", query=q)
        if cached is not None:
            return cached
        news_parser = _get_news()
        raw = news_parser.fetch_data(q)
        news = news_parser.parse_data(raw)

        pinecone_hits: List[Dict[str, Any]] = []
        pm = _get_pinecone()
        if pm is not None:
            try:
                pinecone_hits = pm.similarity_search(q, top_k=5)
                try:
                    from src.agent.rag_quality import get_rag_tracker
                    get_rag_tracker().log_search(q, pinecone_hits, top_k=5)
                except Exception:
                    pass
            except Exception as exc:
                logger.warning("Pinecone search in tool failed: %s", exc)

        result = {
            "query": q,
            "news_count": len(news),
            "news": news[:15],
            "rag_hits": pinecone_hits,
        }
        out = _safe_json(result)
        _cache_set("search_bond_news_tool", out, query=q)
        return out
    except Exception as exc:
        logger.exception("search_bond_news_tool failed")
        return _safe_json({"error": str(exc)})


@tool
def get_key_rate_tool() -> str:
    """
    Возвращает актуальную ключевую ставку Банка России (ЦБ РФ) в долях.
    Используется для оценки доходности флоатеров.
    """
    try:
        cached = _cache_get("get_key_rate_tool")
        if cached is not None:
            return cached
        macro = _get_macro()
        rate = macro.get_key_rate()
        out = _safe_json({"key_rate": rate, "unit": "share", "pct": round(rate * 100, 2)})
        _cache_set("get_key_rate_tool", out)
        return out
    except Exception as exc:
        logger.exception("get_key_rate_tool failed")
        return _safe_json({"error": str(exc), "key_rate": 0.16})


def get_all_tools() -> list:
    """Возвращает список всех инструментов для передачи в агент."""
    return [
        get_bond_info_tool,
        analyze_bond_finance_tool,
        search_bond_news_tool,
        get_key_rate_tool,
    ]
