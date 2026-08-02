from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3
import sys
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

import app
import ipo_data_service
FETCH_NSE_UPCOMING_IPOS = ipo_data_service.fetch_nse_upcoming_ipos
from ipo_cache import load_or_generate, make_ipo_cache_key
from ipo_data_service import (
    IPO_NO_VERIFIED_DATA_MESSAGE,
    IPO_SIMPLE_EXPORT_FIELDS,
    IPO_SNAPSHOT_FIELDS,
    build_ipo_value_investor_prompt,
    build_ipo_dashboard,
    build_simple_ipo_performance_dashboard,
    export_ipo_records_csv,
    load_ipo_snapshots,
    save_ipo_top10_snapshot,
    selected_ipo_rows_for_value_analysis,
)
from ipo_scoring_engine import filter_multibaggers_or_all, score_ipo_company
from ipo_screener_engine import score_quarterly_results
from ipo.symbol_resolution.symbol_resolver import (
    load_symbol_overrides,
    normalize_company_key,
    resolve_ipo_identity,
)
from ipo.utils.company_name_cleaner import clean_display_company_name
from ipo.utils.ipo_price_cleaner import clean_price as clean_ipo_price


def chittorgarh_table(rows: str) -> str:
    return f"""
    <table>
      <tr>
        <th>Company</th>
        <th>Symbol</th>
        <th>ISIN</th>
        <th>Listing Date</th>
        <th>Issue Price</th>
        <th>CMP</th>
        <th>Current Gain</th>
        <th>Market Cap</th>
      </tr>
      {rows}
    </table>
    """


def table_html(page_html: str, table_id: str = "ipo-combined-table") -> str:
    start = page_html.index(f'id="{table_id}"')
    end = page_html.index("</table>", start)
    return page_html[start:end]


def table_header_html(page_html: str, table_id: str = "ipo-combined-table") -> str:
    table = table_html(page_html, table_id)
    start = table.index("<thead")
    end = table.index("</thead>", start)
    return table[start:end]


def header_count(page_html: str, table_id: str = "ipo-combined-table") -> int:
    header = table_header_html(page_html, table_id)
    return header.count("<th ") + header.count("<th>")


@pytest.fixture(autouse=True)
def offline_ipo_sources(monkeypatch):
    monkeypatch.setenv("IPO_DATA_MODE", "production")
    monkeypatch.setattr(
        ipo_data_service,
        "fetch_chittorgarh_listed_ipos",
        lambda year: {"records": [], "source": "test listed source", "error": ""},
    )
    monkeypatch.setattr(
        ipo_data_service,
        "fetch_nse_upcoming_ipos",
        lambda today=None: {"records": [], "source": "test nse source", "error": ""},
    )
    monkeypatch.setattr(
        ipo_data_service,
        "fetch_ipowatch_upcoming_ipos",
        lambda today=None: {"records": [], "source": "test upcoming source", "error": ""},
    )
    monkeypatch.setattr(
        ipo_data_service,
        "enrich_listed_ipos_with_screener",
        lambda records, max_records=6: (records, []),
    )


def verified_live_record(**overrides):
    record = {
        "company_name": "Live Quality IPO",
        "symbol": "LIVEIPO",
        "isin": "INE000X01010",
        "exchange": "NSE",
        "ipo_year": 2026,
        "listing_date": "2026-07-10",
        "issue_price": 100,
        "ipo_price": 100,
        "listing_price": 130,
        "current_price": 260,
        "return_from_issue_pct": 160,
        "return_from_listing_pct": 100,
        "gain_from_ipo_pct": 160,
        "drawdown_from_52w_high_pct": -24,
        "sector": "Capital markets infrastructure",
        "theme": "AMC/financialization",
        "market_type": "Mainboard",
        "market_cap": 22000,
        "current_market_cap": 22000,
        "ipo_market_cap": 8500,
        "data_source": "Chittorgarh public IPO report",
        "last_updated_at": "2026-07-19T10:00:00",
        "screener_url": "https://www.screener.in/company/LIVEIPO/",
        "revenue_growth_yoy": 28,
        "latest_revenue_growth_yoy": 28,
        "profit_growth_yoy": 30,
        "pat_growth_yoy": 30,
        "latest_pat_growth_yoy": 30,
        "eps_growth_yoy": 25,
        "roe": 19,
        "roce": 21,
        "debt_to_equity": 0.1,
        "current_ratio": 1.6,
        "operating_margin": 24,
        "opm_trend_pct": 1,
        "net_profit_margin": 13,
        "pe_ratio": 32,
        "industry_pe": 42,
        "peer_median_pe": 42,
        "promoter_holding": 62,
        "promoter_holding_change": 0,
        "fii_dii_holding": 14,
        "fii_dii_change": 0,
        "pledge_pct": 0,
        "pledge_change": 0,
        "cfo_pat": 0.9,
        "fcf": 100,
        "debtor_days": 45,
        "inventory_days": 30,
        "cash_conversion_cycle": 75,
    }
    record.update(overrides)
    return record


def test_quarterly_results_score_rewards_strong_execution():
    result = score_quarterly_results(
        verified_live_record(
            ebitda_growth_yoy=27,
            debtor_days_change_pct=-4,
            inventory_days_change_pct=3,
        )
    )

    assert result.score is not None
    assert result.score >= 80
    assert result.rating == "STRONG"
    assert result.coverage_pct == 100
    assert "revenue growth" in result.explanation


def test_quarterly_results_score_flags_deterioration():
    result = score_quarterly_results(
        verified_live_record(
            latest_revenue_growth_yoy=-8,
            ebitda_growth_yoy=-15,
            latest_pat_growth_yoy=-20,
            eps_growth_yoy=-18,
            opm_trend_pct=-5,
            roce=7,
            cfo_pat=0.2,
            debt_to_equity=2.5,
            debtor_days_change_pct=35,
        )
    )

    assert result.score is not None
    assert result.score < 50
    assert result.rating == "WEAK"
    assert "PAT growth -20.0%" in result.explanation


def test_quarterly_results_score_handles_missing_and_invalid_data():
    missing = score_quarterly_results({"symbol": "PENDING"})
    invalid = score_quarterly_results(None)  # type: ignore[arg-type]

    assert missing.score is None
    assert missing.rating == "DATA UNAVAILABLE"
    assert missing.warnings
    assert invalid.score is None
    assert "invalid" in invalid.explanation


def test_ipo_score_exposes_quarterly_score_and_explanation():
    scored = score_ipo_company(
        verified_live_record(
            ebitda_growth_yoy=27,
            debtor_days_change_pct=-4,
            inventory_days_change_pct=3,
        )
    )

    assert scored["quarterly_results_score"] >= 80
    assert scored["quarterly_results_rating"] == "STRONG"
    assert scored["quarterly_results_explanation"]


def test_clean_display_company_name_removes_known_trailing_identifier_only():
    assert clean_display_company_name("Apsis AerocomAPSISAERO", "APSISAERO") == "Apsis Aerocom"
    assert clean_display_company_name("Indo SMC544681", "", "544681") == "Indo SMC"
    assert clean_display_company_name("Symbolic Systems Limited", "SYS") == "Symbolic Systems Limited"


def test_source_current_price_is_not_promoted_to_kite_ltp():
    row = ipo_data_service._enrich_simple_ipo_decision(
        verified_live_record(
            company_name="Source Price IPO",
            current_price=153,
            ltp=None,
            kite_ltp=None,
            quote_verified=False,
        )
    )

    assert row["source_current_price"] == 153
    assert row["kite_ltp"] is None
    assert row["market_data_status"] == "UNVERIFIED_SOURCE_PRICE"


def simple_perf_record(index: int, ipo_type: str, gain: float, listed_year: int = 2026) -> dict:
    prefix = "SME" if ipo_type.lower() == "sme" else "MAIN"
    ipo_price = 100 + index
    current_price = round(ipo_price * (1 + gain / 100), 2)
    return {
        "company_name": f"{prefix} IPO {index}",
        "symbol": f"{prefix}{index}",
        "isin": f"INE{prefix[:3]}{index:05d}",
        "exchange": "SME" if ipo_type.lower() == "sme" else "NSE",
        "ipo_year": listed_year,
        "listing_date": f"{listed_year}-07-{min(index, 28):02d}",
        "ipo_price": ipo_price,
        "issue_price": ipo_price,
        "listing_price": ipo_price + 5,
        "current_price": current_price,
        "gain_from_ipo_pct": gain,
        "return_from_issue_pct": gain,
        "return_from_listing_pct": 5,
        "issue_size": f"{100 + index} Cr",
        "ipo_market_cap": 1000 + index,
        "market_cap": 1800 + index,
        "current_market_cap": 1800 + index,
        "sector": "Manufacturing capex" if ipo_type.lower() != "sme" else "EMS/electronics",
        "theme": "Manufacturing capex" if ipo_type.lower() != "sme" else "EMS/electronics",
        "revenue_growth_yoy": 22,
        "latest_revenue_growth_yoy": 22,
        "profit_growth_yoy": 24,
        "pat_growth_yoy": 24,
        "latest_pat_growth_yoy": 24,
        "eps_growth_yoy": 20,
        "roe": 18,
        "roce": 22,
        "debt_to_equity": 0.2,
        "current_ratio": 1.4,
        "operating_margin": 18,
        "opm_trend_pct": 0,
        "net_profit_margin": 10,
        "pe_ratio": 28,
        "industry_pe": 36,
        "peer_median_pe": 36,
        "promoter_holding": 60,
        "promoter_holding_change": 0,
        "fii_dii_holding": 10,
        "fii_dii_change": 0,
        "pledge_pct": 0,
        "pledge_change": 0,
        "cfo_pat": 0.8,
        "fcf": 50,
        "debtor_days": 45,
        "inventory_days": 30,
        "cash_conversion_cycle": 75,
        "market_type": "SME" if ipo_type.lower() == "sme" else "Mainboard",
        "source_url": f"https://www.chittorgarh.com/{prefix.lower()}{index}",
    }


