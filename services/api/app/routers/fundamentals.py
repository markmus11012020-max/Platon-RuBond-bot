from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse

from app.config import get_settings
from app.risk.repository import RiskRepository
from app.routers.risk import require_admin
from app.schemas import (
    FundamentalsEntry,
    FundamentalsImportResult,
    FundamentalsRequest,
)
from app.services.fundamentals_csv import parse_fundamentals_csv, template_csv

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


@router.get("/template", response_class=PlainTextResponse)
async def download_template() -> PlainTextResponse:
    return PlainTextResponse(
        template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="fundamentals_template.csv"'
        },
    )


@router.post("/import", response_model=FundamentalsImportResult)
async def import_fundamentals(
    file: UploadFile = File(...),
    _: None = Depends(require_admin),
    repo: RiskRepository = Depends(repository),
) -> FundamentalsImportResult:
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=413, detail="CSV больше 2 МБ")
    parsed = parse_fundamentals_csv(raw)
    imported = 0
    skipped = 0
    errors = list(parsed.errors)
    for row in parsed.rows:
        if row.error:
            skipped += 1
            errors.append(row.error)
            continue
        try:
            repo.upsert_fundamentals(
                isin=str(row.data.get("isin") or ""),
                issuer=str(row.data.get("issuer") or ""),
                period=str(row.data.get("period") or ""),
                revenue_rub=row.data.get("revenue_rub"),
                net_profit_rub=row.data.get("net_profit_rub"),
                ebitda_rub=row.data.get("ebitda_rub"),
                net_debt_rub=row.data.get("net_debt_rub"),
                equity_rub=row.data.get("equity_rub"),
                current_ratio=row.data.get("current_ratio"),
                source=str(row.data.get("source") or ""),
                source_url=str(row.data.get("source_url") or ""),
                notes=str(row.data.get("notes") or ""),
            )
            imported += 1
        except Exception as exc:
            skipped += 1
            errors.append(f"{row.data.get('isin') or row.data.get('issuer')}: {exc}")
    return FundamentalsImportResult(
        imported=imported,
        skipped=skipped,
        errors=errors[:50],
        total=len(parsed.rows),
    )


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
