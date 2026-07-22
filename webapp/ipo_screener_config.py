"""Config for the IPO long-term opportunity screener.

The numbers here are intentionally plain so the investment model can be tuned
without touching page rendering code.
"""

from __future__ import annotations


# Score weights add up to 100. Each component is scored independently and then
# combined into a long-term IPO opportunity score.
IPO_SCORE_WEIGHTS = {
    "sector_tailwind": 20,
    "business_quality": 15,
    "growth_quality": 20,
    "capital_efficiency": 15,
    "cash_flow_quality": 15,
    "valuation_comfort": 10,
    "governance_ownership": 5,
}


IPO_MARKET_TYPE_OPTIONS = ["All", "Mainboard", "SME"]


IPO_THEME_OPTIONS = [
    "All",
    "Power & electrical infra",
    "EMS/electronics",
    "Defence/aerospace",
    "Healthcare/diagnostics",
    "AMC/financialization",
    "Specialty chemicals",
    "Consumer premiumization",
    "Manufacturing capex",
    "Data centre infra",
    "Industrial automation",
]


IPO_RANKING_VIEWS = [
    "Best IPOs by long-term score",
    "Best IPOs by sector quality",
    "Best corrected IPOs with strong fundamentals",
    "IPOs with strong results but expensive valuation",
    "IPOs with weak cash conversion",
    "IPOs to avoid",
]


# Buy-zone rules: wait for quarterly proof and valuation comfort instead of
# buying every fresh listing that moves fast after the IPO.
IPO_BUY_ZONE_RULES = {
    "min_lt_score": 75,
    "min_sector_score": 70,
    "min_revenue_growth_yoy": 15,
    "min_cfo_pat": 0.70,
    "min_drawdown_from_52w_high_pct": 20,
}


IPO_FLAG_RULES = {
    "green_revenue_growth_yoy": 20,
    "green_pat_growth_yoy": 20,
    "green_roce": 20,
    "green_cfo_pat": 0.70,
    "red_debtor_days_increase": 30,
    "red_debt_increase_pct": 25,
    "red_promoter_selling_pct": -2.0,
    "red_pledge_increase_pct": 0.5,
    "red_margin_collapse_pct": -3.0,
}


IPO_SME_POSITION_SIZING = {
    "tracking_allocation": "0.25% to 0.5%",
    "staggered_accumulation": "0.5% to 1.5%",
    "core_candidate_rule": "Core only after 4 to 6 listed quarters of execution.",
}


IPO_EXPORT_FIELD_SETS = {
    "watchlist": [
        "company_name",
        "symbol",
        "listing_date",
        "sector",
        "theme",
        "market_type",
        "lt_score",
        "action",
        "flag",
        "current_price",
        "drawdown_from_52w_high_pct",
        "latest_revenue_growth_yoy",
        "latest_pat_growth_yoy",
        "cfo_pat",
        "final_recommendation",
    ],
    "buy_zone": [
        "company_name",
        "symbol",
        "listing_date",
        "sector",
        "theme",
        "lt_score",
        "current_price",
        "drawdown_from_52w_high_pct",
        "pe_ratio",
        "peer_median_pe",
        "action",
        "final_recommendation",
    ],
    "risk_alerts": [
        "company_name",
        "symbol",
        "alert_type",
        "severity",
        "message",
        "lt_score",
        "action",
    ],
    "quarterly": [
        "company_name",
        "symbol",
        "quarter",
        "latest_revenue_growth_yoy",
        "ebitda_growth_yoy",
        "latest_pat_growth_yoy",
        "opm_trend",
        "roce",
        "roe",
        "debt_to_equity",
        "debtor_days",
        "inventory_days",
        "cash_conversion_cycle",
        "cfo_pat",
        "fcf",
        "promoter_holding_change",
        "pledge_change",
        "fii_dii_change",
        "flag",
        "action",
    ],
}


DEFAULT_IPO_SCREENER_CONFIG = {
    "score_weights": IPO_SCORE_WEIGHTS,
    "buy_zone_rules": IPO_BUY_ZONE_RULES,
    "flag_rules": IPO_FLAG_RULES,
    "sme_position_sizing": IPO_SME_POSITION_SIZING,
}
