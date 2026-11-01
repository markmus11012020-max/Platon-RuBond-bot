from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.risk.repository import RiskRepository
from app.routers.risk import require_admin
from app.schemas import FundamentalsEntry, FundamentalsRequest

router = APIRouter()


def repository() -> RiskRepository:
    settings = get_settings()
    return RiskRepository(settings.risk_db_path)


@router.get("", response_model=list[FundamentalsEntry])
async def list_fundamentals(
    isin: str = Query(default=""),
    issuer: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    repo: RiskRepository = Depends(repository),
) -> list[FundamentalsEntry]:
    if isin or issuer:
        items = repo.fundamentals_for(isin=isin, issuer=issuer, limit=limit)
    else:
        items = repo.list_fundamentals(limit=limit)
    return [FundamentalsEntry(**item) for item in items]


@router.post("", response_model=FundamentalsEntry)
async def add_fundamentals(
    payload: FundamentalsRequest,
    _: None = Depends(require_admin),
    repo: RiskRepository = Depends(repository),
) -> FundamentalsEntry:
    if not payload.isin.strip() and not payload.issuer.strip():
        raise HTTPException(status_code=422, detail="Нужен ISIN или issuer")
    item = repo.upsert_fundamentals(
        isin=payload.isin,
        issuer=payload.issuer,
        period=payload.period,
        revenue_rub=payload.revenue_rub,
        net_profit_rub=payload.net_profit_rub,
        ebitda_rub=payload.ebitda_rub,
        net_debt_rub=payload.net_debt_rub,
        equity_rub=payload.equity_rub,
        current_ratio=payload.current_ratio,
        source=payload.source,
        source_url=payload.source_url,
        notes=payload.notes,
    )
    return FundamentalsEntry(**item)


__all__ = ["router"]
