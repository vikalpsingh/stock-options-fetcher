"""Fixed IT F&O universe for the DHAN-IT paired spread screen."""

from __future__ import annotations

from typing import Any


IT_FNO_SYMBOLS = ["TCS", "INFY", "HCLTECH", "TECHM"]

IT_COMPANY_NAMES = {
    "TCS": "Tata Consultancy Services Ltd",
    "INFY": "Infosys Ltd",
    "HCLTECH": "HCL Technologies Ltd",
    "TECHM": "Tech Mahindra Ltd",
}


def dhan_it_universe_rows() -> list[dict[str, Any]]:
    return [
        {
            "symbol": symbol,
            "company_name": IT_COMPANY_NAMES.get(symbol, symbol),
            "active": 1,
        }
        for symbol in IT_FNO_SYMBOLS
    ]


def is_dhan_it_symbol(symbol: str) -> bool:
    return str(symbol or "").strip().upper() in set(IT_FNO_SYMBOLS)
