from __future__ import annotations

import app
from sector_income import (
    SECTOR_SCORE_WEIGHTS,
    SECTOR_INCOME_UNIVERSE,
    calculate_sector_sell_on_rise_score,
    choose_default_sector,
    classify_fii_flow_regime,
    configured_sector_symbols,
    rank_all_sectors,
    rank_sector_candidates,
    sector_options,
    validate_sector_fno_symbols,
)


def test_sector_income_selector_contains_configured_sectors() -> None:
    options = sector_options()

    assert len(options) == len(SECTOR_INCOME_UNIVERSE)
    assert {"key": "INFORMATION_TECHNOLOGY", "label": "Information Technology"} in options
    assert {"key": "FINANCIAL_SERVICES", "label": "Financial Services"} in options
    assert configured_sector_symbols("HEALTHCARE_PHARMA")[:3] == ["SUNPHARMA", "DRREDDY", "CIPLA"]


def test_sector_income_scorecard_weights_and_default_sector_are_deterministic() -> None:
    assert sum(SECTOR_SCORE_WEIGHTS.values()) == 100

    ranking = rank_all_sectors(generated_at="2026-08-30T10:00:00+00:00")

    assert len(ranking["all_sectors"]) == len(SECTOR_INCOME_UNIVERSE)
    assert len(ranking["top_sectors"]) == 3
    assert ranking["selected_sector"] == ""
    assert ranking["message"] == "NO SECTOR CURRENTLY QUALIFIES"
    assert ranking["generated_at"] == "2026-08-30T10:00:00+00:00"

    assert (
        choose_default_sector(
            [
                {"sector_key": "HIGH_SCORE_BLOCKED", "decision": "BLOCKED", "sector_score": 99},
                {"sector_key": "LOWER_SCORE_READY", "decision": "CONFIRM_REQUIRED", "sector_score": 45},
            ]
        )
        == "LOWER_SCORE_READY"
    )


def test_sector_income_fii_flow_regimes_do_not_use_ownership_as_standalone_signal() -> None:
    assert classify_fii_flow_regime(-52281, 2530) == "RELIEF_RALLY_SELL_ON_RISE"
    assert classify_fii_flow_regime(-7789, -3322) == "STRUCTURAL_WEAKNESS"
    assert classify_fii_flow_regime(25344, -720) == "PROFIT_BOOKING_ONLY"
    assert classify_fii_flow_regime(25344, 720) == "ACCUMULATION - AVOID SYSTEMATIC CALL SELLING"

    high_aum_accumulation = calculate_sector_sell_on_rise_score(
        "METALS_MINING",
        sector_technical={"sector_regime": "BULLISH", "distance_50_pct": 2.0},
        valid_fno_count=4,
    )

    assert high_aum_accumulation["fii_aum_pct"] == 3.8
    assert high_aum_accumulation["fii_regime"] == "ACCUMULATION - AVOID SYSTEMATIC CALL SELLING"
    assert high_aum_accumulation["decision"] != "GREEN - SCAN TOP 4"


def test_sector_income_validates_fno_symbols_without_substitution() -> None:
    rows = validate_sector_fno_symbols("INFORMATION_TECHNOLOGY", {"TCS", "INFY", "LTM"})
    by_symbol = {row["symbol"]: row for row in rows}

    assert by_symbol["TCS"]["fno_eligible"] is True
    assert by_symbol["WIPRO"]["fno_eligible"] is False
    assert by_symbol["WIPRO"]["status"] == "F&O UNAVAILABLE - ORDER BLOCKED"


def test_sector_income_ranking_returns_top_four_sell_on_rise_candidates() -> None:
    sector_score = calculate_sector_sell_on_rise_score(
        "INFORMATION_TECHNOLOGY",
        sector_technical={"sector_regime": "BEARISH_RALLY", "distance_50_pct": -1.0},
        valid_fno_count=6,
    )
    rows = [
        {"symbol": "TCS", "fno_eligible": True, "stock_regime": "BEARISH_RALLY", "day_change_pct": 2.5, "distance_from_50dma_pct": -0.5, "distance_from_200dma_pct": -4, "liquidity_view": "GREEN"},
        {"symbol": "INFY", "fno_eligible": True, "stock_regime": "BEARISH", "day_change_pct": 2.0, "distance_from_50dma_pct": -1.0, "distance_from_200dma_pct": -6, "liquidity_view": "AMBER"},
        {"symbol": "HCLTECH", "fno_eligible": True, "stock_regime": "MIXED", "day_change_pct": 1.8, "distance_from_50dma_pct": 0.3, "distance_from_200dma_pct": -1, "liquidity_view": "GREEN"},
        {"symbol": "TECHM", "fno_eligible": True, "stock_regime": "BEARISH_RALLY", "day_change_pct": 5.2, "distance_from_50dma_pct": -0.2, "distance_from_200dma_pct": -2, "liquidity_view": "GREEN"},
        {"symbol": "WIPRO", "fno_eligible": True, "stock_regime": "BULLISH", "day_change_pct": 3.0, "distance_from_50dma_pct": 4, "distance_from_200dma_pct": 6, "liquidity_view": "GREEN"},
    ]

    ranked = rank_sector_candidates(rows, sector_score, top_n=4)

    assert len(ranked) == 4
    assert ranked[0]["symbol"] == "TCS"
    assert ranked[0]["final_decision"] in {"ALLOWED", "CONFIRM_REQUIRED"}
    assert "WIPRO" not in [row["symbol"] for row in ranked]


