from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings
from app.schemas import BondOverview

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — Bond Copilot, старший аналитик рынка российских облигаций.
Отвечай по-русски, кратко и структурно, простым деловым текстом без Markdown.
Используй только данные из контекста. Не выдумывай числа, эмитентов и события.
Не давай индивидуальных инвестиционных рекомендаций. В конце добавь:
«Не индивидуальная инвестиционная рекомендация».
"""


class LLMAnswerer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def ready(self) -> bool:
        return self.settings.llm_enabled and bool(self.settings.openai_api_key)

    def _context(self, overview: BondOverview) -> dict[str, Any]:
        return {
            "as_of": overview.as_of,
            "summary": overview.summary.model_dump(),
            "positions": [item.model_dump() for item in overview.positions],
            "events": [item.model_dump() for item in overview.events[:8]],
            "candidates": [item.model_dump() for item in overview.candidates[:4]],
            "insights": overview.insights,
        }

    async def answer(
        self,
        question: str,
        overview: BondOverview,
        history: list[dict[str, str]] | None = None,
    ) -> str | None:
        if not self.ready:
            return None
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *[
                {
                    "role": item.get("role", "user"),
                    "content": (item.get("content") or "")[:1200],
                }
                for item in (history or [])[-6:]
                if item.get("role") in {"user", "assistant"}
            ],
            {
                "role": "user",
                "content": (
                    f"Вопрос: {question}\n\n"
                    f"Контекст портфеля (JSON): {self._context(overview)}"
                ),
            },
        ]
        try:
            client = AsyncOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                timeout=self.settings.llm_timeout,
            )
            response = await client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                temperature=0.2,
                max_tokens=self.settings.llm_max_tokens,
            )
            text = (response.choices[0].message.content or "").strip()
            return text or None
        except Exception as exc:
            log.warning("LLM answer failed: %s", exc)
            return None


__all__ = ["LLMAnswerer"]
