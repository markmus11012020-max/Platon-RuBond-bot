from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import BondOverview, ChatRequest, ChatResponse, ConfirmResponse
from app.services.bond_service import answer, build_overview, confirm_action

router = APIRouter()


@router.get("/overview", response_model=BondOverview)
async def overview() -> BondOverview:
    return build_overview()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    history = [item.model_dump() for item in request.history]
    return answer(request.message, history)


@router.post("/actions/{action_id}/confirm", response_model=ConfirmResponse)
async def confirm(action_id: str) -> ConfirmResponse:
    result = confirm_action(action_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Действие не найдено или устарело")
    return result


__all__ = ["router"]
