#!/usr/bin/env python3
"""
Create Zerodha Kite BUY orders from current open positions with a dry-run default.

Environment variables:
  KITE_API_KEY            Zerodha Kite app API key
  KITE_ACCESS_TOKEN       Daily access token generated after login
  KITE_CONFIRM_LIVE_ORDER Set to YES for live order placement

Examples:
  python src/script/kite_buy_positions.py
  python src/script/kite_buy_positions.py --output-csv src/script/kite_buy_orders.csv
  python src/script/kite_buy_positions.py --live
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build BUY LIMIT orders for Kite positions using profit-aware discount pricing."
    )
    parser.add_argument("--live", action="store_true", help="Actually place BUY orders.")
    parser.add_argument(
        "--discount-percent",
        "--percent",
        dest="discount_percent",
        type=float,
        default=20.0,
        help=(
            "Buy limit discount. Profitable positions use LTP; non-profitable "
            "positions use average price. Default: 20 means basis price minus 20%%. "
            "Use 5 near market close."
        ),
    )
    parser.add_argument("--exchange", default="NFO", help="Only include this exchange.")
    parser.add_argument("--product", help="Only include this product, for example NRML.")
    parser.add_argument(
        "--include-long",
        action="store_true",
        help="Also create BUY orders for long positions. Default only covers shorts.",
    )
    parser.add_argument(
        "--profit-only",
        action="store_true",
        help="Only create BUY orders for positions that are currently profitable.",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        help="Only include this tradingsymbol. Repeat for multiple symbols.",
    )
    parser.add_argument("--order-type", default="LIMIT", choices=["LIMIT"], help="Order type.")
    parser.add_argument("--validity", default="DAY")
    parser.add_argument("--variety", default="regular")
    parser.add_argument("--tag", default="GPT_BUY")
    parser.add_argument("--tick-size", type=float, default=0.05)
    parser.add_argument(
        "--autoslice",
        action="store_true",
        help="Send autoslice=True only if your kiteconnect SDK supports it.",
    )
    parser.add_argument(
        "--keep-existing-orders",
        "--place-new-order",
        dest="keep_existing_orders",
        action="store_true",
        help="Do not modify a similar open order; place a new live order instead.",
    )
    parser.add_argument(
        "--max-orders",
        type=int,
        help="Safety cap. Refuse to create/place more than this many orders.",
    )
    parser.add_argument(
        "--output-csv",
        help="Write generated BUY orders to a CSV that kite_place_order.py can consume.",
    )
    parser.add_argument("--status-wait-seconds", type=int, default=2)
    return parser.parse_args()


def load_kite_connect_class() -> Any:
    try:
        from kiteconnect import KiteConnect
    except ImportError as exc:
        raise SystemExit("Install kiteconnect first: pip install kiteconnect") from exc
    return KiteConnect


def mask_secret(value: str | None) -> str:
    if not value:
        return "<not set>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def kite_client() -> Any:
    KiteConnect = load_kite_connect_class()
    api_key = os.getenv("KITE_API_KEY")
    access_token = os.getenv("KITE_ACCESS_TOKEN")
    print(f"KITE_API_KEY: {mask_secret(api_key)}")
    print(f"KITE_ACCESS_TOKEN: {mask_secret(access_token)}")

    if not api_key or not access_token:
        raise SystemExit("Missing KITE_API_KEY or KITE_ACCESS_TOKEN environment variable.")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


def round_down_to_tick(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        raise SystemExit("Tick size must be greater than zero.")
    return round(math.floor(price / tick_size) * tick_size, 2)


def get_last_price(kite: Any, exchange: str, tradingsymbol: str) -> float:
    instrument_key = f"{exchange}:{tradingsymbol}"
    try:
        quote = kite.ltp(instrument_key)
    except Exception as exc:
        raise SystemExit(f"Could not fetch LTP from Kite for {instrument_key}: {exc}") from exc

    last_price = float(quote[instrument_key]["last_price"])
    if last_price <= 0:
        raise SystemExit(f"Invalid LTP received for {instrument_key}: {last_price}")
    return last_price


def selected_position(position: dict[str, Any], args: argparse.Namespace) -> bool:
    quantity = int(position.get("quantity") or 0)
    if quantity == 0:
        return False
    if not args.include_long and quantity > 0:
        return False
    if args.exchange and str(position.get("exchange", "")).upper() != args.exchange.upper():
        return False
    if args.product and str(position.get("product", "")).upper() != args.product.upper():
        return False
    if args.symbol:
        allowed = {symbol.upper() for symbol in args.symbol}
        if str(position.get("tradingsymbol", "")).upper() not in allowed:
            return False
    return True


def current_positions(kite: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    positions = kite.positions()
    net_positions = positions.get("net", [])
    selected = [position for position in net_positions if selected_position(position, args)]

    if not selected:
        raise SystemExit("No matching open positions found.")
    return selected


def is_profitable_position(quantity: int, average_price: float, ltp: float, pnl: float) -> bool:
    if pnl > 0:
        return True
    if average_price <= 0 or ltp <= 0:
        return False
    if quantity < 0:
        return ltp < average_price
    return ltp > average_price


def build_buy_order(
    position: dict[str, Any], args: argparse.Namespace, kite: Any
) -> dict[str, Any] | None:
    exchange = str(position["exchange"]).upper()
    tradingsymbol = str(position["tradingsymbol"]).upper()
    position_quantity = int(position["quantity"])
    quantity = abs(position_quantity)
    product = str(position["product"]).upper()
    pnl = float(position.get("pnl") or 0)
    average_price = float(position.get("average_price") or 0)
    ltp = float(position.get("last_price") or position.get("ltp") or 0)
    if ltp <= 0:
        ltp = get_last_price(kite, exchange, tradingsymbol)

    if args.profit_only and not is_profitable_position(
        position_quantity, average_price, ltp, pnl
    ):
        print(
            "Skipping non-profitable position: "
            f"{tradingsymbol} | position_qty={position_quantity} | "
            f"average_price={average_price} | LTP={ltp} | pnl={pnl}"
        )
        return None

    is_profitable = is_profitable_position(position_quantity, average_price, ltp, pnl)
    price_basis_name = "LTP" if is_profitable else "average_price"
    price_basis = ltp if is_profitable else average_price
    if price_basis <= 0:
        raise SystemExit(
            f"Invalid {price_basis_name} for {tradingsymbol}: {price_basis}"
        )

    raw_price = price_basis * (1 - args.discount_percent / 100)
    price = round_down_to_tick(raw_price, args.tick_size)

    if quantity <= 0:
        raise SystemExit(f"Invalid quantity for {tradingsymbol}: {quantity}")
    if price <= 0:
        raise SystemExit(f"Invalid calculated BUY price for {tradingsymbol}: {price}")

    order = {
        "variety": args.variety,
        "exchange": exchange,
        "tradingsymbol": tradingsymbol,
        "transaction_type": "BUY",
        "quantity": quantity,
        "product": product,
        "order_type": args.order_type,
        "price": price,
        "validity": args.validity.upper(),
        "tag": args.tag,
        "average_price": average_price,
        "ltp": ltp,
        "pnl": pnl,
        "price_basis": price_basis_name,
        "discount_percent": args.discount_percent,
    }
    if args.autoslice:
        order["autoslice"] = True

    print(
        "Resolved BUY price: "
        f"{tradingsymbol} | position_qty={position_quantity} | "
        f"average_price={average_price} | LTP={ltp} | pnl={pnl} | "
        f"basis={price_basis_name} | "
        f"discount=-{args.discount_percent}% | "
        f"raw={raw_price:.4f} | limit={price}"
    )
    return order


def print_order(order: dict[str, Any]) -> None:
    print("Order request:")
    for key, value in order.items():
        print(f"  {key}: {value}")


def confirm_order(order: dict[str, Any]) -> bool:
    price_text = f" @ {order['price']}" if "price" in order else ""
    avg_text = f" | avg={order['average_price']}" if "average_price" in order else ""
    ltp_text = f" | LTP={order['ltp']}" if "ltp" in order else ""
    pnl_text = f" | P&L={order['pnl']}" if "pnl" in order else ""
    prompt = (
        f"Place {order['transaction_type']} {order['quantity']} "
        f"{order['tradingsymbol']}{price_text}{avg_text}{ltp_text}{pnl_text}? [Y/N]: "
    )
    while True:
        answer = input(prompt).strip().upper()
        if answer == "Y":
            return True
        if answer == "N":
            return False
        print("Enter Y to place the order, or N to skip it.")


def place_order(kite: Any, order: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in order.items()
        if key not in {"average_price", "ltp", "pnl", "price_basis", "discount_percent"}
    }
    variety = payload.pop("variety")
    return str(kite.place_order(variety=variety, **payload))


def is_open_order(existing_order: dict[str, Any]) -> bool:
    status = str(existing_order.get("status", "")).upper()
    pending_quantity = int(existing_order.get("pending_quantity") or 0)
    terminal_statuses = {"COMPLETE", "CANCELLED", "REJECTED"}
    return status not in terminal_statuses and pending_quantity > 0


def is_similar_order(existing_order: dict[str, Any], new_order: dict[str, Any]) -> bool:
    return (
        str(existing_order.get("exchange", "")).upper() == new_order["exchange"]
        and str(existing_order.get("tradingsymbol", "")).upper() == new_order["tradingsymbol"]
        and str(existing_order.get("transaction_type", "")).upper()
        == new_order["transaction_type"]
        and str(existing_order.get("product", "")).upper() == new_order["product"]
        and str(existing_order.get("order_type", "")).upper() == new_order["order_type"]
        and str(existing_order.get("variety", "")).lower() == str(new_order["variety"]).lower()
    )


def find_similar_open_orders(kite: Any, new_order: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        existing_order
        for existing_order in kite.orders()
        if is_open_order(existing_order) and is_similar_order(existing_order, new_order)
    ]


def modify_order(kite: Any, existing_order: dict[str, Any], new_order: dict[str, Any]) -> str:
    order_id = str(existing_order["order_id"])
    variety = str(existing_order.get("variety") or new_order["variety"])
    payload = {
        "quantity": new_order["quantity"],
        "order_type": new_order["order_type"],
        "validity": new_order["validity"],
    }
    if "price" in new_order:
        payload["price"] = new_order["price"]

    print(
        "Modifying similar open order: "
        f"order_id={order_id} | {existing_order.get('tradingsymbol')} | "
        f"old_price={existing_order.get('price')} | new_price={new_order.get('price')} | "
        f"old_pending_quantity={existing_order.get('pending_quantity')} | "
        f"new_quantity={new_order.get('quantity')}"
    )
    kite.modify_order(variety=variety, order_id=order_id, **payload)
    return order_id


def modify_or_place_order(kite: Any, new_order: dict[str, Any]) -> str:
    similar_orders = find_similar_open_orders(kite, new_order)

    if not similar_orders:
        print("No similar open orders found to modify.")
        return place_order(kite, new_order)

    if len(similar_orders) > 1:
        print(
            f"Found {len(similar_orders)} similar open orders. "
            "Modifying the latest one and leaving the others unchanged."
        )
    return modify_order(kite, similar_orders[-1], new_order)


def print_order_history(kite: Any, order_id: str) -> None:
    history = kite.order_history(order_id)
    latest = history[-1] if history else {}
    print("\nLatest order status:")
    print(f"  order_id: {order_id}")
    print(f"  status: {latest.get('status', 'UNKNOWN')}")
    print(f"  filled_quantity: {latest.get('filled_quantity', 0)}")
    print(f"  pending_quantity: {latest.get('pending_quantity', 0)}")
    print(f"  average_price: {latest.get('average_price', 0)}")
    if latest.get("status_message"):
        print(f"  status_message: {latest['status_message']}")


def write_orders_csv(orders: list[dict[str, Any]], output_csv: str) -> None:
    path = Path(output_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "exchange",
        "tradingsymbol",
        "quantity",
        "transaction_type",
        "product",
        "order_type",
        "price",
        "validity",
        "tag",
        "average_price",
        "ltp",
        "pnl",
        "price_basis",
        "discount_percent",
    ]
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for order in orders:
            writer.writerow({field: order.get(field, "") for field in fieldnames})
    print(f"\nWrote generated orders to: {path}")


def main() -> int:
    args = parse_args()
    if args.live and os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise SystemExit("Refusing live order. Set KITE_CONFIRM_LIVE_ORDER=YES first.")

    kite = kite_client()
    positions = current_positions(kite, args)
    orders = [
        order
        for position in positions
        if (order := build_buy_order(position, args, kite)) is not None
    ]

    if not orders:
        raise SystemExit("No matching positions found after filters.")

    if args.max_orders is not None and len(orders) > args.max_orders:
        raise SystemExit(
            f"Refusing to create {len(orders)} orders because max-orders is {args.max_orders}."
        )

    for index, order in enumerate(orders, start=1):
        if len(orders) > 1:
            print(f"\nOrder {index}/{len(orders)}")
        print_order(order)

    if args.output_csv:
        write_orders_csv(orders, args.output_csv)

    if not args.live:
        print("\nDry run only. Add --live and set KITE_CONFIRM_LIVE_ORDER=YES to place orders.")
        return 0

    try:
        for index, order in enumerate(orders, start=1):
            print(f"\nPlacing BUY order {index}/{len(orders)}: {order['tradingsymbol']}")
            if not confirm_order(order):
                print(f"Skipped order {index}/{len(orders)}: {order['tradingsymbol']}")
                continue
            if args.keep_existing_orders:
                order_id = place_order(kite, order)
                print(f"Order registered with OMS. order_id: {order_id}")
            else:
                order_id = modify_or_place_order(kite, order)
                print(f"Order placed or modified with OMS. order_id: {order_id}")
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
