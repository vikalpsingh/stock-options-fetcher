from __future__ import annotations

from pathlib import Path

import app
import ipo_data_service
from company_research.services.company_detail_service import CompanyDetailService
from company_research.services.financial_calculator import calculated_pe
from company_research.services.financial_normalizer import normalize_flat_financial_row
from company_research.services.source_link_builder import (
    build_google_finance_url,
    build_yahoo_symbol,
    validate_yahoo_mapping,
)


def ipo_row(**overrides):
    row = {
        "company_name": "Quality IPO Limited",
        "symbol": "QUALITY",
        "exchange": "NSE",
        "ipo_type": "Mainboard",
        "kite_ltp": 210,
        "ipo_price": 100,
        "current_gain_pct": 110,
        "one_month_return_pct": 12,
        "three_month_return_pct": 18,
        "drawdown_from_52w_high_pct": -15,
        "market_cap": 5000,
        "pe_ratio": 22,
        "latest_revenue_growth_yoy": 25,
        "latest_pat_growth_yoy": 30,
        "opm_pct": 18,
        "roce": 24,
        "debt_to_equity": 0.3,
        "cfo_pat": 1.1,
        "promoter_holding": 62,
        "screener_url": "https://www.screener.in/company/QUALITY/",
        "source_url": "https://www.nseindia.com/get-quotes/equity?symbol=QUALITY",
        "lt_data_quality_score": 84,
        "lt_final_decision": "WAIT",
    }
    row.update(overrides)
    return row


def test_yahoo_and_google_symbol_builders_use_exchange_suffixes():
    assert build_yahoo_symbol({"exchange": "NSE", "symbol": "APSISAERO"}) == "APSISAERO.NS"
    assert build_yahoo_symbol({"exchange": "BSE", "bse_security_code": "544681"}) == "544681.BO"
    assert build_google_finance_url({"exchange": "NSE", "symbol": "KSHINTL"}) == "https://www.google.com/finance/quote/KSHINTL:NSE"
    assert build_google_finance_url({"exchange": "BSE", "bse_security_code": "544681"}) == "https://www.google.com/finance/quote/544681:BOM"


def test_yahoo_candidate_requires_company_name_match_before_verified():
    good = validate_yahoo_mapping({"exchange": "NSE", "symbol": "QUALITY", "company_name": "Quality IPO Limited"}, "Quality IPO Ltd")
    bad = validate_yahoo_mapping({"exchange": "NSE", "symbol": "QUALITY", "company_name": "Quality IPO Limited"}, "Different Industries Ltd")

    assert good["mapping_status"] == "VERIFIED"
    assert bad["mapping_status"] == "MISMATCH"


def test_financial_normalizer_maps_aliases_and_negative_pat_pe_is_nm():
    normalized = normalize_flat_financial_row(
        {
            "Total Revenue": "1000",
            "Operating Income": "180",
            "NetIncomeCommonStockholders": "-25",
            "Price to Earning": "18",
        },
        source_name="screener_csv",
        period="FY2026",
    )
    pe, warnings = calculated_pe(5000, -25, 4)

    assert normalized["metrics"]["sales"] == 1000
    assert normalized["metrics"]["operating_profit"] == 180
    assert normalized["metrics"]["pat"] == -25
    assert pe == "NM"
    assert warnings == []
    assert normalized["raw_values"][0]["source_name"] == "screener_csv"
    assert normalized["raw_values"][0]["period"] == "FY2026"


def test_company_snapshot_repository_preserves_history_and_deduplicates(tmp_path):
    service = CompanyDetailService(tmp_path / "company_research.db")
    first = service.save_snapshot_from_row(ipo_row(kite_ltp=210, pe_ratio=22))
    duplicate = service.save_snapshot_from_row(ipo_row(kite_ltp=210, pe_ratio=22))
    changed = service.save_snapshot_from_row(ipo_row(kite_ltp=220, pe_ratio=24))
    detail = service.detail(first["company_key"])

    assert first["market_saved"] is True
    assert duplicate["market_saved"] is False
    assert changed["market_saved"] is True
    market_history = [row for row in detail["history"] if row.get("ltp") is not None]
    assert len(market_history) == 2


def test_company_detail_evidence_is_local_database_only(tmp_path):
    service = CompanyDetailService(tmp_path / "company_research.db")
    result = service.save_snapshot_from_row(ipo_row())
    evidence = service.local_gpt_evidence(result["company_key"])

    assert evidence["identity"]["canonical_name"] == "Quality IPO Limited"
    assert evidence["market_snapshot"]["ltp"] == 210
    assert evidence["financial_snapshot"]["pe"] == "22.0" or evidence["financial_snapshot"]["pe"] == 22
    assert "sources" in evidence


def test_ipo_company_modal_renders_cached_data_without_iframe(monkeypatch, tmp_path):
    class FakeService:
        def detail(self, company_key):
            return {
                "identity": {
                    "company_key": company_key,
                    "canonical_name": "Quality IPO Limited",
                    "exchange": "NSE",
                    "nse_symbol": "QUALITY",
                    "kite_key": "NSE:QUALITY",
                },
                "row": ipo_row(),
                "market": {"ltp": 210, "one_month_return": 12, "drawdown_52w": -15, "liquidity_status": "GOOD"},
                "financial": {"pe": 22, "sales_yoy": 25, "pat_yoy": 30, "opm": 18, "roce": 24, "source": "cached_row"},
                "sources": [
                    {
                        "source_name": "SCREENER",
                        "source_url": "https://www.screener.in/company/QUALITY/",
                        "mapping_status": "AVAILABLE",
                        "updated_at": "2026-07-31T10:00:00",
                    }
                ],
                "history": [],
                "fetch_logs": [],
            }

    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "ipo.db")
    monkeypatch.setattr(app, "CompanyDetailService", lambda: FakeService())
    row = ipo_row()
    key = app.ipo_gpt_row_key(row)
    state = app.PageState(active_tab="ipo", ipo_year=2026, ipo_selected_company_key=key)
    state.ipo_dashboard = {
        "mode": "simple_performance",
        "upcoming_pipeline_version": ipo_data_service.IPO_UPCOMING_PIPELINE_VERSION,
        "year": 2026,
        "mainboard_top20": [],
        "sme_top20": [],
        "combined_top40": [row],
        "upcoming_next7": [],
        "messages": [],
        "summary": {},
    }

    html = app.render_ipo_panel(state)

    assert "Company Research" in html
    assert "Quality IPO Limited" in html
    assert "Refresh Market" in html
    assert "Refresh Financials" in html
    assert "Save Snapshot" in html
    assert "https://www.screener.in/company/QUALITY/" in html
    assert "<iframe" not in html[html.index("Company Research") :]

