from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ipo_evaluation.analytics.decision_engine import apply_final_guardrail, evaluate_company
from ipo_evaluation.analytics.liquidity_analyzer import analyze_liquidity
from ipo_evaluation.analytics.peer_comparison import calculate_peer_medians
from ipo_evaluation.analytics.ratio_calculator import safe_divide
from ipo_evaluation.analytics.return_calculator import calculate_period_returns, get_close_on_or_before, normalise_daily_candles
from ipo_evaluation.analytics.sector_specific_metrics import is_financial_sector, sector_metric_coverage
from ipo_evaluation.gpt.batch_evaluator import match_batch_outputs
from ipo_evaluation.gpt.response_validator import GptResponseValidationError, validate_gpt_response
from ipo_evaluation.models.business_snapshot import BusinessSnapshot
from ipo_evaluation.models.evaluation_input import EvaluationInput, IpoSnapshot, ValuationSnapshot
from ipo_evaluation.models.evaluation_output import Decision
from ipo_evaluation.models.financial_snapshot import EvidenceValue, FinancialPeriod, FinancialSnapshot, SourceEvidence
from ipo_evaluation.models.governance_snapshot import GovernanceSnapshot, GovernanceStatus
from ipo_evaluation.models.market_snapshot import MarketSnapshot
from ipo_evaluation.models.peer_snapshot import PeerRelationship, PeerSnapshot
from ipo_evaluation.models.security import SecurityIdentity
from ipo_evaluation.reports.html_report import render_html_report
from ipo_evaluation.storage.repositories import EvaluationRepository


def source(group: str = "financials") -> SourceEvidence:
    return SourceEvidence(
        field_group=group,
        source_name="NSE filing",
        source_url="https://example.test/filing",
        period="FY2026",
        fetched_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        is_audited=True,
    )


def period(name: str) -> FinancialPeriod:
    return FinancialPeriod(period=name)


def strong_evidence(**updates) -> EvaluationInput:
    evidence = EvaluationInput(
        identity=SecurityIdentity(
            canonical_name="Quality IPO",
            primary_exchange="NSE",
            segment="EQ",
            nse_symbol="QUALITY",
            kite_tradingsymbol="QUALITY",
            kite_key="NSE:QUALITY",
            instrument_token=123,
            mapping_status="VERIFIED",
            kite_verified=True,
            quote_verified=True,
        ),
        ipo=IpoSnapshot(
            ipo_year=2026,
            listing_date="2025-07-01",
            ipo_price=100,
            listing_price=110,
            listed_quarters=4,
            sources=[source("ipo")],
        ),
        market=MarketSnapshot(
            ltp=200,
            quote_timestamp=datetime(2026, 7, 29, tzinfo=timezone.utc),
            average_volume_20d=500_000,
            average_traded_value_20d=100_000_000,
            bid_ask_spread_pct=0.2,
            zero_volume_days_20d=0,
            circuit_limit_frequency=0,
            drawdown_from_52w_high_pct=-20,
        ),
        financials=FinancialSnapshot(
            annual_periods=[period("FY2024"), period("FY2025"), period("FY2026")],
            quarterly_periods=[period("Q3 FY2026"), period("Q4 FY2026")],
            metrics={
                "revenue": 1000,
                "pat": 120,
                "eps": 10,
                "revenue_growth_yoy": 25,
                "pat_growth_yoy": 30,
                "revenue_cagr_3y": 24,
                "pat_cagr_3y": 28,
                "roce": 25,
                "roe": 22,
                "debt_equity": 0.2,
                "cash_flow_from_operations": 130,
                "cfo_pat": 1.08,
                "cumulative_cfo_pat_3y": 1.0,
                "debtor_days": 45,
                "debtor_days_change_pct": -5,
                "interest_coverage": 8,
            },
            sources=[source()],
        ),
        business=BusinessSnapshot(
            business_summary="Critical engineering products for domestic and export customers.",
            business_model_subtype="precision engineering",
            competitive_advantages=["certifications", "customer qualification"],
            sector_tailwinds=["India manufacturing capex"],
            india_opportunity="Import substitution",
            global_opportunity="Export growth",
            sector_metrics={
                "order_book": 1200,
                "order_book_to_sales": 1.2,
                "capacity_utilization": 75,
                "asset_turnover": 2,
                "working_capital_days": 60,
            },
            sources=[source("business")],
        ),
        governance=GovernanceSnapshot(
            promoter_holding=62,
            promoter_change_qoq=0,
            promoter_pledge=0,
            status=GovernanceStatus.GREEN,
            sources=[source("governance")],
        ),
        valuation=ValuationSnapshot(
            market_cap=5000,
            pe=20,
            pb=3,
            ps=2,
            ev_ebitda=12,
            peer_median_pe=25,
            peer_median_pb=4,
            peer_median_ps=3,
            peer_median_ev_ebitda=15,
            share_count_reliable=True,
            sources=[source("valuation")],
        ),
        peers=[
            PeerSnapshot(
                company_name="Exact Peer",
                symbol="PEER",
                industry="engineering",
                business_model_subtype="precision engineering",
                relationship=PeerRelationship.EXACT_PEER,
                metrics={"pe": 25, "roce": 20},
                financial_data_available=True,
                liquidity_score=90,
            )
        ],
        sector="manufacturing engineering",
        market_type="Mainboard",
    )
    return evidence.model_copy(update=updates)


