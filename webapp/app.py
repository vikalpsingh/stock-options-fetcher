#!/usr/bin/env python3
"""
Small local web UI for previewing and placing Zerodha Kite CSV orders.

Run:
  python app.py

Then open:
  http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import csv
import html
import io
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.request import Request, urlopen


APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent
SCRIPT_ROOT = PROJECT_ROOT / "src" / "script"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

try:
    import kite_place_order as kite_orders
    import kite_buy_positions as kite_buy_positions
except Exception as exc:  # pragma: no cover - shown in browser if import fails
    kite_orders = None
    kite_buy_positions = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


DEFAULT_CSV_PATH = PROJECT_ROOT / "src" / "script" / "kite_orders.csv"
DEFAULT_KITE_ENV = {
    "KITE_CONFIRM_LIVE_ORDER": "YES",
    "KITE_API_KEY": "vr6yz47r650vum8p",
    "KITE_API_SECRET": "vgbk58nvcdmtjc68mbrwoebkbldmm4oj",
    "KITE_ACCESS_TOKEN": "CPtYMoCuAxtMvoNNnGKSnCFERiRK94Lx",
}
ORDER_FIELDS = [
    "variety",
    "exchange",
    "tradingsymbol",
    "transaction_type",
    "quantity",
    "product",
    "order_type",
    "price",
    "validity",
    "tag",
    "autoslice",
]
DISPLAY_FIELDS = [
    "exchange",
    "tradingsymbol",
    "transaction_type",
    "quantity",
    "product",
    "order_type",
    "price",
    "validity",
    "tag",
]
MMI_URL = "https://www.tickertape.in/market-mood-index"
DEFAULT_GPT_SHARE_URL = "https://chatgpt.com/share/6a058d56-7558-83a4-ac3d-d4ea9058b663"

for env_name, env_value_default in DEFAULT_KITE_ENV.items():
    os.environ[env_name] = env_value_default


def read_default_csv_text() -> str:
    if not DEFAULT_CSV_PATH.exists():
        return ""
    return DEFAULT_CSV_PATH.read_text(encoding="utf-8-sig")


@dataclass
class PageState:
    active_tab: str = "place"
    message: str = ""
    error: str = ""
    csv_path: str = str(DEFAULT_CSV_PATH)
    csv_text: str = field(default_factory=read_default_csv_text)
    rows: list[dict[str, str]] | None = None
    orders: list[dict[str, Any]] | None = None
    selected_indexes: set[int] | None = None
    no_ltp_price: bool = True
    keep_existing_orders: bool = False
    dry_run: bool = True
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    confirm_live_order: str = ""
    results: list[dict[str, Any]] | None = None
    console_log: str = ""
    position_orders: list[dict[str, Any]] | None = None
    position_selected_indexes: set[int] | None = None
    position_results: list[dict[str, Any]] | None = None
    position_dry_run: bool = True
    position_discount_percent: float = 20.0
    position_exchange: str = "NFO"
    position_product: str = ""
    position_include_long: bool = False
    position_profit_only: bool = False
    position_symbols: str = ""
    position_validity: str = "DAY"
    position_variety: str = "regular"
    position_tag: str = "GPT_BUY"
    position_tick_size: float = 0.05
    position_autoslice: bool = False
    position_keep_existing_orders: bool = False
    position_max_orders: str = ""
    gpt_url: str = DEFAULT_GPT_SHARE_URL
    gpt_conversation: str = ""
    gpt_csv_text: str = ""


def mask_secret(value: str | None) -> str:
    if not value:
        return "<not set>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def env_value(name: str) -> str:
    return os.getenv(name, "")


def set_kite_env(form: dict[str, list[str]]) -> None:
    env_names = {
        "api_key": "KITE_API_KEY",
        "api_secret": "KITE_API_SECRET",
        "access_token": "KITE_ACCESS_TOKEN",
        "confirm_live_order": "KITE_CONFIRM_LIVE_ORDER",
    }
    for field, env_name in env_names.items():
        value = first(form, field)
        if value != "":
            os.environ[env_name] = value.strip()


def first(form: dict[str, list[str]], name: str, default: str = "") -> str:
    values = form.get(name)
    return values[0] if values else default


def checked(form: dict[str, list[str]], name: str, default: bool = False) -> bool:
    if name not in form:
        return default
    return first(form, name).lower() in {"1", "true", "yes", "on"}


def optional_int_text(value: str) -> int | None:
    text = value.strip()
    return int(text) if text else None


def encode_orders(orders: list[dict[str, Any]]) -> str:
    payload = json.dumps(orders, separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_orders(value: str) -> list[dict[str, Any]]:
    payload = base64.urlsafe_b64decode(value.encode("ascii"))
    return json.loads(payload.decode("utf-8"))


def parse_csv_text(csv_text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if not reader.fieldnames:
        raise ValueError("CSV is missing a header row.")
    if not rows:
        raise ValueError("CSV has no order rows.")
    return rows


def load_rows(csv_path: str, csv_text: str) -> tuple[list[dict[str, str]], str]:
    if csv_text.strip():
        return parse_csv_text(csv_text), csv_text

    path = Path(csv_path.strip() or DEFAULT_CSV_PATH)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    return parse_csv_text(text), text


def persist_default_csv_text(csv_text: str) -> str:
    text = csv_text.strip()
    if not text:
        return ""

    current_text = read_default_csv_text()
    normalized_new = text.rstrip() + "\n"
    if current_text == normalized_new:
        return "kite_orders.csv already has these input details."

    archive_message = ""
    if DEFAULT_CSV_PATH.exists() and current_text.strip():
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        archive_path = DEFAULT_CSV_PATH.with_name(
            f"kite_orders_last_input_order_{stamp}.csv"
        )
        DEFAULT_CSV_PATH.replace(archive_path)
        archive_message = f"Archived previous CSV to {archive_path.name}. "

    DEFAULT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CSV_PATH.write_text(normalized_new, encoding="utf-8")
    return f"{archive_message}Updated kite_orders.csv from the input box."


def mmi_zone(value: float) -> str:
    if value >= 71:
        return "Extreme Greed"
    if value >= 51:
        return "Greed"
    if value > 49:
        return "Neutral"
    if value >= 30:
        return "Fear"
    return "Extreme Fear"


def fetch_mmi_snapshot() -> dict[str, Any]:
    request = Request(
        MMI_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=8) as response:
        page = response.read().decode("utf-8", errors="ignore")

    patterns = [
        r'"mmi"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        r'"currentValue"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        r"Market Mood Index[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, page, flags=re.IGNORECASE)
        if match:
            value = float(match.group(1))
            return {
                "ok": True,
                "value": round(value, 2),
                "zone": mmi_zone(value),
                "source": MMI_URL,
            }

    return {
        "ok": False,
        "error": "Could not read MMI value from Tickertape page.",
        "source": MMI_URL,
    }


def compact_text(value: str) -> str:
    value = re.sub(r"\r\n?", "\n", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def html_page_to_text(page: str) -> str:
    code_blocks = re.findall(
        r"<(?:pre|code)[^>]*>(.*?)</(?:pre|code)>",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    chunks = code_blocks or [page]
    text_chunks = []
    for chunk in chunks:
        chunk = re.sub(r"<script\b.*?</script>", " ", chunk, flags=re.IGNORECASE | re.DOTALL)
        chunk = re.sub(r"<style\b.*?</style>", " ", chunk, flags=re.IGNORECASE | re.DOTALL)
        chunk = re.sub(r"<br\s*/?>", "\n", chunk, flags=re.IGNORECASE)
        chunk = re.sub(r"</(?:p|div|li|tr|h[1-6])>", "\n", chunk, flags=re.IGNORECASE)
        chunk = re.sub(r"<[^>]+>", " ", chunk)
        text_chunks.append(html.unescape(chunk))
    return compact_text("\n\n".join(text_chunks))


def fetch_gpt_conversation(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=12) as response:
        page = response.read().decode("utf-8", errors="ignore")
    text = html_page_to_text(page)
    if not text:
        raise ValueError("Could not read visible text from GPT share page.")
    return text


def normalize_csv_candidate(candidate: str) -> str:
    candidate = html.unescape(candidate)
    candidate = candidate.replace("\u00a0", " ")
    candidate = compact_text(candidate)
    lines = [line.strip().strip("`") for line in candidate.splitlines() if line.strip()]
    return "\n".join(lines).strip()


def extract_csv_from_text(text: str) -> str:
    fenced_blocks = re.findall(r"```(?:csv)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    candidates = [normalize_csv_candidate(block) for block in fenced_blocks]

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    required_headers = {"tradingsymbol", "quantity", "transaction_type"}
    for index, line in enumerate(lines):
        if "," not in line:
            continue
        header = {item.strip().lower() for item in line.split(",")}
        if not required_headers.issubset(header):
            continue
        csv_lines = [line]
        for next_line in lines[index + 1 :]:
            if "," not in next_line:
                break
            csv_lines.append(next_line)
        candidates.append(normalize_csv_candidate("\n".join(csv_lines)))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parse_csv_text(candidate)
            return candidate.rstrip() + "\n"
        except Exception:
            continue
    raise ValueError(
        "Could not find a valid Kite order CSV. Paste the GPT CSV output into the text box and try again."
    )


def default_args(no_ltp_price: bool, keep_existing_orders: bool) -> argparse.Namespace:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")

    cfg = kite_orders.OrderConfig()
    return argparse.Namespace(
        login=False,
        live=False,
        orders_csv=None,
        symbol=cfg.tradingsymbol,
        exchange=cfg.exchange,
        transaction_type=cfg.transaction_type,
        quantity=cfg.quantity,
        lots=None,
        lot_size=None,
        product=cfg.product,
        order_type=cfg.order_type,
        price=cfg.price,
        price_markup_percent=None,
        no_ltp_price=no_ltp_price,
        tick_size=cfg.tick_size,
        validity=cfg.validity,
        tag=cfg.tag,
        variety=cfg.variety,
        market_protection=cfg.market_protection,
        autoslice=False,
        keep_existing_orders=keep_existing_orders,
        max_live_price=None,
        status_wait_seconds=0,
    )


def build_orders(
    rows: list[dict[str, str]], no_ltp_price: bool, keep_existing_orders: bool
) -> list[dict[str, Any]]:
    base_args = default_args(no_ltp_price, keep_existing_orders)
    row_args = [kite_orders.args_for_csv_row(base_args, row) for row in rows]
    needs_kite = any(not item.no_ltp_price for item in row_args)
    kite = kite_orders.kite_client() if needs_kite else None
    return [kite_orders.build_order(item, kite) for item in row_args]


def encode_rows(rows: list[dict[str, str]]) -> str:
    payload = json.dumps(rows, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_rows(value: str) -> list[dict[str, str]]:
    payload = base64.urlsafe_b64decode(value.encode("ascii"))
    return json.loads(payload.decode("utf-8"))


def execute_orders(
    rows: list[dict[str, str]],
    selected_indexes: set[int],
    dry_run: bool,
    no_ltp_price: bool,
    keep_existing_orders: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_rows = [row for index, row in enumerate(rows) if index in selected_indexes]
    if not selected_rows:
        raise ValueError("Select at least one order.")

    orders = build_orders(selected_rows, no_ltp_price, keep_existing_orders)
    if dry_run:
        return orders, [
            {
                "tradingsymbol": order["tradingsymbol"],
                "status": "DRY_RUN",
                "detail": "Order was built but not sent to Kite.",
            }
            for order in orders
        ]

    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Live placement refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )

    kite = kite_orders.kite_client()
    kite_orders.attach_position_info(kite, orders)
    results: list[dict[str, Any]] = []
    for order in orders:
        try:
            if keep_existing_orders:
                order_id = kite_orders.place_order(kite, order)
                action = "placed"
            else:
                order_id = kite_orders.modify_or_place_order(kite, order)
                action = "placed_or_modified"
            results.append(
                {
                    "tradingsymbol": order["tradingsymbol"],
                    "status": "LIVE_SENT",
                    "order_id": order_id,
                    "detail": action,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "tradingsymbol": order.get("tradingsymbol", "<unknown>"),
                    "status": "ERROR",
                    "detail": str(exc),
                }
            )
    return orders, results


def position_args_from_state(state: PageState) -> argparse.Namespace:
    symbols = [
        symbol.strip().upper()
        for symbol in state.position_symbols.replace("\n", ",").split(",")
        if symbol.strip()
    ]
    return argparse.Namespace(
        live=False,
        discount_percent=float(state.position_discount_percent),
        exchange=state.position_exchange.strip() or "NFO",
        product=state.position_product.strip() or None,
        include_long=state.position_include_long,
        profit_only=state.position_profit_only,
        symbol=symbols or None,
        order_type="LIMIT",
        validity=state.position_validity.strip() or "DAY",
        variety=state.position_variety.strip() or "regular",
        tag=state.position_tag.strip() or "GPT_BUY",
        tick_size=float(state.position_tick_size),
        autoslice=state.position_autoslice,
        keep_existing_orders=state.position_keep_existing_orders,
        max_orders=optional_int_text(state.position_max_orders),
        output_csv=None,
        status_wait_seconds=0,
    )


def build_position_buy_orders(state: PageState) -> list[dict[str, Any]]:
    if kite_buy_positions is None:
        raise RuntimeError(f"Could not import kite_buy_positions.py: {IMPORT_ERROR}")

    args = position_args_from_state(state)
    kite = kite_buy_positions.kite_client()
    positions = kite_buy_positions.current_positions(kite, args)
    orders = [
        order
        for position in positions
        if (order := kite_buy_positions.build_buy_order(position, args, kite)) is not None
    ]
    if not orders:
        raise ValueError("No matching positions found after filters.")
    if args.max_orders is not None and len(orders) > args.max_orders:
        raise ValueError(
            f"Refusing to create {len(orders)} orders because max-orders is {args.max_orders}."
        )
    return orders


def execute_position_buy_orders(
    orders: list[dict[str, Any]],
    selected_indexes: set[int],
    dry_run: bool,
    keep_existing_orders: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_orders = [order for index, order in enumerate(orders) if index in selected_indexes]
    if not selected_orders:
        raise ValueError("Select at least one BUY order.")

    if dry_run:
        return selected_orders, [
            {
                "tradingsymbol": order["tradingsymbol"],
                "status": "DRY_RUN",
                "detail": "BUY order was built but not sent to Kite.",
            }
            for order in selected_orders
        ]

    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Live placement refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )

    kite = kite_buy_positions.kite_client()
    results: list[dict[str, Any]] = []
    for order in selected_orders:
        try:
            if keep_existing_orders:
                order_id = kite_buy_positions.place_order(kite, order)
                action = "placed"
            else:
                order_id = kite_buy_positions.modify_or_place_order(kite, order)
                action = "placed_or_modified"
            results.append(
                {
                    "tradingsymbol": order["tradingsymbol"],
                    "status": "LIVE_SENT",
                    "order_id": order_id,
                    "detail": action,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "tradingsymbol": order.get("tradingsymbol", "<unknown>"),
                    "status": "ERROR",
                    "detail": str(exc),
                }
            )
    return selected_orders, results


def call_with_console(func: Any, *args: Any, **kwargs: Any) -> tuple[Any, str]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        result = func(*args, **kwargs)
    return result, stream.getvalue()


def render_input(name: str, label: str, value: str, input_type: str = "text") -> str:
    safe_value = html.escape(value, quote=True)
    secret_class = " secret-field" if input_type == "password" else ""
    return (
        f'<label><span>{html.escape(label)}</span>'
        f'<input class="{secret_class}" name="{name}" type="{input_type}" value="{safe_value}" autocomplete="off"></label>'
    )


def render_number_input(name: str, label: str, value: Any, step: str = "1") -> str:
    safe_value = html.escape(str(value), quote=True)
    return (
        f'<label><span>{html.escape(label)}</span>'
        f'<input name="{name}" type="number" step="{html.escape(step, quote=True)}" '
        f'value="{safe_value}" autocomplete="off"></label>'
    )


def render_checkbox(name: str, label: str, is_checked: bool, hint: str = "") -> str:
    attr = " checked" if is_checked else ""
    hint_html = f"<small>{html.escape(hint)}</small>" if hint else ""
    return (
        f'<label class="check"><input type="checkbox" name="{name}" value="1"{attr}>'
        f"<span>{html.escape(label)}</span>{hint_html}</label>"
    )


def render_orders_table(orders: list[dict[str, Any]] | None, selected: set[int] | None = None) -> str:
    if not orders:
        return ""
    selected = selected or set(range(len(orders)))
    header = "".join(f"<th>{html.escape(field)}</th>" for field in DISPLAY_FIELDS)
    rows = []
    for index, order in enumerate(orders):
        checked_attr = " checked" if index in selected else ""
        cells = "".join(
            f"<td>{html.escape(str(order.get(field, '')))}</td>" for field in DISPLAY_FIELDS
        )
        rows.append(
            "<tr>"
            f'<td><input type="checkbox" name="selected" value="{index}"{checked_attr}></td>'
            f"{cells}</tr>"
        )
    return (
        '<section class="panel"><div class="panel-title">Orders</div>'
        '<div class="table-wrap"><table><thead><tr><th>Select</th>'
        f"{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"
    )


def render_position_orders_table(
    orders: list[dict[str, Any]] | None, selected: set[int] | None = None
) -> str:
    if not orders:
        return ""
    selected = selected or set(range(len(orders)))
    fields = DISPLAY_FIELDS + ["average_price", "ltp", "pnl", "price_basis", "discount_percent"]
    header = "".join(f"<th>{html.escape(field)}</th>" for field in fields)
    rows = []
    for index, order in enumerate(orders):
        checked_attr = " checked" if index in selected else ""
        cells = "".join(f"<td>{html.escape(str(order.get(field, '')))}</td>" for field in fields)
        rows.append(
            "<tr>"
            f'<td><input type="checkbox" name="position_selected" value="{index}"{checked_attr}></td>'
            f"{cells}</tr>"
        )
    return (
        '<section class="panel"><div class="panel-title">Position BUY Orders</div>'
        '<div class="table-wrap"><table><thead><tr><th>Select</th>'
        f"{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"
    )


def render_results(results: list[dict[str, Any]] | None) -> str:
    if not results:
        return ""
    rows = []
    for result in results:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(result.get('tradingsymbol', '')))}</td>"
            f"<td>{html.escape(str(result.get('status', '')))}</td>"
            f"<td>{html.escape(str(result.get('order_id', '')))}</td>"
            f"<td>{html.escape(str(result.get('detail', '')))}</td>"
            "</tr>"
        )
    return (
        '<section class="panel"><div class="panel-title">Execution Results</div>'
        "<table><thead><tr><th>Symbol</th><th>Status</th><th>Order ID</th><th>Detail</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></section>"
    )


def render_console(console_log: str) -> str:
    if not console_log.strip():
        return ""
    return (
        '<section class="panel"><div class="panel-title">Kite Console</div>'
        f'<pre class="console">{html.escape(console_log)}</pre></section>'
    )


def render_market_topper() -> str:
    return f"""
    <section class="market-shell">
      <div class="rule-strip">
        <div class="rule-card sell-stock">
          <div class="rule-kicker">Rule 1</div>
          <div class="rule-title">SELL only when you hold the stock</div>
        </div>
        <div class="rule-card sell-put">
          <div class="rule-kicker">Rule 2</div>
          <div class="rule-title">SELL PUT only when you have cash</div>
        </div>
        <div class="mmi-card">
          <div class="rule-kicker">Market Mood Index</div>
          <div class="mmi-value" id="mmi-value">Loading...</div>
          <div class="mmi-zone" id="mmi-zone">Tickertape MMI</div>
          <a href="{MMI_URL}" target="_blank" rel="noopener">Open MMI</a>
        </div>
      </div>
      <div class="ticker-panel">
        <div class="ticker-title">NSE Live Ticker</div>
        <div class="tradingview-widget-container">
          <div class="tradingview-widget-container__widget"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
          {{
            "symbols": [
              {{"proName": "NSE:NIFTY", "title": "NIFTY 50"}},
              {{"proName": "NSE:BANKNIFTY", "title": "BANK NIFTY"}},
              {{"proName": "NSE:FINNIFTY", "title": "FIN NIFTY"}},
              {{"proName": "NSE:RELIANCE", "title": "RELIANCE"}},
              {{"proName": "NSE:HDFCBANK", "title": "HDFC BANK"}},
              {{"proName": "NSE:ICICIBANK", "title": "ICICI BANK"}},
              {{"proName": "NSE:TCS", "title": "TCS"}},
              {{"proName": "NSE:INFY", "title": "INFY"}}
            ],
            "showSymbolLogo": true,
            "colorTheme": "dark",
            "isTransparent": true,
            "displayMode": "adaptive",
            "locale": "in"
          }}
          </script>
        </div>
      </div>
    </section>"""


def render_page(state: PageState) -> bytes:
    rows_payload = encode_rows(state.rows or []) if state.rows else ""
    position_orders_payload = encode_orders(state.position_orders or []) if state.position_orders else ""
    status = (
        f"KITE_API_KEY {mask_secret(env_value('KITE_API_KEY'))} | "
        f"KITE_API_SECRET {mask_secret(env_value('KITE_API_SECRET'))} | "
        f"KITE_ACCESS_TOKEN {mask_secret(env_value('KITE_ACCESS_TOKEN'))} | "
        f"KITE_CONFIRM_LIVE_ORDER {html.escape(env_value('KITE_CONFIRM_LIVE_ORDER') or '<not set>')}"
    )
    alert = ""
    if state.message:
        alert += f'<div class="alert ok">{html.escape(state.message)}</div>'
    if state.error:
        alert += f'<div class="alert error"><pre>{html.escape(state.error)}</pre></div>'

    orders_table = render_orders_table(state.orders, state.selected_indexes)
    position_orders_table = render_position_orders_table(
        state.position_orders, state.position_selected_indexes
    )
    execute_button = (
        '<button type="submit" formaction="/execute" class="danger">Execute Selected</button>'
        if state.rows
        else ""
    )
    position_execute_button = (
        '<button type="submit" formaction="/positions/execute" class="danger">Execute Selected BUY</button>'
        if state.position_orders
        else ""
    )
    place_tab_class = "active" if state.active_tab == "place" else ""
    positions_tab_class = "active" if state.active_tab == "positions" else ""
    gpt_tab_class = "active" if state.active_tab == "gpt" else ""
    place_panel_style = "" if state.active_tab == "place" else ' style="display:none"'
    positions_panel_style = "" if state.active_tab == "positions" else ' style="display:none"'
    gpt_panel_style = "" if state.active_tab == "gpt" else ' style="display:none"'
    env_panel = f"""
        <section class="panel">
          <div class="panel-title">Kite Environment</div>
          {render_input("api_key", "KITE_API_KEY", state.api_key or env_value("KITE_API_KEY"))}
          {render_input("api_secret", "KITE_API_SECRET", state.api_secret or env_value("KITE_API_SECRET"), "password")}
          {render_input("access_token", "KITE_ACCESS_TOKEN", state.access_token or env_value("KITE_ACCESS_TOKEN"), "password")}
          {render_input("confirm_live_order", "KITE_CONFIRM_LIVE_ORDER", state.confirm_live_order or env_value("KITE_CONFIRM_LIVE_ORDER"))}
          {render_checkbox("show_credentials", "Show credential values", False, "Reveals KITE_API_SECRET and KITE_ACCESS_TOKEN in this local browser page.")}
          <div class="status">{status}</div>
        </section>"""
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kite CSV Trader</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #eef3f7;
      --ink: #17202a;
      --muted: #627084;
      --line: #d8dee8;
      --panel: #ffffff;
      --accent: #1769aa;
      --danger: #b42318;
      --ok: #0f766e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background:
        radial-gradient(circle at 14% -8%, rgba(23, 105, 170, 0.22), transparent 28%),
        linear-gradient(180deg, #eef6fb 0%, #f6f7f9 44%, #eef3f7 100%);
      color: var(--ink);
    }}
    header {{
      background: linear-gradient(135deg, #0f172a 0%, #164e63 54%, #0f766e 100%);
      border-bottom: 1px solid var(--line);
      padding: 22px 24px;
      color: #ffffff;
    }}
    header h1 {{ margin: 0 0 6px; font-size: 30px; letter-spacing: 0; }}
    header p {{ margin: 0; color: #d5eef3; font-size: 14px; }}
    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 22px auto 40px;
    }}
    .market-shell {{
      margin-bottom: 18px;
    }}
    .rule-strip {{
      display: grid;
      grid-template-columns: 1.1fr 1.1fr 0.9fr;
      gap: 14px;
      margin-bottom: 12px;
    }}
    .rule-card, .mmi-card {{
      border-radius: 8px;
      padding: 16px;
      color: #ffffff;
      min-height: 108px;
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
      border: 1px solid rgba(255, 255, 255, 0.18);
    }}
    .sell-stock {{
      background: linear-gradient(135deg, #123c69 0%, #1769aa 100%);
    }}
    .sell-put {{
      background: linear-gradient(135deg, #14532d 0%, #0f766e 100%);
    }}
    .mmi-card {{
      background: linear-gradient(135deg, #3f1d64 0%, #7c3aed 100%);
    }}
    .rule-kicker {{
      font-size: 12px;
      text-transform: uppercase;
      font-weight: 700;
      color: rgba(255, 255, 255, 0.76);
      margin-bottom: 10px;
    }}
    .rule-title {{
      font-size: 22px;
      line-height: 1.15;
      font-weight: 800;
    }}
    .mmi-value {{
      font-size: 30px;
      font-weight: 800;
      line-height: 1;
      margin-bottom: 7px;
    }}
    .mmi-zone {{
      color: rgba(255, 255, 255, 0.82);
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .mmi-card a {{
      color: #ffffff;
      font-size: 13px;
      font-weight: 700;
    }}
    .ticker-panel {{
      background: #0b1220;
      color: #ffffff;
      border-radius: 8px;
      border: 1px solid rgba(255, 255, 255, 0.12);
      overflow: hidden;
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
    }}
    .ticker-title {{
      padding: 10px 14px 0;
      color: #a7f3d0;
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .tradingview-widget-container {{
      min-height: 74px;
      width: 100%;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      align-items: start;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
    }}
    .panel-title {{
      font-weight: 700;
      margin-bottom: 14px;
      font-size: 16px;
    }}
    .tabs {{
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--line);
    }}
    .tab-button {{
      border: 1px solid var(--line);
      border-bottom: 0;
      border-radius: 8px 8px 0 0;
      background: #eef2f7;
      color: var(--ink);
      padding: 10px 14px;
    }}
    .tab-button.active {{
      background: #ffffff;
      color: var(--accent);
    }}
    label {{ display: block; margin-bottom: 12px; }}
    label span {{ display: block; font-size: 13px; color: var(--muted); margin-bottom: 5px; }}
    input[type="text"], input[type="password"], textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      font-size: 14px;
      background: #ffffff;
      color: var(--ink);
    }}
    textarea {{
      min-height: 150px;
      resize: vertical;
      font-family: Consolas, "Courier New", monospace;
    }}
    input[type="file"] {{ width: 100%; }}
    .check {{
      display: grid;
      grid-template-columns: 18px 1fr;
      column-gap: 8px;
      align-items: start;
    }}
    .check span {{ color: var(--ink); margin: 0; }}
    .check small {{
      grid-column: 2;
      color: var(--muted);
      line-height: 1.35;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 10px;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      padding: 10px 14px;
      background: linear-gradient(135deg, #1769aa 0%, #0f766e 100%);
      color: #ffffff;
      cursor: pointer;
      font-weight: 700;
    }}
    button.secondary {{ background: #4b5563; }}
    button.danger {{ background: linear-gradient(135deg, #b42318 0%, #7f1d1d 100%); }}
    .alert {{
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 16px;
      border: 1px solid;
    }}
    .alert.ok {{ color: var(--ok); background: #ecfdf5; border-color: #99f6e4; }}
    .alert.error {{ color: var(--danger); background: #fff1f2; border-color: #fecdd3; }}
    .alert pre {{ margin: 0; white-space: pre-wrap; font-family: Consolas, "Courier New", monospace; }}
    .console {{
      margin: 0;
      padding: 12px;
      max-height: 360px;
      overflow: auto;
      border-radius: 6px;
      background: #111827;
      color: #e5e7eb;
      font-family: Consolas, "Courier New", monospace;
      font-size: 13px;
      line-height: 1.45;
      white-space: pre-wrap;
    }}
    .conversation {{
      min-height: 260px;
    }}
    .csv-output {{
      min-height: 220px;
    }}
    .status {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      margin-top: 10px;
    }}
    .inline-link {{
      display: inline-block;
      margin: -4px 0 12px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
    }}
    .table-wrap {{ overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      text-align: left;
      white-space: nowrap;
    }}
    th {{ color: var(--muted); font-weight: 700; background: #f9fafb; }}
    @media (max-width: 820px) {{
      .rule-strip {{ grid-template-columns: 1fr; }}
      .grid {{ grid-template-columns: 1fr; }}
      header {{ padding: 16px; }}
      main {{ width: calc(100vw - 20px); }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Kite Trader</h1>
    <p>Place CSV orders or build BUY orders from existing Kite positions.</p>
  </header>
  <main>
    {render_market_topper()}
    {alert}
    <div class="tabs">
      <button class="tab-button {place_tab_class}" type="button" data-tab="place">Place Order</button>
      <button class="tab-button {positions_tab_class}" type="button" data-tab="positions">Current Position BUY</button>
      <button class="tab-button {gpt_tab_class}" type="button" data-tab="gpt">GPT CSV Generator</button>
    </div>
    <form id="place-panel" method="post" action="/load"{place_panel_style}>
      <input type="hidden" name="rows_payload" value="{html.escape(rows_payload, quote=True)}">
      <div class="grid">
        <section class="panel">
          <div class="panel-title">CSV Source</div>
          {render_input("csv_path", "CSV path", state.csv_path)}
          <label><span>Upload CSV</span><input id="csv-file" type="file" accept=".csv,text/csv"></label>
          <label><span>CSV text</span><textarea id="csv-text" name="csv_text" placeholder="Paste CSV here or choose a file above">{html.escape(state.csv_text)}</textarea></label>
        </section>
        {env_panel}
      </div>
      <section class="panel">
        <div class="panel-title">Execution Options</div>
        {render_checkbox("dry_run", "Dry run", state.dry_run, "Build orders and show what would happen without sending anything to Kite.")}
        {render_checkbox("no_ltp_price", "Use CSV/manual price only", state.no_ltp_price, "Leave this on when the CSV already has prices or lot_size. Turn off to fetch LTP/lot size from Kite.")}
        {render_checkbox("keep_existing_orders", "Place new order instead of modifying similar open order", state.keep_existing_orders)}
        <div class="actions">
          <button type="submit" formaction="/load">Load / Preview CSV</button>
          {execute_button}
        </div>
      </section>
      {orders_table}
      {render_results(state.results)}
      {render_console(state.console_log)}
    </form>
    <form id="positions-panel" method="post" action="/positions/load"{positions_panel_style}>
      <input type="hidden" name="position_orders_payload" value="{html.escape(position_orders_payload, quote=True)}">
      <div class="grid">
        <section class="panel">
          <div class="panel-title">Position BUY Options</div>
          {render_number_input("position_discount_percent", "Discount percent", state.position_discount_percent, "0.05")}
          {render_input("position_exchange", "Exchange", state.position_exchange)}
          {render_input("position_product", "Product filter", state.position_product)}
          {render_input("position_symbols", "Symbol filter, comma-separated", state.position_symbols)}
          {render_input("position_variety", "Variety", state.position_variety)}
          {render_input("position_validity", "Validity", state.position_validity)}
          {render_input("position_tag", "Tag", state.position_tag)}
          {render_number_input("position_tick_size", "Tick size", state.position_tick_size, "0.01")}
          {render_input("position_max_orders", "Max orders", state.position_max_orders)}
        </section>
        {env_panel}
      </div>
      <section class="panel">
        <div class="panel-title">Execution Options</div>
        {render_checkbox("position_dry_run", "Dry run", state.position_dry_run, "Build BUY orders and show what would happen without sending anything to Kite.")}
        {render_checkbox("position_include_long", "Include long positions", state.position_include_long, "Default only creates BUY orders for short positions.")}
        {render_checkbox("position_profit_only", "Profit-only positions", state.position_profit_only)}
        {render_checkbox("position_autoslice", "Autoslice", state.position_autoslice)}
        {render_checkbox("position_keep_existing_orders", "Place new order instead of modifying similar open order", state.position_keep_existing_orders)}
        <div class="actions">
          <button type="submit" formaction="/positions/load">Get Current Position / Preview BUY</button>
          {position_execute_button}
        </div>
      </section>
      {position_orders_table}
      {render_results(state.position_results)}
      {render_console(state.console_log)}
    </form>
    <form id="gpt-panel" method="post" action="/gpt/load"{gpt_panel_style}>
      <div class="grid">
        <section class="panel">
          <div class="panel-title">GPT Conversation</div>
          {render_input("gpt_url", "GPT share URL", state.gpt_url)}
          <a class="inline-link" href="{html.escape(state.gpt_url, quote=True)}" target="_blank" rel="noopener">Open GPT Share</a>
          <label><span>Conversation / GPT output</span><textarea class="conversation" name="gpt_conversation" placeholder="Fetch the share link, or paste GPT output here">{html.escape(state.gpt_conversation)}</textarea></label>
          <div class="actions">
            <button type="submit" formaction="/gpt/load">Fetch GPT Share</button>
            <button type="submit" formaction="/gpt/extract">Extract CSV</button>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title">CSV To Save</div>
          <label><span>Extracted CSV</span><textarea class="csv-output" name="gpt_csv_text" placeholder="CSV generated from GPT appears here">{html.escape(state.gpt_csv_text)}</textarea></label>
          <div class="actions">
            <button type="submit" formaction="/gpt/save">Save to kite_orders.csv</button>
            <button type="submit" formaction="/gpt/save-preview">Save and Preview Orders</button>
          </div>
          <div class="status">Saved CSV uses the same archive flow as Place Order, so the previous kite_orders.csv is kept as a last input order record.</div>
        </section>
      </div>
      {orders_table}
      {render_console(state.console_log)}
    </form>
  </main>
  <script>
    const fileInput = document.getElementById('csv-file');
    const textArea = document.getElementById('csv-text');
    const showCredentials = Array.from(document.querySelectorAll('input[name="show_credentials"]'));
    const secretFields = Array.from(document.querySelectorAll('.secret-field'));
    fileInput && fileInput.addEventListener('change', async () => {{
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      textArea.value = await file.text();
    }});
    for (const toggle of showCredentials) {{
      toggle.addEventListener('change', () => {{
        for (const field of secretFields) {{
          field.type = toggle.checked ? 'text' : 'password';
        }}
        for (const other of showCredentials) {{
          other.checked = toggle.checked;
        }}
      }});
    }}
    for (const button of document.querySelectorAll('.tab-button')) {{
      button.addEventListener('click', () => {{
        const active = button.dataset.tab;
        document.getElementById('place-panel').style.display = active === 'place' ? '' : 'none';
        document.getElementById('positions-panel').style.display = active === 'positions' ? '' : 'none';
        document.getElementById('gpt-panel').style.display = active === 'gpt' ? '' : 'none';
        for (const item of document.querySelectorAll('.tab-button')) {{
          item.classList.toggle('active', item.dataset.tab === active);
        }}
      }});
    }}
    async function refreshMmi() {{
      const value = document.getElementById('mmi-value');
      const zone = document.getElementById('mmi-zone');
      if (!value || !zone) return;
      try {{
        const response = await fetch('/market-mmi', {{ cache: 'no-store' }});
        const data = await response.json();
        if (data.ok) {{
          value.textContent = data.value;
          zone.textContent = data.zone;
        }} else {{
          value.textContent = 'Open';
          zone.textContent = 'Tickertape live MMI';
        }}
      }} catch (error) {{
        value.textContent = 'Open';
        zone.textContent = 'Tickertape live MMI';
      }}
    }}
    refreshMmi();
  </script>
</body>
</html>"""
    return html_doc.encode("utf-8")


