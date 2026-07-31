from __future__ import annotations

from dataclasses import dataclass

from ..models.evaluation_input import EvaluationInput


DATA_QUALITY_WEIGHTS = {
    "identity": 10,
    "kite_quote": 10,
    "historical_market": 10,
    "annual_financials": 15,
    "quarterly_results": 20,
    "valuation": 10,
    "cash_flow": 10,
    "shareholding": 5,
    "business_disclosures": 5,
    "peer_data": 5,
}


@dataclass(frozen=True)
class DataQualityResult:
    score: float
    status: str
    breakdown: dict[str, float]
    missing_fields: list[str]
    critical_missing: list[str]


def calculate_data_quality(evidence: EvaluationInput) -> DataQualityResult:
    available = {
        "identity": evidence.identity.is_valid,
        "kite_quote": evidence.market.quote_available,
        "historical_market": evidence.market.average_volume_20d is not None,
        "annual_financials": evidence.financials.has_annual,
        "quarterly_results": evidence.financials.has_quarterly,
        "cash_flow": evidence.financials.has_cash_flow,
        "shareholding": evidence.governance.has_data,
        "valuation": evidence.valuation.has_data,
        "business_disclosures": evidence.business.has_disclosures,
        "peer_data": bool(evidence.peers),
    }
    breakdown = {
        key: float(DATA_QUALITY_WEIGHTS[key] if is_available else 0)
        for key, is_available in available.items()
    }
    score = sum(breakdown.values())
    status = (
        "HIGH_CONFIDENCE_DATA"
        if score >= 90
        else "GOOD_DATA"
        if score >= 80
        else "PARTIAL_DATA"
        if score >= 65
        else "INSUFFICIENT_DATA"
    )
    critical_checks = {
        "identity": evidence.identity.is_valid,
        "current_market_price": evidence.market.quote_available,
        "market_cap": evidence.valuation.market_cap is not None,
        "latest_annual_revenue": evidence.financials.metric("revenue") is not None,
        "latest_annual_pat": evidence.financials.metric("pat") is not None,
        "latest_quarterly_results": evidence.financials.has_quarterly,
        "debt": evidence.financials.metric("debt_equity") is not None,
        "cash_flow": evidence.financials.has_cash_flow,
        "valuation": evidence.valuation.has_data,
        "promoter_holding": evidence.governance.promoter_holding is not None,
    }
    return DataQualityResult(
        score=score,
        status=status,
        breakdown=breakdown,
        missing_fields=[key for key, present in available.items() if not present],
        critical_missing=[key for key, present in critical_checks.items() if not present],
    )