def test_ipo_dashboard_defaults_to_upcoming_and_multibaggers(tmp_path):
    dashboard = build_ipo_dashboard(
        2026,
        "Latest Available",
        tmp_path / "ipo.db",
        True,
        today=date(2026, 7, 19),
    )

    assert dashboard["upcoming"] == []
    assert dashboard["listed"] == []
    assert dashboard["listed_tracker"] == []
    assert dashboard["top10"] == []
    assert dashboard["quarterly_monitor"] == []
    assert dashboard["validation_report"]["total_rows_loaded"] == 0
    assert dashboard["validation_report"]["eligible_for_scoring"] == 0
    assert dashboard["research_decision"]["outcome"] == IPO_NO_VERIFIED_DATA_MESSAGE
    assert any(IPO_NO_VERIFIED_DATA_MESSAGE in message for message in dashboard["messages"])


def test_ipo_positive_return_filter_replaces_legacy_multibagger_filter():
    records = [
        {"symbol": "LOSSIPO", "gain_from_ipo_pct": -5},
        {"symbol": "FLATIPO", "gain_from_ipo_pct": 0},
        {"symbol": "POSIPO", "gain_from_ipo_pct": 12},
    ]

    filtered, message = filter_multibaggers_or_all(records)

    assert [row["symbol"] for row in filtered] == ["POSIPO"]
    assert "positive return" in message


def test_ipo_cache_reuses_daily_payload_until_force_refresh(tmp_path):
    db_path = tmp_path / "ipo.db"
    calls = {"count": 0}

    def generate():
        calls["count"] += 1
        return {"value": calls["count"]}

    cache_key = make_ipo_cache_key(2026, "Q1", "dashboard")

    assert load_or_generate(db_path, cache_key, generate, today=date(2026, 7, 19))["value"] == 1
    assert load_or_generate(db_path, cache_key, generate, today=date(2026, 7, 19))["value"] == 1
    assert calls["count"] == 1
    assert (
        load_or_generate(
            db_path,
            cache_key,
            generate,
            force_refresh=True,
            today=date(2026, 7, 19),
        )["value"]
        == 2
    )


def test_ipo_scoring_ignores_gmp_for_long_term_score():
    base = {
        "company_name": "Test Infra",
        "symbol": "TEST",
        "sector": "manufacturing",
        "issue_price": 100,
        "current_price": 250,
        "return_from_issue_pct": 150,
        "revenue_growth_yoy": 25,
        "profit_growth_yoy": 25,
        "eps_growth_yoy": 20,
        "roe": 18,
        "roce": 18,
        "operating_margin": 18,
        "net_profit_margin": 10,
        "debt_to_equity": 0.2,
        "current_ratio": 1.4,
        "pledge_pct": 0,
        "pe_ratio": 25,
        "industry_pe": 35,
        "promoter_holding": 60,
        "fii_dii_holding": 12,
    }

    high_gmp_score = score_ipo_company({**base, "gmp": "100"})["total_score"]
    low_gmp_score = score_ipo_company({**base, "gmp": "-25"})["total_score"]

    assert high_gmp_score == low_gmp_score


def test_ipo_dashboard_uses_live_source_records_when_available(tmp_path, monkeypatch):
    live_record = verified_live_record()
    upcoming_record = {
        "company_name": "Upcoming Live IPO",
        "symbol": "UPLIVE",
        "ipo_date": "2026-08-01",
        "sector": "Manufacturing",
        "issue_size": "500 Cr",
        "price_band": "100-110",
        "gmp": "12",
        "source": "NSE upcoming IPO API",
        "last_updated_at": "2026-07-19T10:00:00",
    }
    monkeypatch.setattr(
        ipo_data_service,
        "fetch_chittorgarh_listed_ipos",
        lambda year: {"records": [live_record], "source": "test listed source", "error": ""},
    )
    monkeypatch.setattr(
        ipo_data_service,
        "fetch_nse_upcoming_ipos",
        lambda today=None: {"records": [upcoming_record], "source": "test nse source", "error": ""},
    )

    dashboard = build_ipo_dashboard(
        2026,
        "Latest Available",
        tmp_path / "ipo.db",
        False,
        force_refresh=True,
        today=date(2026, 7, 19),
    )

    live_row = next(row for row in dashboard["listed"] if row["symbol"] == "LIVEIPO")
    assert live_row["is_listed_verified"] is True
    assert live_row["eligible_for_scoring"] is True
    assert any(row["symbol"] == "LIVEIPO" for row in dashboard["listed_tracker"])
    assert any(row["symbol"] == "UPLIVE" for row in dashboard["upcoming"])
    assert dashboard["data_issues"] == []
    assert "1 eligible ranked row" in dashboard["research_decision"]["source_quality"]
    assert any("Chittorgarh" in note for note in dashboard["source_notes"])


def test_fetch_nse_upcoming_ipos_preserves_subscription_close_date(monkeypatch):
    payload = """
    {
      "data": [
        {
          "companyName": "Active NSE IPO Limited",
          "symbol": "ACTIVEIPO",
          "issueStartDate": "29-Jul-2026",
          "issueEndDate": "31-Jul-2026",
          "issueSize": "1000000"
        }
      ]
    }
    """
    monkeypatch.setattr(ipo_data_service, "_http_get_text", lambda *args, **kwargs: payload)

    result = FETCH_NSE_UPCOMING_IPOS(date(2026, 7, 31))

    assert result["records"][0]["ipo_date"] == "29-Jul-2026"
    assert result["records"][0]["ipo_close_date"] == "31-Jul-2026"
    open_date, close_date = ipo_data_service._upcoming_ipo_subscription_window(
        result["records"][0],
        2026,
    )
    assert open_date == date(2026, 7, 29)
    assert close_date == date(2026, 7, 31)


def test_ipo_dashboard_does_not_auto_fallback_when_live_sources_fail(tmp_path, monkeypatch):
    def raise_url_error(*args, **kwargs):
        raise URLError("network down")

    monkeypatch.setattr(ipo_data_service, "fetch_chittorgarh_listed_ipos", raise_url_error)
    monkeypatch.setattr(ipo_data_service, "fetch_nse_upcoming_ipos", raise_url_error)
    monkeypatch.setattr(ipo_data_service, "fetch_ipowatch_upcoming_ipos", raise_url_error)

    dashboard = build_ipo_dashboard(
        2026,
        "Latest Available",
        tmp_path / "ipo.db",
        True,
        force_refresh=True,
        today=date(2026, 7, 19),
    )

    assert dashboard["listed"] == []
    assert dashboard["upcoming"] == []
    assert dashboard["top10"] == []
    assert any("unavailable" in note.lower() for note in dashboard["source_notes"])
    assert dashboard["research_decision"]["outcome"] == IPO_NO_VERIFIED_DATA_MESSAGE


def test_ipo_snapshot_and_export_include_component_scores(tmp_path, monkeypatch):
    db_path = tmp_path / "ipo.db"
    monkeypatch.setattr(
        ipo_data_service,
        "fetch_chittorgarh_listed_ipos",
        lambda year: {"records": [verified_live_record()], "source": "test listed source", "error": ""},
    )
    dashboard = build_ipo_dashboard(2026, "Q1", db_path, False, today=date(2026, 7, 19))

    saved_count = save_ipo_top10_snapshot(db_path, 2026, "Q1", dashboard["top10"])
    assert saved_count == min(10, len(dashboard["top10"]))

    snapshots = load_ipo_snapshots(db_path, 2026)
    assert snapshots
    assert "profitability_score" in snapshots[0]
    assert "market_performance_score" in snapshots[0]

    csv_text = export_ipo_records_csv(snapshots, IPO_SNAPSHOT_FIELDS)
    assert "profitability_score" in csv_text
    assert "market_performance_score" in csv_text


def test_demo_fake_ipos_are_excluded_from_production_rankings(tmp_path, monkeypatch):
    monkeypatch.setenv("IPO_DATA_MODE", "demo")

    dashboard = build_ipo_dashboard(
        2026,
        "Latest Available",
        tmp_path / "ipo.db",
        False,
        force_refresh=True,
        today=date(2026, 7, 19),
    )

    fake_symbols = {"DIGIX", "GGPOWER", "BDS"}
    assert fake_symbols.isdisjoint({row.get("symbol") for row in dashboard["listed"]})
    assert fake_symbols.isdisjoint({row.get("symbol") for row in dashboard["listed_tracker"]})
    assert fake_symbols.isdisjoint({row.get("symbol") for row in dashboard["top10"]})
    assert fake_symbols.isdisjoint({row.get("symbol") for row in dashboard["quarterly_monitor"]})
    issue_rows = [row for row in dashboard["data_issues"] if row.get("symbol") in fake_symbols]
    assert issue_rows
    assert all(row.get("total_score") is None for row in issue_rows)
    assert all(row.get("action") == "UNVERIFIED - EXCLUDED" for row in issue_rows)
    assert all(not row.get("is_buy_zone") for row in issue_rows)


def test_verified_listing_missing_financials_is_data_pending_not_buy_zone(tmp_path, monkeypatch):
    pending_record = verified_live_record(
        symbol="PENDINGIPO",
        company_name="Verified But Pending Financials",
        revenue_growth_yoy=None,
        latest_revenue_growth_yoy=None,
        profit_growth_yoy=None,
        pat_growth_yoy=None,
        latest_pat_growth_yoy=None,
        eps_growth_yoy=None,
        roe=None,
        roce=None,
        cfo_pat=None,
        fcf=None,
    )
    monkeypatch.setattr(
        ipo_data_service,
        "fetch_chittorgarh_listed_ipos",
        lambda year: {"records": [pending_record], "source": "test listed source", "error": ""},
    )

    dashboard = build_ipo_dashboard(
        2026,
        "Latest Available",
        tmp_path / "ipo.db",
        False,
        force_refresh=True,
        today=date(2026, 7, 19),
    )

    assert dashboard["listed"] == []
    tracker_row = next(row for row in dashboard["listed_tracker"] if row["symbol"] == "PENDINGIPO")
    assert tracker_row["action"] == "WATCH / DATA PENDING"
    assert tracker_row["eligible_for_scoring"] is False
    row = dashboard["data_issues"][0]
    assert row["symbol"] == "PENDINGIPO"
    assert row["is_listed_verified"] is True
    assert row["eligible_for_scoring"] is False
    assert row["action"] == "WATCH / DATA PENDING"
    assert "latest_financial_data" in row["missing_fields"]
    assert row.get("total_score") is None
    assert not row.get("is_buy_zone")


