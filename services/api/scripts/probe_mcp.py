from __future__ import annotations

import asyncio
import json

from app.config import get_settings
from app.services.mcp_client import TInvestMCPClient


async def main() -> None:
    settings = get_settings()
    client = TInvestMCPClient(settings)
    tools = await client.list_tools()
    print(
        json.dumps(
            {
                "mode": settings.tinvest_mcp_mode,
                "url": settings.mcp_url,
                "tools": tools,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
