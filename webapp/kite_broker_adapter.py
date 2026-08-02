"""Kite Connect adapter for stock-option spread workflows.

The adapter accepts an injected Kite-like client in tests. In production it
reuses the app's existing `kite_place_order.kite_client()` path, so credentials
continue to come from `KITE_API_KEY` and `KITE_ACCESS_TOKEN`.
"""

from __future__ import annotations

from typing import Any

import kite_spread_config as spread_cfg


class KiteBrokerError(RuntimeError):
    pass


class KiteBrokerAdapter:
    def __init__(self, kite: Any | None = None, paper_trading: bool | None = None, dry_run: bool = False) -> None:
        self.kite = kite
        self.paper_trading = spread_cfg.PAPER_TRADING_MODE if paper_trading is None else bool(paper_trading)
        self.dry_run = bool(dry_run)
        self.call_log: list[dict[str, Any]] = []
        self._paper_order_counter = 0

    def _client(self) -> Any:
        if self.kite is not None:
            return self.kite
        try:
            import kite_place_order as kite_orders  # type: ignore
        except Exception as exc:  # pragma: no cover - environment setup
            raise KiteBrokerError(f"Could not import Kite order module: {exc}") from exc
        try:
            self.kite = kite_orders.kite_client()
        except Exception as exc:  # pragma: no cover - live auth
            raise KiteBrokerError(self._friendly_error(str(exc))) from exc
        return self.kite

    def get_holdings(self) -> list[dict[str, Any]]:
        return list(self._client().holdings())

    def get_positions(self) -> dict[str, Any]:
        return dict(self._client().positions())

    def get_margins(self) -> dict[str, Any]:
        return dict(self._client().margins())

    def get_instruments(self, exchange: str | None = None) -> list[dict[str, Any]]:
        return list(self._client().instruments(exchange) if exchange else self._client().instruments())

    def get_ltp(self, instruments: list[str] | tuple[str, ...] | str) -> dict[str, Any]:
        return dict(self._client().ltp(instruments))

    def get_quote(self, instruments: list[str] | tuple[str, ...] | str) -> dict[str, Any]:
        return dict(self._client().quote(instruments))

    def get_ohlc(self, instruments: list[str] | tuple[str, ...] | str) -> dict[str, Any]:
        return dict(self._client().ohlc(instruments))

    def place_order(self, order_payload: dict[str, Any]) -> dict[str, Any]:
        if self.paper_trading or self.dry_run:
            self._paper_order_counter += 1
            order_id = f"PAPER-KITE-{self._paper_order_counter:06d}"
            self.call_log.append({"action": "place_order", "payload": dict(order_payload), "order_id": order_id})
            return {"order_id": order_id, "status": "OPEN", "paper": True}
        try:
            order_id = self._client().place_order(**order_payload)
        except Exception as exc:
            raise KiteBrokerError(self._friendly_error(str(exc))) from exc
        return {"order_id": str(order_id), "status": "OPEN", "paper": False}

    def modify_order(self, variety: str, order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.paper_trading or self.dry_run:
            self.call_log.append({"action": "modify_order", "variety": variety, "order_id": order_id, "payload": dict(payload)})
            return {"order_id": order_id, "status": "OPEN", "modified": True, "paper": True}
        return {"order_id": self._client().modify_order(variety=variety, order_id=order_id, **payload)}

    def cancel_order(self, variety: str, order_id: str) -> dict[str, Any]:
        if self.paper_trading or self.dry_run:
            self.call_log.append({"action": "cancel_order", "variety": variety, "order_id": order_id})
            return {"order_id": order_id, "status": "CANCELLED", "paper": True}
        return {"order_id": self._client().cancel_order(variety=variety, order_id=order_id)}

    def get_orders(self) -> list[dict[str, Any]]:
        return list([] if (self.paper_trading or self.dry_run) else self._client().orders())

    def get_order_trades(self, order_id: str) -> list[dict[str, Any]]:
        return list([] if (self.paper_trading or self.dry_run) else self._client().order_trades(order_id))

    def get_trades(self) -> list[dict[str, Any]]:
        return list([] if (self.paper_trading or self.dry_run) else self._client().trades())

    def calculate_order_margins(self, order_payloads: list[dict[str, Any]]) -> Any:
        if self.paper_trading or self.dry_run:
            return {"paper": True, "total": 0, "orders": order_payloads}
        return self._client().order_margins(order_payloads)

    def calculate_basket_margins(self, order_payloads: list[dict[str, Any]]) -> Any:
        client = self._client()
        if self.paper_trading or self.dry_run:
            return {"paper": True, "initial": {"total": 0}, "final": {"total": 0}, "orders": order_payloads}
        if hasattr(client, "basket_order_margins"):
            return client.basket_order_margins(order_payloads)
        return client.order_margins(order_payloads)

    def _friendly_error(self, message: str) -> str:
        text = str(message or "")
        lowered = text.lower()
        if "token" in lowered or "session" in lowered or "api_key" in lowered:
            return "Kite session appears expired or credentials are missing. Refresh KITE_ACCESS_TOKEN in Kite Setup."
        return text or "Kite API request failed."