def test_chittorgarh_year_url_falls_back_and_filters_selected_year(monkeypatch):
    year_url = ipo_data_service.CHITTORGARH_MAINBOARD_YEAR_URL.format(year=2026)
    fallback_url = ipo_data_service.CHITTORGARH_MAINBOARD_FALLBACK_URL
    calls = []

    def fake_get(url, headers=None):
        calls.append(url)
        if url == year_url:
            return chittorgarh_table(
                """
                <tr><td>Old Infra Ltd</td><td>OLDX</td><td>INEOLDX01010</td><td>10 Jul 2025</td><td>100</td><td>120</td><td>20%</td><td>1,200</td></tr>
                """
            )
        if url == fallback_url:
            return chittorgarh_table(
                """
                <tr><td>Apex Infra Ltd</td><td>REALX</td><td>INEREAL01010</td><td>10 Jul 2026</td><td>100</td><td>125</td><td>25%</td><td>1,250</td></tr>
                <tr><td>Old Infra Ltd</td><td>OLDX</td><td>INEOLDX01010</td><td>10 Jul 2025</td><td>100</td><td>120</td><td>20%</td><td>1,200</td></tr>
                """
            )
        return ""

    monkeypatch.setattr(ipo_data_service, "_http_get_text", fake_get)

    result = ipo_data_service.fetch_chittorgarh_ipos(2026, "mainboard")

    assert calls[:2] == [year_url, fallback_url]
    assert [row["symbol"] for row in result["records"]] == ["REALX"]
    assert result["records"][0]["isin"] == "INEREAL01010"
    assert result["records"][0]["gain_from_ipo_pct"] == 25
    assert result["source_kind"] == "fallback"


def test_chittorgarh_loader_does_not_invent_missing_symbols(monkeypatch):
    def fake_get(url, headers=None):
        return chittorgarh_table(
            """
            <tr><td>Apex Infra Ltd</td><td></td><td>INEREAL01010</td><td>10 Jul 2026</td><td>100</td><td>125</td><td>25%</td><td>1,250</td></tr>
            """
        )

    monkeypatch.setattr(ipo_data_service, "_http_get_text", fake_get)

    result = ipo_data_service.fetch_chittorgarh_ipos(2026, "mainboard")
    assert len(result["records"]) == 1
    assert result["records"][0]["symbol"] == ""

    verified_rows = ipo_data_service._apply_ipo_verification(result["records"])
    row = verified_rows[0]
    assert row["eligible_for_scoring"] is False
    assert row["action"] == "UNVERIFIED - EXCLUDED"
    assert "symbol" in row["missing_fields"]


def test_rubicon_pending_symbol_uses_verified_screener_alias():
    row = ipo_data_service._simple_ipo_performance_row(
        {
            "company_name": "Rubicon Research Listed: 16 Oct 2025",
            "symbol": "Symbol pending",
            "ipo_price": 100,
            "listing_price": 120,
            "current_price": 145,
            "current_gain_pct": 45,
            "source_url": "https://example.test/rubicon",
        },
        "mainboard",
    )

    assert row["company_name"] == "Rubicon Research"
    assert row["symbol"] == "RUBICON"
    assert row["screener_url"] == "https://www.screener.in/company/RUBICON/"


def test_ipo_company_name_and_screener_search_strip_listing_suffixes():
    row = ipo_data_service._simple_ipo_performance_row(
        {
            "company_name": "Ap Apsis Aerocom Listed: 18 Mar 2026",
            "symbol": "Symbol pending",
            "ipo_price": 100,
            "current_price": 125,
            "current_gain_pct": 25,
        },
        "sme",
    )

    assert row["company_name"] == "Apsis Aerocom"
    assert row["symbol"] == "APSISAERO"
    assert row["screener_url"] == "https://www.screener.in/company/APSISAERO/"
    assert "Listed" not in row["screener_url"]
    assert "Symbol" not in row["screener_url"]


def test_ipo_company_name_removes_symbol_pending_and_uses_verified_alias():
    row = ipo_data_service._simple_ipo_performance_row(
        {
            "company_name": "Xtranet Technologies Listed: 05 Mar 2026 Symbol pending",
            "symbol": "Symbol pending",
            "ipo_price": 100,
            "current_price": 140,
            "current_gain_pct": 40,
        },
        "mainboard",
    )

    assert row["company_name"] == "Xtranet Technologies"
    assert row["symbol"] == "XTRANET"
    assert row["screener_url"] == "https://www.screener.in/company/XTRANET/"


def test_ipo_identity_pipeline_uses_saved_override_after_cleaning():
    resolution = resolve_ipo_identity(
        {
            "company_name": "Rubicon Research Listed: 16 Oct 2025 Symbol pending",
            "symbol": "Symbol pending",
            "screener_url": "https://www.screener.in/search/?q=Rubicon+Research+Listed%3A+16+Oct+2025",
        }
    )

    assert resolution["clean_company_name"] == "Rubicon Research"
    assert resolution["symbol"] == "RUBICON"
    assert resolution["match_method"] == "SECURITY_MAP_SOURCE_VERIFIED"
    assert resolution["screener_url"] == "https://www.screener.in/company/RUBICON/"
    assert "Security map: NSE RUBICON" in resolution["resolution_pipeline"]
    assert "Listed%3A" not in resolution["screener_url"]


def test_ipo_identity_pipeline_matches_kite_master_and_isin():
    instrument_master = [
        {
            "tradingsymbol": "TESTIPO",
            "exchange": "NSE",
            "name": "Test Systems",
            "isin": "INE123456789",
            "instrument_token": 12345,
        }
    ]

    resolution = resolve_ipo_identity(
        {
            "company_name": "Test Systems Listed: 10 Jul 2026",
            "symbol": "Symbol pending",
            "isin": "INE123456789",
            "instrument_master": instrument_master,
        }
    )

    assert resolution["clean_company_name"] == "Test Systems"
    assert resolution["symbol"] == "TESTIPO"
    assert resolution["exchange"] == "NSE"
    assert resolution["instrument_token"] == 12345
    assert resolution["is_listed_verified"] is True
    assert resolution["isin_match_status"] == "MATCHED"
    assert resolution["match_method"] == "KITE_INSTRUMENT_ISIN"
    assert resolution["screener_url"] == "https://www.screener.in/company/TESTIPO/"


def test_ipo_identity_pipeline_keeps_unresolved_company_visible_with_clean_search():
    resolution = resolve_ipo_identity(
        {
            "company_name": "Ap Apsis Aerocom Listed: 18 Mar 2026 Symbol pending",
            "symbol": "Symbol pending",
            "screener_url": "https://www.screener.in/search/?q=Ap+Apsis+Aerocom+Listed%3A+18+Mar+2026",
        }
    )

    assert resolution["clean_company_name"] == "Apsis Aerocom"
    assert resolution["symbol"] == "APSISAERO"
    assert resolution["match_method"] == "SECURITY_MAP_SOURCE_VERIFIED"
    assert resolution["is_listed_verified"] is True
    assert resolution["screener_url"] == "https://www.screener.in/company/APSISAERO/"
    assert "Source symbol: missing/pending" in resolution["resolution_pipeline"]


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("Ap Apsis Aerocom", "Apsis Aerocom"),
        ("Te Teja Engineering Industries", "Teja Engineering Industries"),
        ("In Indo SMC", "Indo SMC"),
        ("Av Avana Electrosystems", "Avana Electrosystems"),
        ("Me Merritronix", "Merritronix"),
        ("Vi Vivid Electromech", "Vivid Electromech"),
        ("Mi Millworks Technologies", "Millworks Technologies"),
        ("Ve Vegorama Punjabi Angithi", "Vegorama Punjabi Angithi"),
        ("Ac Accretion Nutraveda", "Accretion Nutraveda"),
        ("Te Teamtech Formwork Solutions", "Teamtech Formwork Solutions"),
        ("Ti Tipco Engineering India", "Tipco Engineering India"),
        ("KR KRM Ayurveda", "KRM Ayurveda"),
        ("De Devson Catalyst", "Devson Catalyst"),
        ("RF RFBL Flexi Pack", "RFBL Flexi Pack"),
        ("Gr Grover Jewells", "Grover Jewells"),
        ("Su Susan Electricals India", "Susan Electricals India"),
        ("GR GRE Renew Enertech", "GRE Renew Enertech"),
        ("Sh Shreedhar Spinners", "Shreedhar Spinners"),
        ("El Elfin Agro India", "Elfin Agro India"),
        ("IC IC Electricals Company", "IC Electricals Company"),
        ("Na Nanta Tech", "Nanta Tech"),
        ("Ad Admach Systems", "Admach Systems"),
        ("Dh Dhara Rail Projects", "Dhara Rail Projects"),
        ("Ba Bai Kakaji Polymers", "Bai Kakaji Polymers"),
        ("Rubicon Research", "Rubicon Research"),
        ("KSH International", "KSH International"),
        ("Groww", "Groww"),
        ("Corona Remedies", "Corona Remedies"),
        ("Aequs", "Aequs"),
        ("Vidya Wires", "Vidya Wires"),
        ("Meesho", "Meesho"),
        ("ICICI Prudential AMC", "ICICI Prudential AMC"),
        ("PhysicsWallah", "PhysicsWallah"),
        ("LG Electronics India", "LG Electronics India"),
        ("OnEMI Technology Solutions", "OnEMI Technology Solutions"),
        ("SEDEMAC Mechatronics", "SEDEMAC Mechatronics"),
        ("CMR Green Technologies", "CMR Green Technologies"),
    ],
)
def test_ipo_company_name_cleaner_removes_only_duplicate_short_prefixes(raw_name, expected):
    assert ipo_data_service._clean_chittorgarh_company_name(raw_name) == expected


def test_simple_ipo_decision_engine_treats_zero_listing_price_as_missing():
    row = ipo_data_service._simple_ipo_performance_row(
        verified_live_record(
            listing_price=0,
            return_from_listing_pct=None,
            listing_gain_pct=None,
        ),
        "mainboard",
    )

    assert row["listing_price"] is None
    assert row["listing_price_status"] == "LISTING_PRICE_MISSING"


