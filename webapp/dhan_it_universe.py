"""Central IT F&O universe for the DHAN-IT paired spread screen.

NIFTY IT is handled separately as the sector-regime indicator. The symbols in
this module are orderable equity underlyings consumed by cards, scans,
opportunity tables, repair flows, and pair monitoring.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DHAN_IT_STOCK_CONFIGS: dict[str, dict[str, Any]] = {
    "TCS": {
        "symbol": "TCS",
        "display_name": "Tata Consultancy Services Ltd",
        "exchange": "NSE",
        "instrument_type": "EQUITY",
        "orderable": True,
        "risk_bucket": "CONSERVATIVE",
        "short_call_delta_min": 0.15,
        "short_call_delta_max": 0.20,
        "target_short_otm_pct": 5.0,
        "target_hedge_otm_pct": 10.0,
        "max_open_spreads": 2,
    },
    "INFY": {
        "symbol": "INFY",
        "display_name": "Infosys Ltd",
        "exchange": "NSE",
        "instrument_type": "EQUITY",
        "orderable": True,
        "risk_bucket": "CONSERVATIVE",
        "short_call_delta_min": 0.15,
        "short_call_delta_max": 0.20,
        "target_short_otm_pct": 5.0,
        "target_hedge_otm_pct": 10.0,
        "max_open_spreads": 2,
    },
    "HCLTECH": {
        "symbol": "HCLTECH",
        "display_name": "HCL Technologies Ltd",
        "exchange": "NSE",
        "instrument_type": "EQUITY",
        "orderable": True,
        "risk_bucket": "CONSERVATIVE",
        "short_call_delta_min": 0.15,
        "short_call_delta_max": 0.20,
        "target_short_otm_pct": 5.0,
        "target_hedge_otm_pct": 10.0,
        "max_open_spreads": 2,
    },
    "TECHM": {
        "symbol": "TECHM",
        "display_name": "Tech Mahindra Ltd",
        "exchange": "NSE",
        "instrument_type": "EQUITY",
        "orderable": True,
        "risk_bucket": "MODERATE",
        "short_call_delta_min": 0.15,
        "short_call_delta_max": 0.20,
        "target_short_otm_pct": 5.0,
        "target_hedge_otm_pct": 10.0,
        "max_open_spreads": 2,
    },
    "WIPRO": {
        "symbol": "WIPRO",
        "display_name": "Wipro Ltd",
        "exchange": "NSE",
        "instrument_type": "EQUITY",
        "orderable": True,
        "risk_bucket": "CONSERVATIVE",
        "short_call_delta_min": 0.15,
        "short_call_delta_max": 0.20,
        "target_short_otm_pct": 7.0,
        "target_hedge_otm_pct": 12.0,
        "max_open_spreads": 2,
    },
    "LTM": {
        "symbol": "LTM",
        "display_name": "LTIMindtree Ltd",
        "exchange": "NSE",
        "instrument_type": "EQUITY",
        "orderable": True,
        "risk_bucket": "MODERATE",
        "short_call_delta_min": 0.12,
        "short_call_delta_max": 0.16,
        "target_short_otm_pct": 9.0,
        "target_hedge_otm_pct": 14.0,
        "max_open_spreads": 1,
    },
}

IT_FNO_SYMBOLS = list(DHAN_IT_STOCK_CONFIGS)

IT_COMPANY_NAMES = {
    symbol: str(config["display_name"])
    for symbol, config in DHAN_IT_STOCK_CONFIGS.items()
}


def dhan_it_stock_config(symbol: str) -> dict[str, Any]:
    clean_symbol = str(symbol or "").strip().upper()
    return deepcopy(DHAN_IT_STOCK_CONFIGS.get(clean_symbol, {}))


def dhan_it_universe_rows() -> list[dict[str, Any]]:
    return [
        {
            **dhan_it_stock_config(symbol),
            "company_name": IT_COMPANY_NAMES.get(symbol, symbol),
            "active": 1,
        }
        for symbol in IT_FNO_SYMBOLS
    ]


def is_dhan_it_symbol(symbol: str) -> bool:
    return str(symbol or "").strip().upper() in set(IT_FNO_SYMBOLS)
