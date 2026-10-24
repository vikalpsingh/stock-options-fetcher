"""Kite Connect adapter for stock-option spread workflows.

The adapter accepts an injected Kite-like client in tests. In production it
reuses the app's existing `kite_place_order.kite_client()` path, so credentials
continue to come from `KITE_API_KEY` and `KITE_ACCESS_TOKEN`.
"""

from __future__ import annotations
from observability.usage_tracker import tracked

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import kite_spread_config as spread_cfg
from monthly_risk_control import pre_order_risk_check
from pnl_service import PnlRepository, snapshot_from_kite_positions


class KiteBrokerError(RuntimeError):
    pass


class KiteBrokerAdapter:
    def __init__(
        self,
        kite: Any | None = None,
        paper_trading: bool | None = None,
        dry_run: bool = False,
        account_id: str | None = None,
    ) -> None:
        self.kite = kite
        self.paper_trading = spread_cfg.PAPER_TRADING_MODE if paper_trading is None else bool(paper_trading)
        self.dry_run = bool(dry_run)
        self.account_id = str(account_id or "").strip()
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

    @tracked("kite_broker_adapter:KiteBrokerAdapter.get_positions", boundary="broker")
    def get_positions(self) -> dict[str, Any]:
        return dict(self._client().positions())

    def get_margins(self) -> dict[str, Any]:
        return dict(self._client().margins())

    def get_instruments(self, exchange: str | None = None) -> list[dict[str, Any]]:
        return list(self._client().instruments(exchange) if exchange else self._client().instruments())

    def get_ltp(self, instruments: list[str] | tuple[str, ...] | str) -> dict[str, Any]:
        return dict(self._client().ltp(instruments))

    @tracked("kite_broker_adapter:KiteBrokerAdapter.get_quote", boundary="broker")
    def get_quote(self, instruments: list[str] | tuple[str, ...] | str) -> dict[str, Any]:
        return dict(self._client().quote(instruments))

    def get_ohlc(self, instruments: list[str] | tuple[str, ...] | str) -> dict[str, Any]:
        return dict(self._client().ohlc(instruments))

    @tracked("kite_broker_adapter:KiteBrokerAdapter.place_order", boundary="broker")
    def place_order(self, order_payload: dict[str, Any]) -> dict[str, Any]:
        if self.paper_trading or self.dry_run:
            self._paper_order_counter += 1
            order_id = f"PAPER-KITE-{self._paper_order_counter:06d}"
            self.call_log.append({"action": "place_order", "payload": dict(order_payload), "order_id": order_id})
            return {"order_id": order_id, "status": "OPEN", "paper": True}
        broker_payload = dict(order_payload)
        risk_context = broker_payload.pop("_risk_context", {})
        if not isinstance(risk_context, dict):
            risk_context = {}
        try:
            client = self._client()
            positions_response = client.positions()
            current_positions = (
                list(positions_response.get("net") or [])
                if isinstance(positions_response, dict)
                else []
            )
            db_path = Path(
                os.getenv("TRADING_APP_DB_PATH")
                or Path(__file__).resolve().parent / "vikalp_income.db"
            )
            account_id = str(
                risk_context.get("account_id")
                or self.account_id
                or os.getenv("KITE_ACCOUNT_ID")
                or "DEFAULT"
            )
            # Persist the same fresh broker positions used by the gate. This keeps
            # booked/open P&L current during the session instead of waiting for EOD.
            live_pnl_records = snapshot_from_kite_positions(
                current_positions,
                account_id=account_id,
                trade_date=datetime.now(ZoneInfo("Asia/Kolkata")).date(),
            )
            pnl_repository = PnlRepository(db_path)
            pnl_repository.upsert_daily_records(
                live_pnl_records,
                audit_event="PRE_ORDER_RISK_PNL_SYNC",
            )
            pnl_repository.upsert_account_daily_summary(
                live_pnl_records,
                account_id=account_id,
                trade_date=datetime.now(ZoneInfo("Asia/Kolkata")).date(),
                source="ACCOUNT_DAILY",
            )
            decision = pre_order_risk_check(
                db_path,
                {**broker_payload, **risk_context},
                account_id=account_id,
                current_positions=current_positions,
            )
            if not decision.allowed:
                raise KiteBrokerError(
                    f"MONTHLY_RISK_BLOCKED: {decision.reason} "
                    f"Booked P&L {decision.booked_pnl:.2f}; "
                    f"remaining loss budget {decision.remaining_loss_budget:.2f}."
                )
            order_id = client.place_order(**broker_payload)
        except KiteBrokerError:
            raise
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
