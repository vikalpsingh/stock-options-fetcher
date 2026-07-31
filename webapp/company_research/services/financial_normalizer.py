from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .financial_calculator import number


FIELD_ALIASES = {
    "sales": {"sales", "total revenue", "totalrevenue", "operating revenue", "operatingrevenue", "revenue"},
    "operating_profit": {"operating profit", "operatingprofit", "operating income", "operatingincome", "ebit"},
    "pat": {"pat", "net profit", "netprofit", "net income", "netincome", "netincomecommonstockholders"},
    "cfo": {"operating cash flow", "totalcashfromoperatingactivities", "cash flow from operations", "cfo"},
    "market_cap": {"market capitalization", "market cap", "marketcap"},
    "pe": {"price to earning", "price to earnings", "trailing pe", "pe", "p/e"},
    "pb": {"price to book", "price/book", "pb", "p/b"},
    "ev_ebitda": {"enterprise/ebitda", "ev/ebitda", "enterprise to ebitda"},
    "roce": {"roce"},
    "roe": {"roe", "return on equity"},
    "debt_equity": {"debt to equity", "debt/equity", "debt_equity"},
    "promoter_holding": {"promoter holding", "promoter_holding"},
    "promoter_pledge": {"pledged percentage", "promoter pledge", "promoter_pledge"},
}


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch in {" ", "/", "_"}).strip()


def normalize_field_name(raw_name: Any) -> str | None:
    key = _norm(raw_name).replace("_", " ")
    compact = key.replace(" ", "")
    for normalized, aliases in FIELD_ALIASES.items():
        if key in aliases or compact in {alias.replace(" ", "") for alias in aliases}:
            return normalized
    return None


def normalize_flat_financial_row(
    row: dict[str, Any],
    *,
    source_name: str,
    source_url: str = "",
    period: str = "",
) -> dict[str, Any]:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metrics: dict[str, Any] = {}
    raw_values: list[dict[str, Any]] = []
    for raw_name, raw_value in row.items():
        normalized = normalize_field_name(raw_name)
        if not normalized:
            continue
        parsed = number(raw_value)
        metrics[normalized] = parsed
        raw_values.append(
            {
                "raw_field_name": str(raw_name),
                "normalized_field_name": normalized,
                "raw_value": raw_value,
                "normalized_value": parsed,
                "period": period or str(row.get("Period") or row.get("Financial Year") or row.get("Quarter") or ""),
                "source_name": source_name,
                "source_url": source_url,
                "fetched_at": captured_at,
            }
        )
    return {
        "metrics": metrics,
        "raw_values": raw_values,
        "source_name": source_name,
        "source_url": source_url,
        "period": period or str(row.get("Period") or row.get("Financial Year") or row.get("Quarter") or ""),
        "fetched_at": captured_at,
    }

