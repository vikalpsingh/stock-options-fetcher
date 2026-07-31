from __future__ import annotations

from dataclasses import dataclass

from ..models.evaluation_input import EvaluationInput
from ..models.governance_snapshot import GovernanceStatus
from .sector_specific_metrics import sector_metric_coverage


INVESTMENT_WEIGHTS = {
    "sector_opportunity": 15,
    "business_quality": 15,
    "growth_quality": 20,
    "profitability": 15,
    "cash_flow_balance_sheet": 15,
    "valuation_comfort": 15,
    "governance": 5,
}


@dataclass(frozen=True)
class InvestmentScoreResult:
    score: float
    breakdown: dict[str, float]
    warnings: list[str]


def _scaled(value: float | None, target: float, weight: float) -> float:
    if value is None:
        return 0.0
    return round(max(0.0, min(1.0, value / target)) * weight, 2)


def calculate_investment_score(evidence: EvaluationInput) -> InvestmentScoreResult:
    metrics = evidence.financials
    coverage, sector_missing = sector_metric_coverage(evidence.sector, evidence.business.sector_metrics)
    sector_evidence = bool(evidence.business.sector_tailwinds and evidence.business.sources)
    business_evidence = bool(evidence.business.competitive_advantages and evidence.business.sources)
    revenue_growth = metrics.metric("revenue_cagr_3y") or metrics.metric("revenue_growth_yoy")
    pat_growth = metrics.metric("pat_cagr_3y") or metrics.metric("pat_growth_yoy")
    growth = None if revenue_growth is None or pat_growth is None else (revenue_growth + pat_growth) / 2
    roce = metrics.metric("roce")
    cfo_pat = metrics.metric("cfo_pat")
    debt = metrics.metric("debt_equity")
    valuation_ratio = (
        None
        if evidence.valuation.pe is None or evidence.valuation.peer_median_pe in {None, 0}
        else evidence.valuation.pe / evidence.valuation.peer_median_pe
    )
    breakdown = {
        "sector_opportunity": 15.0 if sector_evidence else 7.5 if evidence.sector else 0.0,
        "business_quality": round(15 * min(1.0, coverage / 100), 2) if business_evidence else 0.0,
        "growth_quality": _scaled(growth, 20, 20),
        "profitability": _scaled(roce, 20, 15),
        "cash_flow_balance_sheet": round(
            _scaled(cfo_pat, 1.0, 10) + (5 if debt is not None and debt <= 0.5 else 2 if debt is not None and debt <= 1 else 0),
            2,
        ),
        "valuation_comfort": (
            15.0 if valuation_ratio is not None and valuation_ratio <= 0.9
            else 10.0 if valuation_ratio is not None and valuation_ratio <= 1.1
            else 5.0 if valuation_ratio is not None and valuation_ratio <= 1.4
            else 0.0
        ),
        "governance": (
            5.0 if evidence.governance.status == GovernanceStatus.GREEN
            else 2.5 if evidence.governance.status == GovernanceStatus.YELLOW
            else 0.0
        ),
    }
    warnings = [f"Missing sector metric: {name}" for name in sector_missing]
    return InvestmentScoreResult(round(sum(breakdown.values()), 2), breakdown, warnings)
