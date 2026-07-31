from __future__ import annotations

from datetime import date
from typing import Any

from ..analytics.data_quality import calculate_data_quality
from ..analytics.peer_comparison import calculate_peer_medians
from ..models.evaluation_input import EvaluationInput
from ..models.evaluation_output import EvaluationOutput


def build_evidence_package(
    evidence: EvaluationInput,
    evaluation: EvaluationOutput,
) -> dict[str, Any]:
    quality = calculate_data_quality(evidence)
    all_sources = [
        *evidence.ipo.sources,
        *evidence.financials.sources,
        *evidence.business.sources,
        *evidence.governance.sources,
        *evidence.valuation.sources,
    ]
    return {
        "run_metadata": {
            "research_date": date.today().isoformat(),
            "snapshot_id": evaluation.snapshot_hash,
            "ipo_year": evidence.ipo.ipo_year,
            "analysis_type": evidence.analysis_type,
            "data_quality_score": quality.score,
            "data_freshness": (
                evidence.market.quote_timestamp.isoformat()
                if evidence.market.quote_timestamp
                else "UNKNOWN"
            ),
        },
        "identity": {
            "company_name": evidence.identity.canonical_name,
            "legal_name": evidence.identity.legal_name,
            "symbol": evidence.identity.kite_tradingsymbol,
            "exchange": evidence.identity.primary_exchange,
            "segment": evidence.identity.segment,
            "isin": evidence.identity.isin,
            "kite_key": evidence.identity.kite_key,
            "identity_verified": evidence.identity.is_valid,
        },
        "ipo": evidence.ipo.model_dump(mode="json", exclude={"sources"}),
        "market": evidence.market.model_dump(mode="json"),
        "business": evidence.business.model_dump(mode="json", exclude={"sources"}),
        "financials": {
            "annual_periods": [period.model_dump(mode="json") for period in evidence.financials.annual_periods],
            "quarterly_periods": [period.model_dump(mode="json") for period in evidence.financials.quarterly_periods],
            **evidence.financials.metrics,
        },
        "valuation": {
            **evidence.valuation.model_dump(mode="json", exclude={"sources"}),
            "buy_zone": evaluation.buy_zone.model_dump(mode="json"),
        },
        "governance": evidence.governance.model_dump(mode="json", exclude={"sources"}),
        "peers": [peer.model_dump(mode="json") for peer in evidence.peers],
        "peer_medians": calculate_peer_medians(evidence.peers),
        "python_evaluation": {
            "data_quality_score": evaluation.data_quality_score,
            "investment_score": evaluation.investment_score,
            "hard_rule_blocks": evaluation.hard_rule_blocks,
            "provisional_decision": evaluation.python_provisional_decision.value,
            "maximum_allowed_decision": evaluation.maximum_allowed_decision.value,
            "score_breakdown": evaluation.score_breakdown,
        },
        "missing_fields": evaluation.missing_fields,
        "sources": [source.model_dump(mode="json") for source in all_sources],
    }
