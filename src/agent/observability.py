"""
Observability: локальный tracer + опциональный LangSmith (улучшение 8).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.observability")


@dataclass
class Span:
    name: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    parent_id: Optional[str] = None
    start_ts: float = field(default_factory=time.time)
    end_ts: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error: Optional[str] = None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_ts is None:
            return None
        return round((self.end_ts - self.start_ts) * 1000, 2)


class LocalTracer:
    """Простой файловый/in-memory tracer (OpenTelemetry-подобный API)."""

    def __init__(self, log_path: Optional[str] = "agent_traces.jsonl") -> None:
        self.log_path = log_path
        self.spans: List[Span] = []
        self._stack: List[Span] = []

    @contextmanager
    def start_span(
        self, name: str, **attributes: Any
    ) -> Generator[Span, None, None]:
        parent_id = self._stack[-1].span_id if self._stack else None
        span = Span(name=name, parent_id=parent_id, attributes=dict(attributes))
        self._stack.append(span)
        try:
            yield span
            span.status = "ok"
        except Exception as exc:
            span.status = "error"
            span.error = str(exc)
            raise
        finally:
            span.end_ts = time.time()
            self._stack.pop()
            self.spans.append(span)
            self._persist(span)
            logger.info(
                "span %s status=%s duration_ms=%s attrs=%s",
                name,
                span.status,
                span.duration_ms,
                {k: v for k, v in span.attributes.items() if k != "output"},
            )

    def _persist(self, span: Span) -> None:
        if not self.log_path:
            return
        try:
            Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
            record = {
                **asdict(span),
                "duration_ms": span.duration_ms,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:
            logger.debug("trace persist failed: %s", exc)

    def get_recent(self, n: int = 20) -> List[Dict[str, Any]]:
        return [asdict(s) for s in self.spans[-n:]]

    def clear(self) -> None:
        self.spans.clear()


def setup_langsmith() -> bool:
    """
    Включает LangSmith tracing, если заданы LANGCHAIN_API_KEY / LANGSMITH_API_KEY.
    Returns True если tracing активирован.
    """
    api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
    if not api_key:
        return False
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGCHAIN_PROJECT", "platon-rubond"))
    logger.info("LangSmith tracing enabled (project=%s)", os.environ["LANGCHAIN_PROJECT"])
    return True


# Глобальный tracer
_tracer: Optional[LocalTracer] = None


def get_tracer(log_path: str = "agent_traces.jsonl") -> LocalTracer:
    global _tracer
    if _tracer is None:
        setup_langsmith()
        _tracer = LocalTracer(log_path=log_path)
    return _tracer
