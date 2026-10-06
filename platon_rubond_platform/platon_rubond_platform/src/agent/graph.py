"""
LangGraph state machine для Platon-RuBond-bot (улучшения 1, 5, 7).

Граф:
  parse_intent → route →
    [fetch_bond | analyze_bond | search_news | key_rate | general] →
    risk_review → (human_gate?) → respond

Fallback: PipelineRunner без langgraph.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, TypedDict

from src.agent.observability import get_tracer
from src.agent.schemas import (
    AgentFinalResponse,
    BondAnalysisReport,
    BondSnapshot,
    IntentType,
    NewsItem,
    NewsSearchResult,
    RiskLevel,
    RiskReview,
)
from src.agent.tools import (
    analyze_bond_finance_tool,
    get_bond_info_tool,
    get_key_rate_tool,
    search_bond_news_tool,
)
from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.agent.graph")


# ------------------------------------------------------------------
# State
# ------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    input: str
    session_id: str
    intent: str
    secid: Optional[str]
    bond_raw: Optional[str]
    analysis_raw: Optional[str]
    news_raw: Optional[str]
    key_rate: Optional[float]
    risk_review: Optional[Dict[str, Any]]
    needs_human: bool
    human_decision: Optional[str]  # "approve" | "reject" | None
    intermediate: List[str]
    final: Optional[Dict[str, Any]]
    error: Optional[str]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_secid(text: str) -> Optional[str]:
    m = re.search(r"\b(RU[A-Z0-9]{10})\b", text.upper())
    if m:
        return m.group(1)
    m = re.search(r"\b(SU\d{5}[A-Z0-9]+)\b", text.upper())
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Z]{2}\d{5,}[A-Z0-9]*)\b", text.upper())
    if m:
        return m.group(1)
    return None


def _call_tool(tool: Any, **kwargs: Any) -> str:
    try:
        if hasattr(tool, "invoke"):
            return str(tool.invoke(kwargs if kwargs else {}))
        if kwargs:
            return str(tool(**kwargs))
        return str(tool())
    except TypeError:
        if len(kwargs) == 1:
            return str(tool(next(iter(kwargs.values()))))
        raise
    except Exception as exc:
        logger.exception("tool error")
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _parse_json(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return {"raw": raw}


# ------------------------------------------------------------------
# Nodes
# ------------------------------------------------------------------

def parse_intent(state: AgentState) -> AgentState:
    text = (state.get("input") or "").lower()
    intermediate = list(state.get("intermediate") or [])
    secid = _extract_secid(state.get("input") or "")

    if any(k in text for k in ("ключев", "ставк", "цб", "key rate", "cbr")):
        intent = IntentType.KEY_RATE.value
    elif any(k in text for k in ("новост", "news", "оферт", "раскрыт", "выпуск")):
        intent = IntentType.NEWS_SEARCH.value
    elif secid and any(
        k in text for k in ("анализ", "ytm", "доходн", "флоат", "финанс", "риск", "analyze")
    ):
        intent = IntentType.BOND_ANALYSIS.value
    elif secid:
        intent = IntentType.BOND_INFO.value
    elif any(k in text for k in ("портфел", "portfolio", "диверсиф")):
        intent = IntentType.PORTFOLIO.value
    else:
        intent = IntentType.GENERAL.value

    intermediate.append(f"intent={intent}, secid={secid}")
    return {
        **state,
        "intent": intent,
        "secid": secid,
        "intermediate": intermediate,
    }


def fetch_bond(state: AgentState) -> AgentState:
    tracer = get_tracer()
    secid = state.get("secid") or ""
    with tracer.start_span("fetch_bond", secid=secid):
        raw = _call_tool(get_bond_info_tool, secid=secid)
    intermediate = list(state.get("intermediate") or [])
    intermediate.append("fetch_bond done")
    return {**state, "bond_raw": raw, "intermediate": intermediate}


def analyze_bond(state: AgentState) -> AgentState:
    tracer = get_tracer()
    secid = state.get("secid") or ""
    key_rate = state.get("key_rate")
    if key_rate is None:
        kr_raw = _call_tool(get_key_rate_tool)
        key_rate = _parse_json(kr_raw).get("key_rate", 0.16)
    with tracer.start_span("analyze_bond", secid=secid):
        raw = _call_tool(
            analyze_bond_finance_tool,
            secid=secid,
            current_key_rate=float(key_rate),
        )
    intermediate = list(state.get("intermediate") or [])
    intermediate.append("analyze_bond done")
    return {
        **state,
        "analysis_raw": raw,
        "key_rate": float(key_rate) if key_rate is not None else None,
        "intermediate": intermediate,
    }


def search_news(state: AgentState) -> AgentState:
    tracer = get_tracer()
    query = state.get("input") or "облигации"
    with tracer.start_span("search_news", query=query[:80]):
        raw = _call_tool(search_bond_news_tool, query=query)
    intermediate = list(state.get("intermediate") or [])
    intermediate.append("search_news done")
    return {**state, "news_raw": raw, "intermediate": intermediate}


def fetch_key_rate(state: AgentState) -> AgentState:
    tracer = get_tracer()
    with tracer.start_span("fetch_key_rate"):
        raw = _call_tool(get_key_rate_tool)
    data = _parse_json(raw)
    rate = data.get("key_rate")
    intermediate = list(state.get("intermediate") or [])
    intermediate.append(f"key_rate={rate}")
    return {**state, "key_rate": rate, "intermediate": intermediate}


def risk_officer(state: AgentState) -> AgentState:
    """
    Multi-agent: Risk Officer ревьюит анализ (улучшение 7).
    Блокирует/помечает ВДО, отсутствие рейтинга, экстремальные YTM.
    """
    tracer = get_tracer()
    with tracer.start_span("risk_officer"):
        review = RiskReview(approved=True, risk_level=RiskLevel.LOW, reasons=[])
        analysis = _parse_json(state.get("analysis_raw") or "{}")
        bond_raw = _parse_json(state.get("bond_raw") or "{}")
        data = {**bond_raw, **analysis}

        reasons: List[str] = []
        risk = RiskLevel.LOW
        needs_human = False

        ytm = data.get("ytm")
        if ytm is not None:
            try:
                y = float(ytm)
                if y > 0.35:
                    reasons.append(f"Очень высокая YTM ({y*100:.1f}%) — возможен ВДО")
                    risk = RiskLevel.HIGH
                    needs_human = True
                elif y > 0.25:
                    reasons.append(f"Повышенная YTM ({y*100:.1f}%)")
                    risk = RiskLevel.MEDIUM
            except (TypeError, ValueError):
                pass

        rating = data.get("rating") or data.get("credit_rating")
        if not rating and state.get("intent") in (
            IntentType.BOND_ANALYSIS.value,
            IntentType.BOND_INFO.value,
        ):
            reasons.append("Кредитный рейтинг отсутствует в данных")
            if risk == RiskLevel.LOW:
                risk = RiskLevel.MEDIUM

        if data.get("is_vdo") is True:
            reasons.append("Бумага помечена как ВДО")
            risk = RiskLevel.CRITICAL
            needs_human = True
            review.approved = False
            review.blocked_recommendations.append(
                "Рекомендация к покупке ВДО заблокирована до подтверждения оператора"
            )

        coupon_type = str(data.get("coupon_type") or "").lower()
        if "флоат" in coupon_type and data.get("estimated_floater_yield") is None:
            reasons.append("Флоатер без оценки доходности")

        review.risk_level = risk
        review.reasons = reasons
        review.requires_human_confirmation = needs_human
        if needs_human and risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            review.approved = False

        intermediate = list(state.get("intermediate") or [])
        intermediate.append(
            f"risk_officer: approved={review.approved}, level={risk.value}"
        )

    return {
        **state,
        "risk_review": review.model_dump(),
        "needs_human": needs_human,
        "intermediate": intermediate,
    }


def human_gate(state: AgentState) -> AgentState:
    """
    Human-in-the-loop (улучшение 5).
    Если needs_human и нет human_decision — формируем запрос подтверждения.
    """
    intermediate = list(state.get("intermediate") or [])
    decision = state.get("human_decision")

    if not state.get("needs_human"):
        intermediate.append("human_gate: skip")
        return {**state, "intermediate": intermediate}

    if decision == "approve":
        rr = dict(state.get("risk_review") or {})
        rr["approved"] = True
        rr["requires_human_confirmation"] = False
        intermediate.append("human_gate: APPROVED by operator")
        return {
            **state,
            "risk_review": rr,
            "needs_human": False,
            "intermediate": intermediate,
        }

    if decision == "reject":
        rr = dict(state.get("risk_review") or {})
        rr["approved"] = False
        intermediate.append("human_gate: REJECTED by operator")
        return {
            **state,
            "risk_review": rr,
            "needs_human": False,
            "intermediate": intermediate,
        }

    # Ожидаем решения
    intermediate.append("human_gate: waiting for confirmation")
    return {**state, "needs_human": True, "intermediate": intermediate}


def respond(state: AgentState) -> AgentState:
    """Собирает AgentFinalResponse (structured output)."""
    intent = state.get("intent") or IntentType.GENERAL.value
    intermediate = list(state.get("intermediate") or [])
    risk_data = state.get("risk_review")
    risk_review = RiskReview(**risk_data) if risk_data else None

    bond_report = None
    news_result = None
    summary_parts: List[str] = []

    if state.get("analysis_raw"):
        data = _parse_json(state["analysis_raw"])
        if "error" not in data:
            snap = BondSnapshot(
                isin=data.get("isin"),
                secid=data.get("secid"),
                shortname=data.get("shortname"),
                maturity_date=data.get("maturity_date"),
                offer_date=data.get("offer_date"),
                face_value=data.get("face_value"),
                current_price=data.get("current_price"),
                coupon_period=data.get("coupon_period"),
                coupon_type=data.get("coupon_type"),
                nearest_coupon_value=data.get("nearest_coupon_value"),
                rating=data.get("rating") or data.get("credit_rating"),
            )
            ytm = data.get("ytm")
            risk_level = (
                risk_review.risk_level if risk_review else RiskLevel.MEDIUM
            )
            bond_report = BondAnalysisReport(
                bond=snap,
                ytm=ytm,
                ytm_pct=round(ytm * 100, 2) if ytm is not None else None,
                current_yield=data.get("current_yield"),
                estimated_floater_yield=data.get("estimated_floater_yield"),
                credit_spread=data.get("credit_spread"),
                z_spread=data.get("z_spread"),
                key_rate_used=data.get("key_rate_used") or state.get("key_rate"),
                risk_level=risk_level,
                risk_notes=list(risk_review.reasons) if risk_review else [],
                warnings=[data["risk_note"]] if data.get("risk_note") else [],
            )
            summary_parts.append(
                f"Анализ {snap.shortname or snap.isin}: "
                f"YTM={bond_report.ytm_pct or 'n/a'}%, "
                f"тип купона={snap.coupon_type or 'n/a'}"
            )

    elif state.get("bond_raw"):
        data = _parse_json(state["bond_raw"])
        if "error" not in data:
            snap = BondSnapshot(**{
                k: data.get(k) for k in BondSnapshot.model_fields
            })
            bond_report = BondAnalysisReport(bond=snap)
            summary_parts.append(
                f"Данные по {snap.shortname or snap.isin}: "
                f"цена={snap.current_price}, погашение={snap.maturity_date}"
            )

    if state.get("news_raw"):
        data = _parse_json(state["news_raw"])
        items = []
        for n in data.get("news") or []:
            if isinstance(n, dict):
                items.append(
                    NewsItem(
                        title=n.get("title", ""),
                        text=n.get("text", ""),
                        date=n.get("date", ""),
                        source=n.get("source", ""),
                        link=n.get("link", ""),
                    )
                )
        news_result = NewsSearchResult(
            query=data.get("query", ""),
            news=items,
            rag_hits=data.get("rag_hits") or [],
            news_count=data.get("news_count") or len(items),
        )
        summary_parts.append(f"Найдено новостей: {news_result.news_count}")

    if state.get("key_rate") is not None and intent == IntentType.KEY_RATE.value:
        summary_parts.append(
            f"Ключевая ставка ЦБ РФ: {float(state['key_rate'])*100:.2f}%"
        )

    needs_human = bool(state.get("needs_human"))
    human_prompt = None
    if needs_human:
        reasons = (risk_review.reasons if risk_review else []) or ["повышенный риск"]
        human_prompt = (
            "Операция требует подтверждения из-за: "
            + "; ".join(reasons)
            + ".\nОтветьте 'approve' или 'reject'."
        )
        summary_parts.append("⏳ Ожидается подтверждение оператора")

    if not summary_parts:
        summary_parts.append(
            "Запрос обработан. Укажите ISIN/SECID, спросите ставку ЦБ или новости."
        )

    final = AgentFinalResponse(
        intent=IntentType(intent) if intent in IntentType._value2member_map_ else IntentType.GENERAL,
        summary="\n".join(summary_parts),
        bond_report=bond_report,
        news=news_result,
        risk_review=risk_review,
        key_rate=state.get("key_rate"),
        intermediate_steps=intermediate,
        needs_human_input=needs_human,
        human_prompt=human_prompt,
        raw_output="\n".join(summary_parts),
    )

    intermediate.append("respond done")
    return {
        **state,
        "final": final.model_dump(),
        "intermediate": intermediate,
    }


# ------------------------------------------------------------------
# Routing
# ------------------------------------------------------------------

def route_after_intent(state: AgentState) -> str:
    intent = state.get("intent")
    mapping = {
        IntentType.BOND_INFO.value: "fetch_bond",
        IntentType.BOND_ANALYSIS.value: "analyze_bond",
        IntentType.NEWS_SEARCH.value: "search_news",
        IntentType.KEY_RATE.value: "fetch_key_rate",
        IntentType.PORTFOLIO.value: "respond",
        IntentType.GENERAL.value: "respond",
    }
    return mapping.get(intent, "respond")


def route_after_risk(state: AgentState) -> str:
    if state.get("needs_human") and not state.get("human_decision"):
        return "human_gate"
    return "respond"


# ------------------------------------------------------------------
# Graph builder + fallback pipeline
# ------------------------------------------------------------------

def build_langgraph():
    """Собирает StateGraph, если langgraph установлен."""
    from langgraph.graph import END, StateGraph

    g = StateGraph(AgentState)
    g.add_node("parse_intent", parse_intent)
    g.add_node("fetch_bond", fetch_bond)
    g.add_node("analyze_bond", analyze_bond)
    g.add_node("search_news", search_news)
    g.add_node("fetch_key_rate", fetch_key_rate)
    g.add_node("risk_officer", risk_officer)
    g.add_node("human_gate", human_gate)
    g.add_node("respond", respond)

    g.set_entry_point("parse_intent")
    g.add_conditional_edges("parse_intent", route_after_intent)
    g.add_edge("fetch_bond", "risk_officer")
    g.add_edge("analyze_bond", "risk_officer")
    g.add_edge("search_news", "respond")
    g.add_edge("fetch_key_rate", "respond")
    g.add_conditional_edges("risk_officer", route_after_risk)
    g.add_edge("human_gate", "respond")
    g.add_edge("respond", END)

    return g.compile()


class PipelineRunner:
    """
    Fallback без langgraph: тот же pipeline линейно.
    Поддерживает invoke и stream (генератор шагов).
    """

    def invoke(self, state: AgentState) -> AgentState:
        state = parse_intent(state)
        route = route_after_intent(state)
        node_map = {
            "fetch_bond": fetch_bond,
            "analyze_bond": analyze_bond,
            "search_news": search_news,
            "fetch_key_rate": fetch_key_rate,
            "respond": respond,
        }
        node = node_map.get(route, respond)
        state = node(state)
        if route in ("fetch_bond", "analyze_bond"):
            state = risk_officer(state)
            if state.get("needs_human") and not state.get("human_decision"):
                state = human_gate(state)
            state = respond(state)
        elif route != "respond":
            # news / key_rate already set fields; ensure respond
            if not state.get("final"):
                state = respond(state)
        return state

    def stream(self, state: AgentState):
        """Генератор: yield (node_name, partial_state) для UI streaming."""
        state = parse_intent(state)
        yield "parse_intent", dict(state)

        route = route_after_intent(state)
        yield "route", {"next": route}

        node_map = {
            "fetch_bond": fetch_bond,
            "analyze_bond": analyze_bond,
            "search_news": search_news,
            "fetch_key_rate": fetch_key_rate,
        }
        if route in node_map:
            state = node_map[route](state)
            yield route, dict(state)

        if route in ("fetch_bond", "analyze_bond"):
            state = risk_officer(state)
            yield "risk_officer", dict(state)
            if state.get("needs_human") and not state.get("human_decision"):
                state = human_gate(state)
                yield "human_gate", dict(state)

        state = respond(state)
        yield "respond", dict(state)


def get_graph_runner():
    """Возвращает compiled LangGraph или PipelineRunner."""
    try:
        graph = build_langgraph()
        logger.info("LangGraph compiled successfully")
        return graph
    except ImportError:
        logger.info("langgraph not installed — using PipelineRunner")
        return PipelineRunner()
    except Exception as exc:
        logger.warning("LangGraph build failed (%s) — PipelineRunner", exc)
        return PipelineRunner()
