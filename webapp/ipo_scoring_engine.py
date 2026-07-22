"""Compatibility wrapper for the IPO long-term screener engine.

Older app routes and tests import this module. The implementation now delegates
to the richer long-term IPO opportunity model while preserving the historical
function names and output fields.
"""

from __future__ import annotations

from typing import Any

from ipo_screener_engine import rank_scored_ipos, score_ipo_opportunity


def _num(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        if isinstance(value, str) and value.strip().upper() in {"", "N/A", "NA", "NONE"}:
            return default
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def score_ipo_company(record: dict[str, Any]) -> dict[str, Any]:
    """Return the 100-point IPO long-term opportunity score."""
    return score_ipo_opportunity(record)


def rank_ipo_candidates(
    records: list[dict[str, Any]],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    ranked = rank_scored_ipos(records)
    if limit is not None:
        return ranked[:limit]
    return ranked


def _ipo_return_pct(record: dict[str, Any]) -> float | None:
    for key in ("gain_from_ipo_pct", "return_from_issue_pct"):
        value = _num(record.get(key))
        if value is not None:
            return value
    return None


def filter_multibaggers_or_all(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Compatibility filter now keeps IPOs with positive return so far.

    The old UI used a >100% issue-return filter. That was too restrictive for
    current-year IPO research because it hid useful names before the first
    serious quarterly review. Keep the public function name so existing routes
    remain stable, but apply a trader-friendly "above issue price" screen.
    """
    filtered = [
        record
        for record in records
        if (_ipo_return_pct(record) is not None and (_ipo_return_pct(record) or 0) > 0)
    ]
    if filtered:
        return filtered, f"Showing {len(filtered)} IPO(s) with positive return from issue price."
    return records, "No IPO has positive return for this selection, so all verified IPOs are shown."