def test_ipo_price_cleaner_handles_currency_commas_percent_and_zero_missing():
    assert clean_ipo_price("₹1,234.50") == 1234.5
    assert clean_ipo_price("â‚¹80.6") == 80.6
    assert clean_ipo_price("16.88%") == 16.88
    assert clean_ipo_price(" 0 ", zero_is_missing=True) is None
    assert clean_ipo_price("N/A") is None


def test_simple_ipo_decision_engine_marks_all_zero_prices_as_missing():
    row = ipo_data_service._simple_ipo_performance_row(
        verified_live_record(
            company_name="Rubicon Research",
            symbol="RUBICON",
            isin="INERUBI01010",
            ipo_price="0",
            issue_price="0",
            listing_price="₹0",
            current_price="0",
            ltp="0",
            market_cap=5000,
            sector="Pharma",
            theme="Specialty pharma",
        ),
        "mainboard",
    )

    assert row["ipo_price"] is None
    assert row["listing_price"] is None
    assert row["current_price"] is None
    assert row["ipo_price_status"] == "IPO_PRICE_MISSING"
    assert row["listing_price_status"] == "LISTING_PRICE_MISSING"
    assert row["price_data_status"] == "CURRENT_PRICE_MISSING"
    assert row["action"] == "DATA PENDING"


def test_simple_ipo_decision_engine_excludes_demo_rows_from_scoring():
    row = ipo_data_service._simple_ipo_performance_row(
        {
            **verified_live_record(
                company_name="GreenGrid Power Infra",
                symbol="GGPOWER",
                current_price=515,
                current_gain_pct=60,
            ),
            "is_demo": True,
        },
        "mainboard",
    )

    assert row["action"] == "UNVERIFIED - EXCLUDED"
    assert row["eligible_for_scoring"] is False
    assert row["value_score"] is None
    assert row["buy_zone_allowed"] is False


def test_simple_ipo_decision_engine_blocks_strong_runup_without_valuation():
    row_data = verified_live_record(
        current_price=260,
        current_gain_pct=160,
        return_from_issue_pct=160,
        gain_from_ipo_pct=160,
    )
    for field in ("pe_ratio", "pe", "industry_pe", "peer_median_pe", "price_to_sales", "ps_ratio", "pb_ratio", "ev_ebitda"):
        row_data[field] = None

    row = ipo_data_service._simple_ipo_performance_row(row_data, "mainboard")

    assert row["action"] == "STRONG RUN-UP / AVOID CHASING"
    assert row["valuation_status"] == "Valuation Data Pending"
    assert row["eligible_for_scoring"] is False
    assert row["value_score"] is None
    assert row["buy_zone_allowed"] is False


def test_simple_ipo_decision_engine_marks_unknown_sector_as_research_only():
    row = ipo_data_service._simple_ipo_performance_row(
        verified_live_record(
            company_name="Unmapped Silent Alpha",
            sector="",
            theme="",
            industry="",
            business="",
            description="",
        ),
        "mainboard",
    )

    assert row["sector"] == "Sector Review Needed"
    assert row["theme"] == "Theme Review Needed"
    assert row["action"] == "RESEARCH ONLY"
    assert row["eligible_for_scoring"] is False
    assert row["buy_zone_allowed"] is False


def test_simple_ipo_decision_engine_buy_zone_requires_verified_financials():
    row = ipo_data_service._simple_ipo_performance_row(
        verified_live_record(
            current_price=150,
            current_gain_pct=50,
            drawdown_from_52w_high_pct=-25,
        ),
        "mainboard",
    )

    assert row["action"] == "BUY ZONE REACHED"
    assert row["value_score"] >= 75
    assert row["financial_data_status"] == "Financial Data Available"
    assert row["data_quality_score"] >= 80
    assert row["suggested_allocation"] != "No order"


def test_simple_ipo_decision_engine_missing_financials_stays_watchlist():
    row = ipo_data_service._simple_ipo_performance_row(
        {
            **simple_perf_record(1, "mainboard", 45, 2026),
            "symbol": "PEND",
            "current_price": 145,
            "current_gain_pct": 45,
            "revenue_growth_yoy": None,
            "latest_revenue_growth_yoy": None,
            "profit_growth_yoy": None,
            "pat_growth_yoy": None,
            "latest_pat_growth_yoy": None,
            "eps_growth_yoy": None,
            "roe": None,
            "roce": None,
            "cfo_pat": None,
            "fcf": None,
        },
        "mainboard",
    )

    assert row["action"] == "DATA PENDING"
    assert row["financial_data_status"] == "Financial Data Pending"
    assert row["value_score"] is None
    assert "Financial data pending" in row["risk_alerts"]


def test_simple_ipo_decision_engine_unresolved_symbol_needs_review():
    row = ipo_data_service._simple_ipo_performance_row(
        {
            "company_name": "Ap Apsis Aerocom Listed: 18 Mar 2026",
            "symbol": "Symbol pending",
            "ipo_price": 100,
            "current_price": 125,
            "current_gain_pct": 25,
        },
        "sme",
    )

    assert row["company_name"] == "Apsis Aerocom"
    assert row["symbol"] == "APSISAERO"
    assert row["action"] == "DATA PENDING"
    assert row["value_score"] is None
    assert row["symbol_resolution_confidence"] >= 85


def test_unverified_2025_alias_stays_symbol_review_but_sector_maps():
    row = ipo_data_service._simple_ipo_performance_row(
        {
            "company_name": "Na Nanta Tech Listed: 20 Oct 2025",
            "symbol": "Symbol pending",
            "ipo_price": 100,
            "listing_price": 112,
            "current_price": 130,
            "current_gain_pct": 30,
            "market_cap": 1200,
        },
        "mainboard",
    )

    assert row["company_name"] == "Nanta Tech"
    assert row["symbol"] == "544668"
    assert row["action"] == "DATA PENDING"
    assert row["sector"] == "Industrial technology"
    assert row["theme"] == "Industrial technology"
    assert row["eligible_for_scoring"] is False
    assert row["screener_url"] == "https://www.screener.in/company/544668/"


def test_unverified_seed_aliases_do_not_become_verified_symbols():
    overrides = load_symbol_overrides()

    assert normalize_company_key("Rubicon Research") in overrides
    assert normalize_company_key("Nanta Tech") not in overrides
    assert normalize_company_key("Admach Systems") not in overrides
    assert normalize_company_key("Groww") not in overrides


@pytest.mark.parametrize(
    ("company", "expected_sector", "expected_theme"),
    [
        ("Rubicon Research", "Pharma", "Specialty pharma"),
        ("Groww", "Financialization", "Capital markets / wealth platform"),
        ("LG Electronics India", "Consumer durables", "Consumer appliances / premiumization"),
        ("Dhara Rail Projects", "Rail infrastructure", "Rail projects / infrastructure capex"),
        ("Bai Kakaji Polymers", "Polymer packaging", "Polymer packaging"),
        ("CMR Green Technologies", "Aluminium recycling", "Aluminium recycling / circular economy"),
    ],
)
def test_additional_ipo_sector_mapping(company, expected_sector, expected_theme):
    row = ipo_data_service._simple_ipo_performance_row(
        verified_live_record(
            company_name=company,
            sector="",
            theme="",
            industry="",
            business="",
            description="",
        ),
        "mainboard",
    )

    assert row["sector"] == expected_sector
    assert row["theme"] == expected_theme


def test_cached_simple_ipo_loader_does_not_emit_success_noise(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ipo_data_service,
        "_simple_ipo_cache_path",
        lambda year, ipo_type: tmp_path / f"ipo_performance_{ipo_type}_{year}.csv",
    )
    row = ipo_data_service._simple_ipo_performance_row(simple_perf_record(1, "mainboard", 25, 2026), "mainboard")
    ipo_data_service._write_simple_ipo_csv_cache(2026, "mainboard", [row], "2026-07-20T10:00:00")

    result = ipo_data_service._load_simple_chittorgarh_performance(2026, "mainboard", force_refresh=False)

    assert result["source_mode"] == "cache"
    assert result["messages"] == []


def test_chittorgarh_parser_supports_performance_tracker_columns(monkeypatch):
    year_url = ipo_data_service.CHITTORGARH_MAINBOARD_YEAR_URL.format(year=2025)

    def fake_get(url, headers=None):
        assert url == year_url
        return """
        <table>
          <tr>
            <th>Company Name</th>
            <th>Listed On</th>
            <th>Issue Price</th>
            <th>Listing Day Close</th>
            <th>Listing Day Gain</th>
            <th>Current Price</th>
            <th>Profit/Loss</th>
          </tr>
          <tr>
            <td>Apollo Techno Industries Ltd. IPO Detail | Stock Quotes</td>
            <td>Wed, Dec 31, 2025</td>
            <td>₹130</td>
            <td>₹151.95</td>
            <td>16.88%</td>
            <td>₹80.6</td>
            <td>-38%</td>
          </tr>
        </table>
        """

    monkeypatch.setattr(ipo_data_service, "_http_get_text", fake_get)

    result = ipo_data_service.fetch_chittorgarh_ipos(2025, "mainboard")

    assert len(result["records"]) == 1
    row = result["records"][0]
    assert row["company_name"].startswith("Apollo Techno Industries")
    assert row["ipo_price"] == 130
    assert row["listing_price"] == 151.95
    assert row["current_price"] == 80.6
    assert row["return_from_listing_pct"] == 16.88
    assert row["gain_from_ipo_pct"] == -38


