from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.evaluation_output import Decision


class ScoredView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float = Field(ge=0, le=100)
    summary: str


class SectorView(ScoredView):
    india_opportunity: str
    global_opportunity: str
    risks: list[str]


class BusinessQualityView(ScoredView):
    moat: str
    scalability: str
    weaknesses: list[str]


class GrowthView(ScoredView):
    revenue_outlook: str
    profit_outlook: str
    margin_outlook: str
    key_growth_drivers: list[str]
    growth_risks: list[str]


class FinancialQualityView(ScoredView):
    profitability: str
    capital_efficiency: str
    balance_sheet: str
    cash_flow: str
    working_capital: str


class ValuationView(ScoredView):
    status: str
    peer_comparison: str
    buy_zone_status: str
    buy_zone_low: float | None
    buy_zone_high: float | None


class GovernanceView(ScoredView):
    status: str
    flags: list[str]


class PeerView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    selected_company_advantages: list[str]
    selected_company_disadvantages: list[str]
    best_peer: str
    peer_ranking: list[str]


class Allocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maximum_portfolio_pct: float = Field(ge=0, le=100)
    position_type: Literal["NONE", "TRACKING", "STAGGERED", "CORE"]
    rationale: str


class GptEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    company_name: str
    symbol: str
    research_date: str
    decision: Decision
    action_detail: str
    decision_confidence: float = Field(ge=0, le=100)
    executive_summary: str
    why_now: str
    sector_view: SectorView
    business_quality: BusinessQualityView
    growth_view: GrowthView
    financial_quality: FinancialQualityView
    valuation_view: ValuationView
    governance_view: GovernanceView
    peer_view: PeerView
    key_strengths: list[str]
    key_risks: list[str]
    missing_evidence: list[str]
    upgrade_triggers: list[str]
    downgrade_triggers: list[str]
    next_result_metrics_to_watch: list[str]
    allocation: Allocation
    python_decision_respected: bool
    evidence_quality_comment: str
    investor_conclusion: str
