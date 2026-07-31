from __future__ import annotations

import difflib
import re
from typing import Any
from urllib.parse import quote_plus


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalize_company_name(value: Any) -> str:
    text = _text(value).upper()
    text = re.sub(r"\b(LIMITED|LTD|PRIVATE|PVT|INDIA|THE)\b", " ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def identity_match_score(expected_name: Any, returned_name: Any) -> float:
    expected = normalize_company_name(expected_name)
    returned = normalize_company_name(returned_name)
    if not expected or not returned:
        return 0.0
    return round(difflib.SequenceMatcher(None, expected, returned).ratio() * 100, 2)


def build_yahoo_symbol(mapping: dict[str, Any]) -> str | None:
    stored = _text(mapping.get("yahoo_symbol"))
    if stored and _text(mapping.get("yahoo_symbol_status")).upper() == "VERIFIED":
        return stored
    exchange = _text(mapping.get("exchange") or mapping.get("primary_exchange")).upper()
    nse_symbol = _text(mapping.get("nse_symbol") or mapping.get("symbol"))
    bse_code = _text(mapping.get("bse_security_code") or mapping.get("bse_code"))
    if "NSE" in exchange and nse_symbol:
        return f"{nse_symbol.upper()}.NS"
    if "BSE" in exchange and bse_code:
        return f"{bse_code}.BO"
    if nse_symbol:
        return f"{nse_symbol.upper()}.NS"
    if bse_code:
        return f"{bse_code}.BO"
    return None


def validate_yahoo_mapping(mapping: dict[str, Any], returned_company_name: Any) -> dict[str, Any]:
    symbol = build_yahoo_symbol(mapping)
    score = identity_match_score(
        mapping.get("canonical_name") or mapping.get("company_name") or mapping.get("legal_name"),
        returned_company_name,
    )
    status = "VERIFIED" if symbol and score >= 85 else "MISMATCH" if symbol and returned_company_name else "NOT_FOUND"
    return {
        "source_name": "YAHOO",
        "source_identifier": symbol or "",
        "mapping_status": status,
        "identity_match_score": score,
    }


def build_google_finance_url(mapping: dict[str, Any]) -> str | None:
    exchange = _text(mapping.get("exchange") or mapping.get("primary_exchange")).upper()
    nse_symbol = _text(mapping.get("nse_symbol") or mapping.get("symbol"))
    bse_code = _text(mapping.get("bse_security_code") or mapping.get("bse_code"))
    if "BSE" in exchange and bse_code:
        return f"https://www.google.com/finance/quote/{quote_plus(bse_code)}:BOM"
    if nse_symbol:
        return f"https://www.google.com/finance/quote/{quote_plus(nse_symbol.upper())}:NSE"
    if bse_code:
        return f"https://www.google.com/finance/quote/{quote_plus(bse_code)}:BOM"
    return None


def build_yahoo_finance_url(mapping: dict[str, Any]) -> str | None:
    symbol = build_yahoo_symbol(mapping)
    status = _text(mapping.get("yahoo_symbol_status")).upper()
    if not symbol or status not in {"VERIFIED", "CANDIDATE"}:
        return None
    return f"https://finance.yahoo.com/quote/{quote_plus(symbol)}/"


def build_screener_url(mapping: dict[str, Any]) -> str | None:
    existing = _text(mapping.get("screener_url"))
    if existing:
        return existing
    exchange = _text(mapping.get("exchange") or mapping.get("primary_exchange")).upper()
    nse_symbol = _text(mapping.get("nse_symbol") or mapping.get("symbol"))
    bse_code = _text(mapping.get("bse_security_code") or mapping.get("bse_code"))
    identifier = bse_code if "BSE" in exchange and bse_code else nse_symbol or bse_code
    if not identifier:
        return None
    return f"https://www.screener.in/company/{quote_plus(identifier.upper())}/"


def build_external_links(mapping: dict[str, Any]) -> dict[str, dict[str, str]]:
    yahoo_url = build_yahoo_finance_url(mapping)
    google_url = build_google_finance_url(mapping)
    screener_url = build_screener_url(mapping)
    exchange_url = _text(mapping.get("source_url") or mapping.get("exchange_url"))
    return {
        "yahoo": {
            "label": "Yahoo Finance",
            "url": yahoo_url or "",
            "status": "AVAILABLE" if yahoo_url else "MAPPING_UNAVAILABLE",
        },
        "google": {
            "label": "Google Finance",
            "url": google_url or "",
            "status": "AVAILABLE" if google_url else "MAPPING_UNAVAILABLE",
        },
        "screener": {
            "label": "Screener",
            "url": screener_url or "",
            "status": "AVAILABLE" if screener_url else "MAPPING_UNAVAILABLE",
        },
        "exchange": {
            "label": "Exchange",
            "url": exchange_url,
            "status": "AVAILABLE" if exchange_url else "MAPPING_UNAVAILABLE",
        },
    }

