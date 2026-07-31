from __future__ import annotations

import hashlib
import json
from typing import Iterable

from ..models.evaluation_input import EvaluationInput
from ..models.evaluation_output import ActionDetail, Decision, EvaluationOutput
from ..models.governance_snapshot import GovernanceStatus
from .data_quality import calculate_data_quality
from .governance_analyzer import analyze_governance
from .hard_rules import evaluate_hard_rules
from .investment_score import calculate_investment_score
from .liquidity_analyzer import analyze_liquidity
from .valuation_analyzer import calculate_buy_zone


DECISION_RANK = {
    Decision.DATA_INSUFFICIENT: 0,
    Decision.AVOID: 1,
    Decision.WAIT: 2,
    Decision.BUY: 3,
}


def apply_final_guardrail(
    python_provisional_decision: Decision | str,
    maximum_allowed_decision: Decision | str,
    gpt_decision: Decision | str,
    hard_rule_blocks: Iterable[str],
    *,
    data_quality_score: float = 100,
    governance_status: str = "GREEN",
    liquidity_status: str = "GOOD",
    valuation_available: bool = True,
    quarterly_available: bool = True,
    cash_flow_available: bool = True,
) -> Decision:
    provisional = Decision(python_provisional_decision)
    maximum = Decision(maximum_allowed_decision)
    proposed = Decision(gpt_decision)
    if data_quality_score < 65:
        return Decision.DATA_INSUFFICIENT
    if governance_status == GovernanceStatus.RED.value:
        return Decision.AVOID
    allowed = min(DECISION_RANK[provisional], DECISION_RANK[maximum])
    if hard_rule_blocks or liquidity_status == "ILLIQUID" or not valuation_available or not quarterly_available or not cash_flow_available:
        allowed = min(allowed, DECISION_RANK[Decision.WAIT])
    if 65 <= data_quality_score < 80:
        allowed = min(allowed, DECISION_RANK[Decision.WAIT])
    return proposed if DECISION_RANK[proposed] <= allowed else next(
        decision for decision, rank in DECISION_RANK.items() if rank == allowed
    )


def evaluate_company(evidence: EvaluationInput, gpt_decision: Decision | None = None) -> EvaluationOutput:
    governance = analyze_governance(evidence.governance)
    evidence = evidence.model_copy(update={"governance": governance})
    quality = calculate_data_quality(evidence)
    liquidity = analyze_liquidity(evidence.market, evidence.market_type)
    investment = calculate_investment_score(evidence)
    hard_rules = evaluate_hard_rules(evidence, quality, liquidity, investment.score)
    buy_zone = calculate_buy_zone(evidence, quality)
    if quality.score < 65 or not evidence.identity.is_valid:
        provisional = maximum = Decision.DATA_INSUFFICIENT
        action = ActionDetail.RESEARCH_ONLY
    elif hard_rules.avoid_triggers:
        provisional = maximum = Decision.AVOID
        action = (
            ActionDetail.AVOID_GOVERNANCE
            if "GOVERNANCE_RED" in hard_rules.avoid_triggers
            else ActionDetail.AVOID_QUALITY
        )
    elif quality.score < 80 or hard_rules.buy_blocks or investment.score < 78:
        provisional = maximum = Decision.WAIT
        action = (
            ActionDetail.WAIT_FOR_RESULTS
            if not evidence.financials.has_quarterly
            else ActionDetail.WAIT_FOR_CASH_FLOW
            if not evidence.financials.has_cash_flow
            else ActionDetail.WAIT_FOR_VALUATION
        )
    elif buy_zone.status != "CALCULATED" or (
        buy_zone.preferred_entry_high is not None
        and evidence.market.ltp is not None
        and evidence.market.ltp > buy_zone.preferred_entry_high
    ):
        provisional = maximum = Decision.WAIT
        action = ActionDetail.BUY_ON_CORRECTION
    else:
        provisional = maximum = Decision.BUY
        action = ActionDetail.STAGGERED_ACCUMULATION
    proposed = gpt_decision or provisional
    final = apply_final_guardrail(
        provisional,
        maximum,
        proposed,
        hard_rules.buy_blocks,
        data_quality_score=quality.score,
        governance_status=governance.status.value,
        liquidity_status=liquidity.status,
        valuation_available=evidence.valuation.has_data,
        quarterly_available=evidence.financials.has_quarterly,
        cash_flow_available=evidence.financials.has_cash_flow,
    )
    snapshot_payload = {
        "identity": evidence.identity.model_dump(mode="json"),
        "market_period": evidence.market.quote_timestamp.isoformat() if evidence.market.quote_timestamp else None,
        "financial_period": evidence.financials.annual_periods[-1].period if evidence.financials.annual_periods else None,
        "quarter": evidence.financials.quarterly_periods[-1].period if evidence.financials.quarterly_periods else None,
        "valuation_sources": [source.period for source in evidence.valuation.sources],
    }
    snapshot_hash = hashlib.sha256(
        json.dumps(snapshot_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    missing = list(dict.fromkeys([*quality.missing_fields, *quality.critical_missing]))
    confidence = min(100.0, quality.score * 0.7 + min(investment.score, 100) * 0.3)
    return EvaluationOutput(
        company_name=evidence.identity.canonical_name,
        symbol=evidence.identity.kite_tradingsymbol or evidence.identity.nse_symbol,
        data_quality_score=quality.score,
        data_quality_status=quality.status,
        investment_score=investment.score,
        score_breakdown=investment.breakdown,
        hard_rule_blocks=hard_rules.buy_blocks,
        python_provisional_decision=provisional,
        maximum_allowed_decision=maximum,
        gpt_proposed_decision=gpt_decision,
        final_decision=final,
        action_detail=action,
        decision_confidence=round(confidence, 2),
        buy_zone=buy_zone,
        liquidity_score=liquidity.score,
        liquidity_status=liquidity.status,
        maximum_allocation_pct=liquidity.maximum_allocation_pct if final == Decision.BUY else min(0.5, liquidity.maximum_allocation_pct),
        limit_order_only=True,
        reasons=[*hard_rules.wait_triggers, *hard_rules.avoid_triggers],
        key_risks=[*hard_rules.buy_blocks, *investment.warnings],
        missing_fields=missing,
        upgrade_triggers=["Complete missing evidence", "Quarterly growth and cash conversion improve", "Price enters preferred valuation range"],
        downgrade_triggers=["Governance red flag", "Negative CFO with rising receivables", "Leverage or margins deteriorate"],
        next_result_metrics_to_watch=["Revenue growth", "PAT growth", "Operating margin", "CFO/PAT", "Debtor days"],
        snapshot_hash=snapshot_hash,
    )
