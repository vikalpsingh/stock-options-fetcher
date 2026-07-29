from __future__ import annotations

import csv
import os
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ipo.symbol_resolution.symbol_resolver import (
    clean_company_name,
    load_symbol_overrides,
    normalize_company_key,
    normalize_symbol,
    screener_url_for,
)


def _score_name(left: str, right: str) -> int:
    if not left or not right:
        return 0
    if left == right:
        return 100
    if left in right or right in left:
        return 88
    return int(SequenceMatcher(None, left, right).ratio() * 100)


def load_kite_equity_instruments(path: str | Path | None = None) -> list[dict[str, Any]]:
    instruments_path = Path(path or os.getenv("IPO_KITE_INSTRUMENTS_CSV") or os.getenv("KITE_INSTRUMENTS_CSV") or "")
    if not instruments_path or not instruments_path.exists():
        return []
    with instruments_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result: list[dict[str, Any]] = []
    for row in rows:
        exchange = str(row.get("exchange") or "").upper()
        segment = str(row.get("segment") or "").upper()
        instrument_type = str(row.get("instrument_type") or "").upper()
        if exchange not in {"NSE", "BSE"}:
            continue
        if segment and "NFO" in segment:
            continue
        if instrument_type and instrument_type not in {"EQ", "BE", "SM", "ST"}:
            continue
        result.append(row)
    return result


def resolve_kite_symbol(
    company_name: str,
    row: dict[str, Any] | None = None,
    instruments: list[dict[str, Any]] | None = None,
    overrides: dict[str, str] | None = None,
    market: str = "NSE",
) -> dict[str, Any]:
    row = row or {}
    company = clean_company_name(company_name or row.get("company_name") or "")
    raw_symbol = normalize_symbol(row.get("symbol") or row.get("tradingsymbol"))
    manual_overrides = overrides if overrides is not None else load_symbol_overrides()
    company_key = normalize_company_key(company)
    if raw_symbol:
        return {
            "symbol": raw_symbol,
            "exchange": str(row.get("exchange") or market or "NSE").upper(),
            "confidence": 95,
            "status": "RESOLVED",
            "method": "SOURCE_SYMBOL",
            "top_candidates": [],
            "screener_url": screener_url_for(raw_symbol, company, 95),
        }
    if company_key in manual_overrides:
        symbol = manual_overrides[company_key]
        return {
            "symbol": symbol,
            "exchange": str(row.get("exchange") or market or "NSE").upper(),
            "confidence": 90,
            "status": "RESOLVED",
            "method": "VERIFIED_MANUAL_OVERRIDE",
            "top_candidates": [],
            "screener_url": screener_url_for(symbol, company, 90),
        }

    candidates = []
    for instrument in instruments or load_kite_equity_instruments():
        symbol = normalize_symbol(instrument.get("tradingsymbol") or instrument.get("symbol"))
        name = clean_company_name(instrument.get("name") or instrument.get("company_name") or symbol)
        score = _score_name(normalize_company_key(company), normalize_company_key(name))
        if score <= 0:
            continue
        exchange = str(instrument.get("exchange") or "NSE").upper()
        candidates.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "name": name,
                "score": score + (3 if exchange == "NSE" else 0),
            }
        )
    candidates = sorted(candidates, key=lambda item: item["score"], reverse=True)[:5]
    best = candidates[0] if candidates else {}
    confidence = int(best.get("score") or 0)
    if confidence >= 85:
        status = "RESOLVED"
    elif confidence >= 70:
        status = "SYMBOL_REVIEW_NEEDED"
    else:
        status = "UNRESOLVED"
    symbol = str(best.get("symbol") or "") if confidence >= 70 else ""
    return {
        "symbol": symbol if status == "RESOLVED" else "",
        "exchange": str(best.get("exchange") or row.get("exchange") or market or "NSE").upper(),
        "confidence": confidence,
        "status": status,
        "method": "KITE_INSTRUMENTS_FUZZY" if candidates else "NO_MATCH",
        "top_candidates": candidates,
        "screener_url": screener_url_for(symbol if status == "RESOLVED" else "", company, confidence),
    }

