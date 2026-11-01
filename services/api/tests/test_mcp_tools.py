from __future__ import annotations

from app.services.mcp_tools import build_tool_specs, is_destructive, is_read_only, split_tools

TOOLS = [
    {
        "name": "get_portfolio",
        "description": "Портфель",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_accounts",
        "description": "Счета",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "post_order",
        "description": "Выставить заявку",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
        },
    },
    {
        "name": "cancel_order",
        "description": "Отменить заявку",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def test_read_only_classification() -> None:
    assert is_read_only("get_portfolio")
    assert is_read_only("find_instrument")
    assert is_read_only("list_bonds")
    assert not is_read_only("post_order")
    assert is_destructive("post_order")
    assert is_destructive("cancel_order")


def test_build_tool_specs_excludes_trading_by_default() -> None:
    specs = build_tool_specs(TOOLS)
    names = {item["function"]["name"] for item in specs}
    assert names == {"get_portfolio", "get_accounts"}
    assert specs[0]["function"]["parameters"] == {"type": "object", "properties": {}}


def test_build_tool_specs_can_allow_trading() -> None:
    specs = build_tool_specs(TOOLS, allow_trading=True)
    names = {item["function"]["name"] for item in specs}
    assert names == {"get_portfolio", "get_accounts", "post_order", "cancel_order"}


def test_split_tools() -> None:
    result = split_tools(TOOLS)
    assert result["read_only"] == ["get_portfolio", "get_accounts"]
    assert result["destructive"] == ["post_order", "cancel_order"]
    assert result["other"] == []
