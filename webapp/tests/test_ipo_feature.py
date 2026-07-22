from __future__ import annotations

from datetime import date
from pathlib import Path
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
    IPO_SNAPSHOT_FIELDS,
    build_ipo_dashboard,
    export_ipo_records_csv,
    load_ipo_snapshots,
    save_ipo_top10_snapshot,
)
from ipo_scoring_engine import filter_multibaggers_or_all, score_ipo_company


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
    row = dashboard["data_issues"][0]
    assert row["symbol"] == "PENDINGIPO"
    assert row["is_listed_verified"] is True
    assert row["eligible_for_scoring"] is False
    assert row["action"] == "WATCH / DATA PENDING"
    assert "latest_financial_data" in row["missing_fields"]
    assert row.get("total_score") is None
    assert not row.get("is_buy_zone")


def test_render_ipo_panel_has_default_controls(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "ipo.db")
    state = app.PageState(active_tab="ipo", ipo_year=2026, ipo_quarter="Latest Available")

    html = app.render_ipo_panel(state)

    assert "IPO Screener" in html
    assert "Upcoming IPOs" in html
    assert 'option value="2026" selected' in html
    assert "/ipo/export-watchlist" in html
    assert "/ipo/export-buy-zone" in html
    assert "/ipo/export-risk-alerts" in html
    assert "/ipo/export-quarterly" in html
    assert "Only positive return IPOs" in html
    assert "GMP is unofficial" in html
    assert IPO_NO_VERIFIED_DATA_MESSAGE in html
    assert "Data Issues" in html
    assert "Company Detail Page" in html
    assert "Quarterly Monitoring Table" in html
    assert "Quarterly Ranking Snapshots" not in html
    assert "Buy-zone" in html
    assert 'name="ipo_market_type"' in html
    assert 'name="ipo_theme"' in html
    assert 'name="ipo_ranking_view"' in html
    assert 'name="ipo_only_multibagger_present"' in html
