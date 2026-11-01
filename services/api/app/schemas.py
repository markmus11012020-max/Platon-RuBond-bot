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
    risk_flags: list[str] = Field(default_factory=list)


class ExcludedCandidate(BaseModel):
    isin: str
    name: str
    reason: str
    severity: Literal["blocked", "review"] = "blocked"


class BondOverview(BaseModel):
    as_of: str
    summary: PortfolioSummary
    positions: list[PositionCard]
    allocation: list[AllocationSlice]
    rating_mix: dict[str, float]
    events: list[EventCard]
    candidates: list[CandidateCard]
    excluded: list[ExcludedCandidate] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)
    bot_id: str = "bond"
    session_id: str | None = None


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
    session_id: str | None = None
    active_isin: str | None = None


class ChatSessionResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    active_isin: str | None = None
    expires_at: str | None = None


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


class BlocklistEntry(BaseModel):
    isin: str
    reason: str
    source: str
    source_url: str = ""
    severity: str = "blocked"
    added_at: str
    expires_at: str | None = None


class BlocklistRequest(BaseModel):
    isin: str = Field(min_length=6, max_length=32)
    reason: str = Field(min_length=3, max_length=500)
    source: str = Field(min_length=2, max_length=200)
    source_url: str = ""
    severity: str = "blocked"
    expires_at: str | None = None


class CreditEventEntry(BaseModel):
    id: int | None = None
    isin: str
    issuer: str = ""
    event_type: str
    severity: str
    event_date: str
    source: str
    source_url: str = ""
    summary: str
    created_at: str | None = None


class CreditEventRequest(BaseModel):
    isin: str = Field(min_length=6, max_length=32)
    issuer: str = ""
    event_type: str = Field(default="other", max_length=60)
    severity: Literal["critical", "warning", "info"] = "warning"
    event_date: str
    source: str = Field(min_length=2, max_length=200)
    source_url: str = ""
    summary: str = Field(min_length=3, max_length=1000)


class CreditCheckRequest(BaseModel):
    isin: str = Field(min_length=6, max_length=32)
    status: Literal["passed", "failed", "pending"] = "passed"
    source: str = Field(min_length=2, max_length=200)
    source_url: str = ""
    note: str = ""
    valid_days: int = Field(default=90, ge=1, le=365)


class FundamentalsEntry(BaseModel):
    isin: str = ""
    issuer: str = ""
    period: str
    revenue_rub: float | None = None
    net_profit_rub: float | None = None
    ebitda_rub: float | None = None
    net_debt_rub: float | None = None
    equity_rub: float | None = None
    current_ratio: float | None = None
    source: str
    source_url: str = ""
    notes: str = ""
    updated_at: str | None = None


class FundamentalsRequest(BaseModel):
    isin: str = Field(default="", max_length=32)
    issuer: str = Field(default="", max_length=200)
    period: str = Field(min_length=2, max_length=40)
    revenue_rub: float | None = None
    net_profit_rub: float | None = None
    ebitda_rub: float | None = None
    net_debt_rub: float | None = None
    equity_rub: float | None = None
    current_ratio: float | None = None
    source: str = Field(min_length=2, max_length=200)
    source_url: str = ""
    notes: str = ""


class FundamentalsImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
    total: int = 0


class RiskSummary(BaseModel):
    credit_events: int
    blocklist: int
    credit_checks: int
    checks: dict[str, Any] = Field(default_factory=dict)
