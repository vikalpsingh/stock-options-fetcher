from __future__ import annotations

from typing import Any


class YFinanceProvider:
    """Optional yfinance fallback provider. Import lazily so the app works without it."""

    def __init__(self) -> None:
        try:
            import yfinance as yf  # type: ignore
        except Exception as exc:  # pragma: no cover - environment dependent
            self.yf = None
            self.import_error = exc
        else:
            self.yf = yf
            self.import_error = None

    @property
    def configured(self) -> bool:
        return self.yf is not None

    def profile(self, yahoo_symbol: str) -> dict[str, Any]:
        if not self.yf:
            return {"status": "NOT_CONFIGURED", "error": type(self.import_error).__name__ if self.import_error else ""}
        try:
            ticker = self.yf.Ticker(yahoo_symbol)
            info = ticker.info or {}
        except Exception as exc:
            return {"status": "ERROR", "error": type(exc).__name__}
        long_name = info.get("longName") or info.get("shortName")
        if not long_name:
            return {"status": "MISSING", "error": "EMPTY_PROFILE"}
        return {"status": "FRESH", "profile": info}

