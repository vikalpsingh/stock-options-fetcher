from __future__ import annotations

import app
import pytest
from fii_sector_pdf_parser import (
    FiiSectorPdfError,
    FiiSectorPdfParser,
    map_fii_sector_name,
    normalize_indian_currency,
    validate_pdf_upload,
)
from fii_sector_repository import FiiSectorSnapshotRepository
from sector_income import (
    SECTOR_SCORE_WEIGHTS,
    SECTOR_INCOME_UNIVERSE,
    SectorIncomeConfigRepository,
    calculate_sector_sell_on_rise_score,
    choose_default_sector,
    classify_fii_flow_regime,
    configured_sector_symbols,
    sector_income_selected_symbols,
    rank_all_sectors,
    rank_sector_candidates,
    sector_options,
    validate_sector_fno_symbols,
)


FII_FIXTURE_TEXT = """
30 Aug 2026
Financial Services
27.1% of AUM
+6,950 Cr Last fortnight
-1,35,301 Cr 1Y net flow
Automobile and Auto Components
7.1% of AUM
+4,393 Cr Last fortnight
-28,630 Cr 1Y net flow
Healthcare
6.8% of AUM
+2,910 Cr Last fortnight
-24,869 Cr 1Y net flow
Capital Goods
6.5% of AUM
-1,556 Cr Last fortnight
+16,914 Cr 1Y net flow
Oil, Gas & Consumable Fuels
6.0% of AUM
+492 Cr Last fortnight
-15,517 Cr 1Y net flow
Information Technology
5.1% of AUM
+2,530 Cr Last fortnight
-52,281 Cr 1Y net flow
Telecommunication
5.0% of AUM
-3,322 Cr Last fortnight
-7,789 Cr 1Y net flow
Fast Moving Consumer Goods
3.9% of AUM
-189 Cr Last fortnight
-48,177 Cr 1Y net flow
Metals & Mining
3.8% of AUM
+720 Cr Last fortnight
+25,344 Cr 1Y net flow
Consumer Services
3.7% of AUM
+3,398 Cr Last fortnight
-14,766 Cr 1Y net flow
Power
3.4% of AUM
-2,216 Cr Last fortnight
-17,292 Cr 1Y net flow
Consumer Durables
2.6% of AUM
+1,472 Cr Last fortnight
-2,192 Cr 1Y net flow
Realty
1.9% of AUM
-1,206 Cr Last fortnight
-13,202 Cr 1Y net flow
Construction Materials
1.4% of AUM
+384 Cr Last fortnight
-9,604 Cr 1Y net flow
"""


def test_fii_sector_parser_validates_upload_and_numbers() -> None:
    validate_pdf_upload(b"%PDF-1.7\nbody", "fii.pdf", "application/pdf")

    assert normalize_indian_currency("₹ -1,35,301 Cr") == -135301.0
    assert normalize_indian_currency("▲ + 6,950 Cr") == 6950.0
    assert normalize_indian_currency("▼ -1,556 Cr") == -1556.0
    assert normalize_indian_currency("1.00 Cr") == 1.0
    assert map_fii_sector_name("Automobile and Auto Components") == "AUTOMOBILE_AUTO_COMPONENTS"
    assert map_fii_sector_name("Unknown Theme") == "UNMAPPED"

    with pytest.raises(FiiSectorPdfError):
        validate_pdf_upload(b"not-pdf", "fii.txt", "text/plain")

    with pytest.raises(FiiSectorPdfError):
        validate_pdf_upload(b"%PDF-1.7" + (b"x" * (11 * 1024 * 1024)), "fii.pdf", "application/pdf")


def test_fii_sector_parser_extracts_valid_screener_layout_text() -> None:
    snapshot = FiiSectorPdfParser().parse_text(FII_FIXTURE_TEXT, source_filename="fii.pdf")
    by_sector = {row.sector_code: row for row in snapshot.rows}

    assert snapshot.extraction_status == "VALID"
    assert snapshot.recognized_sector_count >= 8
    assert by_sector["INFORMATION_TECHNOLOGY"].fii_aum_pct == 5.1
    assert by_sector["INFORMATION_TECHNOLOGY"].fortnight_flow_cr == 2530.0
    assert by_sector["INFORMATION_TECHNOLOGY"].one_year_flow_cr == -52281.0
    assert by_sector["INFORMATION_TECHNOLOGY"].fii_regime == "RELIEF_RALLY_SELL_ON_RISE"
    assert all(row.validation_status == "VALID" for row in snapshot.valid_rows())


def test_fii_sector_parser_rejects_insufficient_or_duplicate_extraction() -> None:
    with pytest.raises(FiiSectorPdfError):
        FiiSectorPdfParser().parse_text(
            """
            Information Technology
            5.1% of AUM
            +2,530 Cr Last fortnight
            -52,281 Cr 1Y net flow
            """,
            source_filename="fii.pdf",
        )


