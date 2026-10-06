"""
Pydantic-схемы структурированного вывода агента (улучшение 2).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IntentType(str, Enum):
    BOND_INFO = "bond_info"
    BOND_ANALYSIS = "bond_analysis"
    NEWS_SEARCH = "news_search"
    KEY_RATE = "key_rate"
    PORTFOLIO = "portfolio"
    GENERAL = "general"
    UNKNOWN = "unknown"


class BondSnapshot(BaseModel):
    """Нормализованные рыночные данные по облигации."""

    isin: Optional[str] = None
    secid: Optional[str] = None
    shortname: Optional[str] = None
    maturity_date: Optional[str] = None
    offer_date: Optional[str] = None
    face_value: Optional[float] = None
    current_price: Optional[float] = None
    coupon_period: Optional[int] = None
    coupon_type: Optional[str] = None
    nearest_coupon_value: Optional[float] = None
    rating: Optional[str] = None


class BondAnalysisReport(BaseModel):
    """Структурированный финансовый отчёт по облигации."""

    bond: BondSnapshot
    ytm: Optional[float] = Field(None, description="YTM в долях")
    ytm_pct: Optional[float] = Field(None, description="YTM в %")
    current_yield: Optional[float] = None
    estimated_floater_yield: Optional[float] = None
    credit_spread: Optional[float] = None
    z_spread: Optional[float] = None
    key_rate_used: Optional[float] = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_notes: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    def to_display_dict(self) -> Dict[str, Any]:
        d = self.model_dump()
        if self.ytm is not None:
            d["ytm_pct"] = round(self.ytm * 100, 2)
        return d


class NewsItem(BaseModel):
    title: str
    text: str = ""
    date: str = ""
    source: str = ""
    link: str = ""
    score: Optional[float] = None


class NewsSearchResult(BaseModel):
    query: str
    news: List[NewsItem] = Field(default_factory=list)
    rag_hits: List[Dict[str, Any]] = Field(default_factory=list)
    news_count: int = 0


class RiskReview(BaseModel):
    """Вердикт Risk Officer-агента."""

    approved: bool = True
    risk_level: RiskLevel = RiskLevel.MEDIUM
    reasons: List[str] = Field(default_factory=list)
    requires_human_confirmation: bool = False
    blocked_recommendations: List[str] = Field(default_factory=list)


class AgentFinalResponse(BaseModel):
    """Финальный структурированный ответ агента для UI."""

    intent: IntentType = IntentType.GENERAL
    summary: str = ""
    bond_report: Optional[BondAnalysisReport] = None
    news: Optional[NewsSearchResult] = None
    risk_review: Optional[RiskReview] = None
    key_rate: Optional[float] = None
    intermediate_steps: List[str] = Field(default_factory=list)
    needs_human_input: bool = False
    human_prompt: Optional[str] = None
    raw_output: str = ""

    def to_ui_text(self) -> str:
        if self.needs_human_input and self.human_prompt:
            return f"⚠️ Требуется подтверждение:\n{self.human_prompt}\n\n{self.summary}"
        parts = [self.summary] if self.summary else []
        if self.bond_report:
            r = self.bond_report
            parts.append(
                f"\n📊 {r.bond.shortname or r.bond.isin or 'Облигация'}: "
                f"YTM={((r.ytm or 0)*100):.2f}%, риск={r.risk_level.value}"
            )
            if r.warnings:
                parts.append("⚠️ " + "; ".join(r.warnings))
        if self.risk_review and not self.risk_review.approved:
            parts.append(
                "🛑 Risk Officer: " + "; ".join(self.risk_review.reasons or ["отклонено"])
            )
        if self.key_rate is not None:
            parts.append(f"\n🔑 Ключевая ставка ЦБ: {self.key_rate*100:.2f}%")
        return "\n".join(parts) if parts else self.raw_output or "Нет данных."
