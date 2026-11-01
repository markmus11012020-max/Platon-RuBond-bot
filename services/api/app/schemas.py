from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BotManifest(BaseModel):
    id: str
    name: str
    tagline: str
    icon: str
    status: Literal["live", "beta", "soon"] = "beta"
    accent: str = "#38d9a9"
    features: list[str] = Field(default_factory=list)


class PortfolioSummary(BaseModel):
    total_value_rub: float
    profit_rub: float
    annual_coupon_rub: float
    weighted_ytm_pct: float | None = None
    weighted_duration_years: float | None = None
    risk_level: str = "MEDIUM"
    risk_score: int = 0
    positions_count: int = 0


class PositionCard(BaseModel):
    isin: str
    name: str
    qty: float
    value_rub: float
    weight_pct: float
    ytm_pct: float | None = None
    duration_years: float | None = None
    rating: str | None = None
    current_price_pct: float | None = None
    buy_price_pct: float | None = None
    pnl_rub: float | None = None
    annual_coupon_rub: float | None = None
    next_coupon_date: str | None = None
    maturity_date: str | None = None
    offer_date: str | None = None


class AllocationSlice(BaseModel):
    name: str
    value_rub: float
    share_pct: float
    color: str


class EventCard(BaseModel):
    date: str
    kind: Literal["coupon", "offer", "maturity"]
    title: str
    isin: str
    days: int


class CandidateCard(BaseModel):
    isin: str
    name: str
    ytm_pct: float
    duration_years: float
    rating: str
    price_pct: float
    volume_mn_rub: float
    reason: str


class BondOverview(BaseModel):
    as_of: str
    summary: PortfolioSummary
    positions: list[PositionCard]
    allocation: list[AllocationSlice]
    rating_mix: dict[str, float]
    events: list[EventCard]
    candidates: list[CandidateCard]
    insights: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)
    bot_id: str = "bond"


class ActionLeg(BaseModel):
    side: Literal["buy", "sell"]
    isin: str
    name: str
    quantity: float
    price_pct: float
    amount_rub: float


class ActionCard(BaseModel):
    id: str
    title: str
    description: str
    kind: str = "rebalance"
    status: Literal["proposed", "confirmed", "cancelled"] = "proposed"
    expected_effect: dict[str, Any] = Field(default_factory=dict)
    legs: list[ActionLeg] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    message: str
    suggestions: list[str] = Field(default_factory=list)
    action: ActionCard | None = None


class ConfirmResponse(BaseModel):
    action_id: str
    status: str
    message: str
    audit_id: str
    executed_at: str


class FreelanceOrder(BaseModel):
    id: int
    title: str
    source: str
    budget_text: str
    score: int
    url: str
    published_at: str | None = None
    category: str = ""
    matched_keywords: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


class FreelanceResponse(BaseModel):
    orders: list[FreelanceOrder]
    summary: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    demo_mode: bool
    mcp_enabled: bool
    mcp_ready: bool
    mcp_mode: str
    bonds_db: bool
    freelance_db: bool