def test_fii_sector_repository_keeps_pending_until_activation(tmp_path) -> None:
    repo = FiiSectorSnapshotRepository(tmp_path / "fii.db")
    snapshot = FiiSectorPdfParser().parse_text(FII_FIXTURE_TEXT, source_filename="fii.pdf")

    pending = repo.save_pending_snapshot(snapshot)

    assert pending["active"] is False
    assert repo.get_active_snapshot() is None

    active = repo.activate_snapshot(int(pending["snapshot_id"]))

    assert active["active"] is True
    assert active["recognized_sector_count"] >= 8
    assert repo.get_active_snapshot()["snapshot_id"] == pending["snapshot_id"]


def test_sector_score_repository_persists_latest_calculation(tmp_path) -> None:
    repo = FiiSectorSnapshotRepository(tmp_path / "fii.db")
    saved = repo.save_sector_score_snapshot(
        selected_sector="INFORMATION_TECHNOLOGY",
        score={"sector_key": "INFORMATION_TECHNOLOGY", "sector_score": 88.5},
        ranking={
            "selected_sector": "INFORMATION_TECHNOLOGY",
            "top_sectors": [{"sector_key": "INFORMATION_TECHNOLOGY", "sector_score": 88.5}],
            "all_sectors": [],
        },
        source="TEST",
    )

    latest = repo.get_latest_sector_score_snapshot()

    assert saved["score_snapshot_id"] == latest["score_snapshot_id"]
    assert latest["selected_sector"] == "INFORMATION_TECHNOLOGY"
    assert latest["score"]["sector_score"] == 88.5
    assert latest["ranking"]["top_sectors"][0]["sector_score"] == 88.5


def test_sector_income_parent_loads_saved_score_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(app, "enrich_dhan_market_data_from_kite", lambda *args, **kwargs: (None, [], {}))
    monkeypatch.setattr(app, "stock_moving_averages", lambda *args, **kwargs: {})
    monkeypatch.setattr(app, "load_dhan_it_holding_position_rows", lambda: [])
    monkeypatch.setattr(app, "build_sector_income_opportunities", lambda *args, **kwargs: ([], []))

    repo = FiiSectorSnapshotRepository(app.APP_DB_PATH)
    repo.save_sector_score_snapshot(
        selected_sector="HEALTHCARE_PHARMA",
        score={
            "sector_key": "HEALTHCARE_PHARMA",
            "sector_label": "Healthcare & Pharmaceuticals",
            "sector_score": 91.25,
            "component_scores": {},
        },
        ranking={
            "selected_sector": "HEALTHCARE_PHARMA",
            "top_sectors": [
                {
                    "rank": 1,
                    "sector_key": "HEALTHCARE_PHARMA",
                    "sector_label": "Healthcare & Pharmaceuticals",
                    "sector_score": 91.25,
                    "status": "GREEN",
                    "confidence": "HIGH",
                    "decision": "SCAN_TOP_4",
                }
            ],
            "all_sectors": [],
        },
        source="TEST_PARENT_LOAD",
    )

    state = app.PageState(active_tab="sector-income")
    app.load_sector_income_state(state)

    assert state.sector_income_sector == "HEALTHCARE_PHARMA"
    assert state.sector_income_score["sector_score"] == 91.25
    assert state.sector_income_ranking["top_sectors"][0]["sector_score"] == 91.25


def test_sector_income_selector_contains_configured_sectors() -> None:
    options = sector_options()

    assert len(options) == len(SECTOR_INCOME_UNIVERSE)
    assert {"key": "INFORMATION_TECHNOLOGY", "label": "Information Technology"} in options
    assert {"key": "FINANCIAL_SERVICES", "label": "Financial Services"} in options
    assert configured_sector_symbols("HEALTHCARE_PHARMA")[:3] == ["SUNPHARMA", "DRREDDY", "CIPLA"]


def test_sector_income_config_repository_persists_three_sector_four_company_scope(tmp_path) -> None:
    repo = SectorIncomeConfigRepository(tmp_path / "sector.db")

    saved = repo.save(
        ["INFORMATION_TECHNOLOGY", "HEALTHCARE_PHARMA", "AUTOMOBILE_AUTO_COMPONENTS", "BANKING"],
        {
            "INFORMATION_TECHNOLOGY": ["TCS", "INFY", "HCLTECH", "TECHM", "WIPRO"],
            "HEALTHCARE_PHARMA": ["SUNPHARMA", "DRREDDY"],
            "AUTOMOBILE_AUTO_COMPONENTS": ["MARUTI", "M&M", "TATAMOTORS", "EICHERMOT"],
        },
    )
    loaded = repo.load()

    assert loaded["selected_sectors"] == ["INFORMATION_TECHNOLOGY", "HEALTHCARE_PHARMA", "AUTOMOBILE_AUTO_COMPONENTS"]
    assert loaded["sector_companies"]["INFORMATION_TECHNOLOGY"] == ["TCS", "INFY", "HCLTECH", "TECHM"]
    assert saved["source"] == "USER_CONFIGURED"
    assert sector_income_selected_symbols(loaded["selected_sectors"], loaded["sector_companies"])[:4] == [
        "TCS",
        "INFY",
        "HCLTECH",
        "TECHM",
    ]


