from __future__ import annotations

from fastapi import APIRouter, Query

from app.config import get_settings
from app.schemas import FreelanceResponse
from app.services.freelance_service import build_freelance_feed

router = APIRouter()


@router.get("/orders", response_model=FreelanceResponse)
async def orders(limit: int = Query(default=20, ge=1, le=50)) -> FreelanceResponse:
    return build_freelance_feed(get_settings(), limit=limit)


__all__ = ["router"]
