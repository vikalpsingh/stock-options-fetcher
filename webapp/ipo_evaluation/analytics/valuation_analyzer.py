from __future__ import annotations

from ..models.evaluation_input import EvaluationInput
from ..models.evaluation_output import BuyZone
from .data_quality import DataQualityResult


def calculate_buy_zone(evidence: EvaluationInput, quality: DataQualityResult) -> BuyZone:
    missing: list[str] = []
    if quality.score < 80:
        missing.append("data_quality_below_80")
    if evidence.valuation.market_cap is None:
        missing.append("market_cap")
    if not evidence.valuation.share_count_reliable:
        missing.append("reliable_share_count")
    eps = evidence.financials.metric("eps")
    if eps is None or eps <= 0:
        missing.append("positive_normalized_eps")
    peer_pe = evidence.valuation.peer_median_pe
    if peer_pe is None or not evidence.peers:
        missing.append("peer_comparison")
    if missing:
        return BuyZone(
            status="NOT_CALCULABLE",
            reason="Missing: " + ", ".join(missing),
            current_price=evidence.market.ltp,
        )
    growth = evidence.financials.metric("pat_cagr_3y")
    justified_pe = min(peer_pe or 0, max(8.0, min(35.0, (growth or 12) * 1.1)))
    fair_base = round((eps or 0) * justified_pe, 2)
    fair_low = round(fair_base * 0.85, 2)
    fair_high = round(fair_base * 1.15, 2)
    entry_low = round(fair_base * 0.75, 2)
    entry_high = round(fair_base * 0.9, 2)
    current = evidence.market.ltp
    return BuyZone(
        status="CALCULATED",
        fair_value_low=fair_low,
        fair_value_base=fair_base,
        fair_value_high=fair_high,
        preferred_entry_low=entry_low,
        preferred_entry_high=entry_high,
        current_price=current,
        upside_to_base=None if current in {None, 0} else round((fair_base / current - 1) * 100, 2),
        downside_to_entry=None if current in {None, 0} else round((entry_high / current - 1) * 100, 2),
        valuation_confidence=min(100.0, quality.score),
    )
