from __future__ import annotations

import logging
from typing import Any

from app.config import Settings

log = logging.getLogger(__name__)


class MCPUnavailable(RuntimeError):
    pass


class TInvestMCPClient:
    """Thin async client around the official T-Invest MCP server.

    The MCP SDK is imported lazily so the API can run in demo mode without
    the optional dependency being installed.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.tinvest_mcp_token}"}

    def _ensure_ready(self) -> None:
        if not self.settings.tinvest_mcp_enabled:
            raise MCPUnavailable("T-Invest MCP выключен")
        if not self.settings.tinvest_mcp_token:
            raise MCPUnavailable("T-Invest MCP token не задан")

    async def list_tools(self) -> list[dict[str, Any]]:
        self._ensure_ready()
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise MCPUnavailable("Пакет mcp не установлен") from exc

        async with streamablehttp_client(
            self.settings.mcp_url,
            headers=self._headers(),
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema,
                    }
                    for tool in result.tools
                ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._ensure_ready()
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise MCPUnavailable("Пакет mcp не установлен") from exc

        async with streamablehttp_client(
            self.settings.mcp_url,
            headers=self._headers(),
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                return result.model_dump(mode="json")

    async def health(self) -> dict[str, Any]:
        if not self.settings.tinvest_mcp_enabled:
            return {"enabled": False, "ready": False, "reason": "disabled"}
        if not self.settings.tinvest_mcp_token:
            return {"enabled": True, "ready": False, "reason": "token_missing"}
        try:
            tools = await self.list_tools()
        except Exception as exc:
            log.warning("MCP health failed: %s", exc)
            return {"enabled": True, "ready": False, "reason": str(exc)}
        return {
            "enabled": True,
            "ready": True,
            "mode": self.settings.tinvest_mcp_mode,
            "tools": len(tools),
        }


__all__ = ["MCPUnavailable", "TInvestMCPClient"]
