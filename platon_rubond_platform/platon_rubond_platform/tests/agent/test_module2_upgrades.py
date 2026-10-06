"""Тесты улучшений Модуля 2."""

from __future__ import annotations

import pytest

from src.agent.cache import ToolCache
from src.agent.schemas import AgentFinalResponse, BondAnalysisReport, BondSnapshot, RiskLevel
from src.agent.rag_quality import RAGQualityTracker
from src.agent.observability import LocalTracer
from src.agent.graph import PipelineRunner, risk_officer
from src.agent.agent_factory import PlatonAgentFactory


class TestCache:
    def test_ttl_cache(self, tmp_path):
        cache = ToolCache(db_path=str(tmp_path / "c.db"))
        cache.set("get_key_rate_tool", '{"key_rate": 0.16}')
        assert cache.get("get_key_rate_tool") == '{"key_rate": 0.16}'
        cache.invalidate("get_key_rate_tool")
        assert cache.get("get_key_rate_tool") is None
        cache.close()


class TestSchemas:
    def test_final_response(self):
        r = AgentFinalResponse(
            summary="Тест",
            bond_report=BondAnalysisReport(
                bond=BondSnapshot(isin="RU000A105XX3", shortname="Test"),
                ytm=0.12,
                risk_level=RiskLevel.LOW,
            ),
        )
        text = r.to_ui_text()
        assert "Тест" in text


class TestRAGQuality:
    def test_log_and_stats(self, tmp_path):
        t = RAGQualityTracker(db_path=str(tmp_path / "rag.db"))
        qid = t.log_search(
            "газпром",
            [{"text": "новость", "score": 0.8, "metadata": {}}],
        )
        assert qid > 0
        t.add_feedback(qid, rating=1, comment="ok")
        stats = t.stats()
        assert stats["queries"] == 1
        t.close()


class TestObservability:
    def test_span(self, tmp_path):
        tracer = LocalTracer(log_path=str(tmp_path / "t.jsonl"))
        with tracer.start_span("test", foo=1) as span:
            span.attributes["bar"] = 2
        assert len(tracer.spans) == 1
        assert tracer.spans[0].duration_ms is not None
        assert tracer.spans[0].status == "ok"


class TestPipeline:
    def test_key_rate_intent(self):
        runner = PipelineRunner()
        state = runner.invoke({"input": "Какая ключевая ставка ЦБ?", "intermediate": []})
        assert state.get("intent") == "key_rate"
        assert state.get("final") is not None
        final = AgentFinalResponse(**state["final"])
        assert final.summary

    def test_stream(self):
        runner = PipelineRunner()
        steps = list(runner.stream({"input": "новости облигаций", "intermediate": []}))
        names = [s[0] for s in steps]
        assert "parse_intent" in names
        assert "respond" in names

    def test_risk_officer_high_ytm(self):
        state = {
            "analysis_raw": '{"ytm": 0.40, "isin": "X", "is_vdo": true}',
            "intent": "bond_analysis",
            "intermediate": [],
        }
        out = risk_officer(state)
        assert out["needs_human"] is True
        assert out["risk_review"]["risk_level"] in ("high", "critical")


class TestFactory:
    def test_run_and_stream(self, tmp_path):
        from src.config import Config
        cfg = Config()
        cfg.history_db = str(tmp_path / "h.db")
        factory = PlatonAgentFactory(config=cfg)
        resp = factory.run("Какая сейчас ключевая ставка?", session_id="test-upg")
        assert isinstance(resp, AgentFinalResponse)
        assert resp.summary

        steps = list(factory.stream("Новости про оферты", session_id="test-upg-2"))
        assert len(steps) >= 1

    def test_create_agent_graph(self, tmp_path):
        from src.config import Config
        cfg = Config()
        cfg.history_db = str(tmp_path / "h2.db")
        factory = PlatonAgentFactory(config=cfg)
        agent = factory.create_agent(session_id="g1", use_graph=True)
        result = agent.invoke({"input": "Ключевая ставка ЦБ"})
        assert "output" in result
