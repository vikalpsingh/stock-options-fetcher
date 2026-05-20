#!/usr/bin/env python3
"""
Place Zerodha Kite Connect orders with a dry-run default.

Environment variables:
  KITE_API_KEY            Zerodha Kite app API key
  KITE_API_SECRET         Zerodha Kite app API secret, used only to create token
  KITE_ACCESS_TOKEN       Daily access token generated after login
  KITE_CONFIRM_LIVE_ORDER Set to YES for live order placement

Examples:
  python src/script/kite_place_order.py --login
  python src/script/kite_place_order.py --orders-csv src/script/kite_orders_sample.csv
  python src/script/kite_place_order.py --orders-csv src/script/kite_orders_sample.csv --live
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse
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
    price_markup_percent: float = 20.0
    tick_size: float = 0.05


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely place Zerodha Kite orders.")
    parser.add_argument("--login", action="store_true", help="Generate daily access token.")
    parser.add_argument("--live", action="store_true", help="Actually place orders.")
    parser.add_argument(
        "--orders-csv",
        help=(
            "CSV for multiple orders. Columns: symbol,transaction_type,lots,lot_size,"
            "price_markup_percent. Optional: exchange,product,order_type,validity,tag,"
            "variety,price,max_live_price."
        ),
    )
    parser.add_argument("--symbol", default=OrderConfig.tradingsymbol)
    parser.add_argument("--exchange", default=OrderConfig.exchange)
    parser.add_argument("--transaction-type", default=OrderConfig.transaction_type)
    parser.add_argument("--quantity", type=int, default=OrderConfig.quantity)
    parser.add_argument("--lots", type=int, help="Number of lots.")
    parser.add_argument("--lot-size", type=int, help="Manual lot size.")
    parser.add_argument("--product", default=OrderConfig.product)
    parser.add_argument("--order-type", default=OrderConfig.order_type)
    parser.add_argument("--price", type=float, default=OrderConfig.price)
    parser.add_argument(
        "--price-markup-percent",
        "--percent",
        dest="price_markup_percent",
        type=float,
        help=(
            "For LIMIT orders, set price from current LTP using this percent. "
            "SELL uses +percent, BUY uses -percent. Default: 20. Use 5 near market close."
        ),
    )
    parser.add_argument(
        "--no-ltp-price",
        action="store_true",
        help="Use --price instead of fetching LTP and applying percentage.",
    )
    parser.add_argument("--tick-size", type=float, default=OrderConfig.tick_size)
    parser.add_argument("--validity", default=OrderConfig.validity)
    parser.add_argument("--tag", default=OrderConfig.tag)
    parser.add_argument("--variety", default=OrderConfig.variety)
    parser.add_argument("--market-protection", type=int, default=OrderConfig.market_protection)
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
        "--max-live-price",
        type=float,
        help="Reject LIMIT order if calculated/manual price is above this value.",
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


def load_env_files() -> None:
    """Load KEY=VALUE pairs from local .env files."""
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[1]
    candidates = [repo_root / ".env", script_dir / ".env", Path.cwd() / ".env"]
    seen: set[Path] = set()

    for path in candidates:
        path = path.resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        with path.open(encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ[key] = value


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


def generate_access_token() -> int:
    KiteConnect = load_kite_connect_class()
    api_key = os.getenv("KITE_API_KEY")
    api_secret = os.getenv("KITE_API_SECRET")

    if not api_key or not api_secret:
        raise SystemExit("Missing KITE_API_KEY or KITE_API_SECRET environment variable.")

    kite = KiteConnect(api_key=api_key)
    print("Open this URL in your browser and login:")
    print(kite.login_url())
    print(
        "\nAfter login, copy the full redirected URL or only the request_token value."
    )
    try:
        request_token_input = input("Paste redirected URL or request_token: ").strip()
    except EOFError as exc:
        raise SystemExit(
            "Could not read request_token. Run this command in an interactive terminal, "
            "open the login URL, then paste the request_token from the redirected URL."
        ) from exc

    request_token = extract_request_token(request_token_input)
    if not request_token:
        raise SystemExit("request_token cannot be empty.")

    data = kite.generate_session(request_token, api_secret=api_secret)
    print("\nDaily access token generated. Run this in PowerShell:")
    print(f'$env:KITE_ACCESS_TOKEN="{data["access_token"]}"')
    return 0


def extract_request_token(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.query:
        token = parse_qs(parsed.query, keep_blank_values=True).get("request_token", [""])[0]
        if token:
            return token.strip()
    if "request_token=" in text:
        token = parse_qs(text.split("?", 1)[-1], keep_blank_values=True).get(
            "request_token", [""]
        )[0]
        if token:
            return token.strip()
    return text


def parse_optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def parse_optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def row_value(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return None


def args_for_csv_row(base_args: argparse.Namespace, row: dict[str, str]) -> argparse.Namespace:
    item = argparse.Namespace(**vars(base_args))
    symbol = row_value(row, "symbol", "tradingsymbol")
    if not symbol:
        raise SystemExit("Each CSV row must include symbol or tradingsymbol.")

    item.symbol = symbol
    item.exchange = row_value(row, "exchange") or base_args.exchange
    item.transaction_type = (
        row_value(row, "transaction_type", "side", "buy_sell") or base_args.transaction_type
    )
    item.product = row_value(row, "product") or base_args.product
    item.order_type = row_value(row, "order_type") or base_args.order_type
    item.validity = row_value(row, "validity") or base_args.validity
    item.tag = row_value(row, "tag") or base_args.tag
    item.variety = row_value(row, "variety") or base_args.variety

    quantity = parse_optional_int(row_value(row, "quantity"))
    lots = parse_optional_int(row_value(row, "lots"))
    if quantity is None and lots is None:
        raise SystemExit(f"CSV row for {symbol} must include lots or quantity.")

    item.quantity = quantity or 0
    item.lots = lots
    item.lot_size = parse_optional_int(row_value(row, "lot_size"))
    item.price = parse_optional_float(row_value(row, "price")) or base_args.price

    percent = row_value(row, "price_markup_percent", "price_offset_percent", "percent")
    item.price_markup_percent = parse_optional_float(percent) if percent is not None else None

    max_price = row_value(row, "max_live_price")
    item.max_live_price = (
        parse_optional_float(max_price)
        if max_price is not None
        else base_args.max_live_price
    )
    return item


def load_order_args(args: argparse.Namespace) -> list[argparse.Namespace]:
    if not args.orders_csv:
        return [args]

    orders_csv = resolve_orders_csv_path(args.orders_csv)
    with open(orders_csv, newline="", encoding="utf-8-sig") as csv_file:
        orders = [args_for_csv_row(args, row) for row in csv.DictReader(csv_file)]

    if not orders:
        raise SystemExit(f"No orders found in {orders_csv}.")
    return orders


def resolve_orders_csv_path(csv_path: str) -> Path:
    path = Path(csv_path)
    if path.exists():
        return path

    script_folder_path = Path(__file__).resolve().parent / csv_path
    if script_folder_path.exists():
        return script_folder_path

    raise SystemExit(
        f"Orders CSV not found: {csv_path}. Try --orders-csv src\\script\\kite_orders.csv"
    )


def get_lot_size(kite: Any, exchange: str, tradingsymbol: str) -> int:
    for instrument in kite.instruments(exchange):
        if instrument.get("tradingsymbol") == tradingsymbol.upper():
            lot_size = int(instrument["lot_size"])
            if lot_size <= 0:
                raise SystemExit(f"Invalid lot size received for {tradingsymbol}: {lot_size}")
            return lot_size
    raise SystemExit(f"Could not find {tradingsymbol} in {exchange} instruments.")


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
            raise SystemExit("Use --lot-size for dry run, or use Kite LTP/instruments mode.")
        lot_size = get_lot_size(kite, args.exchange.upper(), args.symbol.upper())

    if lot_size <= 0:
        raise SystemExit("Lot size must be greater than zero.")

    quantity = args.lots * lot_size
    print(f"Resolved quantity: {args.lots} lot(s) * lot size {lot_size} = {quantity}")
    return quantity


def get_last_price(kite: Any, exchange: str, tradingsymbol: str) -> float:
    instrument_key = f"{exchange}:{tradingsymbol}"
    try:
        quote = kite.ltp(instrument_key)
    except Exception as exc:
        raise SystemExit(
            "Could not fetch LTP from Kite for "
            f"{instrument_key}: {exc}\n"
            "Fix: enable market quote/LTP permission for this Kite app, then create a fresh access token.\n"
            "Fallback dry run: python src\\script\\kite_place_order.py --orders-csv kite_orders.csv --no-ltp-price"
        ) from exc

    last_price = float(quote[instrument_key]["last_price"])
    if last_price <= 0:
        raise SystemExit(f"Invalid LTP received for {instrument_key}: {last_price}")
    return last_price


def round_up_to_tick(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        raise SystemExit("Tick size must be greater than zero.")
    return round(math.ceil(price / tick_size) * tick_size, 2)


def resolve_price(args: argparse.Namespace, order_type: str, kite: Any | None = None) -> float:
    if order_type not in {"LIMIT", "SL"}:
        return args.price

    price = args.price
    if kite is not None and not args.no_ltp_price:
        price_markup_percent = effective_price_markup_percent(args)
        last_price = get_last_price(kite, args.exchange.upper(), args.symbol.upper())
        raw_price = last_price * (1 + price_markup_percent / 100)
        price = round_up_to_tick(raw_price, args.tick_size)
        sign = "+" if price_markup_percent >= 0 else ""
        print(
            "Resolved limit price: "
            f"{args.transaction_type.upper()} {args.symbol.upper()} | "
            f"LTP={last_price} | "
            f"adjustment={sign}{price_markup_percent}% | "
            f"raw={raw_price:.4f} | "
            f"limit={price}"
        )

    if price <= 0:
        raise SystemExit("LIMIT orders require a positive price.")
    if args.max_live_price is not None and price > args.max_live_price:
        raise SystemExit(f"Refusing order: price {price} exceeds max-live-price {args.max_live_price}.")
    return price


def effective_price_markup_percent(args: argparse.Namespace) -> float:
    if args.price_markup_percent is not None:
        return args.price_markup_percent
    if args.transaction_type.upper() == "SELL":
        return OrderConfig.price_markup_percent
    if args.transaction_type.upper() == "BUY":
        return -OrderConfig.price_markup_percent
    return 0.0


def build_order(args: argparse.Namespace, kite: Any | None = None) -> dict[str, Any]:
    order_type = args.order_type.upper()
    transaction_type = args.transaction_type.upper()
    if transaction_type not in {"BUY", "SELL"}:
        raise SystemExit("transaction_type must be BUY or SELL.")
    if order_type not in {"MARKET", "LIMIT", "SL", "SL-M"}:
        raise SystemExit("order_type must be MARKET, LIMIT, SL, or SL-M.")

    order = {
        "variety": args.variety,
        "exchange": args.exchange.upper(),
        "tradingsymbol": args.symbol.upper(),
        "transaction_type": transaction_type,
        "quantity": resolve_quantity(args, kite),
        "product": args.product.upper(),
        "order_type": order_type,
        "validity": args.validity.upper(),
        "tag": args.tag,
    }
    if args.autoslice:
        order["autoslice"] = True
    if order_type in {"LIMIT", "SL"}:
        order["price"] = resolve_price(args, order_type, kite)
    if order_type in {"MARKET", "SL-M"}:
        order["market_protection"] = args.market_protection
    return order


def attach_position_info(kite: Any, orders: list[dict[str, Any]]) -> None:
    positions = kite.positions().get("net", [])
    position_by_key = {
        (
            str(position.get("exchange", "")).upper(),
            str(position.get("tradingsymbol", "")).upper(),
            str(position.get("product", "")).upper(),
        ): position
        for position in positions
    }

    for order in orders:
        position = position_by_key.get(
            (order["exchange"], order["tradingsymbol"], order["product"])
        )
        if position:
            order["average_price"] = float(position.get("average_price") or 0)
            order["ltp"] = float(position.get("last_price") or position.get("ltp") or 0)
            order["pnl"] = float(position.get("pnl") or 0)


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
    payload = order.copy()
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
    if "trigger_price" in new_order:
        payload["trigger_price"] = new_order["trigger_price"]

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


def main() -> int:
    load_env_files()
    args = parse_args()
    if args.login:
        return generate_access_token()

    if args.live and os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise SystemExit("Refusing live order. Set KITE_CONFIRM_LIVE_ORDER=YES first.")

    order_args = load_order_args(args)
    needs_kite = args.live or (
        args.orders_csv is not None and any(not item.no_ltp_price for item in order_args)
    )
    kite = kite_client() if needs_kite else None
    orders = [build_order(item, kite) for item in order_args]
    if args.live and kite is not None:
        attach_position_info(kite, orders)

    for index, order in enumerate(orders, start=1):
        if len(orders) > 1:
            print(f"\nOrder {index}/{len(orders)}")
        print_order(order)

    if not args.live:
        print("\nDry run only. Add --live and set KITE_CONFIRM_LIVE_ORDER=YES to place orders.")
        return 0

    try:
        for index, order in enumerate(orders, start=1):
            print(f"\nPlacing order {index}/{len(orders)}: {order['tradingsymbol']}")
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
