from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.chat.repository import ChatRepository
from app.config import get_settings
from app.schemas import ChatSessionResponse

router = APIRouter()


def repository() -> ChatRepository:
    settings = get_settings()
    return ChatRepository(settings.chat_db_path, settings.session_ttl_minutes)


def _response(session: dict) -> ChatSessionResponse:
    return ChatSessionResponse(
        session_id=session["session_id"],
        messages=session.get("messages") or [],
        active_isin=(session.get("state") or {}).get("active_isin"),
        expires_at=session.get("expires_at"),
    )


@router.post("/session", response_model=ChatSessionResponse)
async def create_session(repo: ChatRepository = Depends(repository)) -> ChatSessionResponse:
    return _response(repo.create_session())


@router.get("/session/{session_id}", response_model=ChatSessionResponse)
async def get_session(
    session_id: str,
    repo: ChatRepository = Depends(repository),
) -> ChatSessionResponse:
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена или истекла")
    return _response(session)


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    repo: ChatRepository = Depends(repository),
) -> dict[str, bool]:
    return {"removed": repo.delete_session(session_id)}


__all__ = ["router"]
