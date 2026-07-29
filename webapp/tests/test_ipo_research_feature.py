from __future__ import annotations

import json
from datetime import datetime

import pytest

import ipo.research as research
from ipo.research import (
    build_ipo_research_analysis,
    enforce_gpt_research_hard_rules,
    find_saved_research,
    load_research_index,
    peer_comparison_highlights,
    render_ipo_research_html,
    save_ipo_research,
)


@pytest.fixture(autouse=True)
def no_live_ipo_enrichment(monkeypatch):
    monkeypatch.setattr(research, "_enrich_simple_ipo_decision", None)


def ipo_row(
    company: str = "Rubicon Research",
    symbol: str = "RUBICON",
    sector: str = "Healthcare/diagnostics",
    *,
    isin: str = "INE000A01001",
    current_price: float = 160.0,
    market_cap: float = 5200.0,
    revenue_growth: float = 28.0,
    pat_growth: float = 24.0,
    roce: float = 24.0,
    roe: float = 21.0,
    cfo_pat: float = 0.85,
    pe: float = 34.0,
    peer_pe: float = 38.0,
    value_score: float | None = 82.0,
    drawdown: float = -24.0,
    financial_status: str = "Financial Data Available",
) -> dict[str, object]:
    row: dict[str, object] = {
        "company_name": company,
        "symbol": symbol,
        "exchange": "NSE",
        "isin": isin,
        "ipo_type": "Mainboard",
        "listing_date": "2026-03-18",
        "ipo_price": 100.0,
        "current_price": current_price,
        "current_gain_pct": current_price - 100.0,
        "drawdown_from_52w_high_pct": drawdown,
        "sector": sector,
        "theme": sector,
        "market_cap": market_cap,
        "financial_data_status": financial_status,
        "latest_revenue_growth_yoy": revenue_growth,
        "revenue_growth_yoy": revenue_growth,
        "sales_growth_yoy": revenue_growth,
        "latest_pat_growth_yoy": pat_growth,
        "pat_growth_yoy": pat_growth,
        "profit_growth_yoy": pat_growth,
        "cfo": 100.0,
        "cfo_pat": cfo_pat,
        "free_cash_flow": 80.0,
        "roce": roce,
        "roe": roe,
        "opm": 18.0,
        "debt_to_equity": 0.2,
        "debtor_days": 45.0,
        "pe": pe,
        "pe_ratio": pe,
        "peer_median_pe": peer_pe,
        "promoter_holding": 60.0,
        "promoter_pledge": 0.0,
        "promoter_change_qoq": 0.0,
        "pledge_change_qoq": 0.0,
        "fii_holding": 3.0,
        "dii_holding": 5.0,
        "liquidity_score": 85.0,
        "average_volume": 250000.0,
        "screener_url": f"https://www.screener.in/company/{symbol}/" if symbol else "",
    }
    if value_score is not None:
        row["value_score"] = value_score
    return row


def test_one_selected_company_auto_adds_top_two_sector_peers():
    analysis = build_ipo_research_analysis(
        [ipo_row(sector="Power & electrical infra")],
        2026,
        as_of=datetime(2026, 7, 28, 9, 30),
    )

    assert len(analysis["selected_companies"]) == 1
    assert len(analysis["peer_companies"]) == 2
    assert all(row["role"] == "Peer" for row in analysis["peer_companies"])
    assert analysis["selected_companies"][0]["symbol"] == "RUBICON"


def test_multiple_selected_companies_compare_selected_only_without_peers():
    rows = [
        ipo_row("Rubicon Research", "RUBICON", "Healthcare/diagnostics"),
        ipo_row("Omnitech Engineering", "OMNITECH", "Manufacturing capex"),
    ]

    analysis = build_ipo_research_analysis(rows, 2026, add_sector_leaders=False)

    assert len(analysis["selected_companies"]) == 2
    assert analysis["peer_companies"] == []
    assert {row["symbol"] for row in analysis["all_companies"]} == {"RUBICON", "OMNI"}