def test_missing_identity_produces_data_insufficient():
    evidence = strong_evidence(
        identity=SecurityIdentity(canonical_name="Unknown", mapping_status="UNRESOLVED")
    )
    assert evaluate_company(evidence).final_decision == Decision.DATA_INSUFFICIENT


def test_missing_financial_data_produces_data_insufficient():
    assert evaluate_company(strong_evidence(financials=FinancialSnapshot())).final_decision == Decision.DATA_INSUFFICIENT


def test_data_quality_75_cannot_return_buy():
    assert apply_final_guardrail(Decision.BUY, Decision.BUY, Decision.BUY, [], data_quality_score=75) == Decision.WAIT


def test_governance_red_returns_avoid():
    governance = strong_evidence().governance.model_copy(
        update={"status": GovernanceStatus.RED, "flags": ["auditor_resignation"]}
    )
    assert evaluate_company(strong_evidence(governance=governance)).final_decision == Decision.AVOID


def test_negative_cfo_and_rising_debtors_blocks_buy():
    financials = strong_evidence().financials.model_copy(
        update={"metrics": {**strong_evidence().financials.metrics, "cash_flow_from_operations": -10, "debtor_days_change_pct": 35}}
    )
    result = evaluate_company(strong_evidence(financials=financials))
    assert result.final_decision == Decision.AVOID
    assert "NEGATIVE_CFO_RISING_DEBTORS" in result.hard_rule_blocks


def test_expensive_high_quality_company_returns_wait():
    valuation = strong_evidence().valuation.model_copy(update={"pe": 60})
    market = strong_evidence().market.model_copy(update={"ltp": 500})
    assert evaluate_company(strong_evidence(valuation=valuation, market=market)).final_decision == Decision.WAIT


def test_high_quality_reasonably_valued_company_can_buy():
    result = evaluate_company(strong_evidence())
    assert result.investment_score >= 78
    assert result.final_decision == Decision.BUY


def test_gpt_cannot_upgrade_python_wait_to_buy():
    assert apply_final_guardrail(Decision.WAIT, Decision.WAIT, Decision.BUY, []) == Decision.WAIT


def test_gpt_can_downgrade_python_buy_to_wait():
    assert apply_final_guardrail(Decision.BUY, Decision.BUY, Decision.WAIT, []) == Decision.WAIT


