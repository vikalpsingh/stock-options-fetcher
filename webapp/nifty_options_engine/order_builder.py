from __future__ import annotations

from typing import Any

from .config import engine_config
from .models import OrderIntent


def round_to_tick(price: float, tick_size: float = 0.05) -> float:
    if price <= 0:
        return 0.0
    return round(round(price / tick_size) * tick_size, 2)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _leg_price(leg: dict[str, Any], config: dict[str, Any]) -> float:
    side = str(leg.get("transaction_type") or "").upper()
    ltp = _float(leg.get("ltp") or leg.get("price"))
    bid = _float(leg.get("bid"))
    ask = _float(leg.get("ask"))
    if side == "SELL":
        return round_to_tick(bid or ltp * (1 + _float(config.get("sell_limit_markup_pct"), 10.0) / 100.0))
    if side == "BUY":
        return round_to_tick(ask or ltp * (1 - _float(config.get("buy_limit_discount_pct"), 5.0) / 100.0))
    return round_to_tick(ltp)


def build_order_intents(strategy: dict[str, Any], config: dict[str, Any] | None = None) -> list[OrderIntent]:
    config = engine_config(config)
    strategy_id = str(strategy.get("strategy_id") or "NIFTY_TACTICAL")
    legs = list(strategy.get("legs") or [])
    ordered = sorted(legs, key=lambda leg: 0 if str(leg.get("transaction_type") or "").upper() == "BUY" else 1)
    intents: list[OrderIntent] = []
    for leg in ordered:
        intents.append(
            OrderIntent(
                strategy_id=strategy_id,
                exchange=str(leg.get("exchange") or "NFO"),
                tradingsymbol=str(leg.get("tradingsymbol") or ""),
                quantity=int(_float(leg.get("quantity"))),
                transaction_type=str(leg.get("transaction_type") or "").upper(),
                product=str(leg.get("product") or config.get("product") or "NRML"),
                order_type=str(leg.get("order_type") or config.get("order_type") or "LIMIT"),
                price=_leg_price(leg, config),
                validity=str(leg.get("validity") or config.get("validity") or "DAY"),
                dry_run=bool(config.get("dry_run_default", True)),
            )
        )
    return intents


def order_intents_to_csv_rows(intents: list[OrderIntent]) -> list[dict[str, Any]]:
    return [intent.kite_csv_row() for intent in intents]
