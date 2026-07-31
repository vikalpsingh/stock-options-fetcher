from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .analytics.decision_engine import evaluate_company
from .models.business_snapshot import BusinessSnapshot
from .models.evaluation_input import EvaluationInput, IpoSnapshot, ValuationSnapshot
from .models.evaluation_output import EvaluationOutput
from .models.financial_snapshot import FinancialSnapshot
from .models.governance_snapshot import GovernanceSnapshot, GovernanceStatus
from .models.market_snapshot import MarketSnapshot
from .models.security import SecurityIdentity


def _number(value: Any) -> float | None:
    try:
        if value in {None, "", "N/A", "NA"}:
            return None
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def legacy_evaluation_input(row: dict[str, Any]) -> EvaluationInput:
    """Adapt a legacy IPO row without falsely promoting unprovenanced fields.

    This compatibility path exposes a safe decision in the current table. Live
    provider snapshots should construct ``EvaluationInput`` directly so annual,
    quarterly and valuation evidence carries period/source metadata.
    """
    mapping_status = str(row.get("mapping_status") or row.get("verification_status") or "")
    if row.get("is_listed_verified") and mapping_status.upper() not in {"VERIFIED", "PARTIALLY_VERIFIED"}:
        mapping_status = "PARTIALLY_VERIFIED"
    token = _number(row.get("instrument_token"))
    identity = SecurityIdentity(
        canonical_name=str(row.get("company_name") or "Unknown IPO"),
        legal_name=str(row.get("legal_name") or ""),
        primary_exchange=str(row.get("exchange") or ""),
        segment=str(row.get("segment") or row.get("ipo_type") or ""),
        nse_symbol=str(row.get("symbol") or ""),
        isin=str(row.get("isin") or ""),
        kite_tradingsymbol=str(row.get("resolved_tradingsymbol") or row.get("symbol") or ""),
        kite_key=str(row.get("kite_key") or ""),
        instrument_token=int(token) if token is not None else None,
        mapping_status=mapping_status,
        kite_verified=bool(row.get("kite_verified")),
        quote_verified=bool(row.get("quote_verified")),
    )
    timestamp: datetime | None = None
    raw_timestamp = row.get("quote_timestamp")
    if raw_timestamp:
        try:
            timestamp = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
        except ValueError:
            timestamp = None
    market = MarketSnapshot(
        ltp=_number(row.get("kite_ltp") or row.get("ltp")),
        quote_timestamp=timestamp,
        day_return_pct=_number(row.get("day_return_pct") or row.get("daily_gain_pct")),
        one_week_return_pct=_number(row.get("one_week_return_pct") or row.get("weekly_gain_pct")),
        one_month_return_pct=_number(row.get("one_month_return_pct")),
        three_month_return_pct=_number(row.get("three_month_return_pct")),
        six_month_return_pct=_number(row.get("six_month_return_pct")),
        one_year_return_pct=_number(row.get("one_year_return_pct")),
        return_since_listing_pct=_number(row.get("return_since_listing_pct")),
        gain_from_ipo_price_pct=_number(row.get("gain_from_ipo_price_pct") or row.get("current_gain_pct")),
        drawdown_from_52w_high_pct=_number(row.get("drawdown_from_52w_high_pct")),
        average_volume_20d=_number(row.get("average_volume_20d")),
        average_traded_value_20d=_number(row.get("average_traded_value_20d")),
        bid_ask_spread_pct=_number(row.get("bid_ask_spread_pct")),
        zero_volume_days_20d=int(_number(row.get("zero_volume_days_20d")) or 0)
        if row.get("zero_volume_days_20d") is not None
        else None,
        circuit_limit_frequency=_number(row.get("circuit_limit_frequency")),
    )
    financials = FinancialSnapshot(
        metrics={
            "revenue": _number(row.get("revenue")),
            "pat": _number(row.get("pat")),
            "eps": _number(row.get("eps")),
            "revenue_growth_yoy": _number(row.get("latest_revenue_growth_yoy") or row.get("revenue_growth_yoy")),
            "pat_growth_yoy": _number(row.get("latest_pat_growth_yoy") or row.get("pat_growth_yoy")),
            "revenue_cagr_3y": _number(row.get("revenue_cagr_3y")),
            "pat_cagr_3y": _number(row.get("pat_cagr_3y")),
            "roce": _number(row.get("roce")),
            "roe": _number(row.get("roe")),
            "debt_equity": _number(row.get("debt_to_equity")),
            "cash_flow_from_operations": _number(row.get("cash_flow_from_operations")),
            "cfo_pat": _number(row.get("cfo_pat")),
            "cumulative_cfo_pat_3y": _number(row.get("cumulative_cfo_pat_3y")),
            "debtor_days": _number(row.get("debtor_days")),
            "debtor_days_change_pct": _number(row.get("debtor_days_change_pct")),
            "interest_coverage": _number(row.get("interest_coverage")),
        }
    )
    governance_status_raw = str(row.get("governance_status") or row.get("governance_flag") or "DATA_PENDING").upper()
    try:
        governance_status = GovernanceStatus(governance_status_raw.replace("DATA PENDING", "DATA_PENDING"))
    except ValueError:
        governance_status = GovernanceStatus.DATA_PENDING
    governance = GovernanceSnapshot(
        promoter_holding=_number(row.get("promoter_holding")),
        promoter_change_qoq=_number(row.get("promoter_holding_change")),
        promoter_pledge=_number(row.get("pledge_pct") or row.get("promoter_pledge")),
        pledge_change_qoq=_number(row.get("pledge_change")),
        status=governance_status,
    )
    valuation = ValuationSnapshot(
        market_cap=_number(row.get("market_cap") or row.get("current_market_cap")),
        pe=_number(row.get("pe_ratio")),
        pb=_number(row.get("pb_ratio")),
        ps=_number(row.get("ps_ratio")),
        ev_ebitda=_number(row.get("ev_ebitda")),
        peer_median_pe=_number(row.get("peer_median_pe") or row.get("industry_pe")),
        peer_median_ev_ebitda=_number(row.get("peer_median_ev_ebitda")),
        share_count_reliable=bool(row.get("share_count_reliable")),
    )
    evidence = EvaluationInput(
        identity=identity,
        ipo=IpoSnapshot(
            ipo_year=int(_number(row.get("ipo_year")) or datetime.now(timezone.utc).year),
            listing_date=str(row.get("listing_date") or ""),
            ipo_price=_number(row.get("ipo_price") or row.get("issue_price")),
            listing_price=_number(row.get("listing_price")),
            issue_size=_number(row.get("issue_size")),
            ipo_market_cap=_number(row.get("ipo_market_cap")),
            current_return_pct=_number(row.get("current_gain_pct") or row.get("gain_from_ipo_pct")),
            listed_quarters=int(_number(row.get("listed_quarters")) or 0)
            if row.get("listed_quarters") is not None
            else None,
        ),
        market=market,
        financials=financials,
        business=BusinessSnapshot(
            business_summary=str(row.get("business_snapshot") or ""),
            business_model_subtype=str(row.get("business_model_subtype") or ""),
            competitive_advantages=list(row.get("competitive_advantages") or []),
            sector_tailwinds=list(row.get("sector_tailwinds") or []),
            india_opportunity=str(row.get("india_opportunity") or ""),
            global_opportunity=str(row.get("global_opportunity") or ""),
            sector_metrics=dict(row.get("sector_metrics") or {}),
        ),
        governance=governance,
        valuation=valuation,
        sector=str(row.get("sector") or ""),
        market_type=str(row.get("ipo_type") or row.get("market_type") or "Mainboard"),
    )
    return evidence