def test_ipomarket_parser_supports_year_performance_rows(monkeypatch):
    year_url = ipo_data_service.IPOMARKET_YEAR_URL.format(year=2026)

    def fake_get(url, headers=None):
        assert url == year_url
        return """
        <table>
          <tr>
            <th>Company Name</th>
            <th>Symbol</th>
            <th>Listed On</th>
            <th>Issue Price</th>
            <th>Listing Day Close</th>
            <th>Listing Day Gain</th>
            <th>Current Price</th>
            <th>Profit/Loss</th>
            <th>Segment</th>
          </tr>
          <tr>
            <td>Real Infra Ltd</td>
            <td>REALINFRA</td>
            <td>15 Jul 2026</td>
            <td>100</td>
            <td>118</td>
            <td>18%</td>
            <td>145</td>
            <td>45%</td>
            <td>Mainboard</td>
          </tr>
          <tr>
            <td>Real SME Ltd</td>
            <td>REALSME</td>
            <td>18 Jul 2026</td>
            <td>50</td>
            <td>60</td>
            <td>20%</td>
            <td>80</td>
            <td>60%</td>
            <td>SME</td>
          </tr>
        </table>
        """

    monkeypatch.setattr(ipo_data_service, "_http_get_text", fake_get)

    mainboard = ipo_data_service.fetch_ipomarket_ipos(2026, "mainboard")
    sme = ipo_data_service.fetch_ipomarket_ipos(2026, "sme")

    assert [row["symbol"] for row in mainboard["records"]] == ["REALINFRA"]
    assert mainboard["records"][0]["current_price"] == 145
    assert mainboard["records"][0]["gain_from_ipo_pct"] == 45
    assert [row["symbol"] for row in sme["records"]] == ["REALSME"]
    assert sme["records"][0]["market_type"] == "SME"


def test_simple_ipo_loader_prefers_ipomarket_before_chittorgarh(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ipo_data_service,
        "_simple_ipo_cache_path",
        lambda year, ipo_type: tmp_path / f"ipo_performance_{ipo_type}_{year}.csv",
    )
    ipomarket_record = simple_perf_record(1, "mainboard", 42, 2026)
    ipomarket_record["company_name"] = "IPO Market Winner"
    ipomarket_sme_record = simple_perf_record(1, "sme", 44, 2026)
    ipomarket_sme_record["company_name"] = "IPO Market SME Winner"
    monkeypatch.setattr(
        ipo_data_service,
        "fetch_ipomarket_ipos",
        lambda year, ipo_type="mainboard": {
            "records": [ipomarket_record] if ipo_type == "mainboard" else [ipomarket_sme_record],
            "source": f"https://ipomarket/{year}",
            "source_kind": "ipomarket",
            "source_priority": "ipomarket",
            "error": "",
        },
    )
    monkeypatch.setattr(
        ipo_data_service,
        "fetch_chittorgarh_ipos",
        lambda year, ipo_type="mainboard": pytest.fail("Chittorgarh should not be used when IPO Market returns rows"),
    )
    monkeypatch.setattr(ipo_data_service, "fetch_ipoguru_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_secondary_ipo_source", lambda source_key, year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "_load_research_ready_upcoming_ipos", lambda today=None: ([], []))

    dashboard = build_simple_ipo_performance_dashboard(
        2026,
        force_refresh=True,
        today=date(2026, 7, 20),
    )

    assert dashboard["mainboard_top20"][0]["company_name"] == "IPO Market Winner"
    assert dashboard["sources"]["mainboard"] == "https://ipomarket/2026"


def test_simple_ipo_performance_dashboard_loads_top20_mainboard_and_sme(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ipo_data_service,
        "_simple_ipo_cache_path",
        lambda year, ipo_type: tmp_path / f"chittorgarh_{ipo_type}_{year}.csv",
    )

    def fake_fetch(year, ipo_type="mainboard"):
        gains = list(range(35, 10, -1)) if ipo_type == "mainboard" else list(range(70, 45, -1))
        records = [simple_perf_record(i, ipo_type, gain, year) for i, gain in enumerate(gains, start=1)]
        records.append(simple_perf_record(99, ipo_type, -10, year))
        return {"records": records, "source": f"https://source/{ipo_type}/{year}", "error": ""}

    monkeypatch.setattr(ipo_data_service, "fetch_chittorgarh_ipos", fake_fetch)
    monkeypatch.setattr(ipo_data_service, "fetch_ipomarket_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_ipoguru_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_secondary_ipo_source", lambda source_key, year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "_load_research_ready_upcoming_ipos", lambda today=None: ([], []))

    dashboard = build_simple_ipo_performance_dashboard(
        2026,
        force_refresh=True,
        today=date(2026, 7, 20),
    )

    assert len(dashboard["mainboard_top20"]) == 20
    assert len(dashboard["sme_top20"]) == 20
    assert len(dashboard["combined_top40"]) == 40
    assert all(row["current_gain_pct"] >= 0 for row in dashboard["mainboard_top20"])
    assert all(row["current_gain_pct"] >= 0 for row in dashboard["sme_top20"])
    assert dashboard["mainboard_top20"][0]["current_gain_pct"] >= dashboard["mainboard_top20"][-1]["current_gain_pct"]
    assert dashboard["sme_top20"][0]["current_gain_pct"] >= dashboard["sme_top20"][-1]["current_gain_pct"]
    assert dashboard["summary"]["mainboard_positive_return"] == 25
    assert dashboard["summary"]["sme_positive_return"] == 25


def test_simple_ipo_dashboard_summary_counts_decision_quality(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ipo_data_service,
        "_simple_ipo_cache_path",
        lambda year, ipo_type: tmp_path / f"decision_{ipo_type}_{year}.csv",
    )
    verified = verified_live_record(
        current_price=150,
        current_gain_pct=50,
        drawdown_from_52w_high_pct=-25,
    )
    unresolved = {
        "company_name": "Ap Apsis Aerocom Listed: 18 Mar 2026",
        "symbol": "Symbol pending",
        "ipo_price": 100,
        "current_price": 125,
        "current_gain_pct": 25,
    }

    def fake_fetch(year, ipo_type="mainboard"):
        if ipo_type == "mainboard":
            return {"records": [verified, unresolved], "source": "https://source/mainboard", "error": ""}
        return {"records": [], "source": "https://source/sme", "error": ""}

    monkeypatch.setattr(ipo_data_service, "fetch_chittorgarh_ipos", fake_fetch)
    monkeypatch.setattr(ipo_data_service, "fetch_ipomarket_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_ipoguru_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_secondary_ipo_source", lambda source_key, year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "_load_research_ready_upcoming_ipos", lambda today=None: ([], []))

    dashboard = build_simple_ipo_performance_dashboard(2026, force_refresh=True, today=date(2026, 7, 20))

    assert dashboard["summary"]["total_ipos_loaded"] == 2
    assert dashboard["summary"]["symbols_resolved"] == 2
    assert dashboard["summary"]["financial_data_available"] == 1
    assert dashboard["summary"]["buy_zone_candidates"] == 1
    assert dashboard["summary"]["symbol_review_needed"] == 0
    assert [row["symbol"] for row in dashboard["combined_top40"]] == ["LIVEIPO", "APSISAERO"]
    assert dashboard["combined_top40"][0]["eligible_for_scoring"] is True
    assert dashboard["combined_top40"][1]["eligible_for_scoring"] is False
    assert dashboard["combined_top40"][1]["action"] == "DATA PENDING"


def test_simple_ipo_top40_shows_unverified_rows_as_research_only_across_years(monkeypatch):
    def fake_loader(selected_year, ipo_type, force_refresh=False):
        verified = ipo_data_service._simple_ipo_performance_row(
            verified_live_record(
                company_name=f"Live Quality IPO {selected_year}",
                symbol=f"LIVE{str(selected_year)[-2:]}",
                current_gain_pct=35,
                source_url=f"https://example.test/{selected_year}",
            ),
            ipo_type,
        )
        unverified = ipo_data_service._simple_ipo_performance_row(
            {
                "company_name": "Na Nanta Tech Listed: 20 Oct 2025" if selected_year == 2025 else "Ap Apsis Aerocom Listed: 18 Mar 2026",
                "symbol": "Symbol pending",
                "ipo_price": 100,
                "listing_price": 110,
                "current_price": 150,
                "current_gain_pct": 50,
                "market_cap": 1500,
                "source_url": f"https://example.test/unverified/{selected_year}",
            },
            ipo_type,
        )
        return {
            "rows": [unverified, verified] if ipo_type == "mainboard" else [],
            "source": "test",
            "source_mode": "test",
            "last_refreshed": "2026-07-20T10:00:00",
            "messages": [],
        }

    monkeypatch.setattr(ipo_data_service, "_load_simple_chittorgarh_performance", fake_loader)
    monkeypatch.setattr(ipo_data_service, "_upcoming_ipos_next_7_days", lambda today=None: ([], []))

    for selected_year in (2024, 2025, 2026):
        dashboard = build_simple_ipo_performance_dashboard(selected_year, force_refresh=True, today=date(2026, 7, 20))
        top40_names = [row["company_name"] for row in dashboard["combined_top40"]]

        expected_review_name = "Nanta Tech" if selected_year == 2025 else "Apsis Aerocom"
        assert top40_names == [f"Live Quality IPO {selected_year}", expected_review_name]
        review_row = dashboard["combined_top40"][1]
        assert review_row["eligible_for_scoring"] is False
        assert review_row["action"] == "DATA PENDING"
        assert dashboard["summary"]["symbol_review_needed"] == 0


