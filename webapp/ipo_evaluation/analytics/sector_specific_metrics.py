from __future__ import annotations


SECTOR_METRICS = {
    "manufacturing": {"order_book", "order_book_to_sales", "capacity_utilization", "asset_turnover", "working_capital_days"},
    "pharma": {"export_revenue_pct", "research_development_pct", "regulatory_observations", "gross_margin_trend"},
    "healthcare": {"bed_count", "occupancy", "arpob", "ebitda_per_occupied_bed"},
    "financial": {"aum_growth", "nim", "gnpa", "nnpa", "capital_adequacy", "roa", "roe"},
    "insurance": {"annualized_premium_equivalent", "vnb_margin", "persistency", "solvency_ratio"},
    "consumer": {"repeat_rate", "contribution_margin", "active_user_growth", "distribution_expansion"},
    "power": {"installed_capacity", "order_pipeline", "capacity_utilization", "debtor_exposure"},
}


def sector_metric_coverage(sector: str, metrics: dict[str, object]) -> tuple[float, list[str]]:
    normalized = sector.lower()
    group = next((name for name in SECTOR_METRICS if name in normalized), "manufacturing")
    required = SECTOR_METRICS[group]
    missing = sorted(name for name in required if metrics.get(name) is None)
    return round((len(required) - len(missing)) / len(required) * 100, 2), missing


def is_financial_sector(sector: str) -> bool:
    value = sector.lower()
    return any(term in value for term in ("financial", "nbfc", "bank", "lender", "insurance", "amc"))