def test_multiple_selected_companies_can_add_sector_leaders():
    rows = [
        ipo_row("Rubicon Research", "RUBICON", "Healthcare/diagnostics"),
        ipo_row("Omnitech Engineering", "OMNITECH", "Manufacturing capex"),
    ]

    analysis = build_ipo_research_analysis(rows, 2026, add_sector_leaders=True)

    assert len(analysis["selected_companies"]) == 2
    assert len(analysis["peer_companies"]) >= 2
    assert all(row["role"] == "Peer" for row in analysis["peer_companies"])


def test_symbol_confidence_below_85_blocks_buy_zone():
    row = ipo_row("Unverified Future Winner", "", "", isin="", value_score=90.0)

    analysis = build_ipo_research_analysis([row], 2026)
    selected = analysis["selected_companies"][0]

    assert selected["resolution"]["resolution_confidence"] < 85
    assert "SYMBOL_REVIEW_NEEDED" in selected["hard_rule_blocks"]
    assert selected["buy_zone_allowed"] is False
    assert selected["final_action"] == "Symbol Review Needed"


def test_missing_financial_data_results_in_data_pending():
    row = {
        "company_name": "Rubicon Research",
        "symbol": "RUBICON",
        "exchange": "NSE",
        "isin": "INE000A01001",
        "ipo_type": "Mainboard",
        "listing_date": "2026-03-18",
        "ipo_price": 100.0,
        "current_price": 160.0,
        "market_cap": 5200.0,
        "sector": "Healthcare/diagnostics",
        "financial_data_status": "Financial Data Pending",
    }

    analysis = build_ipo_research_analysis([row], 2026)
    selected = analysis["selected_companies"][0]

    assert "FINANCIAL_DATA_PENDING" in selected["hard_rule_blocks"]
    assert selected["final_action"] == "Data Pending"
    assert selected["buy_zone_allowed"] is False


def test_gpt_cannot_override_python_hard_risk_rules():
    analysis = build_ipo_research_analysis(
        [ipo_row("Unverified Future Winner", "", "", isin="", value_score=90.0)],
        2026,
    )
    raw_gpt = json.dumps(
        {
            "buy_zone": "BUY NOW",
            "final_action": "Buy Zone Reached",
            "investment_summary": "Buy and accumulate aggressively.",
        }
    )

    enforced = json.loads(enforce_gpt_research_hard_rules(analysis, raw_gpt))

    assert enforced["buy_zone"] == "BLOCKED_BY_PYTHON_HARD_RULES"
    assert enforced["final_action"] == "WATCHLIST - HARD RULE BLOCKED"
    assert "SYMBOL_REVIEW_NEEDED" in enforced["python_hard_rule_override"]["reason_codes"]


def test_html_report_is_generated_successfully():
    analysis = build_ipo_research_analysis([ipo_row()], 2026)

    html = render_ipo_research_html(analysis, '{"investment_summary":"Watch for valuation comfort"}')

    assert "<!doctype html>" in html
    assert "IPO Long-Term Research" in html
    assert "Rubicon Research" in html
    assert "Selected Company vs Sector Leaders" in html
    assert "Peer Highlights" in html
    assert "Data Quality Gate" in html


def test_html_report_uses_sections_tables_and_green_strong_positive_markers():
    analysis = build_ipo_research_analysis([ipo_row()], 2026)

    html = render_ipo_research_html(
        analysis,
        json.dumps({"investment_summary": "Strong business, wait for valuation comfort."}),
    )

    assert "summary-grid" in html
    assert "Strong Positives" in html
    assert "Revenue Growth" in html
    assert "PAT Growth" in html
    assert "strong-positive-row" in html
    assert "strong-positive-cell" in html
    assert "Investment Summary" in html


