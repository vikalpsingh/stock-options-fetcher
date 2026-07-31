from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class Decision(StrEnum):
    BUY = "BUY"
    WAIT = "WAIT"
    AVOID = "AVOID"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class ActionDetail(StrEnum):
    STAGGERED_ACCUMULATION = "STAGGERED_ACCUMULATION"
    TRACKING_POSITION = "TRACKING_POSITION"
    BUY_ON_CORRECTION = "BUY_ON_CORRECTION"
    WAIT_FOR_RESULTS = "WAIT_FOR_RESULTS"
    WAIT_FOR_CASH_FLOW = "WAIT_FOR_CASH_FLOW"
    WAIT_FOR_VALUATION = "WAIT_FOR_VALUATION"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    AVOID_QUALITY = "AVOID_QUALITY"
    AVOID_GOVERNANCE = "AVOID_GOVERNANCE"
    AVOID_LIQUIDITY = "AVOID_LIQUIDITY"
    AVOID_VALUATION_TRAP = "AVOID_VALUATION_TRAP"


class BuyZone(BaseModel):
    status: str
    reason: str = ""
    fair_value_low: float | None = None
    fair_value_base: float | None = None
    fair_value_high: float | None = None
    preferred_entry_low: float | None = None
    preferred_entry_high: float | None = None
    current_price: float | None = None
    upside_to_base: float | None = None
    downside_to_entry: float | None = None
    valuation_confidence: float = 0


class EvaluationOutput(BaseModel):
    schema_version: str = "1.0"
    company_name: str
    symbol: str
    research_date: date = Field(default_factory=date.today)
    data_quality_score: float
    data_quality_status: str
    investment_score: float
    score_breakdown: dict[str, float]
    hard_rule_blocks: list[str]
    python_provisional_decision: Decision
    maximum_allowed_decision: Decision
    gpt_proposed_decision: Decision | None = None
    final_decision: Decision
    action_detail: ActionDetail
    decision_confidence: float = Field(ge=0, le=100)
    buy_zone: BuyZone
    liquidity_score: float | None = None
    liquidity_status: str = ""
    maximum_allocation_pct: float = 0
    limit_order_only: bool = True
    reasons: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    upgrade_triggers: list[str] = Field(default_factory=list)
    downgrade_triggers: list[str] = Field(default_factory=list)
    next_result_metrics_to_watch: list[str] = Field(default_factory=list)
    snapshot_hash: str = ""
