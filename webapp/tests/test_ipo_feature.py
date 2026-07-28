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

    assert row["company_name"] == "Ap Apsis Aerocom"
    assert row["symbol"] == ""
    assert row["screener_url"] == "https://www.screener.in/search/?q=Ap+Apsis+Aerocom"
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

    assert "Listed IPO Performance Tracker" in html
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
    assert "GMP %" in html
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
    assert "Value Investor GPT Analysis" in html
    assert "g-6a031ff323688191872d730b281c71f0-next-multi-bagger-of-indian-market" in html
    assert 'option value="2026" selected' in html
    assert "/ipo/export-mainboard" not in html
    assert "/ipo/export-sme" not in html
    assert "/ipo/export-combined" in html
    assert "Screener" in html
    assert "Data Source" in html
    assert "Quarterly Monitoring Table" not in html
    assert "Company Detail Page" not in html
    assert "Data Issues" not in html
    assert "Quarterly Ranking Snapshots" not in html


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
