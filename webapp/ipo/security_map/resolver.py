from __future__ import annotations

from typing import Any

from .kite_validator import validate_mapping_with_kite
from .models import SecurityMapping
from .normalizer import (
    canonical_name_for,
    clean_security_company_name,
    forbidden_false_matches_for,
    is_forbidden_false_match,
    normalize_company_name,
    normalize_security_symbol,
)
from .repository import load_security_map
from .screener_links import build_screener_url


def _mapping_by_source_symbol(security_map: dict[str, SecurityMapping], source_symbol: str) -> SecurityMapping | None:
    symbol = normalize_security_symbol(source_symbol)
    if not symbol:
        return None
    for mapping in security_map.values():
        if mapping.nse_symbol and normalize_security_symbol(mapping.nse_symbol) == symbol:
            return mapping
        if mapping.bse_security_code and normalize_security_symbol(mapping.bse_security_code) == symbol:
            return mapping
        if mapping.bse_security_id and normalize_security_symbol(mapping.bse_security_id) == symbol:
            return mapping
    return None


def _to_resolution(
    mapping: SecurityMapping,
    *,
    company_name: str,
    source_symbol: str = "",
    instrument_master: Any = None,
    steps: list[str] | None = None,
) -> dict[str, Any]:
    steps = list(steps or [])
    validation = validate_mapping_with_kite(mapping, instrument_master)
    kite_match = validation.get("match") if validation.get("kite_verified") else None
    kite_verified = bool(kite_match)
    kite_symbol = ""
    kite_key = ""
    instrument_token = ""
    if kite_match:
        kite_symbol = normalize_security_symbol(kite_match.get("tradingsymbol") or kite_match.get("symbol"))
        exchange = str(kite_match.get("exchange") or mapping.primary_exchange).strip().upper()
        kite_key = f"{exchange}:{kite_symbol}" if kite_symbol else ""
        instrument_token = kite_match.get("instrument_token") or kite_match.get("token") or ""
        steps.append(f"Kite exact validation: {kite_key}")
    else:
        steps.append(f"Kite exact validation: pending ({validation.get('reason')})")

    screener_url, screener_status = build_screener_url(mapping, company_name)
    symbol = mapping.nse_symbol or mapping.bse_security_code or mapping.bse_security_id
    resolved_tradingsymbol = kite_symbol or (mapping.nse_symbol if mapping.primary_exchange == "NSE" else "")
    return {
        "company_name": company_name,
        "raw_company_name": company_name,
        "clean_company_name": clean_security_company_name(company_name),
        "validated_company_name": mapping.canonical_name,
        "canonical_name": mapping.canonical_name,
        "legal_name": mapping.legal_name,
        "source_symbol": source_symbol,
        "symbol": symbol,
        "resolved_tradingsymbol": resolved_tradingsymbol or symbol,
        "exchange": mapping.primary_exchange,
        "primary_exchange": mapping.primary_exchange,
        "segment": mapping.segment,
        "nse_symbol": mapping.nse_symbol,
        "bse_security_code": mapping.bse_security_code,
        "bse_security_id": mapping.bse_security_id,
        "isin": mapping.isin,
        "screener_url": screener_url,
        "screener_url_status": screener_status,
        "kite_symbol": kite_symbol,
        "kite_key": kite_key,
        "instrument_token": instrument_token,
        "kite_verified": kite_verified,
        "screener_verified": mapping.screener_verified,
        "identity_verified": mapping.identity_verified,
        "mapping_status": "PARTIALLY_VERIFIED" if kite_verified else mapping.status,
        "status": "SOURCE_VERIFIED",
        "resolution_status": "SOURCE_VERIFIED",
        "match_method": "SECURITY_MAP_KITE_EXACT" if kite_verified else "SECURITY_MAP_SOURCE_VERIFIED",
        "resolution_confidence": 100,
        "is_listed_verified": True,
        "eligible_identity": True,
        "exchange_verified": True,
        "isin_match_status": "SOURCE_ISIN" if mapping.isin else "MISSING",
        "verification_status": "SOURCE_VERIFIED" if not kite_verified else "PARTIALLY_VERIFIED",
        "verification_reasons": [] if kite_verified else ["kite_quote_pending"],
        "notes": mapping.notes,
        "forbidden_false_matches": mapping.forbidden_false_matches,
        "resolution_steps": steps,
        "resolution_pipeline": " -> ".join(steps),
    }


def resolve_security(row_or_name: dict[str, Any] | str, instrument_master: Any = None) -> dict[str, Any] | None:
    row = row_or_name if isinstance(row_or_name, dict) else {"company_name": row_or_name}
    raw_company = str(row.get("company_name") or row.get("company") or row.get("ipo_name") or "")
    company = clean_security_company_name(raw_company)
    source_symbol = normalize_security_symbol(row.get("symbol") or row.get("ticker") or row.get("tradingsymbol") or "")
    steps = [f"Security map clean company: {company or 'MISSING'}"]
    security_map = load_security_map()
    mapping = security_map.get(normalize_company_name(company))
    if not mapping:
        canonical = canonical_name_for(company)
        mapping = security_map.get(normalize_company_name(canonical))
        if mapping:
            steps.append(f"Alias resolved: {canonical}")
    if not mapping and source_symbol:
        mapping = _mapping_by_source_symbol(security_map, source_symbol)
        if mapping:
            steps.append(f"Source symbol resolved in security map: {source_symbol}")
    if not mapping:
        steps.append("Security map: no source-verified match")
        return None
    forbidden = forbidden_false_matches_for(mapping.canonical_name)
    if is_forbidden_false_match(mapping.canonical_name, source_symbol):
        steps.append(f"Rejected forbidden source symbol {source_symbol}; using verified security map identity")
        source_symbol = ""
    elif forbidden:
        steps.append(f"Forbidden false matches protected: {', '.join(forbidden)}")
    steps.append(
        "Security map: "
        f"{mapping.primary_exchange} {mapping.nse_symbol or mapping.bse_security_code or mapping.bse_security_id}"
    )
    return _to_resolution(mapping, company_name=company, source_symbol=source_symbol, instrument_master=instrument_master, steps=steps)
