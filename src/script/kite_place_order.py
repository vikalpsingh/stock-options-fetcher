#!/usr/bin/env python3
"""
Place a Zerodha Kite Connect order with a dry-run default.

Environment variables:
  KITE_API_KEY            Zerodha Kite app API key
  KITE_API_SECRET         Zerodha Kite app API secret, used only to create token
  KITE_ACCESS_TOKEN       Daily access token generated after login
  KITE_CONFIRM_LIVE_ORDER Set to YES for live order placement

Example generate daily access token:
  $env:KITE_API_KEY="your_api_key"
  $env:KITE_API_SECRET="your_api_secret"
  python src/script/kite_place_order.py --login

Example dry run:
  python src/script/kite_place_order.py

Example live order:
  $env:KITE_API_KEY="your_api_key"
  $env:KITE_ACCESS_TOKEN="your_access_token"
  $env:KITE_CONFIRM_LIVE_ORDER="YES"
  python src/script/kite_place_order.py --lots 1 --live
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OrderConfig:
    variety: str = "regular"
    exchange: str = "NFO"
    tradingsymbol: str = "HAVELLS26MAY1600CE"
    transaction_type: str = "SELL"
    quantity: int = 500
    product: str = "NRML"
    order_type: str = "LIMIT"
    price: float = 18.50
    validity: str = "DAY"
    tag: str = "GPT_CC"
    market_protection: int = 0
    autoslice: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely place a Zerodha Kite Connect order."
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Generate daily KITE_ACCESS_TOKEN using KITE_API_KEY and KITE_API_SECRET.",
    )
    parser.add_argument("--live", action="store_true", help="Actually place the order.")
    parser.add_argument("--symbol", default=OrderConfig.tradingsymbol)
    parser.add_argument("--exchange", default=OrderConfig.exchange)
    parser.add_argument("--transaction-type", default=OrderConfig.transaction_type)
    parser.add_argument("--quantity", type=int, default=OrderConfig.quantity)
    parser.add_argument(
        "--lots",
        type=int,
        help="Number of lots. If provided, quantity becomes lots * lot_size.",
    )
    parser.add_argument(
        "--lot-size",
        type=int,
        help="Manual lot size for dry runs or when you do not want to fetch instruments.",
    )
    parser.add_argument("--product", default=OrderConfig.product)
    parser.add_argument("--order-type", default=OrderConfig.order_type)
    parser.add_argument("--price", type=float, default=OrderConfig.price)
    parser.add_argument("--validity", default=OrderConfig.validity)
    parser.add_argument("--tag", default=OrderConfig.tag)
    parser.add_argument("--variety", default=OrderConfig.variety)
    parser.add_argument("--market-protection", type=int, default=OrderConfig.market_protection)
    parser.add_argument(
        "--autoslice",
        action="store_true",
        help="Send autoslice=True if your kiteconnect SDK version supports it.",
    )
    parser.add_argument(
        "--max-live-price",
        type=float,
        default=OrderConfig.price,
        help="For live LIMIT orders, reject if price is above this value.",
    )
    parser.add_argument(
        "--status-wait-seconds",
        type=int,
        default=2,
        help="Seconds to wait before reading order history after placement.",
    )
    return parser.parse_args()


def load_kite_connect_class() -> Any:
    try:
        from kiteconnect import KiteConnect
    except ImportError as exc:
        raise SystemExit("Install kiteconnect first: pip install kiteconnect") from exc

    return KiteConnect


def kite_client() -> Any:
    KiteConnect = load_kite_connect_class()
    api_key = os.getenv("KITE_API_KEY")
    access_token = os.getenv("KITE_ACCESS_TOKEN")
    print(f"KITE_API_KEY: {mask_secret(api_key)}")
    print(f"KITE_ACCESS_TOKEN: {mask_secret(access_token)}")

    if not api_key or not access_token:
        raise SystemExit(
            "Missing KITE_API_KEY or KITE_ACCESS_TOKEN environment variable."
        )

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


def mask_secret(value: str | None) -> str:
    if not value:
        return "<not set>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def generate_access_token() -> int:
    KiteConnect = load_kite_connect_class()
    api_key = os.getenv("KITE_API_KEY")
    api_secret = os.getenv("KITE_API_SECRET")

    if not api_key or not api_secret:
        raise SystemExit("Missing KITE_API_KEY or KITE_API_SECRET environment variable.")

    kite = KiteConnect(api_key=api_key)
    print("Open this URL in your browser and login:")
    print(kite.login_url())
    print()
    print("After login, copy request_token from the redirected URL.")
    request_token = input("Paste request_token: ").strip()

    if not request_token:
        raise SystemExit("request_token cannot be empty.")

    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]

    print("\nDaily access token generated.")
    print("Set it in this PowerShell session:")
    print(f'$env:KITE_ACCESS_TOKEN="{access_token}"')
    return 0


def get_lot_size(kite: Any, exchange: str, tradingsymbol: str) -> int:
    instruments = kite.instruments(exchange)
    symbol = tradingsymbol.upper()

    for instrument in instruments:
        if instrument.get("tradingsymbol") == symbol:
            lot_size = int(instrument["lot_size"])
            if lot_size <= 0:
                raise SystemExit(f"Invalid lot size received for {symbol}: {lot_size}")
            return lot_size

    raise SystemExit(f"Could not find {symbol} in {exchange} instruments.")


def resolve_quantity(args: argparse.Namespace, kite: Any | None = None) -> int:
    if args.lots is None:
        if args.quantity <= 0:
            raise SystemExit("Quantity must be greater than zero.")
        return args.quantity

    if args.lots <= 0:
        raise SystemExit("Lots must be greater than zero.")

    lot_size = args.lot_size
    if lot_size is None:
        if kite is None:
            raise SystemExit(
                "Use --lot-size for dry run lot calculation, or use --live to fetch lot size from Kite."
            )
        lot_size = get_lot_size(kite, args.exchange.upper(), args.symbol.upper())

    if lot_size <= 0:
        raise SystemExit("Lot size must be greater than zero.")

    quantity = args.lots * lot_size
    print(f"Resolved quantity: {args.lots} lot(s) * lot size {lot_size} = {quantity}")
    return quantity


def build_order(args: argparse.Namespace, kite: Any | None = None) -> dict[str, Any]:
    quantity = resolve_quantity(args, kite)

    order_type = args.order_type.upper()
    transaction_type = args.transaction_type.upper()
    product = args.product.upper()
    validity = args.validity.upper()
    exchange = args.exchange.upper()

    if transaction_type not in {"BUY", "SELL"}:
        raise SystemExit("transaction_type must be BUY or SELL.")
    if order_type not in {"MARKET", "LIMIT", "SL", "SL-M"}:
        raise SystemExit("order_type must be MARKET, LIMIT, SL, or SL-M.")
    if order_type == "LIMIT" and args.price <= 0:
        raise SystemExit("LIMIT orders require a positive price.")
    if order_type == "LIMIT" and args.price > args.max_live_price:
        raise SystemExit(
            f"Refusing order: price {args.price} exceeds max-live-price {args.max_live_price}."
        )

    order = {
        "variety": args.variety,
        "exchange": exchange,
        "tradingsymbol": args.symbol.upper(),
        "transaction_type": transaction_type,
        "quantity": quantity,
        "product": product,
        "order_type": order_type,
        "validity": validity,
        "tag": args.tag,
    }

    if args.autoslice:
        order["autoslice"] = True

    if order_type in {"LIMIT", "SL"}:
        order["price"] = args.price
    if order_type in {"MARKET", "SL-M"}:
        order["market_protection"] = args.market_protection

    return order


def print_order(order: dict[str, Any]) -> None:
    print("Order request:")
    for key, value in order.items():
        print(f"  {key}: {value}")


def place_order(kite: Any, order: dict[str, Any]) -> str:
    payload = order.copy()
    variety = payload.pop("variety")
    order_id = kite.place_order(variety=variety, **payload)
    return str(order_id)


def print_order_history(kite: Any, order_id: str) -> None:
    history = kite.order_history(order_id)
    latest = history[-1] if history else {}

    print("\nLatest order status:")
    print(f"  order_id: {order_id}")
    print(f"  status: {latest.get('status', 'UNKNOWN')}")
    print(f"  filled_quantity: {latest.get('filled_quantity', 0)}")
    print(f"  pending_quantity: {latest.get('pending_quantity', 0)}")
    print(f"  average_price: {latest.get('average_price', 0)}")

    status_message = latest.get("status_message")
    if status_message:
        print(f"  status_message: {status_message}")


def main() -> int:
    args = parse_args()

    if args.login:
        return generate_access_token()

    kite = None
    if args.live:
        kite = kite_client()

    order = build_order(args, kite)
    print_order(order)

    if not args.live:
        print("\nDry run only. Add --live and set KITE_CONFIRM_LIVE_ORDER=YES to place it.")
        return 0

    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise SystemExit("Refusing live order. Set KITE_CONFIRM_LIVE_ORDER=YES first.")

    try:
        order_id = place_order(kite, order)
        print(f"\nOrder registered with OMS. order_id: {order_id}")
        print("This is not execution confirmation; checking order history next.")

        if args.status_wait_seconds > 0:
            time.sleep(args.status_wait_seconds)

        print_order_history(kite, order_id)
        return 0
    except Exception as exc:
        print(f"Kite error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
