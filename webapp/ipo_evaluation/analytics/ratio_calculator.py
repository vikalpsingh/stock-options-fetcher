from __future__ import annotations

import math
from collections.abc import Sequence


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def percentage_change(current: float | None, previous: float | None) -> float | None:
    ratio = safe_divide(
        None if current is None or previous is None else current - previous,
        previous,
    )
    return round(ratio * 100, 2) if ratio is not None else None


def cagr(latest: float | None, oldest: float | None, years: float) -> float | None:
    if latest is None or oldest is None or latest <= 0 or oldest <= 0 or years <= 0:
        return None
    return round(((latest / oldest) ** (1 / years) - 1) * 100, 2)


def null_safe_median(values: Sequence[float | None]) -> float | None:
    clean = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / 2


def calculate_financial_ratios(values: dict[str, float | None]) -> tuple[dict[str, float | None], list[str]]:
    warnings: list[str] = []

    def ratio(name: str, numerator: str, denominator: str, multiplier: float = 1.0) -> float | None:
        value = safe_divide(values.get(numerator), values.get(denominator))
        if value is None:
            warnings.append(f"{name}: missing or invalid {numerator}/{denominator}")
            return None
        return round(value * multiplier, 4)

    revenue = values.get("revenue")
    cfo = values.get("cash_flow_from_operations")
    pat = values.get("pat")
    capex = values.get("capital_expenditure")
    debt = values.get("total_debt")
    cash = values.get("cash_and_equivalents")
    output: dict[str, float | None] = {
        "ebitda_margin": ratio("ebitda_margin", "ebitda", "revenue", 100),
        "net_margin": ratio("net_margin", "pat", "revenue", 100),
        "roe": ratio("roe", "pat", "equity", 100),
        "roa": ratio("roa", "pat", "total_assets", 100),
        "asset_turnover": ratio("asset_turnover", "revenue", "total_assets"),
        "debt_equity": ratio("debt_equity", "total_debt", "equity"),
        "interest_coverage": ratio("interest_coverage", "ebit", "finance_cost"),
        "current_ratio": ratio("current_ratio", "current_assets", "current_liabilities"),
        "cfo_pat": ratio("cfo_pat", "cash_flow_from_operations", "pat"),
        "cfo_ebitda": ratio("cfo_ebitda", "cash_flow_from_operations", "ebitda"),
        "debtor_days": ratio("debtor_days", "receivables", "revenue", 365),
        "inventory_days": ratio("inventory_days", "inventory", "revenue", 365),
        "payable_days": ratio("payable_days", "payables", "revenue", 365),
    }
    if debt is None or cash is None:
        output["net_debt_equity"] = None
        warnings.append("net_debt_equity: total_debt or cash_and_equivalents missing")
    else:
        output["net_debt_equity"] = safe_divide(debt - cash, values.get("equity"))
    output["free_cash_flow"] = None if cfo is None or capex is None else cfo - abs(capex)
    output["fcf_margin"] = safe_divide(output["free_cash_flow"], revenue)
    debtor = output["debtor_days"]
    inventory = output["inventory_days"]
    payable = output["payable_days"]
    output["cash_conversion_cycle"] = (
        None if debtor is None or inventory is None or payable is None else debtor + inventory - payable
    )
    return output, warnings
