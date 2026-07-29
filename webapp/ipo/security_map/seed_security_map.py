from __future__ import annotations

from typing import Any

from ipo.config.verified_bse_mappings import VERIFIED_BSE_MAPPINGS
from ipo.config.verified_nse_mappings import VERIFIED_NSE_MAPPINGS

from .models import SecurityMapping
from .normalizer import ALIASES, FORBIDDEN_FALSE_MATCHES, normalize_company_name


def _seed_from_nse(row: dict[str, str]) -> SecurityMapping:
    name = row["name"]
    symbol = row["symbol"]
    segment = row.get("segment") or "NSE"
    return SecurityMapping(
        canonical_name=name,
        legal_name=row.get("legal_name") or name,
        aliases=ALIASES.get(name, []),
        primary_exchange="NSE",
        segment=segment,
        nse_symbol=symbol,
        kite_tradingsymbol="",
        kite_key="",
        source="verified_nse_seed",
        source_url="https://www.nseindia.com/",
        forbidden_false_matches=FORBIDDEN_FALSE_MATCHES.get(name, []),
    )


def _seed_from_bse(row: dict[str, str]) -> SecurityMapping:
    name = row["name"]
    return SecurityMapping(
        canonical_name=name,
        legal_name=row.get("legal_name") or name,
        aliases=ALIASES.get(name, []),
        primary_exchange="BSE",
        segment=row.get("segment") or "BSE SME",
        bse_security_code=row["security_code"],
        bse_security_id=row.get("security_id") or "",
        source="verified_bse_seed",
        source_url="https://www.bseindia.com/",
        forbidden_false_matches=FORBIDDEN_FALSE_MATCHES.get(name, []),
    )


def build_seed_security_map() -> dict[str, SecurityMapping]:
    security_map: dict[str, SecurityMapping] = {}
    for row in VERIFIED_NSE_MAPPINGS:
        mapping = _seed_from_nse(row)
        security_map[normalize_company_name(mapping.canonical_name)] = mapping
    for row in VERIFIED_BSE_MAPPINGS:
        mapping = _seed_from_bse(row)
        security_map[normalize_company_name(mapping.canonical_name)] = mapping
    return security_map


def run_security_map_audit(security_map: dict[str, SecurityMapping] | None = None) -> list[dict[str, Any]]:
    security_map = security_map or build_seed_security_map()
    audit_rows: list[dict[str, Any]] = []
    seen_nse: dict[str, str] = {}
    seen_bse: dict[str, str] = {}
    for key, mapping in security_map.items():
        issues: list[str] = []
        if not mapping.canonical_name:
            issues.append("missing canonical_name")
        if mapping.primary_exchange == "NSE":
            if not mapping.nse_symbol:
                issues.append("missing nse_symbol")
            if mapping.nse_symbol in seen_nse:
                issues.append(f"duplicate NSE symbol with {seen_nse[mapping.nse_symbol]}")
            seen_nse[mapping.nse_symbol] = mapping.canonical_name
        elif mapping.primary_exchange == "BSE":
            if not mapping.bse_security_code:
                issues.append("missing bse_security_code")
            if mapping.bse_security_code in seen_bse:
                issues.append(f"duplicate BSE code with {seen_bse[mapping.bse_security_code]}")
            seen_bse[mapping.bse_security_code] = mapping.canonical_name
        else:
            issues.append("unsupported primary_exchange")
        audit_rows.append(
            {
                "key": key,
                "company": mapping.canonical_name,
                "exchange": mapping.primary_exchange,
                "symbol": mapping.nse_symbol or mapping.bse_security_code,
                "status": "PASS" if not issues else "FAIL",
                "issues": "; ".join(issues),
            }
        )
    return audit_rows
