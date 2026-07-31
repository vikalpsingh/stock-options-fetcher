from __future__ import annotations

from typing import Any


class ExchangeFilingsProvider:
    """Interface boundary for authorized NSE/BSE filing adapters."""

    def fetch(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "status": "NOT_CONFIGURED", "filings": []}
