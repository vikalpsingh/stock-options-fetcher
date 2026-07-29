from __future__ import annotations

from typing import Any

from .models import SecurityMapping
from .normalizer import normalize_security_symbol


def validate_mapping_with_kite(mapping: SecurityMapping, instrument_master: Any = None) -> dict[str, Any]:
    """Validate a mapping only by exact Kite instrument master rows.

    This function intentionally does no fuzzy matching. For BSE numeric codes,
    the code is not considered a tradingsymbol unless Kite supplies that exact
    tradingsymbol row.
    """

    if not instrument_master:
        return {"kite_verified": False, "match": None, "reason": "instrument_master_not_supplied"}
    instruments = instrument_master if isinstance(instrument_master, list) else []
    expected_symbol = normalize_security_symbol(mapping.nse_symbol or mapping.kite_tradingsymbol)
    if not expected_symbol and mapping.bse_security_id:
        expected_symbol = normalize_security_symbol(mapping.bse_security_id)
    for instrument in instruments:
        if not isinstance(instrument, dict):
            continue
        instrument_symbol = normalize_security_symbol(instrument.get("tradingsymbol") or instrument.get("symbol"))
        exchange = str(instrument.get("exchange") or "").strip().upper()
        if expected_symbol and instrument_symbol == expected_symbol:
            if mapping.primary_exchange == "BSE" and exchange != "BSE":
                continue
            if mapping.primary_exchange == "NSE" and exchange not in {"NSE", "NSE SME"}:
                continue
            return {"kite_verified": True, "match": instrument, "reason": "exact_symbol_exchange_match"}
    return {"kite_verified": False, "match": None, "reason": "no_exact_kite_match"}