def test_missing_valuation_blocks_numeric_buy_zone():
    result = evaluate_company(strong_evidence(valuation=ValuationSnapshot()))
    assert result.buy_zone.status == "NOT_CALCULABLE"
    assert result.buy_zone.preferred_entry_low is None


def test_null_fields_remain_null_not_zero():
    assert safe_divide(None, 10) is None
    assert safe_divide(10, None) is None
    assert safe_divide(10, 0) is None


def test_weekly_return_uses_close_on_or_before_calendar_date():
    candles = normalise_daily_candles(
        [
            {"date": "2026-07-20", "close": 100, "volume": 10},
            {"date": "2026-07-24", "close": 110, "volume": 10},
            {"date": "2026-07-31", "close": 121, "volume": 10},
        ]
    )

    assert get_close_on_or_before(candles, datetime(2026, 7, 26, tzinfo=timezone.utc).date()) == 110
    returns, warnings = calculate_period_returns(candles)
    assert returns["one_week_return_pct"] == 10
    assert returns["one_year_return_pct"] is None
    assert "INSUFFICIENT_1Y_HISTORY" in warnings


def test_peer_medians_ignore_null_values():
    peers = [
        PeerSnapshot(company_name="A", symbol="A", relationship=PeerRelationship.EXACT_PEER, metrics={"pe": None}),
        PeerSnapshot(company_name="B", symbol="B", relationship=PeerRelationship.EXACT_PEER, metrics={"pe": 20}),
        PeerSnapshot(company_name="C", symbol="C", relationship=PeerRelationship.EXACT_PEER, metrics={"pe": 30}),
    ]
    assert calculate_peer_medians(peers)["pe"] == 25


def test_financial_sector_uses_sector_specific_metrics():
    assert is_financial_sector("NBFC financial services")
    coverage, missing = sector_metric_coverage("financial services", {"aum_growth": 20, "nim": 4})
    assert coverage < 100
    assert "gnpa" in missing


def test_sme_liquidity_risk_caps_allocation():
    market = MarketSnapshot(
        average_traded_value_20d=1_000_000,
        bid_ask_spread_pct=3,
        zero_volume_days_20d=4,
        circuit_limit_frequency=0.3,
    )
    result = analyze_liquidity(market, "SME")
    assert result.maximum_allocation_pct <= 0.5
    assert result.limit_order_only


def test_cached_unchanged_snapshot_can_be_reused(tmp_path):
    repository = EvaluationRepository(tmp_path / "evaluation.db")
    evaluation = evaluate_company(strong_evidence())
    repository.save(evaluation, company_key="QUALITY")
    assert repository.find_unchanged("QUALITY", evaluation.snapshot_hash) is not None


def test_structured_output_rejects_malformed_gpt_response():
    with pytest.raises(GptResponseValidationError):
        validate_gpt_response({"decision": "BUY"}, evaluate_company(strong_evidence()))


def test_batch_output_is_matched_by_custom_id():
    rows = match_batch_outputs(
        ['{"custom_id":"QUALITY_abc","response":{"status_code":200}}', '{"bad":true}']
    )
    assert set(rows) == {"QUALITY_abc"}


def test_old_research_is_not_overwritten(tmp_path):
    repository = EvaluationRepository(tmp_path / "evaluation.db")
    evaluation = evaluate_company(strong_evidence())
    first = repository.save(evaluation, company_key="QUALITY")
    second = repository.save(evaluation, company_key="QUALITY")
    assert first != second
    assert len(repository.list_runs("QUALITY")) == 2


def test_html_report_has_no_external_assets():
    report = render_html_report(evaluate_company(strong_evidence()))
    assert "<style>" in report
    assert "stylesheet" not in report.lower()
    assert "https://" not in report


def test_every_financial_number_requires_period_and_source():
    with pytest.raises(ValidationError):
        EvidenceValue(
            value=100,
            period="",
            unit="INR crore",
            source_name="",
            source_url="https://example.test",
            fetched_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        )