def test_research_json_html_and_index_are_saved(tmp_path):
    analysis = build_ipo_research_analysis(
        [ipo_row()],
        2026,
        as_of=datetime(2026, 7, 28, 9, 30),
    )

    saved = save_ipo_research(analysis, base_dir=tmp_path)
    index_rows = load_research_index(base_dir=tmp_path)

    assert saved["research_id"]
    assert (tmp_path / "research_store" / "json").exists()
    assert (tmp_path / "research_store" / "html").exists()
    assert (tmp_path / "reports" / "ipo_research").exists()
    assert len(index_rows) == 1
    assert "Rubicon Research" in index_rows[0]["company_names"]


def test_research_index_records_html_and_json_paths(tmp_path):
    analysis = build_ipo_research_analysis(
        [ipo_row("Omnitech Engineering", "OMNITECH", "Manufacturing capex")],
        2026,
        as_of=datetime(2026, 7, 28, 9, 30),
    )

    save_ipo_research(analysis, base_dir=tmp_path)
    index_rows = load_research_index(base_dir=tmp_path)

    assert len(index_rows) == 1
    assert index_rows[0]["json_path"].endswith(".json")
    assert index_rows[0]["html_path"].endswith(".html")
    assert "OMNI" in index_rows[0]["symbols_key"]


def test_saved_research_can_be_reopened_by_stock_name_and_date(tmp_path):
    analysis = build_ipo_research_analysis(
        [ipo_row()],
        2026,
        as_of=datetime(2026, 7, 28, 9, 30),
    )
    save_ipo_research(analysis, base_dir=tmp_path)

    found = find_saved_research("RUBICON", "2026-07-28", base_dir=tmp_path)

    assert found is not None
    assert "RUBICON" in found["symbols_key"]


def test_old_research_is_not_overwritten(tmp_path):
    analysis = build_ipo_research_analysis(
        [ipo_row()],
        2026,
        as_of=datetime(2026, 7, 28, 9, 30),
    )

    first = save_ipo_research(analysis, base_dir=tmp_path)
    second = save_ipo_research(analysis, base_dir=tmp_path)

    assert first["json_path"] != second["json_path"]
    assert first["html_path"] != second["html_path"]
    assert len(load_research_index(base_dir=tmp_path)) == 2


def test_peer_comparison_highlights_best_and_worst_metrics():
    rows = [
        ipo_row("Alpha Manufacturing", "ALPHA", "Manufacturing capex", roce=30, roe=22, pe=28, cfo_pat=1.2, value_score=88, revenue_growth=35),
        ipo_row("Beta Manufacturing", "BETA", "Manufacturing capex", roce=12, roe=10, pe=70, cfo_pat=0.25, value_score=55, revenue_growth=8),
    ]
    rows[0]["debt_to_equity"] = 0.1
    rows[1]["debt_to_equity"] = 1.4
    rows[0]["debtor_days"] = 35
    rows[1]["debtor_days"] = 110

    highlights = peer_comparison_highlights(rows)

    assert highlights["best_roce"]["symbol"] == "ALPHA"
    assert highlights["worst_roce"]["symbol"] == "BETA"
    assert highlights["lowest_pe"]["symbol"] == "ALPHA"
    assert highlights["highest_pe"]["symbol"] == "BETA"
    assert highlights["best_cfo_pat"]["symbol"] == "ALPHA"
    assert highlights["weakest_cfo_pat"]["symbol"] == "BETA"
    assert highlights["lowest_debt"]["symbol"] == "ALPHA"
    assert highlights["highest_debt"]["symbol"] == "BETA"
    assert highlights["highest_sales_growth"]["symbol"] == "ALPHA"
    assert highlights["lowest_sales_growth"]["symbol"] == "BETA"
    assert highlights["lowest_debtor_days"]["symbol"] == "ALPHA"
    assert highlights["highest_debtor_days"]["symbol"] == "BETA"
    assert highlights["best_value_score"]["symbol"] == "ALPHA"
    assert highlights["weakest_value_score"]["symbol"] == "BETA"
