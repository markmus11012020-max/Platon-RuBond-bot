from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import bond, chat, freelance, fundamentals, risk, system

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router, prefix="/api")
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(bond.router, prefix="/api/bots/bond", tags=["bond"])
app.include_router(freelance.router, prefix="/api/bots/freelance", tags=["freelance"])
app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
app.include_router(fundamentals.router, prefix="/api/fundamentals", tags=["fundamentals"])


@app.get("/", include_in_schema=False)
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "service": settings.app_name,
            "status": "ok",
            "docs": "/api/docs",
        }
    )


__all__ = ["app"]