def evaluate_legacy_ipo_row(row: dict[str, Any]) -> EvaluationOutput:
    return evaluate_company(legacy_evaluation_input(row))


def evaluation_fields(evaluation: EvaluationOutput) -> dict[str, Any]:
    entry = evaluation.buy_zone
    buy_zone = (
        f"{entry.preferred_entry_low:.2f}-{entry.preferred_entry_high:.2f}"
        if entry.preferred_entry_low is not None and entry.preferred_entry_high is not None
        else entry.status
    )
    return {
        "lt_data_quality_score": evaluation.data_quality_score,
        "lt_data_quality_status": evaluation.data_quality_status,
        "lt_investment_score": evaluation.investment_score,
        "lt_python_decision": evaluation.python_provisional_decision.value,
        "lt_gpt_decision": evaluation.gpt_proposed_decision.value if evaluation.gpt_proposed_decision else "NOT_RUN",
        "lt_final_decision": evaluation.final_decision.value,
        "lt_decision_confidence": evaluation.decision_confidence,
        "lt_buy_zone": buy_zone,
        "lt_allocation": f"{evaluation.maximum_allocation_pct:.2f}%",
        "lt_key_risk": evaluation.key_risks[0] if evaluation.key_risks else "None",
        "lt_missing_evidence": "; ".join(evaluation.missing_fields),
        "lt_snapshot_hash": evaluation.snapshot_hash,
    }
