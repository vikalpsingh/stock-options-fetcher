from __future__ import annotations

from dataclasses import dataclass

from ..models.evaluation_input import EvaluationInput
from ..models.governance_snapshot import GovernanceStatus
from .data_quality import DataQualityResult
from .liquidity_analyzer import LiquidityResult


@dataclass(frozen=True)
class HardRuleResult:
    buy_blocks: list[str]
    avoid_triggers: list[str]
    wait_triggers: list[str]


def evaluate_hard_rules(
    evidence: EvaluationInput,
    quality: DataQualityResult,
    liquidity: LiquidityResult,
    investment_score: float,
) -> HardRuleResult:
    buy_blocks: list[str] = []
    avoid: list[str] = []
    wait: list[str] = []
    metrics = evidence.financials
    if not evidence.identity.is_valid:
        buy_blocks.append("SECURITY_IDENTITY_UNRESOLVED")
    if quality.score < 80:
        buy_blocks.append("DATA_QUALITY_BELOW_80")
    if not evidence.financials.has_quarterly:
        buy_blocks.append("LATEST_QUARTERLY_RESULT_UNAVAILABLE")
    if evidence.valuation.market_cap is None:
        buy_blocks.append("MARKET_CAP_UNAVAILABLE")
    if not evidence.valuation.has_data:
        buy_blocks.append("VALUATION_UNAVAILABLE")
    if not evidence.financials.has_cash_flow:
        buy_blocks.append("CASH_FLOW_UNAVAILABLE")
    if evidence.governance.status == GovernanceStatus.RED:
        buy_blocks.append("GOVERNANCE_RED")
        avoid.append("GOVERNANCE_RED")
    if evidence.governance.status == GovernanceStatus.DATA_PENDING:
        wait.append("GOVERNANCE_DATA_PENDING")
    annual_cfo = metrics.metrics.get("annual_cfo_values")
    if isinstance(annual_cfo, list) and len(annual_cfo) >= 2 and all(
        isinstance(value, (int, float)) and value < 0 for value in annual_cfo[-2:]
    ):
        buy_blocks.append("CFO_NEGATIVE_TWO_PERIODS")
    cumulative = metrics.metric("cumulative_cfo_pat_3y")
    if cumulative is not None and cumulative < 0.5:
        buy_blocks.append("CUMULATIVE_CFO_PAT_BELOW_0_50")
    cfo = metrics.metric("cash_flow_from_operations")
    debtor_change = metrics.metric("debtor_days_change_pct")
    if cfo is not None and cfo < 0 and debtor_change is not None and debtor_change > 20:
        buy_blocks.append("NEGATIVE_CFO_RISING_DEBTORS")
        avoid.append("NEGATIVE_CFO_RISING_DEBTORS")
    interest = metrics.metric("interest_coverage")
    if interest is not None and interest < 2:
        buy_blocks.append("LOW_INTEREST_COVERAGE")
    if liquidity.status == "ILLIQUID":
        buy_blocks.append("ILLIQUID_STOCK")
    if evidence.ipo.listed_quarters is not None and evidence.ipo.listed_quarters < 2:
        buy_blocks.append("LESS_THAN_TWO_LISTED_QUARTERS")
        wait.append("WAIT_FOR_LISTED_HISTORY")
    if investment_score < 55:
        avoid.append("INVESTMENT_SCORE_BELOW_55")
    revenue_growth = metrics.metric("revenue_growth_yoy")
    pat_growth = metrics.metric("pat_growth_yoy")
    if revenue_growth is not None and pat_growth is not None and revenue_growth < 0 and pat_growth < 0:
        avoid.append("DECLINING_REVENUE_AND_PAT")
    if quality.score < 80:
        wait.append("INCOMPLETE_EVIDENCE")
    if evidence.valuation.pe is not None and evidence.valuation.peer_median_pe:
        if evidence.valuation.pe > evidence.valuation.peer_median_pe * 1.4:
            wait.append("VALUATION_ABOVE_PEERS")
    return HardRuleResult(list(dict.fromkeys(buy_blocks)), list(dict.fromkeys(avoid)), list(dict.fromkeys(wait)))
