from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import Settings, get_settings
from app.schemas import BotManifest, HealthResponse
from app.services.mcp_client import TInvestMCPClient

router = APIRouter()

BOTS = [
    BotManifest(
        id="bond",
        name="Bond Copilot",
        tagline="AI-агент для облигационного портфеля",
        icon="bond",
        status="live",
        accent="#38d9a9",
        features=["Портфель", "Сделки", "Купоны", "Риск"],
    ),
    BotManifest(
        id="freelance",
        name="Freelance Radar",
        tagline="Заказы и проекты в одном потоке",
        icon="briefcase",
        status="beta",
        accent="#f6c453",
        features=["Заказы", "Скор", "Бюджеты"],
    ),
]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
        demo_mode=settings.demo_mode,
        mcp_enabled=settings.tinvest_mcp_enabled,
        mcp_ready=settings.mcp_ready,
        mcp_mode=settings.tinvest_mcp_mode,
        bonds_db=settings.bond_db_path.endswith(".db"),
        freelance_db=settings.freelance_db_available,
    )


@router.get("/bots", response_model=list[BotManifest])
async def bots() -> list[BotManifest]:
    return BOTS


@router.get("/notifications/vapid-public-key")
async def vapid_public_key() -> dict[str, str | None]:
    settings = get_settings()
    return {"public_key": settings.vapid_public_key or None}


@router.get("/mcp/tools")
async def mcp_tools() -> dict:
    settings: Settings = get_settings()
    client = TInvestMCPClient(settings)
    try:
        tools = await client.list_tools()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"mode": settings.tinvest_mcp_mode, "tools": tools}


__all__ = ["BOTS", "router"]
