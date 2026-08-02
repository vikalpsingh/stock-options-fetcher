from __future__ import annotations

from dataclasses import dataclass
from typing import Any


Status = str


@dataclass(frozen=True)
class MetricRule:
    metric_code: str
    display_name: str
    category: str
    unit: str = ""
    direction: str = "NEUTRAL"
    green_threshold: float | None = None
    amber_threshold: float | None = None
    red_threshold: float | None = None
    materiality_percent: float = 10.0
    materiality_percentage_points: float = 1.0
    tooltip_template: str = ""


METRIC_RULES: dict[str, MetricRule] = {
    "Sales": MetricRule("sales", "Sales", "growth", "Cr", "HIGHER_IS_BETTER", materiality_percent=15),
    "Expenses": MetricRule("expenses", "Expenses", "cost", "Cr", "LOWER_IS_BETTER", materiality_percent=15),
    "Operating Profit": MetricRule("operating_profit", "Operating Profit", "profit", "Cr", "HIGHER_IS_BETTER", materiality_percent=10),
    "Profit before tax": MetricRule("pbt", "Profit before tax", "profit", "Cr", "HIGHER_IS_BETTER", materiality_percent=10),
    "Net Profit": MetricRule("net_profit", "Net Profit", "profit", "Cr", "HIGHER_IS_BETTER", materiality_percent=10),
    "OPM %": MetricRule("opm", "OPM", "margin", "%", "HIGHER_IS_BETTER", green_threshold=20, amber_threshold=12, red_threshold=12, materiality_percentage_points=1),
    "ROCE %": MetricRule("roce", "ROCE", "profitability", "%", "HIGHER_IS_BETTER", green_threshold=20, amber_threshold=12, red_threshold=12, materiality_percentage_points=1),
    "ROCE": MetricRule("roce", "ROCE", "profitability", "%", "HIGHER_IS_BETTER", green_threshold=20, amber_threshold=12, red_threshold=12, materiality_percentage_points=1),
    "ROE": MetricRule("roe", "ROE", "profitability", "%", "HIGHER_IS_BETTER", green_threshold=18, amber_threshold=10, red_threshold=10, materiality_percentage_points=1),
    "Return on equity": MetricRule("roe", "ROE", "profitability", "%", "HIGHER_IS_BETTER", green_threshold=18, amber_threshold=10, red_threshold=10, materiality_percentage_points=1),
    "Debt to equity": MetricRule("debt_equity", "Debt/Equity", "leverage", "x", "LOWER_IS_BETTER", green_threshold=0.30, amber_threshold=0.75, red_threshold=0.75),
    "Borrowings": MetricRule("borrowings", "Borrowings", "leverage", "Cr", "LOWER_IS_BETTER", materiality_percent=10),
    "Cash from Operating Activity": MetricRule("cfo", "CFO", "cash_flow", "Cr", "HIGHER_IS_BETTER", materiality_percent=10),
    "Free Cash Flow": MetricRule("fcf", "Free Cash Flow", "cash_flow", "Cr", "HIGHER_IS_BETTER", materiality_percent=10),
    "Cash from Financing Activity": MetricRule("financing_cf", "Financing Cash Flow", "cash_flow", "Cr", "CONTEXTUAL", materiality_percent=20),
    "Debtor Days": MetricRule("debtor_days", "Debtor Days", "working_capital", "days", "LOWER_IS_BETTER", green_threshold=45, amber_threshold=90, red_threshold=90, materiality_percent=10),
    "Inventory Days": MetricRule("inventory_days", "Inventory Days", "working_capital", "days", "LOWER_IS_BETTER", green_threshold=60, amber_threshold=150, red_threshold=150, materiality_percent=10),
    "Cash Conversion Cycle": MetricRule("cash_conversion_cycle", "Cash Conversion Cycle", "working_capital", "days", "LOWER_IS_BETTER", green_threshold=45, amber_threshold=90, red_threshold=90, materiality_percent=10),
    "Capacity Utilization": MetricRule("capacity_utilization", "Capacity Utilization", "operating_kpi", "%", "CONTEXTUAL", green_threshold=80, amber_threshold=95, red_threshold=50),
    "Installed Capacity (Components per Annum)": MetricRule("installed_capacity", "Installed Capacity", "operating_kpi", "", "HIGHER_IS_BETTER", materiality_percent=10),
    "Components Produced (Actual Production)": MetricRule("production", "Production", "operating_kpi", "", "HIGHER_IS_BETTER", materiality_percent=10),
    "Manufacturing Accuracy / Quality Rating": MetricRule("quality_rating", "Quality Rating", "operating_kpi", "%", "HIGHER_IS_BETTER", green_threshold=98, amber_threshold=95, red_threshold=95, materiality_percentage_points=0.25),
    "Stock P/E": MetricRule("pe", "P/E", "valuation", "x", "CONTEXTUAL", green_threshold=25, amber_threshold=45, red_threshold=60),
    "EVEBITDA": MetricRule("ev_ebitda", "EV/EBITDA", "valuation", "x", "CONTEXTUAL", green_threshold=15, amber_threshold=25, red_threshold=35),
    "PEG Ratio": MetricRule("peg", "PEG", "valuation", "x", "CONTEXTUAL", green_threshold=1, amber_threshold=2, red_threshold=2),
}


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _ordered_values(row: dict[str, Any]) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for period, value in row.items():
        number = _num(value)
        if number is not None:
            values.append((str(period), number))
    return values


