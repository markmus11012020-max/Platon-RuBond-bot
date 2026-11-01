from __future__ import annotations

from typing import Any

READ_ONLY_PREFIXES = ("get_", "find_", "list_", "search_", "screen_")
DESTRUCTIVE_PREFIXES = ("post_", "cancel_", "delete_", "place_", "close_", "replace_")


def is_read_only(name: str) -> bool:
    return name.startswith(READ_ONLY_PREFIXES)


def is_destructive(name: str) -> bool:
    return name.startswith(DESTRUCTIVE_PREFIXES)


def to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": str(tool.get("name") or ""),
            "description": str(tool.get("description") or ""),
            "parameters": tool.get("input_schema")
            or {"type": "object", "properties": {}},
        },
    }


def build_tool_specs(
    tools: list[dict[str, Any]],
    *,
    allow_trading: bool = False,
) -> list[dict[str, Any]]:
    """Convert MCP tools to OpenAI function specs with a read-only safety gate."""
    specs: list[dict[str, Any]] = []
    for tool in tools:
        name = str(tool.get("name") or "")
        if not name:
            continue
        if not allow_trading and not is_read_only(name):
            continue
        specs.append(to_openai_tool(tool))
    return specs


def split_tools(tools: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "read_only": [str(item.get("name")) for item in tools if is_read_only(str(item.get("name") or ""))],
        "destructive": [
            str(item.get("name"))
            for item in tools
            if is_destructive(str(item.get("name") or ""))
        ],
        "other": [
            str(item.get("name"))
            for item in tools
            if not is_read_only(str(item.get("name") or ""))
            and not is_destructive(str(item.get("name") or ""))
        ],
    }


__all__ = [
    "build_tool_specs",
    "is_destructive",
    "is_read_only",
    "split_tools",
    "to_openai_tool",
]
