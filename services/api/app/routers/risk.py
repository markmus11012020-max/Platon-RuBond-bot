from __future__ import annotations

import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import APIKeyHeader

from app.config import get_settings
from app.risk.repository import RiskRepository
from app.schemas import (
    BlocklistEntry,
    BlocklistRequest,
    CreditCheckRequest,
    CreditEventEntry,
    CreditEventRequest,
    RiskSummary,
)
from app.services.risk_service import evaluate_candidates

router = APIRouter()

admin_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


def repository() -> RiskRepository:
    settings = get_settings()
    repo = RiskRepository(settings.risk_db_path)
    if settings.demo_mode:
        repo.seed_demo()
    return repo


def require_admin(token: str | None = Depends(admin_header)) -> None:
    settings = get_settings()
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="PREMARKET_ADMIN_TOKEN не задан")
    if not token or not secrets.compare_digest(token, settings.admin_token):
        raise HTTPException(status_code=401, detail="Неверный admin token")


@router.get("/check")
async def admin_check(_: None = Depends(require_admin)) -> dict[str, bool]:
    return {"ok": True}


@router.get("/summary", response_model=RiskSummary)
async def summary(repo: RiskRepository = Depends(repository)) -> RiskSummary:
    settings = get_settings()
    assessments = await evaluate_candidates(settings, repo)
    return RiskSummary(
        **repo.summary(),
        checks={
            "total": len(assessments),
            "passed": sum(1 for item in assessments if item.status == "ok"),
            "blocked": sum(1 for item in assessments if item.status == "blocked"),
            "review": sum(1 for item in assessments if item.status == "review"),
        },
    )


@router.get("/blocklist", response_model=list[BlocklistEntry])
async def blocklist(repo: RiskRepository = Depends(repository)) -> list[BlocklistEntry]:
    return [BlocklistEntry(**item) for item in repo.active_blocklist()]


@router.post("/blocklist", response_model=BlocklistEntry)
async def add_blocklist(
    payload: BlocklistRequest,
    _: None = Depends(require_admin),
    repo: RiskRepository = Depends(repository),
) -> BlocklistEntry:
    if payload.expires_at:
        try:
            date.fromisoformat(payload.expires_at[:10])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="expires_at: YYYY-MM-DD") from exc
    item = repo.add_blocklist(
        isin=payload.isin,
        reason=payload.reason,
        source=payload.source,
        source_url=payload.source_url,
        severity=payload.severity,
        expires_at=payload.expires_at,
    )
    return BlocklistEntry(**item)


@router.delete("/blocklist/{isin}")
async def delete_blocklist(
    isin: str,
    _: None = Depends(require_admin),
    repo: RiskRepository = Depends(repository),
) -> dict[str, bool]:
    return {"removed": repo.remove_blocklist(isin)}


@router.get("/events", response_model=list[CreditEventEntry])
async def events(repo: RiskRepository = Depends(repository)) -> list[CreditEventEntry]:
    return [CreditEventEntry(**item) for item in repo.recent_events()]


@router.post("/events", response_model=CreditEventEntry)
async def add_event(
    payload: CreditEventRequest,
    _: None = Depends(require_admin),
    repo: RiskRepository = Depends(repository),
) -> CreditEventEntry:
    try:
        date.fromisoformat(payload.event_date[:10])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="event_date: YYYY-MM-DD") from exc
    item = repo.add_event(
        isin=payload.isin,
        issuer=payload.issuer,
        event_type=payload.event_type,
        severity=payload.severity,
        event_date=payload.event_date,
        source=payload.source,
        source_url=payload.source_url,
        summary=payload.summary,
    )
    return CreditEventEntry(**item)


@router.post("/checks")
async def set_credit_check(
    payload: CreditCheckRequest,
    _: None = Depends(require_admin),
    repo: RiskRepository = Depends(repository),
) -> dict:
    item = repo.set_credit_check(
        isin=payload.isin,
        status=payload.status,
        source=payload.source,
        source_url=payload.source_url,
        note=payload.note,
        valid_days=payload.valid_days,
    )
    return item


@router.get("/candidates")
async def candidates(repo: RiskRepository = Depends(repository)) -> list[dict]:
    settings = get_settings()
    assessments = await evaluate_candidates(settings, repo)
    return [
        {
            "isin": item.isin,
            "name": item.name,
            "issuer": item.issuer,
            "status": item.status,
            "reason": item.reason,
            "checks": item.checks,
            "market": item.market,
            "news": item.news,
            "checked_at": item.checked_at,
        }
        for item in assessments
    ]


__all__ = ["router"]
