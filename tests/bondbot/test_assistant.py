from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

from bondbot.config import load_settings
from bondbot.db import Database
from bondbot.services.assistant import TOOL_SPECS, Assistant


class FakeCompletions:
    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[dict] = []

    async def create(self, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        if self.calls == 1:
            call = SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(name="new_issues", arguments='{"limit": 3}'),
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))]
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Идей пока нет.", tool_calls=None))]
        )


class FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions())


def test_tool_specs_are_complete() -> None:
    names = {item["function"]["name"] for item in TOOL_SPECS}
    assert {"get_bond", "screen_bonds", "portfolio", "market_rate", "news", "stress"} <= names


def test_assistant_tool_roundtrip(tmp_path) -> None:
    db = Database(str(tmp_path / "assistant.db"))
    settings = replace(
        load_settings(),
        openai_api_key="test",
        llm_enabled=True,
        llm_max_tool_rounds=3,
    )
    client = FakeClient()
    try:
        answer = asyncio.run(Assistant(settings, db, client=client).answer("что нового?"))
        assert answer == "Идей пока нет."
        assert client.chat.completions.calls == 2
        messages = client.chat.completions.requests[1]["messages"]
        assert any(message.get("role") == "tool" for message in messages)
    finally:
        db.close()


def test_assistant_fallback_without_key(tmp_path) -> None:
    db = Database(str(tmp_path / "assistant2.db"))
    settings = replace(load_settings(), openai_api_key="", llm_enabled=True)
    try:
        answer = asyncio.run(Assistant(settings, db).answer("что купить?"))
        assert "LLM не настроен" in answer
    finally:
        db.close()