def test_sector_income_page_renders_tab_selector_tables_and_execution_link() -> None:
    opportunity = {
        "rank": 1,
        "symbol": "TCS",
        "strategy_type": "BEAR_CALL_SPREAD",
        "sector_score": 72.5,
        "stock_score": 81.0,
        "fii_regime": "RELIEF_RALLY_SELL_ON_RISE",
        "cmp": 3200,
        "day_change_pct": 2.25,
        "expiry": "2026-09-29",
        "sell_leg_tradingsymbol": "TCS26SEP3400CE",
        "buy_leg_tradingsymbol": "TCS26SEP3600CE",
        "sell_leg_premium": 42.0,
        "buy_leg_premium": 12.0,
        "net_credit": 30.0,
        "max_gain": 6750,
        "max_loss": 38250,
        "pop_estimate": 74.0,
        "return_on_risk_pct": 17.65,
        "pair_liquidity_condition": "AMBER",
        "risk_decision": "APPROVED",
    }
    state = app.PageState(
        active_tab="sector-income",
        sector_income_sector="INFORMATION_TECHNOLOGY",
        sector_income_rows=[
            {
                "symbol": "TCS",
                "cmp": 3200,
                "day_change_pct": 2.25,
                "stock_regime": "BEARISH_RALLY",
                "dma_50": 3300,
                "dma_200": 3400,
                "distance_from_50dma_pct": -3.03,
                "distance_from_200dma_pct": -5.88,
                "fno_eligible": True,
                "stock_score": 81.0,
                "final_decision": "ALLOWED",
                "reasons": ["controlled rise suitable for review"],
            }
        ],
        sector_income_score={
            "sector_key": "INFORMATION_TECHNOLOGY",
            "sector_label": "Information Technology",
            "sector_score": 72.5,
            "fii_aum_pct": 5.1,
            "fortnight_flow_cr": 2530,
            "one_year_flow_cr": -52281,
            "fii_regime": "RELIEF_RALLY_SELL_ON_RISE",
            "sector_regime": "BEARISH_RALLY",
            "valid_fno_count": 6,
            "decision": "GREEN - SCAN TOP 4",
            "status": "GREEN",
            "confidence": "HIGH",
            "liquidity_status": "GREEN",
            "rebound_risk": "LOW",
            "component_scores": {
                "trend_structure": {"score": 18, "weight": 20, "detail": "Sector regime BEARISH_RALLY"},
                "rise_into_resistance": {"score": 12, "weight": 15, "detail": "Today 1.80%, 50DMA dist -1.00%"},
            },
            "reasons": ["negative one-year FII flow with current relief inflow"],
        },
        sector_income_ranking={
            "selected_sector": "INFORMATION_TECHNOLOGY",
            "top_sectors": [
                {
                    "rank": 1,
                    "sector_key": "INFORMATION_TECHNOLOGY",
                    "sector_label": "Information Technology",
                    "sector_score": 72.5,
                    "status": "GREEN",
                    "confidence": "HIGH",
                    "decision": "SCAN_TOP_4",
                    "liquidity_status": "GREEN",
                    "rebound_risk": "LOW",
                    "valid_fno_count": 6,
                    "fii_regime": "RELIEF_RALLY_SELL_ON_RISE",
                    "reasons": ["negative one-year FII flow with current relief inflow"],
                },
                {
                    "rank": 2,
                    "sector_key": "HEALTHCARE_PHARMA",
                    "sector_label": "Healthcare & Pharmaceuticals",
                    "sector_score": 66.0,
                    "status": "GREEN",
                    "confidence": "HIGH",
                    "decision": "SCAN_TOP_4",
                    "liquidity_status": "GREEN",
                    "rebound_risk": "LOW",
                    "valid_fno_count": 6,
                    "fii_regime": "RELIEF_RALLY_SELL_ON_RISE",
                    "reasons": ["negative one-year FII flow with current relief inflow"],
                },
                {
                    "rank": 3,
                    "sector_key": "AUTOMOBILE_AUTO_COMPONENTS",
                    "sector_label": "Automobile & Auto Components",
                    "sector_score": 61.0,
                    "status": "AMBER",
                    "confidence": "HIGH",
                    "decision": "CONFIRM_REQUIRED",
                    "liquidity_status": "GREEN",
                    "rebound_risk": "LOW",
                    "valid_fno_count": 6,
                    "fii_regime": "RELIEF_RALLY_SELL_ON_RISE",
                    "reasons": ["negative one-year FII flow with current relief inflow"],
                },
            ],
            "all_sectors": [],
            "generated_at": "2026-08-30T10:00:00+00:00",
        },
        sector_income_show_rank_modal=True,
        sector_income_cards=[],
        sector_income_holding_positions=[],
        sector_income_opportunities=[opportunity],
        sector_income_selected_index="0",
        sector_income_generated_at="2026-08-30T10:00:00+05:30",
    )

    html = app.render_sector_income_panel(state)

    assert 'id="sector-income-panel"' in html
    assert "SECTOR-Income" in app.render_page(state).decode("utf-8")
    assert "Information Technology" in html
    assert "Top 3 Sector Ranking" in html
    assert 'id="sector-income-rank-modal"' in html
    assert 'formaction="/sector-income/recalculate-sectors"' in html
    assert "Sector Decision & FII Flow" in html
    assert "Current Kite Option Holdings / CE Pair Status" in html
    assert "Pair Order Monitor" in html
    assert 'formaction="/sector-income/monitor-run"' in html
    assert 'formaction="/sector-income/scheduler-start"' in html
    assert 'formaction="/sector-income/scheduler-stop"' in html
    assert 'id="sector-income-opportunity-table"' in html
    assert 'formaction="/sector-income/preview" name="sector_income_selected_index" value="0"' in html
    assert 'formaction="/sector-income/submit"' in html
    assert 'formaction="/sector-income/close-popup"' in html
    assert 'formaction="/dhan-it/submit"' not in html
    assert "TCS26SEP3400CE" in html