def test_simple_ipo_2024_loads_local_fallback_company_names_when_sources_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ipo_data_service,
        "_simple_ipo_cache_path",
        lambda year, ipo_type: tmp_path / f"missing_{ipo_type}_{year}.csv",
    )
    empty_source = lambda *args, **kwargs: {"records": [], "source": "", "error": ""}
    monkeypatch.setattr(ipo_data_service, "fetch_ipomarket_ipos", empty_source)
    monkeypatch.setattr(ipo_data_service, "fetch_ipoguru_ipos", empty_source)
    monkeypatch.setattr(ipo_data_service, "fetch_secondary_ipo_source", lambda *args, **kwargs: {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_chittorgarh_ipos", empty_source)
    monkeypatch.setattr(ipo_data_service, "_upcoming_ipos_next_7_days", lambda today=None: ([], []))

    dashboard = build_simple_ipo_performance_dashboard(2024, force_refresh=True, today=date(2026, 8, 2))
    names = [row["company_name"] for row in dashboard["combined_top40"]]

    assert dashboard["mainboard_all_count"] >= 5
    assert "Premier Energies" in names
    assert "Waaree Energies" in names
    assert "Bajaj Housing Finance" in names
    assert dashboard["sources"]["mainboard_mode"] == "local_history"


def test_flattrade_year_source_parses_2024_and_2023_rows(monkeypatch):
    html = """
    <table>
      <tr><th>Issuer Company</th><th>Exchange</th><th>Open</th><th>Close</th><th>Issue Price</th><th>Issue Size (Rs Cr)</th><th>Lot Size</th></tr>
      <tr><td>Waaree Energies IPO</td><td>BSE, NSE</td><td>October 21, 2024</td><td>October 23, 2024</td><td>1503.00</td><td>4321.44</td><td>9</td></tr>
      <tr><td>BLS E-Services IPO</td><td>BSE, NSE</td><td>January 30, 2024</td><td>February 1, 2024</td><td>135.00</td><td>310.91</td><td>108</td></tr>
      <tr><td>IREDA IPO</td><td>BSE, NSE</td><td>November 21, 2023</td><td>November 23, 2023</td><td>32.00</td><td>2150.21</td><td>460</td></tr>
    </table>
    """
    monkeypatch.setattr(ipo_data_service, "_http_get_text", lambda url: html)

    rows_2024 = ipo_data_service.fetch_flattrade_ipos(2024, "mainboard")["records"]
    rows_2023 = ipo_data_service.fetch_flattrade_ipos(2023, "mainboard")["records"]

    assert [row["company_name"] for row in rows_2024] == ["Waaree Energies", "BLS E-Services"]
    assert rows_2024[0]["ipo_price"] == 1503
    assert rows_2024[0]["data_source"] == "FlatTrade IPO list"
    assert [row["company_name"] for row in rows_2023] == ["IREDA"]


def test_flattrade_rows_without_current_price_remain_visible_as_data_pending(monkeypatch):
    html = """
    <table>
      <tr><th>Issuer Company</th><th>Exchange</th><th>Open</th><th>Close</th><th>Issue Price</th><th>Issue Size (Rs Cr)</th><th>Lot Size</th></tr>
      <tr><td>IREDA IPO</td><td>BSE, NSE</td><td>November 21, 2023</td><td>November 23, 2023</td><td>32.00</td><td>2150.21</td><td>460</td></tr>
    </table>
    """
    monkeypatch.setattr(ipo_data_service, "_http_get_text", lambda url: html)
    monkeypatch.setattr(ipo_data_service, "_upcoming_ipos_next_7_days", lambda today=None: ([], []))

    dashboard = build_simple_ipo_performance_dashboard(2023, force_refresh=True, today=date(2026, 8, 2))
    row = dashboard["combined_top40"][0]

    assert row["company_name"] == "IREDA"
    assert row["current_price"] is None
    assert row["action"] == "DATA PENDING"
    assert dashboard["sources"]["mainboard_mode"] == "live"


def test_cached_flattrade_rows_without_data_source_remain_visible() -> None:
    row = ipo_data_service._simple_ipo_performance_row(
        {
            "company_name": "IREDA",
            "ipo_price": 32,
            "source_url": "https://flattrade.in/kosh/upcoming-ipo-2023/",
        },
        "mainboard",
    )

    assert ipo_data_service._simple_ipo_display_candidate(row) is True


def test_ipo_year_options_include_2023():
    assert 2023 in ipo_data_service.ipo_year_options(date(2026, 8, 2))


def test_simple_ipo_2023_loads_local_flattrade_rows_when_sources_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ipo_data_service,
        "_simple_ipo_cache_path",
        lambda year, ipo_type: tmp_path / f"missing_{ipo_type}_{year}.csv",
    )
    empty_source = lambda *args, **kwargs: {"records": [], "source": "", "error": ""}
    monkeypatch.setattr(ipo_data_service, "fetch_ipomarket_ipos", empty_source)
    monkeypatch.setattr(ipo_data_service, "fetch_ipoguru_ipos", empty_source)
    monkeypatch.setattr(ipo_data_service, "fetch_flattrade_ipos", empty_source)
    monkeypatch.setattr(ipo_data_service, "fetch_secondary_ipo_source", lambda *args, **kwargs: {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_chittorgarh_ipos", empty_source)
    monkeypatch.setattr(ipo_data_service, "_upcoming_ipos_next_7_days", lambda today=None: ([], []))

    dashboard = build_simple_ipo_performance_dashboard(2023, force_refresh=True, today=date(2026, 8, 2))
    names = [row["company_name"] for row in dashboard["combined_top40"]]

    assert "Tata Technologies" in names
    assert "Indian Renewable Energy Development Agency" in names
    assert dashboard["combined_top40"][0]["current_price"] is None
    assert dashboard["combined_top40"][0]["action"] == "DATA PENDING"
    assert dashboard["sources"]["mainboard_mode"] == "local_history"


def test_simple_ipo_dashboard_keeps_positive_source_rows_visible_when_no_verified(monkeypatch):
    def fake_loader(selected_year, ipo_type, force_refresh=False):
        unverified = ipo_data_service._simple_ipo_performance_row(
            {
                "company_name": "Omnitech Engineering Listed: 05 Mar 2026",
                "symbol": "Symbol pending",
                "ipo_price": 100,
                "listing_price": 110,
                "current_price": 150,
                "current_gain_pct": 50,
                "market_cap": 1500,
                "source_url": "https://example.test/omnitech",
            },
            ipo_type,
        )
        return {
            "rows": [unverified] if ipo_type == "mainboard" else [],
            "source": "test",
            "source_mode": "test",
            "last_refreshed": "2026-07-20T10:00:00",
            "messages": [],
        }

    monkeypatch.setattr(ipo_data_service, "_load_simple_chittorgarh_performance", fake_loader)
    monkeypatch.setattr(ipo_data_service, "_upcoming_ipos_next_7_days", lambda today=None: ([], []))

    dashboard = build_simple_ipo_performance_dashboard(2026, force_refresh=True, today=date(2026, 7, 20))

    assert dashboard["summary"]["eligible_for_scoring"] == 0
    assert dashboard["summary"]["display_positive_return"] == 1
    assert dashboard["combined_top40"][0]["company_name"] == "Omnitech Engineering"
    assert dashboard["combined_top40"][0]["eligible_for_scoring"] is False
    assert dashboard["combined_top40"][0]["action"] == "DATA PENDING"
    assert IPO_NO_VERIFIED_DATA_MESSAGE in dashboard["messages"]


def test_simple_ipo_upcoming_filters_next_7_days(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ipo_data_service,
        "_simple_ipo_cache_path",
        lambda year, ipo_type: tmp_path / f"chittorgarh_{ipo_type}_{year}.csv",
    )
    monkeypatch.setattr(
        ipo_data_service,
        "fetch_chittorgarh_ipos",
        lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""},
    )
    monkeypatch.setattr(ipo_data_service, "fetch_ipomarket_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_ipoguru_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_secondary_ipo_source", lambda source_key, year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    upcoming_rows = [
        {"company_name": "Today IPO", "symbol": "TODAY", "ipo_date": "2026-07-20", "sector": "Infra"},
        {"company_name": "Day Seven IPO", "symbol": "SEVEN", "ipo_date": "2026-07-27", "sector": "EMS"},
        {"company_name": "Too Late IPO", "symbol": "LATE", "ipo_date": "2026-07-28", "sector": "NBFC"},
        {"company_name": "Old IPO", "symbol": "OLD", "ipo_date": "2026-07-19", "sector": "Pharma"},
    ]
    monkeypatch.setattr(
        ipo_data_service,
        "_load_research_ready_upcoming_ipos",
        lambda today=None: (upcoming_rows, []),
    )

    dashboard = build_simple_ipo_performance_dashboard(2026, force_refresh=True, today=date(2026, 7, 20))

    assert [row["symbol"] for row in dashboard["upcoming_next7"]] == ["TODAY", "SEVEN"]
    assert [row["market_type"] for row in dashboard["upcoming_next7"]] == ["N/A", "N/A"]


def test_simple_ipo_upcoming_preserves_board_when_source_provides_it(monkeypatch):
    upcoming_rows = [
        {
            "company_name": "SME Board IPO",
            "symbol": "SMEIPO",
            "ipo_date": "2026-07-20",
            "ipo_close_date": "2026-07-22",
            "market_type": "SME",
            "sector": "Industrials",
        },
        {
            "company_name": "Main Board IPO",
            "symbol": "MAINIPO",
            "ipo_date": "2026-07-21",
            "ipo_close_date": "2026-07-23",
            "segment": "Mainboard",
            "sector": "Healthcare",
        },
    ]
    monkeypatch.setattr(
        ipo_data_service,
        "_load_research_ready_upcoming_ipos",
        lambda today=None: (upcoming_rows, []),
    )

    rows, _ = ipo_data_service._upcoming_ipos_next_7_days(date(2026, 7, 20))

    assert [row["market_type"] for row in rows] == ["SME", "Mainboard"]


def test_ipo_value_investor_prompt_uses_selected_rows_and_screener_links():
    rows = [
        {
            "rank": 1,
            "company_name": "Rubicon Research",
            "symbol": "RUBICON",
            "ipo_type": "Mainboard",
            "listing_date": "2025-10-16",
            "ipo_price": 100,
            "listing_price": 120,
            "current_price": 145,
            "current_gain_pct": 45,
            "screener_url": "https://www.screener.in/company/RUBICON/",
            "source_url": "https://example.test/rubicon",
        },
        {
            "rank": 2,
            "company_name": "Demo IPO",
            "symbol": "DEMO",
            "ipo_type": "Mainboard",
            "is_demo": True,
        },
    ]

    selected = selected_ipo_rows_for_value_analysis({"combined_top40": rows}, limit=10)
    prompt = build_ipo_value_investor_prompt(selected, 2025)

    assert [row["symbol"] for row in selected] == ["RUBICON"]
    assert "Rubicon Research" in prompt
    assert "https://www.screener.in/company/RUBICON/" in prompt
    assert "long-term investor" in prompt
    assert "quarterly" in prompt.lower()
    assert "Demo IPO" not in prompt


def test_render_ipo_panel_has_default_controls(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "ipo.db")
    monkeypatch.setattr(
        app,
        "build_simple_ipo_performance_dashboard",
        lambda year, today=None: {
            "mode": "simple_performance",
            "year": year,
            "generated_at": "2026-07-20T10:00:00",
            "last_refreshed": "2026-07-20T10:00:00",
            "mainboard_top20": [simple_perf_record(1, "mainboard", 25, year)],
            "sme_top20": [simple_perf_record(1, "sme", 35, year)],
            "combined_top40": [
                simple_perf_record(1, "sme", 35, year),
                simple_perf_record(1, "mainboard", 25, year),
            ],
            "upcoming_next7": [
                {
                    "company_name": "Upcoming IPO",
                    "symbol": "UPIPO",
                    "ipo_date": "2026-07-22",
                    "sector": "EMS",
                    "market_type": "SME",
                    "issue_size": "500 Cr",
                    "price_band": "100-110",
                    "gmp": "N/A",
                    "gmp_pct": None,
                    "source": "NSE upcoming IPO API",
                    "last_updated_at": "2026-07-20T10:00:00",
                    "screener_url": "https://www.screener.in/company/UPIPO/",
                }
            ],
            "messages": [
                "Loaded cached mainboard IPO performance data for 2026.",
                "Loaded 3 upcoming IPO row(s) from NSE upcoming IPO API.",
                "Loaded 25 upcoming IPO row(s) from IPOWatch GMP/upcoming table.",
                "Useful parser warning",
            ],
            "summary": {
                "total_mainboard_loaded": 1,
                "total_sme_loaded": 1,
                "total_ipos_loaded": 2,
                "symbols_resolved": 2,
                "financial_data_available": 0,
                "buy_zone_candidates": 0,
                "tracking_buy_candidates": 0,
                "risk_alert_count": 0,
                "symbol_review_needed": 0,
                "mainboard_positive_return": 1,
                "sme_positive_return": 1,
                "mainboard_gt50_gain": 0,
                "sme_gt50_gain": 0,
                "best_mainboard": "MAIN IPO 1",
                "best_sme": "SME IPO 1",
                "upcoming_next7_count": 1,
                "last_refreshed": "2026-07-20T10:00:00",
            },
        },
    )
    state = app.PageState(active_tab="ipo", ipo_year=2026, ipo_quarter="Latest Available")

    html = app.render_ipo_panel(state)

    assert "IPO Decision Engine" in html
    assert "Listed IPO Performance Tracker" in html
    assert 'id="ipo-search-box"' in html
    assert 'name="ipo_market_type"' in html
    assert '<option value="Mainboard"' in html
    assert "&gt;50% return" in html
    assert "Financials available" in html
    assert "Top Mainboard" not in html
    assert "Top SME" not in html
    assert "Mainboard loaded" not in html
    assert "SME loaded" not in html
    assert "Last refreshed" not in html
    assert "Loaded cached mainboard IPO performance data" not in html
    assert "Loaded 3 upcoming IPO row(s) from NSE upcoming IPO API" not in html
    assert "Loaded 25 upcoming IPO row(s) from IPOWatch GMP/upcoming table" not in html
    assert "Useful parser warning" in html
    assert "Upcoming IPOs - Next 7 Days" in html
    assert html.index("Upcoming IPOs - Next 7 Days") < html.index("Top 40 IPO Performers")
    assert html.index("Useful parser warning") > html.index("Exports")
    assert "Board" in html
    assert "SME" in html
    assert "GMP %" in html
    assert "Days" in html
    assert 'id="ipo-upcoming-table"' in html
    assert "ipo-upcoming-card" not in html
    assert "Top 20 Mainboard IPOs" not in html
    assert "Top 20 SME IPOs" not in html
    assert "Top 40 IPO Performers" in html
    assert "Combined Top 40 IPO Performers" not in html
    assert "Analyze Selected with GPT" in html
    assert 'name="ipo_selected_key"' in html
    assert "ipo-sortable" in html
    assert "data-sort-type" in html
    compact_table = table_html(html)
    compact_header = table_header_html(html)
    assert header_count(html) <= 19
    assert "Market" in compact_table
    assert "IPO Px" in compact_table
    assert "LTP" in compact_table
    assert "IPO Gain" in compact_header
    assert "1M" not in compact_header
    assert "3M" not in compact_header
    assert "52W DD" not in compact_header
    assert "P/E" not in compact_header
    assert "Sales YoY" not in compact_header
    assert "PAT YoY" not in compact_header
    assert "OPM" not in compact_header
    assert "ROCE" not in compact_header
    assert "Data" in compact_header
    assert "Decision" in compact_header
    assert "Risk" in compact_header
    assert "Links" in compact_header
    assert "Value Score" not in compact_header
    assert "Quarter Score" not in compact_header
    assert "Score Explanation" not in compact_header
    assert "Financial Data" not in compact_header
    assert "Symbol Confidence" not in compact_header
    assert "Risk Alerts" not in compact_header
    assert "Value Investor GPT Analysis" in html
    assert "g-6a031ff323688191872d730b281c71f0-next-multi-bagger-of-indian-market" in html
    assert 'option value="2026" selected' in html
    assert "/ipo/export-mainboard" not in html
    assert "/ipo/export-sme" not in html
    assert "/ipo/export-combined" in html
    assert "Links" in compact_header
    assert "Quarterly Monitoring Table" not in html
    assert "Company Detail Page" not in html
    assert "Data Issues" not in html
    assert "Quarterly Ranking Snapshots" not in html


def test_ipo_compact_table_combines_market_and_keeps_only_one_price_column(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "ipo.db")
    row = simple_perf_record(1, "sme", 35, 2026)
    row.update(
        {
            "company_name": "Apsis AerocomAPSISAERO",
            "symbol": "APSISAERO",
            "exchange": "NSE SME",
            "ipo_type": "SME",
            "kite_ltp": 140,
            "source_current_price": 141,
            "pe_ratio": 18,
            "latest_revenue_growth_yoy": 22,
            "latest_pat_growth_yoy": 19,
            "opm_pct": 16,
            "roce": 21,
            "lt_data_quality_score": 84,
            "lt_final_decision": "WAIT",
            "lt_key_risk": "Valuation expensive; full details",
            "screener_url": "https://www.screener.in/company/APSISAERO/",
            "source_url": "https://example.test/exchange",
        }
    )
    state = app.PageState(active_tab="ipo", ipo_year=2026)
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

    compact = table_html(app.render_ipo_panel(state))
    compact_header = table_header_html(app.render_ipo_panel(state))

    assert header_count(app.render_ipo_panel(state)) == 11
    assert "Apsis Aerocom<" in compact
    assert "Apsis AerocomAPSISAERO" not in compact
    assert "APSISAERO · NSE SME" in compact
    assert "Source Price" not in compact
    assert "Market Data" not in compact
    assert "Gain from IPO in Rs" not in compact
    assert "Python Decision" not in compact_header
    assert "GPT Decision" not in compact_header
    assert "Financial Data" not in compact
    assert "Screener" in compact and "Exchange" in compact and "View Details" in compact
    assert "Valuation expensive" in compact


def test_ipo_detail_panel_keeps_removed_information_available(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "ipo.db")
    row = simple_perf_record(1, "mainboard", 25, 2026)
    row.update(
        {
            "listing_price": 120,
            "issue_size": 500,
            "six_month_return_pct": 12,
            "one_year_return_pct": None,
            "average_traded_value_20d": 10_000_000,
            "pb_ratio": 3.2,
            "ev_ebitda": 14,
            "sales_qoq_pct": 8,
            "pat_qoq_pct": 9,
            "debt_to_equity": 0.4,
            "cfo_pat": 0.9,
            "lt_investment_score": 76,
            "lt_python_decision": "WAIT",
            "lt_gpt_decision": "NOT_RUN",
            "lt_buy_zone": "NOT_CALCULABLE",
            "lt_missing_evidence": "Quarterly; Cash Flow",
        }
    )
    state = app.PageState(active_tab="ipo", ipo_year=2026)
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

    compact = table_html(app.render_ipo_panel(state))

    assert "Listing Price" in compact
    assert "6M %" in compact
    assert "EV/EBITDA" in compact
    assert "Python Decision" in compact
    assert "Missing Evidence" in compact


def test_ipo_view_modes_and_dynamic_empty_column_hiding(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "ipo.db")
    rows = [simple_perf_record(index, "mainboard", 20 + index, 2026) for index in range(1, 4)]
    for row in rows:
        row.update(
            {
                "kite_ltp": 150,
                "latest_revenue_growth_yoy": 18,
                "latest_pat_growth_yoy": 16,
                "opm_pct": 14,
                "roce": 19,
                "lt_data_quality_score": 71,
                "lt_investment_score": 68,
                "lt_final_decision": "WAIT",
                "sales_qoq_pct": None,
                "average_traded_value_20d": 25_000_000,
                "debt_to_equity": 0.5,
            }
        )
    dashboard = {
        "mode": "simple_performance",
        "upcoming_pipeline_version": ipo_data_service.IPO_UPCOMING_PIPELINE_VERSION,
        "year": 2026,
        "mainboard_top20": [],
        "sme_top20": [],
        "combined_top40": rows,
        "upcoming_next7": [],
        "messages": [],
        "summary": {},
    }

    for view, expected in {
        "Compact": "IPO Gain",
        "Price": "20D Value",
        "Fundamentals": "D/E",
        "Research": "Invest",
    }.items():
        state = app.PageState(active_tab="ipo", ipo_year=2026, ipo_table_view=view)
        state.ipo_dashboard = dashboard
        page = app.render_ipo_panel(state)
        rendered = table_header_html(page)
        assert expected in rendered
        assert 'name="ipo_selected_key"' in table_html(page)

    hidden_state = app.PageState(active_tab="ipo", ipo_year=2026, ipo_table_view="Fundamentals")
    hidden_state.ipo_dashboard = dashboard
    hidden = table_header_html(app.render_ipo_panel(hidden_state))
    assert "Sales QoQ" not in hidden
    assert "Sales YoY" in hidden
    assert "PAT YoY" in hidden
    assert "OPM" in hidden
    assert "ROCE" in hidden

    shown_state = app.PageState(
        active_tab="ipo",
        ipo_year=2026,
        ipo_table_view="Fundamentals",
        ipo_show_unavailable_columns=True,
    )
    shown_state.ipo_dashboard = dashboard
    assert "Sales QoQ" in table_header_html(app.render_ipo_panel(shown_state))


def test_ipo_governance_pending_when_evidence_missing():
    row = ipo_data_service._enrich_simple_ipo_decision(
        verified_live_record(
            promoter_holding=None,
            promoter_pledge=None,
            pledge_pct=None,
            pledge_change=None,
            promoter_holding_change=None,
        )
    )

    assert row["governance_flag"] == "DATA PENDING"


def test_render_ipo_panel_rebuilds_dashboard_from_older_upcoming_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "ipo.db")
    calls: list[int] = []
    fresh_dashboard = {
        "mode": "simple_performance",
        "upcoming_pipeline_version": ipo_data_service.IPO_UPCOMING_PIPELINE_VERSION,
        "year": 2026,
        "mainboard_top20": [],
        "sme_top20": [],
        "combined_top40": [],
        "upcoming_next7": [
            {
                "company_name": "Recovered IPO",
                "symbol": "RECOVERED",
                "ipo_open_date": "2026-07-29",
                "ipo_close_date": "2026-07-31",
                "days_to_ipo": -2,
                "is_open_for_application": True,
                "application_status": "Open for application",
                "source": "NSE upcoming IPO API",
            }
        ],
        "messages": [],
        "summary": {"upcoming_next7_count": 1},
    }

    def build_dashboard(year, today=None):
        calls.append(year)
        return fresh_dashboard

    monkeypatch.setattr(app, "build_simple_ipo_performance_dashboard", build_dashboard)
    state = app.PageState(active_tab="ipo", ipo_year=2026)
    state.ipo_dashboard = {
        "mode": "simple_performance",
        "year": 2026,
        "upcoming_next7": [],
        "messages": [],
        "summary": {"upcoming_next7_count": 0},
    }

    html = app.render_ipo_panel(state)

    assert calls == [2026]
    assert state.ipo_dashboard is fresh_dashboard
    assert "Recovered IPO" in html
    assert "ipo-upcoming-open" in html


def test_simple_ipo_upcoming_adds_gmp_percent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ipo_data_service,
        "_simple_ipo_cache_path",
        lambda year, ipo_type: tmp_path / f"simple_{ipo_type}_{year}.csv",
    )
    monkeypatch.setattr(ipo_data_service, "fetch_chittorgarh_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_ipomarket_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_ipoguru_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_secondary_ipo_source", lambda source_key, year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    upcoming_rows = [
        {
            "company_name": "GMP IPO",
            "symbol": "GMPIPO",
            "ipo_date": "2026-07-22",
            "sector": "EMS",
            "price_band": "100-110",
            "gmp": "22",
        }
    ]
    monkeypatch.setattr(ipo_data_service, "_load_research_ready_upcoming_ipos", lambda today=None: (upcoming_rows, []))

    dashboard = build_simple_ipo_performance_dashboard(2026, force_refresh=True, today=date(2026, 7, 20))

    assert dashboard["upcoming_next7"][0]["gmp_pct"] == 20.0


def test_simple_ipo_upcoming_accepts_open_date_range_and_highlights_gmp(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ipo_data_service,
        "_simple_ipo_cache_path",
        lambda year, ipo_type: tmp_path / f"simple_{ipo_type}_{year}.csv",
    )
    monkeypatch.setattr(ipo_data_service, "fetch_chittorgarh_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_ipomarket_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_ipoguru_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_secondary_ipo_source", lambda source_key, year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    upcoming_rows = [
        {
            "company_name": "High GMP IPO",
            "symbol": "HIGHGMP",
            "open_date": "Jul 24 - Jul 28, 2026",
            "sector": "Manufacturing capex",
            "price_band": "100",
            "current_gmp": "45",
        },
        {
            "company_name": "Listing Only IPO",
            "symbol": "LISTIPO",
            "listing_date": "2026-07-24",
            "sector": "EMS",
            "price_band": "100",
            "gmp": "50",
        },
    ]
    monkeypatch.setattr(ipo_data_service, "_load_research_ready_upcoming_ipos", lambda today=None: (upcoming_rows, []))

    dashboard = build_simple_ipo_performance_dashboard(2026, force_refresh=True, today=date(2026, 7, 22))

    assert [row["company_name"] for row in dashboard["upcoming_next7"]] == ["High GMP IPO"]
    row = dashboard["upcoming_next7"][0]
    assert row["ipo_date"] == "2026-07-24"
    assert row["gmp_pct"] == 45.0
    assert row["status_badge"] == "High GMP >40%"
    assert row["status_class"] == "hot"


def test_simple_ipo_upcoming_marks_active_subscription_window_and_keeps_it_visible(monkeypatch):
    upcoming_rows = [
        {
            "company_name": "Already Open IPO",
            "symbol": "OPENIPO",
            "open_date": "Jul 18 - Jul 23, 2026",
        },
        {
            "company_name": "Closes Today IPO",
            "symbol": "CLOSES",
            "ipo_open_date": "2026-07-19",
            "ipo_close_date": "2026-07-20",
        },
        {
            "company_name": "Closed IPO",
            "symbol": "CLOSED",
            "open_date": "2026-07-15",
            "close_date": "2026-07-19",
        },
    ]
    monkeypatch.setattr(
        ipo_data_service,
        "_load_research_ready_upcoming_ipos",
        lambda today=None: (upcoming_rows, []),
    )

    rows, notes = ipo_data_service._upcoming_ipos_next_7_days(date(2026, 7, 20))

    assert notes == []
    assert [row["symbol"] for row in rows] == ["OPENIPO", "CLOSES"]
    assert all(row["is_open_for_application"] is True for row in rows)
    assert all(row["application_status"] == "Open for application" for row in rows)
    assert rows[0]["ipo_open_date"] == "2026-07-18"
    assert rows[0]["ipo_close_date"] == "2026-07-23"
    assert rows[1]["ipo_close_date"] == "2026-07-20"


def test_render_ipo_panel_highlights_high_gmp_upcoming_row(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "ipo.db")
    monkeypatch.setattr(
        app,
        "build_simple_ipo_performance_dashboard",
        lambda year, today=None: {
            "mode": "simple_performance",
            "year": year,
            "generated_at": "2026-07-22T10:00:00",
            "last_refreshed": "2026-07-22T10:00:00",
            "mainboard_top20": [],
            "sme_top20": [],
            "combined_top40": [],
            "upcoming_next7": [
                {
                    "company_name": "High GMP IPO",
                    "symbol": "HIGHGMP",
                    "ipo_date": "2026-07-24",
                    "ipo_open_date": "2026-07-24",
                    "ipo_close_date": "2026-07-28",
                    "days_to_ipo": 2,
                    "is_open_for_application": True,
                    "application_status": "Open for application",
                    "sector": "Manufacturing capex",
                    "ipo_type": "Mainboard",
                    "issue_size": "500 Cr",
                    "price_band": "100",
                    "gmp": "45",
                    "gmp_pct": 45.0,
                    "status_badge": "High GMP >40%",
                    "status_class": "hot",
                    "source": "IPOWatch GMP/upcoming table",
                    "source_url": "https://example.test/high-gmp",
                    "screener_url": "https://www.screener.in/company/HIGHGMP/",
                }
            ],
            "messages": [],
            "summary": {
                "total_ipos_loaded": 0,
                "symbols_resolved": 0,
                "financial_data_available": 0,
                "buy_zone_candidates": 0,
                "tracking_buy_candidates": 0,
                "risk_alert_count": 0,
                "upcoming_next7_count": 1,
            },
        },
    )
    state = app.PageState(active_tab="ipo", ipo_year=2026, ipo_quarter="Latest Available")

    html = app.render_ipo_panel(state)

    assert "ipo-upcoming-hot" in html
    assert 'class="ipo-upcoming-open ipo-upcoming-hot"' in html
    assert "Light-blue rows are currently open for application" in html
    assert "2026-07-28" in html
    assert "Open for application" in html
    assert "+45.00%" in html
    assert "High GMP &gt;40%" in html


def test_simple_ipo_upcoming_keeps_clean_unresolved_company_details(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ipo_data_service,
        "_simple_ipo_cache_path",
        lambda year, ipo_type: tmp_path / f"simple_{ipo_type}_{year}.csv",
    )
    monkeypatch.setattr(ipo_data_service, "fetch_chittorgarh_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_ipomarket_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_ipoguru_ipos", lambda year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    monkeypatch.setattr(ipo_data_service, "fetch_secondary_ipo_source", lambda source_key, year, ipo_type="mainboard": {"records": [], "source": "", "error": ""})
    upcoming_rows = [
        {
            "company_name": "Unknown Future Systems Listed: 22 Jul 2026 Symbol pending",
            "symbol": "Symbol pending",
            "ipo_date": "2026-07-22",
            "sector": "Industrial automation",
            "price_band": "100",
            "gmp": "20",
            "source_url": "https://example.test/ipo",
        }
    ]
    monkeypatch.setattr(ipo_data_service, "_load_research_ready_upcoming_ipos", lambda today=None: (upcoming_rows, []))

    dashboard = build_simple_ipo_performance_dashboard(2026, force_refresh=True, today=date(2026, 7, 20))
    row = dashboard["upcoming_next7"][0]

    assert row["company_name"] == "Unknown Future Systems"
    assert row["symbol"] == ""
    assert row["gmp_pct"] == 20.0
    assert "Listed" not in row["screener_url"]
    assert row["source_url"] == "https://example.test/ipo"


def test_selected_ipo_rows_from_dashboard_keys_filters_checked_rows():
    rows = [simple_perf_record(1, "mainboard", 25, 2026), simple_perf_record(2, "sme", 35, 2026)]
    selected_key = app.ipo_gpt_row_key(rows[1])

    selected = app.selected_ipo_rows_from_dashboard_keys({"combined_top40": rows}, {selected_key}, limit=20)

    assert [row["company_name"] for row in selected] == [rows[1]["company_name"]]


def test_save_ipo_gpt_analysis_to_db(tmp_path):
    db_path = tmp_path / "ipo.db"

    saved_id = app.save_ipo_gpt_analysis_to_db(db_path, 2026, "prompt text", "analysis text", "resp_1", 3)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT year, selected_count, response_id, prompt, output FROM ipo_gpt_analysis WHERE id = ?",
            (saved_id,),
        ).fetchone()
    assert row == (2026, 3, "resp_1", "prompt text", "analysis text")