class KiteWebHandler(BaseHTTPRequestHandler):
    server_version = "KiteCSVTrader/1.0"

    def do_GET(self) -> None:
        if self.path == "/market-mmi":
            try:
                self.send_json(fetch_mmi_snapshot())
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                        "source": MMI_URL,
                    }
                )
            return
        self.send_page(PageState())

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(body, keep_blank_values=True)
        set_kite_env(form)

        state = PageState(
            active_tab=(
                "positions"
                if self.path.startswith("/positions")
                else "gpt"
                if self.path.startswith("/gpt")
                else "place"
            ),
            csv_path=first(form, "csv_path", str(DEFAULT_CSV_PATH)),
            csv_text=first(form, "csv_text"),
            no_ltp_price=checked(form, "no_ltp_price"),
            keep_existing_orders=checked(form, "keep_existing_orders"),
            dry_run=checked(form, "dry_run"),
            api_key=first(form, "api_key"),
            api_secret=first(form, "api_secret"),
            access_token=first(form, "access_token"),
            confirm_live_order=first(form, "confirm_live_order"),
            position_dry_run=checked(form, "position_dry_run"),
            position_discount_percent=float(first(form, "position_discount_percent", "20") or 20),
            position_exchange=first(form, "position_exchange", "NFO"),
            position_product=first(form, "position_product"),
            position_include_long=checked(form, "position_include_long"),
            position_profit_only=checked(form, "position_profit_only"),
            position_symbols=first(form, "position_symbols"),
            position_validity=first(form, "position_validity", "DAY"),
            position_variety=first(form, "position_variety", "regular"),
            position_tag=first(form, "position_tag", "GPT_BUY"),
            position_tick_size=float(first(form, "position_tick_size", "0.05") or 0.05),
            position_autoslice=checked(form, "position_autoslice"),
            position_keep_existing_orders=checked(form, "position_keep_existing_orders"),
            position_max_orders=first(form, "position_max_orders"),
            gpt_url=first(form, "gpt_url", DEFAULT_GPT_SHARE_URL),
            gpt_conversation=first(form, "gpt_conversation"),
            gpt_csv_text=first(form, "gpt_csv_text"),
        )

        try:
            if self.path == "/load":
                persist_message = persist_default_csv_text(state.csv_text)
                state.rows, state.csv_text = load_rows(state.csv_path, state.csv_text)
                state.orders, state.console_log = call_with_console(
                    build_orders,
                    state.rows,
                    state.no_ltp_price,
                    state.keep_existing_orders,
                )
                state.selected_indexes = set(range(len(state.orders)))
                state.message = f"{persist_message} Loaded {len(state.orders)} order(s).".strip()
            elif self.path == "/execute":
                rows_payload = first(form, "rows_payload")
                state.rows = decode_rows(rows_payload) if rows_payload else None
                if not state.rows:
                    persist_message = persist_default_csv_text(state.csv_text)
                    state.rows, state.csv_text = load_rows(state.csv_path, state.csv_text)
                else:
                    persist_message = ""
                selected = {int(value) for value in form.get("selected", [])}
                (state.orders, state.results), state.console_log = call_with_console(
                    execute_orders,
                    state.rows,
                    selected,
                    state.dry_run,
                    state.no_ltp_price,
                    state.keep_existing_orders,
                )
                state.selected_indexes = set(range(len(state.orders)))
                if state.dry_run:
                    state.message = (
                        f"{persist_message} Dry run completed for "
                        f"{len(state.orders)} selected order(s)."
                    ).strip()
                else:
                    state.message = (
                        f"{persist_message} Submitted {len(state.orders)} selected order(s) to Kite."
                    ).strip()
            elif self.path == "/positions/load":
                state.position_orders, state.console_log = call_with_console(
                    build_position_buy_orders,
                    state,
                )
                state.position_selected_indexes = set(range(len(state.position_orders)))
                state.message = f"Loaded {len(state.position_orders)} BUY order(s) from current positions."
            elif self.path == "/positions/execute":
                orders_payload = first(form, "position_orders_payload")
                state.position_orders = decode_orders(orders_payload) if orders_payload else None
                if not state.position_orders:
                    state.position_orders, state.console_log = call_with_console(
                        build_position_buy_orders,
                        state,
                    )
                selected = {int(value) for value in form.get("position_selected", [])}
                (
                    state.position_orders,
                    state.position_results,
                ), execute_log = call_with_console(
                    execute_position_buy_orders,
                    state.position_orders,
                    selected,
                    state.position_dry_run,
                    state.position_keep_existing_orders,
                )
                state.console_log = f"{state.console_log}{execute_log}"
                state.position_selected_indexes = set(range(len(state.position_orders)))
                if state.position_dry_run:
                    state.message = (
                        f"Dry run completed for {len(state.position_orders)} selected BUY order(s)."
                    )
                else:
                    state.message = (
                        f"Submitted {len(state.position_orders)} selected BUY order(s) to Kite."
                    )
            elif self.path == "/gpt/load":
                state.gpt_conversation, state.console_log = call_with_console(
                    fetch_gpt_conversation,
                    state.gpt_url,
                )
                state.message = "Fetched GPT share conversation. Review it, then extract CSV."
            elif self.path == "/gpt/extract":
                state.gpt_csv_text = extract_csv_from_text(state.gpt_conversation)
                state.message = "Extracted CSV from GPT conversation."
            elif self.path in {"/gpt/save", "/gpt/save-preview"}:
                if not state.gpt_csv_text.strip():
                    state.gpt_csv_text = extract_csv_from_text(state.gpt_conversation)
                parse_csv_text(state.gpt_csv_text)
                persist_message = persist_default_csv_text(state.gpt_csv_text)
                state.csv_text = state.gpt_csv_text
                if self.path == "/gpt/save-preview":
                    state.rows = parse_csv_text(state.gpt_csv_text)
                    state.orders, state.console_log = call_with_console(
                        build_orders,
                        state.rows,
                        True,
                        state.keep_existing_orders,
                    )
                    state.selected_indexes = set(range(len(state.orders)))
                    state.message = (
                        f"{persist_message} Previewed {len(state.orders)} order(s)."
                    ).strip()
                else:
                    state.message = persist_message
            else:
                state.error = f"Unknown path: {self.path}"
        except Exception as exc:
            state.error = f"{exc}\n\n{traceback.format_exc()}"

        self.send_page(state)

    def send_page(self, state: PageState) -> None:
        content = render_page(state)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: dict[str, Any]) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> int:
    host = os.getenv("KITE_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("KITE_WEB_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), KiteWebHandler)
    print(f"Kite CSV Trader running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Kite CSV Trader.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
