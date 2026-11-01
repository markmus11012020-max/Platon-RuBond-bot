from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.chat.repository import ChatRepository
from app.chat.utils import extract_isin
from app.config import get_settings
from app.schemas import BondOverview, ChatRequest, ChatResponse, ConfirmResponse
from app.services.bond_service import answer, build_overview, confirm_action

router = APIRouter()


def chat_repository() -> ChatRepository:
    settings = get_settings()
    return ChatRepository(settings.chat_db_path, settings.session_ttl_minutes)


@router.get("/overview", response_model=BondOverview)
async def overview() -> BondOverview:
    return await build_overview()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    repo: ChatRepository = Depends(chat_repository),
) -> ChatResponse:
    session = repo.get_session(request.session_id) if request.session_id else None
    if session is None:
        session = repo.create_session()
        if request.history:
            repo.append_many(
                session["session_id"],
                [item.model_dump() for item in request.history],
            )
            session = repo.get_session(session["session_id"]) or session
    elif not session.get("messages") and request.history:
        repo.append_many(
            session["session_id"],
            [item.model_dump() for item in request.history],
        )
        session = repo.get_session(session["session_id"]) or session

    history = (session.get("messages") or [])[-12:]
    active_isin = (session.get("state") or {}).get("active_isin")
    response = await answer(request.message, history, active_isin)

    repo.append_message(session["session_id"], "user", request.message)
    repo.append_message(session["session_id"], "assistant", response.message)
    new_active = (
        extract_isin(request.message)
        or extract_isin(response.message)
        or active_isin
    )
    state = {**(session.get("state") or {}), "active_isin": new_active}
    repo.update_state(session["session_id"], state)
    return response.model_copy(
        update={
            "session_id": session["session_id"],
            "active_isin": new_active,
        }
    )


@router.post("/actions/{action_id}/confirm", response_model=ConfirmResponse)
async def confirm(action_id: str) -> ConfirmResponse:
    result = confirm_action(action_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Действие не найдено или устарело")
    return result


__all__ = ["router"]
