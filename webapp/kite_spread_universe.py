"""Kite spreads stock universe from holdings, manual rows, and GPT."""

from __future__ import annotations

from typing import Any

from kite_spread_income_universe import DHAN_EXCLUDED_NON_FNO_SYMBOLS, annotate_income_growth_row, seed_income_growth_fno_watchlist
from kite_spread_repository import KiteSpreadRepository


class KiteSpreadUniverse:
    def __init__(self, repository: KiteSpreadRepository | None = None, broker: Any | None = None) -> None:
        self.repository = repository or KiteSpreadRepository()
        self.broker = broker

    def sync_kite_holdings(self) -> int:
        if self.broker is None:
            return 0
        saved = 0
        try:
            holdings = self.broker.get_holdings()
        except Exception:
            return 0
        for row in holdings:
            symbol = str(row.get("tradingsymbol") or "").upper()
            if not symbol:
                continue
            qty = float(row.get("quantity") or row.get("t1_quantity") or 0)
            self.repository.upsert_watchlist(symbol, row.get("company_name") or symbol, "HOLDING", is_current_holding=True, holding_qty=qty)
            saved += 1
        return saved

    def sync_holdings(self) -> int:
        return self.sync_kite_holdings()

    def sync_income_growth_fno_holdings(self) -> int:
        return seed_income_growth_fno_watchlist(self.repository)

    def add_manual(self, symbol: str, company_name: str = "") -> int:
        clean = str(symbol or "").upper().strip()
        return self.repository.upsert_watchlist(clean, company_name or clean, "MANUAL")

    def add_manual_stock(self, symbol: str, company_name: str = "", _bucket: str = "") -> int:
        return self.add_manual(symbol, company_name)

    def deactivate(self, row_id: int) -> bool:
        return self.repository.deactivate_watchlist(row_id)

    def deactivate_stock(self, row_id: int) -> bool:
        return self.deactivate(row_id)

    def save_gpt_suggestions(self, suggestions: list[dict[str, Any]]) -> int:
        saved = 0
        for item in suggestions:
            symbol = str(item.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            self.repository.upsert_watchlist(
                symbol,
                str(item.get("company_name") or symbol),
                "GPT",
                gpt_view=str(item.get("gpt_view") or "UNKNOWN"),
                gpt_reason=str(item.get("reason") or item.get("gpt_reason") or ""),
                event_risk_flag=str(item.get("event_risk") or "").upper() == "YES",
                sector_event_flag=str(item.get("sector_risk") or "").upper() == "YES",
            )
            saved += 1
        return saved

    def list_watchlist(self, active_only: bool = False) -> list[dict[str, Any]]:
        return [
            annotate_income_growth_row(row)
            for row in self.repository.list_watchlist(active_only=active_only)
            if str(row.get("symbol") or "").upper().strip() not in DHAN_EXCLUDED_NON_FNO_SYMBOLS
        ]

    def active_watchlist(self) -> list[dict[str, Any]]:
        return self.list_watchlist(active_only=True)