def test_sector_income_scorecard_weights_and_default_sector_are_deterministic() -> None:
    assert sum(SECTOR_SCORE_WEIGHTS.values()) == 100

    ranking = rank_all_sectors(generated_at="2026-08-30T10:00:00+00:00")

    assert len(ranking["all_sectors"]) == len(SECTOR_INCOME_UNIVERSE)
    assert len(ranking["top_sectors"]) == 3
    assert ranking["selected_sector"] in SECTOR_INCOME_UNIVERSE
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


def test_sector_income_fii_snapshot_has_thirty_percent_weightage() -> None:
    snapshot = FiiSectorPdfParser().parse_text(FII_FIXTURE_TEXT, source_filename="fii.pdf")
    rows = [row.to_dict() for row in snapshot.rows]
    score = calculate_sector_sell_on_rise_score(
        "INFORMATION_TECHNOLOGY",
        fii_snapshot_rows=rows,
        sector_technical={"sector_regime": "BEARISH_RALLY", "today_change_pct": 1.5, "distance_50_pct": -1.0},
        valid_fno_count=6,
    )
    metals = calculate_sector_sell_on_rise_score(
        "METALS_MINING",
        fii_snapshot_rows=rows,
        sector_technical={"sector_regime": "BEARISH_RALLY", "today_change_pct": 1.5, "distance_50_pct": -1.0},
        valid_fno_count=6,
    )

    assert SECTOR_SCORE_WEIGHTS["fii_flow_regime"] == 30
    assert score["fii_source"] == "UPLOADED_PDF"
    assert score["component_scores"]["fii_flow_regime"]["score"] == 30
    assert metals["component_scores"]["fii_flow_regime"]["score"] == 0


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
                    "score": 56.0,
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
        sector_income_show_config_modal=True,
        sector_income_selected_sectors=["INFORMATION_TECHNOLOGY", "HEALTHCARE_PHARMA", "AUTOMOBILE_AUTO_COMPONENTS"],
        sector_income_sector_company_selection={
            "INFORMATION_TECHNOLOGY": ["TCS", "INFY", "HCLTECH", "TECHM"],
            "HEALTHCARE_PHARMA": ["SUNPHARMA", "DRREDDY", "CIPLA", "LUPIN"],
            "AUTOMOBILE_AUTO_COMPONENTS": ["MARUTI", "M&M", "TATAMOTORS", "EICHERMOT"],
        },
        sector_income_pending_fii_snapshot={
            "snapshot_id": 99,
            "report_date": "2026-08-30",
            "source_filename": "fii.pdf",
            "uploaded_at": "2026-08-30T10:00:00+00:00",
            "recognized_sector_count": 14,
            "rows": [row.to_dict() for row in FiiSectorPdfParser().parse_text(FII_FIXTURE_TEXT, source_filename="fii.pdf").rows],
        },
        sector_income_fii_upload_message="Extracted 14 valid FII sector row(s).",
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
    assert "72.50" in html
    assert "Top 3 Sector Ranking" in html
    assert 'id="sector-income-rank-modal"' in html
    assert "SECTOR-Income - FII Upload & Sector Score Details" in html
    assert 'name="sector_income_fii_pdf" type="file"' in html
    assert 'formaction="/sector-income/upload-fii-pdf"' in html
    assert 'formaction="/sector-income/activate-fii-snapshot"' in html
    assert 'formaction="/sector-income/apply-sector"' in html
    assert 'name="sector_income_ranking_json"' in html
    assert 'name="sector_income_score_json"' in html
    assert "Detailed Sector Score Comparison - All Sectors" in html
    assert 'formaction="/sector-income/recalculate-sectors"' in html
    assert "Sector Decision & FII Flow" in html
    assert "Current Kite Option Holdings / CE Pair Status" in html
    assert "Pair Order Monitor" in html
    assert "Configure SECTOR-Income Sectors & Companies" in html
    assert 'formaction="/sector-income/config-save"' in html
    assert 'name="sector_income_config_sectors" value="HEALTHCARE_PHARMA"' in html
    assert 'name="sector_income_config_company_INFORMATION_TECHNOLOGY" value="TCS"' in html
    assert "Configured Sector Call-Spread Cards" in html
    assert 'formaction="/sector-income/monitor-run"' in html
    assert 'formaction="/sector-income/scheduler-start"' in html
    assert 'formaction="/sector-income/scheduler-stop"' in html
    assert 'id="sector-income-opportunity-table"' in html
    assert 'formaction="/sector-income/preview" name="sector_income_selected_index" value="0"' in html
    assert 'formaction="/sector-income/submit"' in html
    assert 'formaction="/sector-income/close-popup"' in html
    assert 'formaction="/dhan-it/submit"' not in html
    assert "TCS26SEP3400CE" in html