def _fmt(value: float | None, unit: str = "") -> str:
    if value is None:
        return "Unavailable"
    decimals = 2 if abs(value) < 100 else 0
    suffix = "%" if unit == "%" else f" {unit}" if unit and unit not in {"x", "Cr", "days"} else ""
    if unit == "x":
        suffix = "x"
    if unit == "Cr":
        suffix = " Cr"
    if unit == "days":
        suffix = " days"
    return f"{value:,.{decimals}f}{suffix}"


def _absolute_status(value: float | None, rule: MetricRule) -> Status:
    if value is None:
        return "unavailable"
    if rule.direction == "NEUTRAL":
        return "neutral"
    if rule.metric_code == "pe" or rule.category == "valuation":
        if rule.red_threshold is not None and value >= rule.red_threshold:
            return "negative"
        if rule.amber_threshold is not None and value >= rule.amber_threshold:
            return "warning"
        return "warning"
    if rule.metric_code == "capacity_utilization":
        if value >= 95:
            return "warning"
        return "positive" if value >= 80 else "warning" if value >= 50 else "negative"
    if rule.direction == "HIGHER_IS_BETTER":
        if rule.green_threshold is not None and value >= rule.green_threshold:
            return "positive"
        if rule.amber_threshold is not None and value >= rule.amber_threshold:
            return "warning"
        if rule.red_threshold is not None:
            return "negative"
    if rule.direction == "LOWER_IS_BETTER":
        if rule.green_threshold is not None and value <= rule.green_threshold:
            return "positive"
        if rule.amber_threshold is not None and value <= rule.amber_threshold:
            return "warning"
        if rule.red_threshold is not None:
            return "negative"
    return "neutral"


def _trend_status(previous: float | None, latest: float | None, rule: MetricRule) -> tuple[Status, float | None, str]:
    if previous is None or latest is None:
        return "unavailable", None, ""
    if rule.unit == "%":
        delta = latest - previous
        if abs(delta) < rule.materiality_percentage_points:
            return "neutral", delta, "percentage_points"
        favourable = delta > 0 if rule.direction != "LOWER_IS_BETTER" else delta < 0
        return ("positive" if favourable else "negative"), delta, "percentage_points"
    if previous == 0:
        return "unavailable", None, ""
    delta_pct = ((latest - previous) / abs(previous)) * 100
    if abs(delta_pct) < rule.materiality_percent:
        return "neutral", delta_pct, "percent"
    favourable = delta_pct > 0 if rule.direction != "LOWER_IS_BETTER" else delta_pct < 0
    if rule.direction == "CONTEXTUAL":
        return "warning", delta_pct, "percent"
    return ("positive" if favourable else "negative"), delta_pct, "percent"


def assess_metric(label: str, row: dict[str, Any], *, revenue_row: dict[str, Any] | None = None) -> dict[str, Any]:
    rule = METRIC_RULES.get(label, MetricRule(label.lower().replace(" ", "_"), label, "other"))
    ordered = _ordered_values(row)
    if not ordered:
        return {
            "value_status": "unavailable",
            "trend_status": "unavailable",
            "display_value": "Unavailable",
            "delta_value": None,
            "delta_unit": "",
            "reason": f"{rule.display_name} unavailable or invalid.",
            "confidence": 0.0,
        }
    previous = ordered[-2][1] if len(ordered) > 1 else None
    latest_period, latest = ordered[-1]
    value_status = _absolute_status(latest, rule)
    trend_status, delta, delta_unit = _trend_status(previous, latest, rule)
    if label == "Expenses" and revenue_row:
        rev_values = _ordered_values(revenue_row)
        if len(rev_values) >= 2 and previous not in {None, 0}:
            expense_growth = ((latest - previous) / abs(previous)) * 100
            rev_previous, rev_latest = rev_values[-2][1], rev_values[-1][1]
            revenue_growth = ((rev_latest - rev_previous) / abs(rev_previous)) * 100 if rev_previous else None
            if revenue_growth is not None and expense_growth > revenue_growth + 5:
                trend_status = "negative"
                delta = expense_growth
                delta_unit = "percent"
    if rule.metric_code == "financing_cf" and latest > 0:
        value_status = "warning"
        trend_status = "warning"
    if rule.metric_code == "fcf" and previous is not None and previous < 0 < latest:
        value_status = "positive"
        trend_status = "positive"
    if value_status == "positive" and trend_status == "negative":
        headline = "Strong but deteriorating"
    elif value_status == "warning" or trend_status == "warning":
        headline = "Caution / mixed"
    elif value_status == "negative" or trend_status == "negative":
        headline = "Unfavourable"
    elif value_status == "positive" or trend_status == "positive":
        headline = "Favourable"
    else:
        headline = "Neutral"
    delta_text = ""
    if delta is not None:
        if delta_unit == "percentage_points":
            delta_text = f" {'↑' if delta > 0 else '↓'}{abs(delta):.2f} pp"
        else:
            delta_text = f" {'↑' if delta > 0 else '↓'}{abs(delta):.1f}%"
    reason = f"{headline}: {rule.display_name} is {_fmt(latest, rule.unit)} in {latest_period}{delta_text}."
    return {
        "value_status": value_status,
        "trend_status": trend_status,
        "display_value": _fmt(latest, rule.unit),
        "delta_value": delta,
        "delta_unit": delta_unit,
        "reason": reason,
        "confidence": 0.9 if len(ordered) >= 2 else 0.65,
    }


def assess_table(table: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    revenue_row = table.get("Sales")
    return {
        label: assess_metric(label, row, revenue_row=revenue_row)
        for label, row in table.items()
        if isinstance(row, dict)
    }
