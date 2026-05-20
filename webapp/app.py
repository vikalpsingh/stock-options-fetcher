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
import hashlib
import hmac
import html
import io
import json
import math
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree


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


DATA_CSV_PATH = PROJECT_ROOT / "data.csv"


def dated_income_csv_path(day: date | None = None) -> Path:
    day = day or datetime.now().date()
    return PROJECT_ROOT / f"{day.day}{day.strftime('%b')}{day.year}.csv"


DEFAULT_CSV_PATH = Path(os.getenv("KITE_DEFAULT_CSV_PATH", str(dated_income_csv_path())))
LEGACY_CSV_PATH = PROJECT_ROOT / "src" / "script" / "kite_orders.csv"
SETTINGS_PATH = APP_ROOT / "app_settings.json"
OPENAI_CSV_PROMPT_PATH = APP_ROOT / "openai_csv_prompt.md"
DEFAULT_ETF_BUY_AMOUNT = 10000.0
DEFAULT_KITE_ENV = {
    "KITE_CONFIRM_LIVE_ORDER": "YES",
    "KITE_API_KEY": "vr6yz47r650vum8p",
    "KITE_API_SECRET": "vgbk58nvcdmtjc68mbrwoebkbldmm4oj",
    "KITE_ACCESS_TOKEN": "TqL81HKQXjdi6KQ9jxsYUz5AIUgrrwxB",
}
BAD_KITE_API_KEYS = {"wg21s30mtedr53q0"}
AUTH_USERNAME = "vikalpsingh"
AUTH_PASSWORD_SALT = b"vikalp-income-desk-v1"
AUTH_PASSWORD_HASH = "77e7696df3cb9025e5e9261f76d258208844447c8af89f4c47353c0d04512a76"
AUTH_COOKIE_NAME = "vikalp_income_session"
AUTH_SESSION_SECONDS = 12 * 60 * 60
AUTH_SESSION_SECRET = os.getenv("VIKALP_AUTH_SECRET") or AUTH_PASSWORD_HASH
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
DEFAULT_OPENAI_MODEL = "gpt-5.5"
KITE_CALLBACK_HOST = "127.0.0.1"
KITE_CALLBACK_PORT = 8000
PUBLIC_IP_ENDPOINTS = [
    ("Current public IP", "https://api64.ipify.org?format=json"),
    ("IPv4 public IP", "https://api.ipify.org?format=json"),
    ("IPv6 public IP", "https://api6.ipify.org?format=json"),
]
DEFAULT_OPENAI_SYSTEM_PROMPT = """You are Monthly Income by Trading GPT.

Generate only Kite-compatible CSV output.

CSV columns must be:
exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity

Rules:
- No explanation.
- No markdown.
- No extra text.
- Return valid CSV only.
- Use NSE/NFO symbols.
- Use exchange NFO for options unless the user explicitly says otherwise.
- transaction_type must be BUY or SELL.
- product should usually be NRML for options.
- order_type should usually be LIMIT.
- validity should usually be DAY.
- Strategy is conservative monthly income using covered call or cash-secured put.
- SELL CALL only when actual share holding covers the full option quantity.
- SELL PUT only when cash is available to buy all lots if assigned.
- Avoid new positions when expiry is too close; prefer next monthly expiry when needed.
- User must verify live premium, lot size, margin, liquidity, and event risk before order placement.
"""
DEFAULT_OPENAI_PROMPT = (
    "generate csv file on basis of current market scenario and mentioned prompts"
)
TOP_WATCHLIST = [
    "BAJFINANCE",
    "TATACONSUM",
    "PGEL",
    "TITAN",
    "ETERNAL",
    "UNITDSPR",
    "HAVELLS",
    "NAUKRI",
    "PFC",
    "CAMS",
    "CDSL",
    "MAZDOCK",
    "NUVAMA",
    "NTPC",
    "WAAREEENER",
]
STOCK_NEWS_NAMES = {
    "BAJFINANCE": "Bajaj Finance",
    "TATACONSUM": "Tata Consumer Products",
    "PGEL": "PG Electroplast",
    "TITAN": "Titan Company",
    "ETERNAL": "Eternal Zomato",
    "UNITDSPR": "United Spirits",
    "HAVELLS": "Havells India",
    "NAUKRI": "Info Edge Naukri",
    "PFC": "Power Finance Corporation",
    "CAMS": "Computer Age Management Services",
    "CDSL": "Central Depository Services",
    "MAZDOCK": "Mazagon Dock Shipbuilders",
    "NUVAMA": "Nuvama Wealth Management",
    "NTPC": "NTPC",
    "WAAREEENER": "Waaree Energies",
}
STOCK_SECTORS = {
    "BAJFINANCE": "Financials",
    "PFC": "Financials",
    "CAMS": "Financials",
    "CDSL": "Financials",
    "NUVAMA": "Financials",
    "TATACONSUM": "Consumer",
    "TITAN": "Consumer",
    "ETERNAL": "Consumer",
    "UNITDSPR": "Consumer",
    "HAVELLS": "Consumer Durables",
    "PGEL": "Electronics",
    "NAUKRI": "Internet",
    "MAZDOCK": "Defence",
    "NTPC": "Power",
    "WAAREEENER": "Energy",
}
COMMODITY_ETFS = [
    {
        "key": "nasdaq",
        "label": "Motilal Oswal Nasdaq 100 ETF",
        "symbol": "MON100",
        "aliases": ["MON100"],
        "threshold": 6.0,
        "allocation": 0.50,
        "profit_target": 0.25,
        "sell_trigger": "25% profit OR RSI > 78",
    },
    {
        "key": "gold",
        "label": "Nippon India ETF Gold BeES",
        "symbol": "GOLDBEES",
        "aliases": ["GOLDBEES"],
        "threshold": 3.0,
        "allocation": 0.30,
        "profit_target": 0.22,
        "sell_trigger": "22% profit",
    },
    {
        "key": "silver",
        "label": "Nippon India Silver ETF",
        "symbol": "SILVERBEES",
        "aliases": ["SILVERBEES"],
        "threshold": 4.0,
        "allocation": 0.20,
        "profit_target": 0.20,
        "sell_trigger": "20% profit",
    },
]
COMMODITY_YEARLY_BASE_AMOUNTS = {
    2021: 10000.0,
    2022: 15000.0,
    2023: 22500.0,
    2024: 33750.0,
    2025: 50625.0,
    2026: 75938.0,
}
COMMODITY_MAX_MULTIPLIER = 2
INCOME_ROLL_TRADING_DAY_THRESHOLD = 9
INCOME_UNDERLYINGS = [
    {
        "symbol": "PFC",
        "name": "Power Finance Corporation Ltd",
        "capital": "5.2-5.5L",
        "stress": "Moderate",
        "annual_return": "18-22%",
        "notes": "Excellent wheel candidate; assignment allowed, hold shares and optionally sell covered calls later.",
    },
    {
        "symbol": "CAMS",
        "name": "Computer Age Management Services Ltd",
        "capital": "5.2-5.5L",
        "stress": "Low",
        "annual_return": "15-18%",
        "notes": "Smoother volatility, lower premium, lower stress; assignment recovery is usually smoother.",
    },
]
MONTH_CODES = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def load_local_env_files() -> None:
    for env_path in [PROJECT_ROOT / ".env", APP_ROOT / ".env"]:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.lstrip("\ufeff").strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_local_env_files()

for env_name, env_value_default in DEFAULT_KITE_ENV.items():
    os.environ.setdefault(env_name, env_value_default)
if os.environ.get("KITE_API_KEY") in BAD_KITE_API_KEYS:
    os.environ["KITE_API_KEY"] = DEFAULT_KITE_ENV["KITE_API_KEY"]


def load_app_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_app_settings(settings: dict[str, Any]) -> None:
    current = load_app_settings()
    current.update(settings)
    SETTINGS_PATH.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")


def save_env_values(values: dict[str, str], env_path: Path = APP_ROOT / ".env") -> None:
    existing: dict[str, str] = {}
    order: list[str] = []
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.lstrip("\ufeff").strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key:
                existing[key] = value.strip().strip('"').strip("'")
                order.append(key)
    for key, value in values.items():
        clean = str(value or "").strip()
        if not clean:
            continue
        existing[key] = clean
        if key not in order:
            order.append(key)
    env_text = "\n".join(f'{key}="{existing[key]}"' for key in order if key in existing)
    env_path.write_text(env_text + ("\n" if env_text else ""), encoding="utf-8")


def etf_buy_amount_setting() -> float:
    value = load_app_settings().get("etf_buy_amount", DEFAULT_ETF_BUY_AMOUNT)
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return DEFAULT_ETF_BUY_AMOUNT
    return amount if amount > 0 else DEFAULT_ETF_BUY_AMOUNT


def format_buy_amount(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = DEFAULT_ETF_BUY_AMOUNT
    if amount >= 1000 and amount % 1000 == 0:
        return f"{int(amount / 1000)}K"
    if amount.is_integer():
        return f"{int(amount)}"
    return f"{amount:.2f}"


def etf_buy_action_text(amount: Any | None = None) -> str:
    value = etf_buy_amount_setting() if amount is None else amount
    return f"Buy the ETF of amount {format_buy_amount(value)} today"


def commodity_yearly_base_amount(year: int | None = None) -> float:
    selected_year = year or datetime.now().year
    if selected_year in COMMODITY_YEARLY_BASE_AMOUNTS:
        return COMMODITY_YEARLY_BASE_AMOUNTS[selected_year]
    available_years = sorted(COMMODITY_YEARLY_BASE_AMOUNTS)
    if selected_year < available_years[0]:
        return COMMODITY_YEARLY_BASE_AMOUNTS[available_years[0]]
    return COMMODITY_YEARLY_BASE_AMOUNTS[available_years[-1]]


def commodity_daily_fall_pct(previous_close: float, current_close: float) -> float:
    if previous_close <= 0 or current_close <= 0:
        return 0.0
    return max((previous_close - current_close) / previous_close * 100, 0.0)


def commodity_dip_multiplier(
    daily_fall_pct: float,
    dip_trigger: float,
    max_multiplier: int = COMMODITY_MAX_MULTIPLIER,
) -> int:
    if dip_trigger <= 0 or daily_fall_pct < dip_trigger:
        return 0
    return min(int(math.floor(daily_fall_pct / dip_trigger)), max_multiplier)


def commodity_strategy_buy_amount(
    etf: dict[str, Any],
    daily_fall_pct: float,
    year: int | None = None,
) -> dict[str, Any]:
    base = commodity_yearly_base_amount(year)
    allocation = float(etf.get("allocation") or 0)
    trigger = float(etf.get("threshold") or 0)
    base_buy_amount = round(base * allocation)
    multiplier = commodity_dip_multiplier(daily_fall_pct, trigger)
    final_buy_amount = base_buy_amount * multiplier
    return {
        "year": year or datetime.now().year,
        "yearly_base_amount": base,
        "allocation": allocation,
        "dip_trigger": trigger,
        "daily_fall_pct": daily_fall_pct,
        "base_buy_amount": base_buy_amount,
        "multiplier": multiplier,
        "final_buy_amount": final_buy_amount,
        "buy_signal": multiplier > 0,
        "max_multiplier": COMMODITY_MAX_MULTIPLIER,
    }


def commodity_action_text(amount: Any) -> str:
    return f"Buy the ETF of amount {format_buy_amount(amount)} today"


def limit_price_one_percent_below_ltp(ltp: float) -> float:
    return max(round(ltp * 0.99, 2), 0.01)


def commodity_backtest_engine(
    price_history_by_symbol: dict[str, list[dict[str, Any]]],
    profit_target: float = 0.25,
    max_multiplier: int = COMMODITY_MAX_MULTIPLIER,
) -> dict[str, Any]:
    """Backtest ETF dip-buy baskets using allocation-adjusted multiplier sizing.

    price_history_by_symbol rows must contain date and close. Date can be a date,
    datetime, or ISO yyyy-mm-dd string. Results are intentionally plain dicts so
    CSV/JSON callers can reuse this engine.
    """
    results: dict[str, Any] = {}
    portfolio = {
        "total_capital_deployed": 0.0,
        "total_realised_profit": 0.0,
        "total_open_mtm": 0.0,
        "total_net_pnl": 0.0,
        "max_active_capital": 0.0,
        "trigger_count_by_etf": {},
        "multiplier_trigger_count_by_etf": {},
    }
    for etf in COMMODITY_ETFS:
        symbol = str(etf["symbol"])
        rows = sorted(
            price_history_by_symbol.get(symbol, []),
            key=lambda row: str(row.get("date", "")),
        )
        units = 0.0
        invested_amount = 0.0
        realised_profit = 0.0
        total_capital_deployed = 0.0
        total_buy_triggers = 0
        multiplier_buys = 0
        max_active_capital = 0.0
        peak_value = 0.0
        max_drawdown = 0.0
        previous_close: float | None = None
        last_close = 0.0
        for row in rows:
            close = float(row.get("close") or 0)
            if close <= 0:
                continue
            raw_date = row.get("date")
            if isinstance(raw_date, datetime):
                row_year = raw_date.year
            elif isinstance(raw_date, date):
                row_year = raw_date.year
            else:
                row_year = int(str(raw_date)[:4]) if str(raw_date)[:4].isdigit() else None
            if previous_close is not None:
                daily_fall = commodity_daily_fall_pct(previous_close, close)
                sizing = commodity_strategy_buy_amount(etf, daily_fall, row_year)
                multiplier = min(int(sizing["multiplier"]), max_multiplier)
                if multiplier > 0:
                    buy_amount = float(sizing["base_buy_amount"]) * multiplier
                    units += buy_amount / close
                    invested_amount += buy_amount
                    total_capital_deployed += buy_amount
                    total_buy_triggers += 1
                    if multiplier > 1:
                        multiplier_buys += 1
            current_value = units * close
            max_active_capital = max(max_active_capital, invested_amount)
            peak_value = max(peak_value, current_value)
            if peak_value > 0:
                max_drawdown = min(max_drawdown, (current_value - peak_value) / peak_value * 100)
            target = float(etf.get("profit_target") or profit_target)
            if invested_amount > 0 and current_value >= invested_amount * (1 + target):
                realised_profit += current_value - invested_amount
                units = 0.0
                invested_amount = 0.0
                peak_value = 0.0
            previous_close = close
            last_close = close
        open_market_value = units * last_close
        open_mtm = open_market_value - invested_amount
        total_pnl = realised_profit + open_mtm
        results[symbol] = {
            "total_buy_triggers": total_buy_triggers,
            "number_of_multiplier_buys": multiplier_buys,
            "total_capital_deployed": total_capital_deployed,
            "realised_profit": realised_profit,
            "open_invested_amount": invested_amount,
            "open_market_value": open_market_value,
            "open_mtm_profit_loss": open_mtm,
            "total_pnl": total_pnl,
            "max_active_capital": max_active_capital,
            "max_drawdown": max_drawdown,
        }
        portfolio["total_capital_deployed"] += total_capital_deployed
        portfolio["total_realised_profit"] += realised_profit
        portfolio["total_open_mtm"] += open_mtm
        portfolio["total_net_pnl"] += total_pnl
        portfolio["max_active_capital"] += max_active_capital
        portfolio["trigger_count_by_etf"][symbol] = total_buy_triggers
        portfolio["multiplier_trigger_count_by_etf"][symbol] = multiplier_buys
    return {"etfs": results, "portfolio": portfolio}


def read_default_csv_text() -> str:
    for path in [DEFAULT_CSV_PATH, DATA_CSV_PATH, LEGACY_CSV_PATH]:
        if path.exists():
            return path.read_text(encoding="utf-8-sig")
    return ""


def read_openai_csv_system_prompt() -> str:
    if OPENAI_CSV_PROMPT_PATH.exists():
        return OPENAI_CSV_PROMPT_PATH.read_text(encoding="utf-8-sig").strip()
    return DEFAULT_OPENAI_SYSTEM_PROMPT


def default_csv_label() -> str:
    return str(DEFAULT_CSV_PATH)


@dataclass
class PageState:
    active_tab: str = "place"
    message: str = ""
    error: str = ""
    csv_path: str = field(default_factory=lambda: str(DEFAULT_CSV_PATH))
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
    order_book: list[dict[str, Any]] | None = None
    order_book_error: str = ""
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
    gpt_api_output: str = ""
    gpt_api_response_id: str = ""
    openai_api_key: str = ""
    openai_model: str = DEFAULT_OPENAI_MODEL
    openai_system_prompt: str = field(default_factory=read_openai_csv_system_prompt)
    openai_prompt: str = DEFAULT_OPENAI_PROMPT
    analytics_symbol: str = ""
    analytics_data: dict[str, Any] | None = None
    trade_validations: list[dict[str, Any]] | None = None
    research_rows: list[dict[str, Any]] | None = None
    positions_rows: list[dict[str, Any]] | None = None
    positions_summary: dict[str, Any] | None = None
    commodity_results: list[dict[str, Any]] | None = None
    commodity_holdings: list[dict[str, Any]] | None = None
    commodity_error: str = ""
    income_rows: list[dict[str, Any]] | None = None
    income_summary: dict[str, Any] | None = None
    income_results: list[dict[str, Any]] | None = None
    income_error: str = ""
    kite_request_token: str = ""
    kite_ip_data: list[dict[str, str]] | None = None
    etf_buy_amount: float = field(default_factory=etf_buy_amount_setting)


def mask_secret(value: str | None) -> str:
    if not value:
        return "<not set>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def hash_login_password(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        AUTH_PASSWORD_SALT,
        200_000,
    ).hex()


def verify_login(username: str, password: str) -> bool:
    return username.strip() == AUTH_USERNAME and hmac.compare_digest(
        hash_login_password(password),
        AUTH_PASSWORD_HASH,
    )


def make_auth_token(username: str) -> str:
    expires = int(time.time()) + AUTH_SESSION_SECONDS
    payload = f"{username}:{expires}"
    signature = hmac.new(
        AUTH_SESSION_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode("utf-8")).decode("ascii")


def valid_auth_token(token: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, expires_text, signature = decoded.rsplit(":", 2)
        if username != AUTH_USERNAME or int(expires_text) < int(time.time()):
            return False
        payload = f"{username}:{expires_text}"
        expected = hmac.new(
            AUTH_SESSION_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


def render_login_page(error: str = "") -> bytes:
    error_html = f'<div class="login-error">{html.escape(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Income Desk Login</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: Arial, Helvetica, sans-serif;
      color: #0f172a;
      background:
        radial-gradient(circle at top left, rgba(45, 212, 191, 0.30), transparent 30%),
        linear-gradient(135deg, #eef7f6 0%, #f8fafc 48%, #ecfeff 100%);
    }}
    .login-card {{
      width: min(420px, calc(100vw - 28px));
      border: 1px solid #bde8e3;
      border-radius: 20px;
      padding: 26px;
      background: rgba(255, 255, 255, 0.94);
      box-shadow: 0 24px 70px rgba(15, 23, 42, 0.14);
    }}
    .brand {{
      display: inline-grid;
      place-items: center;
      min-width: 92px;
      height: 42px;
      padding: 0 14px;
      border-radius: 14px;
      color: #ecfeff;
      background: linear-gradient(135deg, #38bdf8, #14b8a6);
      font-size: 18px;
      font-weight: 950;
      margin-bottom: 14px;
    }}
    h1 {{ margin: 0 0 6px; color: #0f3b65; font-size: 26px; }}
    p {{ margin: 0 0 18px; color: #64748b; line-height: 1.4; }}
    label {{ display: block; margin-bottom: 12px; color: #334155; font-size: 13px; font-weight: 850; }}
    input {{
      width: 100%;
      margin-top: 6px;
      border: 1px solid #cde7e2;
      border-radius: 10px;
      padding: 12px;
      font-size: 15px;
      font-weight: 700;
      background: #f8fafc;
    }}
    button {{
      width: 100%;
      border: 0;
      border-radius: 10px;
      padding: 12px 14px;
      color: #ffffff;
      background: linear-gradient(135deg, #1769aa, #0f766e);
      font-size: 15px;
      font-weight: 950;
      cursor: pointer;
    }}
    .login-error {{
      margin-bottom: 12px;
      border: 1px solid #fecaca;
      border-radius: 10px;
      padding: 10px;
      color: #991b1b;
      background: #fee2e2;
      font-weight: 800;
    }}
  </style>
</head>
<body>
  <form class="login-card" method="post" action="/login">
    <div class="brand">विकल्प</div>
    <h1>Income Desk</h1>
    <p>Sign in to access trading, positions, income strategy, ETF actions, and Kite setup.</p>
    {error_html}
    <label>Username<input name="username" autocomplete="username" autofocus></label>
    <label>Password<input name="password" type="password" autocomplete="current-password"></label>
    <button type="submit">Log in</button>
  </form>
</body>
</html>""".encode("utf-8")


def env_value(name: str) -> str:
    return os.getenv(name, "")


def kite_setup_issue() -> str:
    if kite_orders is None:
        return f"Could not import kite_place_order.py: {IMPORT_ERROR}"
    missing = [
        name
        for name in (
            "KITE_API_KEY",
            "KITE_API_SECRET",
            "KITE_ACCESS_TOKEN",
            "KITE_CONFIRM_LIVE_ORDER",
        )
        if not env_value(name)
    ]
    if missing:
        return f"Missing Kite setup value(s): {', '.join(missing)}"
    return ""


def default_active_tab() -> str:
    return "kite-setup" if kite_setup_issue() else "place"


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
            clean_value = value.strip()
            if env_name == "KITE_API_KEY" and clean_value in BAD_KITE_API_KEYS:
                clean_value = DEFAULT_KITE_ENV["KITE_API_KEY"]
            os.environ[env_name] = clean_value
    openai_api_key = first(form, "openai_api_key")
    if openai_api_key:
        os.environ["OPENAI_API_KEY"] = openai_api_key.strip()


def kite_login_url() -> str:
    api_key = env_value("KITE_API_KEY") or DEFAULT_KITE_ENV["KITE_API_KEY"]
    return f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"


def extract_kite_request_token(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.query:
        token = first(parse_qs(parsed.query, keep_blank_values=True), "request_token")
        if token:
            return token.strip()
    if "request_token=" in text:
        token = first(parse_qs(text.split("?", 1)[-1], keep_blank_values=True), "request_token")
        if token:
            return token.strip()
    return text


def generate_kite_access_token(request_token: str) -> str:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    token = extract_kite_request_token(request_token)
    if not token:
        raise ValueError("Paste the redirected URL or request_token before generating access token.")
    api_key = env_value("KITE_API_KEY")
    api_secret = env_value("KITE_API_SECRET")
    if not api_key or not api_secret:
        raise ValueError("KITE_API_KEY and KITE_API_SECRET are required.")
    KiteConnect = kite_orders.load_kite_connect_class()
    kite = KiteConnect(api_key=api_key)
    data = kite.generate_session(token, api_secret=api_secret)
    access_token = data["access_token"]
    os.environ["KITE_ACCESS_TOKEN"] = access_token
    DEFAULT_KITE_ENV["KITE_ACCESS_TOKEN"] = access_token
    save_env_values(
        {
            "KITE_CONFIRM_LIVE_ORDER": env_value("KITE_CONFIRM_LIVE_ORDER") or "YES",
            "KITE_API_KEY": api_key,
            "KITE_API_SECRET": api_secret,
            "KITE_ACCESS_TOKEN": access_token,
        }
    )
    return access_token


def fetch_public_ip_data() -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for label, url in PUBLIC_IP_ENDPOINTS:
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "KiteTraderLocalApp/1.0",
                },
            )
            with urlopen(request, timeout=8) as response:
                text = response.read().decode("utf-8", errors="ignore").strip()
            try:
                payload = json.loads(text)
                ip_value = str(payload.get("ip") or text)
            except json.JSONDecodeError:
                ip_value = text
            results.append({"label": label, "ip": ip_value, "error": ""})
        except Exception as exc:
            results.append({"label": label, "ip": "", "error": str(exc)})
    return results


POSITIVE_NEWS_TERMS = {
    "advance",
    "approves",
    "beat",
    "beats",
    "bonus",
    "buy",
    "climb",
    "climbs",
    "dividend",
    "gain",
    "gains",
    "growth",
    "higher",
    "jumps",
    "outperform",
    "profit",
    "rally",
    "record",
    "rises",
    "surge",
    "surges",
    "upgrade",
    "upside",
    "wins",
}

NEGATIVE_NEWS_TERMS = {
    "avoid",
    "bearish",
    "concern",
    "concerns",
    "decline",
    "declines",
    "downgrade",
    "fall",
    "falls",
    "fraud",
    "lower",
    "loss",
    "miss",
    "plunge",
    "pressure",
    "probe",
    "red",
    "risk",
    "sell",
    "slips",
    "slump",
    "tumbles",
    "weak",
}


def classify_news_sentiment(title: str) -> str:
    words = set(re.findall(r"[a-z]+", title.lower()))
    positive_score = len(words & POSITIVE_NEWS_TERMS)
    negative_score = len(words & NEGATIVE_NEWS_TERMS)
    if positive_score > negative_score:
        return "positive"
    if negative_score > positive_score:
        return "negative"
    return "neutral"


def parse_news_pubdate(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def fetch_stock_news(symbols: list[str]) -> list[dict[str, str]]:
    underlyings: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        underlying = underlying_for_symbol(symbol.strip().upper())
        if underlying and underlying not in seen:
            underlyings.append(underlying)
            seen.add(underlying)

    news: list[dict[str, str]] = []
    min_published_at = datetime.now().astimezone() - timedelta(days=5)
    for underlying in underlyings[:8]:
        search_name = STOCK_NEWS_NAMES.get(underlying, underlying)
        query = quote_plus(f"{search_name} NSE stock")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            request = Request(url, headers={"User-Agent": "KiteTraderLocalApp/1.0"})
            with urlopen(request, timeout=8) as response:
                xml_text = response.read().decode("utf-8", errors="ignore")
            root = ElementTree.fromstring(xml_text)
            stock_count = 0
            for item in root.findall(".//item"):
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                published = item.findtext("pubDate") or ""
                published_at = parse_news_pubdate(published)
                if not published_at or published_at.astimezone() < min_published_at:
                    continue
                if title and link:
                    news.append(
                        {
                            "symbol": underlying,
                            "title": title,
                            "link": link,
                            "published": published,
                            "published_date": published_at.strftime("%d %b %Y"),
                            "sentiment": classify_news_sentiment(title),
                        }
                    )
                    stock_count += 1
                if stock_count >= 3:
                    break
        except Exception as exc:
            news.append(
                {
                    "symbol": underlying,
                    "title": f"Could not fetch news: {exc}",
                    "link": "",
                    "published": "",
                    "sentiment": "neutral",
                }
            )
    return news


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


def safe_csv_rows(csv_text: str) -> list[dict[str, str]]:
    try:
        return parse_csv_text(csv_text)
    except Exception:
        return []


def is_web_csv_source(value: str) -> bool:
    return value.strip().lower().startswith(("http://", "https://"))


def google_sheet_csv_export_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.netloc not in {"docs.google.com", "www.docs.google.com"}:
        return url.strip()
    match = re.search(r"/spreadsheets/d/([^/]+)", parsed.path)
    if not match:
        return url.strip()
    sheet_id = match.group(1)
    gid = parse_qs(parsed.query).get("gid", ["0"])[0]
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def fetch_csv_text_from_url(url: str) -> str:
    csv_url = google_sheet_csv_export_url(url)
    request = Request(csv_url, headers={"User-Agent": "KiteTraderLocalApp/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            text = response.read().decode("utf-8-sig", errors="ignore")
    except HTTPError as exc:
        raise RuntimeError(
            f"Could not load CSV from URL. HTTP {exc.code}. "
            "For Google Sheets, set sharing to anyone with the link can view."
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Could not load CSV from URL: {exc}") from exc
    parse_csv_text(text)
    return text


def csv_trading_symbols(csv_text: str) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for row in safe_csv_rows(csv_text):
        symbol = (row.get("tradingsymbol") or row.get("symbol") or "").strip().upper()
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols


def option_symbol_parts(symbol: str) -> dict[str, Any] | None:
    match = re.match(
        r"^(?P<underlying>[A-Z0-9-]+?)(?P<yy>\d{2})(?P<mon>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(?P<strike>\d+(?:\.\d+)?)(?P<type>CE|PE)$",
        symbol.upper(),
    )
    if not match:
        return None
    data = match.groupdict()
    year = 2000 + int(data["yy"])
    month = MONTH_CODES[data["mon"]]
    return {
        "underlying": data["underlying"],
        "year": year,
        "month": month,
        "month_code": data["mon"],
        "strike": data["strike"],
        "option_type": data["type"],
    }


def underlying_for_symbol(symbol: str) -> str:
    parts = option_symbol_parts(symbol)
    return parts["underlying"] if parts else symbol.upper()


def last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def expiry_date_for_parts(parts: dict[str, Any]) -> date:
    switch_date = date(2025, 9, 1)
    contract_month = date(parts["year"], parts["month"], 1)
    weekday = 1 if contract_month >= switch_date else 3
    return last_weekday_of_month(parts["year"], parts["month"], weekday)


def trading_days_remaining(expiry: date, today: date | None = None) -> int:
    today = today or datetime.now().date()
    if expiry <= today:
        return 0
    days = 0
    current = today + timedelta(days=1)
    while current <= expiry:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days


def expiry_summaries(symbols: list[str]) -> list[dict[str, Any]]:
    summaries: dict[date, dict[str, Any]] = {}
    for symbol in symbols:
        parts = option_symbol_parts(symbol)
        if not parts:
            continue
        expiry = expiry_date_for_parts(parts)
        summary = summaries.setdefault(
            expiry,
            {
                "expiry": expiry,
                "month": expiry.strftime("%b %Y").upper(),
                "day": expiry.strftime("%A, %d %b %Y"),
                "trading_days": trading_days_remaining(expiry),
                "symbols": [],
            },
        )
        summary["symbols"].append(symbol)
    return [summaries[key] for key in sorted(summaries)]


def normal_cdf(value: float) -> float:
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2 * math.pi)


def bs_d1(spot: float, strike: float, years: float, rate: float, iv: float) -> float:
    return (math.log(spot / strike) + (rate + 0.5 * iv * iv) * years) / (
        iv * math.sqrt(years)
    )


def bs_price(spot: float, strike: float, years: float, rate: float, iv: float, option_type: str) -> float:
    if years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    d1 = bs_d1(spot, strike, years, rate, iv)
    d2 = d1 - iv * math.sqrt(years)
    if option_type == "CE":
        return spot * normal_cdf(d1) - strike * math.exp(-rate * years) * normal_cdf(d2)
    return strike * math.exp(-rate * years) * normal_cdf(-d2) - spot * normal_cdf(-d1)


def bs_greeks(spot: float, strike: float, years: float, rate: float, iv: float, option_type: str) -> dict[str, float]:
    if years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    d1 = bs_d1(spot, strike, years, rate, iv)
    d2 = d1 - iv * math.sqrt(years)
    delta = normal_cdf(d1) if option_type == "CE" else normal_cdf(d1) - 1
    gamma = normal_pdf(d1) / (spot * iv * math.sqrt(years))
    vega = spot * normal_pdf(d1) * math.sqrt(years) / 100
    if option_type == "CE":
        theta = (
            -(spot * normal_pdf(d1) * iv) / (2 * math.sqrt(years))
            - rate * strike * math.exp(-rate * years) * normal_cdf(d2)
        ) / 365
    else:
        theta = (
            -(spot * normal_pdf(d1) * iv) / (2 * math.sqrt(years))
            + rate * strike * math.exp(-rate * years) * normal_cdf(-d2)
        ) / 365
    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def implied_volatility(
    option_price: float,
    spot: float,
    strike: float,
    years: float,
    rate: float,
    option_type: str,
) -> float | None:
    if option_price <= 0 or spot <= 0 or strike <= 0 or years <= 0:
        return None
    low = 0.0001
    high = 5.0
    for _ in range(80):
        mid = (low + high) / 2
        price = bs_price(spot, strike, years, rate, mid, option_type)
        if abs(price - option_price) < 0.0001:
            return mid
        if price > option_price:
            high = mid
        else:
            low = mid
    return (low + high) / 2


def quote_ltp(quote: dict[str, Any]) -> float:
    return float(quote.get("last_price") or 0)


def quote_oi(quote: dict[str, Any]) -> int:
    return int(quote.get("oi") or 0)


def option_analytics_for_symbol(symbol: str) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    symbol = symbol.strip().upper()
    parts = option_symbol_parts(symbol)
    if not parts:
        raise ValueError(f"Could not parse option symbol: {symbol}")

    kite = kite_orders.kite_client()
    expiry = expiry_date_for_parts(parts)
    today = datetime.now().date()
    dte = max((expiry - today).days, 0)
    years = max(dte / 365, 1 / 365)
    rate = 0.065
    strike = float(parts["strike"])
    option_key = f"NFO:{symbol}"
    spot_key = f"NSE:{parts['underlying']}"
    quotes = kite.quote([option_key, spot_key])
    option_quote = quotes.get(option_key, {})
    spot_quote = quotes.get(spot_key, {})
    option_price = quote_ltp(option_quote)
    spot = quote_ltp(spot_quote)
    iv = implied_volatility(option_price, spot, strike, years, rate, parts["option_type"])
    greeks = bs_greeks(spot, strike, years, rate, iv or 0, parts["option_type"])
    expected_move = spot * (iv or 0) * math.sqrt(dte / 365) if dte > 0 else 0
    buy_pop = abs(greeks["delta"])
    sell_pop = max(0.0, min(1.0, 1 - abs(greeks["delta"])))
    chain = option_chain_analytics(kite, parts, spot)
    data = {
        "symbol": symbol,
        "underlying": parts["underlying"],
        "option_type": parts["option_type"],
        "strike": strike,
        "expiry": expiry.strftime("%d %b %Y"),
        "dte": dte,
        "spot": spot,
        "option_price": option_price,
        "oi": quote_oi(option_quote),
        "rate": rate,
        "iv": iv,
        "iv_percent": (iv * 100) if iv is not None else None,
        "delta": greeks["delta"],
        "gamma": greeks["gamma"],
        "theta": greeks["theta"],
        "vega": greeks["vega"],
        "buy_pop": buy_pop * 100,
        "sell_pop": sell_pop * 100,
        "expected_move": expected_move,
        "pcr": chain.get("pcr"),
        "max_pain": chain.get("max_pain"),
        "support": chain.get("support"),
        "resistance": chain.get("resistance"),
        "chain_rows": chain.get("rows", 0),
        "iv_rank": "Requires historical IV database",
        "iv_percentile": "Requires historical IV database",
    }
    data["decision"] = option_decision_metrics(data)
    return data


def option_decision_metrics(data: dict[str, Any]) -> dict[str, Any]:
    spot = float(data.get("spot") or 0)
    strike = float(data.get("strike") or 0)
    option_price = float(data.get("option_price") or 0)
    option_type = str(data.get("option_type") or "").upper()
    delta = float(data.get("delta") or 0)
    sell_pop = float(data.get("sell_pop") or 0)
    buy_pop = float(data.get("buy_pop") or 0)
    expected_move = float(data.get("expected_move") or 0)
    theta = float(data.get("theta") or 0)
    gamma = float(data.get("gamma") or 0)
    vega = float(data.get("vega") or 0)
    support = data.get("support")
    resistance = data.get("resistance")
    upper_range = spot + expected_move
    lower_range = max(spot - expected_move, 0)
    otm_distance = ((strike - spot) / spot * 100) if option_type == "CE" and spot else None
    if option_type == "PE" and spot:
        otm_distance = ((spot - strike) / spot * 100)

    def near(value: Any, target: float, tolerance: float = 0.01) -> bool:
        try:
            return abs(float(value) - target) <= tolerance
        except (TypeError, ValueError):
            return False

    is_ce = option_type == "CE"
    is_pe = option_type == "PE"
    ce_sell_fit = (
        is_ce
        and delta < 0.15
        and sell_pop >= 75
        and strike >= upper_range
        and near(resistance, strike)
    )
    pe_sell_fit = (
        is_pe
        and delta > -0.20
        and sell_pop >= 75
        and strike <= lower_range
        and near(support, strike)
    )
    ce_buy_fit = is_ce and 0.35 <= delta <= 0.60 and buy_pop >= 35 and spot > strike
    pe_buy_fit = is_pe and -0.60 <= delta <= -0.35 and buy_pop >= 35 and spot < strike

    support_text = fmt_number(support) if support is not None else "support"
    resistance_text = fmt_number(resistance) if resistance is not None else "resistance"
    risk_lights = option_risk_lights(data)
    if is_ce:
        sell_call = "SELL_CALL_COVERED_ONLY" if ce_sell_fit else "SELL_CALL_CHECK_COVERAGE"
        buy_call = "BUY_CALL_AVOID" if not ce_buy_fit else "BUY_CALL_POSSIBLE_BREAKOUT"
        sell_put = "SELL_PUT_NEED_PE_CHAIN"
        buy_put = f"BUY_PUT_ONLY_IF_{support_text}_BREAKDOWN"
    elif is_pe:
        sell_call = "SELL_CALL_NEED_CE_CHAIN"
        buy_call = f"BUY_CALL_ONLY_IF_{resistance_text}_BREAKOUT"
        sell_put = "SELL_PUT_CASH_SECURED_ONLY" if pe_sell_fit else "SELL_PUT_CHECK_CASH_AND_SUPPORT"
        buy_put = "BUY_PUT_POSSIBLE_BREAKDOWN" if pe_buy_fit else "BUY_PUT_AVOID"
    else:
        sell_call = "UNKNOWN"
        buy_call = "UNKNOWN"
        sell_put = "UNKNOWN"
        buy_put = "UNKNOWN"

    rows = [
        {
            "indicator": "Delta",
            "sell_call": "Good" if is_ce and delta < 0.15 else "Needs CE delta < 0.15",
            "buy_call": "Good" if is_ce and 0.35 <= delta <= 0.60 else "Needs CE delta 0.35-0.60",
            "sell_put": "Use PE delta > -0.20",
            "buy_put": "Use PE delta -0.35 to -0.60",
        },
        {
            "indicator": "POP",
            "sell_call": "Good" if is_ce and sell_pop > 75 else "Needs Sell POP > 75%",
            "buy_call": "Weak" if is_ce and buy_pop < 35 else "Buy POP improving",
            "sell_put": "Needs PE Sell POP > 75%",
            "buy_put": "Buy POP improving",
        },
        {
            "indicator": "Expected move",
            "sell_call": "Good" if is_ce and strike > upper_range else "Strike should be above upper range",
            "buy_call": "Needs spot above upper range",
            "sell_put": "PE strike should be below lower range",
            "buy_put": "Needs spot below lower range",
        },
        {
            "indicator": "OI",
            "sell_call": "Good" if is_ce and near(resistance, strike) else "Prefer CE strike at resistance",
            "buy_call": "Needs resistance broken",
            "sell_put": "Prefer PE strike at support",
            "buy_put": "Needs support broken",
        },
        {
            "indicator": "Trend",
            "sell_call": "Sideways / sell-on-rise preferred",
            "buy_call": "Needs strong breakout",
            "sell_put": "Buy-on-dips preferred",
            "buy_put": "Needs breakdown",
        },
        {
            "indicator": "VWAP / EMA",
            "sell_call": "Requires intraday candle data",
            "buy_call": "Requires above VWAP + 20 EMA",
            "sell_put": "Requires holding VWAP/support",
            "buy_put": "Requires below VWAP + lower highs",
        },
        {
            "indicator": "Theta",
            "sell_call": "Positive for seller",
            "buy_call": "Negative for buyer",
            "sell_put": "Positive for seller",
            "buy_put": "Negative for buyer",
        },
        {
            "indicator": "Coverage",
            "sell_call": "Shares available required",
            "buy_call": "Premium risk only",
            "sell_put": "Cash available required",
            "buy_put": "Premium risk only",
        },
    ]
    return {
        "sell_call": sell_call,
        "buy_call": buy_call,
        "sell_put": sell_put,
        "buy_put": buy_put,
        "otm_distance": otm_distance,
        "upper_range": upper_range,
        "lower_range": lower_range,
        "breakeven": strike + option_price if is_ce else strike - option_price,
        "risk_lights": risk_lights,
        "summary": rows,
    }


def color_for_signal(signal: str) -> str:
    if signal.startswith("GREEN"):
        return "green"
    if signal.startswith("YELLOW"):
        return "yellow"
    if signal.startswith("RED"):
        return "red"
    return "neutral"


def color_otm(otm_pct: float | None) -> str:
    if otm_pct is None:
        return "neutral"
    if otm_pct >= 10:
        return "lightgreen"
    if otm_pct >= 7:
        return "yellow"
    if otm_pct >= 5:
        return "orange"
    return "lightcoral"


def color_iv(iv_pct: float | None, event_risk: bool = False) -> str:
    if iv_pct is None:
        return "neutral"
    if event_risk:
        return "lightcoral"
    if 15 <= iv_pct <= 35:
        return "lightgreen"
    if 35 < iv_pct <= 50 or iv_pct < 12:
        return "yellow"
    if 50 < iv_pct <= 65:
        return "orange"
    return "lightcoral"


def color_sell_pop(pop_pct: float | None) -> str:
    if pop_pct is None:
        return "neutral"
    if pop_pct >= 80:
        return "lightgreen"
    if pop_pct >= 70:
        return "yellow"
    return "lightcoral"


def color_pcr_for_sell_call(pcr: float | None) -> str:
    if pcr is None:
        return "neutral"
    if pcr < 0.60:
        return "lightgreen"
    if pcr <= 1.00:
        return "yellow"
    return "lightcoral"


def color_pcr_for_sell_put(pcr: float | None) -> str:
    if pcr is None:
        return "neutral"
    if pcr > 0.80:
        return "lightgreen"
    if pcr >= 0.60:
        return "yellow"
    return "lightcoral"


def strike_oi_color(option_type: str, strike: float, support: Any, resistance: Any) -> tuple[str, str]:
    try:
        support_value = float(support)
    except (TypeError, ValueError):
        support_value = None
    try:
        resistance_value = float(resistance)
    except (TypeError, ValueError):
        resistance_value = None
    if option_type == "CE":
        if resistance_value is None:
            return "neutral", "Resistance unavailable"
        if abs(strike - resistance_value) <= 0.01:
            return "lightgreen", "CE strike is at OI resistance"
        if strike < resistance_value:
            return "yellow", "CE strike below resistance"
        return "orange", "CE strike above resistance; check liquidity"
    if option_type == "PE":
        if support_value is None:
            return "neutral", "Support unavailable"
        if abs(strike - support_value) <= 0.01:
            return "lightgreen", "PE strike is at OI support"
        if strike < support_value:
            return "lightgreen", "PE strike below support"
        return "lightcoral", "PE strike above/broken support"
    return "neutral", "Unknown option type"


def strategy_strength_lights(data: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    option_type = str(data.get("option_type") or "").upper()
    strike = float(data.get("strike") or 0)
    otm_pct = decision.get("otm_distance")
    iv_pct = data.get("iv_percent")
    sell_pop = data.get("sell_pop")
    pcr = data.get("pcr")
    pcr_color = (
        color_pcr_for_sell_call(pcr)
        if option_type == "CE"
        else color_pcr_for_sell_put(pcr)
        if option_type == "PE"
        else "neutral"
    )
    oi_color, oi_note = strike_oi_color(
        option_type, strike, data.get("support"), data.get("resistance")
    )
    rows = [
        (
            "OTM distance",
            f"{fmt_number(otm_pct)}%",
            color_otm(otm_pct),
            "Great when >= 10%; avoid when < 5%",
        ),
        (
            "Implied Volatility",
            f"{fmt_number(iv_pct)}%",
            color_iv(iv_pct),
            "15-35% calm; 35-50% premium good; >65% avoid/event risk",
        ),
        (
            "SELL Probability of Profit",
            f"{fmt_number(sell_pop)}%",
            color_sell_pop(sell_pop),
            ">= 80% is preferred for selling",
        ),
        (
            "PCR",
            fmt_number(pcr),
            pcr_color,
            "SELL CALL prefers PCR < 0.60; SELL PUT prefers PCR > 0.80",
        ),
        (
            "Strike vs OI",
            f"Support {fmt_number(data.get('support'))} / Resistance {fmt_number(data.get('resistance'))}",
            oi_color,
            oi_note,
        ),
    ]
    green_count = sum(1 for row in rows[:4] if row[2] == "lightgreen")
    yellow_count = sum(1 for row in rows[:4] if row[2] == "yellow")
    red_count = sum(1 for row in rows[:4] if row[2] == "lightcoral")
    if red_count:
        final = "RED_AVOID"
        color = "lightcoral"
    elif green_count >= 3 and yellow_count <= 1:
        final = "GREEN_SELL_CALL" if option_type == "CE" else "GREEN_SELL_PUT"
        color = "lightgreen"
    elif green_count >= 2:
        final = "YELLOW_REDUCE_SIZE_OR_WAIT"
        color = "yellow"
    else:
        final = "ORANGE_RISKY_RECHECK"
        color = "orange"
    if option_type == "PE" and pcr_color == "lightcoral":
        final = "RED_AVOID_SELL_PUT_PCR_WEAK"
        color = "lightcoral"
    return {"rows": rows, "final": final, "color": color}


def strength_label(color: str, text: str) -> str:
    return f"{color.upper()}: {text}"


def sell_call_signal(
    delta: float,
    pop_sell: float,
    theta: float,
    vega: float,
    gamma: float,
    spot: float,
    ltp: float,
    is_covered: bool,
    is_breakout: bool,
) -> str:
    if ltp <= 0:
        return "RED_AVOID_SELL_CALL"
    delta_abs = abs(delta)
    seller_theta = -theta
    theta_yield_pct = seller_theta / ltp * 100
    vega_risk_pct = vega / ltp * 100
    gamma_1pct = gamma * spot * 0.01
    if not is_covered:
        return "RED_NAKED_CE_NOT_ALLOWED"
    if is_breakout:
        return "RED_AVOID_CALL_SELL"
    green = (
        0.05 <= delta_abs <= 0.15
        and pop_sell >= 80
        and theta_yield_pct >= 5
        and gamma_1pct <= 0.03
        and vega_risk_pct <= 10
    )
    yellow = (
        0.15 < delta_abs <= 0.25
        or 70 <= pop_sell < 80
        or 0.03 < gamma_1pct <= 0.06
        or 10 < vega_risk_pct <= 15
    )
    if green:
        return "GREEN_SELL_CALL_COVERED"
    if yellow:
        return "YELLOW_SELL_CALL_SMALL_SIZE"
    return "RED_AVOID_SELL_CALL"


def sell_put_signal(
    delta: float,
    pop_sell: float,
    theta: float,
    vega: float,
    gamma: float,
    spot: float,
    ltp: float,
    is_cash_secured: bool,
    is_breakdown: bool,
) -> str:
    if ltp <= 0:
        return "RED_AVOID_SELL_PUT"
    delta_abs = abs(delta)
    seller_theta = -theta
    theta_yield_pct = seller_theta / ltp * 100
    vega_risk_pct = vega / ltp * 100
    gamma_1pct = gamma * spot * 0.01
    if not is_cash_secured:
        return "RED_NOT_CASH_SECURED"
    if is_breakdown:
        return "RED_AVOID_PUT_SELL"
    green = (
        0.10 <= delta_abs <= 0.20
        and pop_sell >= 80
        and theta_yield_pct >= 5
        and gamma_1pct <= 0.03
        and vega_risk_pct <= 10
    )
    yellow = (
        0.20 < delta_abs <= 0.30
        or 70 <= pop_sell < 80
        or 0.03 < gamma_1pct <= 0.06
        or 10 < vega_risk_pct <= 15
    )
    if green:
        return "GREEN_SELL_PUT_CASH_SECURED"
    if yellow:
        return "YELLOW_SELL_PUT_SMALL_SIZE"
    return "RED_AVOID_SELL_PUT"


def option_risk_lights(data: dict[str, Any]) -> dict[str, Any]:
    option_type = str(data.get("option_type") or "").upper()
    delta = float(data.get("delta") or 0)
    delta_abs = abs(delta)
    pop_sell = float(data.get("sell_pop") or 0)
    theta = float(data.get("theta") or 0)
    gamma = float(data.get("gamma") or 0)
    vega = float(data.get("vega") or 0)
    spot = float(data.get("spot") or 0)
    ltp = float(data.get("option_price") or 0)
    seller_delta = -delta
    seller_gamma = -gamma
    seller_theta = -theta
    seller_vega = -vega
    theta_yield_pct = seller_theta / ltp * 100 if ltp > 0 else 0
    vega_risk_pct = vega / ltp * 100 if ltp > 0 else 0
    gamma_1pct = gamma * spot * 0.01
    is_ce = option_type == "CE"
    is_pe = option_type == "PE"
    if is_ce:
        if 0.05 <= delta_abs <= 0.15:
            delta_light = ("green", "Green for SELL CALL")
        elif 0.15 < delta_abs <= 0.25:
            delta_light = ("yellow", "Yellow for SELL CALL")
        else:
            delta_light = ("red", "Red for SELL CALL")
    else:
        if 0.10 <= delta_abs <= 0.20:
            delta_light = ("green", "Green for SELL PUT")
        elif 0.20 < delta_abs <= 0.30:
            delta_light = ("yellow", "Yellow for SELL PUT")
        else:
            delta_light = ("red", "Red for SELL PUT")
    if pop_sell > 80:
        pop_light = ("green", "Sell POP above 80%")
    elif 70 <= pop_sell <= 80:
        pop_light = ("yellow", "Sell POP 70-80%")
    else:
        pop_light = ("red", "Sell POP below 70%")
    if gamma_1pct <= 0.03:
        gamma_light = ("green", "Low gamma risk")
    elif gamma_1pct <= 0.06:
        gamma_light = ("yellow", "Medium gamma risk")
    else:
        gamma_light = ("red", "High gamma risk")
    if theta_yield_pct > 5:
        theta_light = ("green", "Theta yield above 5% premium/day")
    elif theta_yield_pct >= 2:
        theta_light = ("yellow", "Theta yield 2-5% premium/day")
    else:
        theta_light = ("red", "Theta yield below 2% premium/day")
    if vega_risk_pct < 5:
        vega_light = ("green", "Low IV spike risk")
    elif vega_risk_pct <= 10:
        vega_light = ("yellow", "Moderate IV spike risk")
    else:
        vega_light = ("red", "High IV spike risk")
    final_sell = (
        sell_call_signal(delta, pop_sell, theta, vega, gamma, spot, ltp, True, False)
        if is_ce
        else sell_put_signal(delta, pop_sell, theta, vega, gamma, spot, ltp, True, False)
    )
    buy_signal = "RED_BUY_CALL_LOW_POP" if is_ce else "RED_BUY_PUT_NEEDS_BREAKDOWN"
    return {
        "seller_delta": seller_delta,
        "seller_gamma": seller_gamma,
        "seller_theta": seller_theta,
        "seller_vega": seller_vega,
        "theta_yield_pct": theta_yield_pct,
        "vega_risk_pct": vega_risk_pct,
        "gamma_1pct": gamma_1pct,
        "final_sell": final_sell,
        "final_sell_color": color_for_signal(final_sell),
        "buy_signal": buy_signal,
        "buy_signal_color": color_for_signal(buy_signal),
        "naked_ce_signal": "RED_NAKED_CE_NOT_ALLOWED" if is_ce else "N/A",
        "cash_rule": "Cash backing 90%+ required for CSP" if is_pe else "N/A",
        "rows": [
            ("Delta / POP", delta_abs, delta_light[0], delta_light[1]),
            ("SELL POP", pop_sell, pop_light[0], pop_light[1]),
            ("Gamma 1% move risk", gamma_1pct, gamma_light[0], gamma_light[1]),
            ("Theta / premium / day", theta_yield_pct, theta_light[0], theta_light[1]),
            ("Vega / premium", vega_risk_pct, vega_light[0], vega_light[1]),
            (
                "Coverage / cash backing",
                "Required",
                "green",
                "Covered CALL required" if is_ce else "90%+ cash ready required",
            ),
        ],
    }


def option_chain_analytics(kite: Any, parts: dict[str, Any], spot: float) -> dict[str, Any]:
    instruments = [
        item
        for item in kite.instruments("NFO")
        if str(item.get("name", "")).upper() == parts["underlying"]
        and str(item.get("instrument_type", "")).upper() in {"CE", "PE"}
        and item.get("expiry") == expiry_date_for_parts(parts)
    ]
    if not instruments:
        return {}

    keys = [f"NFO:{item['tradingsymbol']}" for item in instruments]
    quotes: dict[str, Any] = {}
    for index in range(0, len(keys), 400):
        quotes.update(kite.quote(keys[index : index + 400]))

    by_strike: dict[float, dict[str, int]] = {}
    for item in instruments:
        strike = float(item.get("strike") or 0)
        option_type = str(item.get("instrument_type", "")).upper()
        key = f"NFO:{item['tradingsymbol']}"
        by_strike.setdefault(strike, {"CE": 0, "PE": 0})[option_type] += quote_oi(
            quotes.get(key, {})
        )

    total_pe_oi = sum(row["PE"] for row in by_strike.values())
    total_ce_oi = sum(row["CE"] for row in by_strike.values())
    pcr = (total_pe_oi / total_ce_oi) if total_ce_oi else None
    support = max(by_strike.items(), key=lambda item: item[1]["PE"])[0] if by_strike else None
    resistance = max(by_strike.items(), key=lambda item: item[1]["CE"])[0] if by_strike else None
    max_pain = None
    min_pain = None
    for test_strike in by_strike:
        pain = 0.0
        for strike, oi in by_strike.items():
            pain += max(test_strike - strike, 0) * oi["CE"]
            pain += max(strike - test_strike, 0) * oi["PE"]
        if min_pain is None or pain < min_pain:
            min_pain = pain
            max_pain = test_strike
    return {
        "pcr": pcr,
        "support": support,
        "resistance": resistance,
        "max_pain": max_pain,
        "rows": len(by_strike),
    }


def open_option_positions() -> list[dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    positions = kite.positions().get("net", [])
    active: list[dict[str, Any]] = []
    for position in positions:
        quantity = int(position.get("quantity") or 0)
        symbol = str(position.get("tradingsymbol") or "").upper()
        if quantity == 0 or not option_symbol_parts(symbol):
            continue
        active.append(
            {
                "exchange": str(position.get("exchange") or ""),
                "tradingsymbol": symbol,
                "quantity": quantity,
                "product": str(position.get("product") or ""),
                "average_price": float(position.get("average_price") or 0),
                "ltp": float(position.get("last_price") or position.get("ltp") or 0),
                "pnl": float(position.get("pnl") or 0),
            }
        )
    return active


def active_position_underlyings() -> set[str]:
    if kite_orders is None:
        return set()
    try:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            kite = kite_orders.kite_client()
            positions = kite.positions().get("net", [])
    except Exception:
        return set()
    active: set[str] = set()
    for position in positions:
        try:
            quantity = int(float(position.get("quantity") or 0))
        except (TypeError, ValueError):
            quantity = 0
        if quantity == 0:
            continue
        symbol = str(position.get("tradingsymbol") or "").strip().upper()
        if not symbol:
            continue
        active.add(symbol)
        active.add(underlying_for_symbol(symbol))
    return {item for item in active if item}


EVENT_RISK_TERMS = {
    "board",
    "bonus",
    "budget",
    "dividend",
    "earnings",
    "merger",
    "policy",
    "rbi",
    "record",
    "result",
    "results",
    "split",
}


def validation_status_class(status: str) -> str:
    clean = status.lower()
    if clean.startswith("green"):
        return "validation-green"
    if clean.startswith("red"):
        return "validation-red"
    if clean.startswith("yellow"):
        return "validation-yellow"
    return "validation-neutral"


def validation_score(status: str) -> float:
    clean = status.lower()
    if clean.startswith("green"):
        return 1.0
    if clean.startswith("yellow"):
        return 0.5
    if clean.startswith("red"):
        return 0.0
    return 0.25


def event_risk_check(symbol: str, news_cache: dict[str, list[dict[str, str]]]) -> tuple[str, str]:
    underlying = underlying_for_symbol(symbol)
    if not underlying:
        return "YELLOW", "Could not detect underlying for event/news check."
    if underlying not in news_cache:
        try:
            news_cache[underlying] = fetch_stock_news([symbol])
        except Exception as exc:
            news_cache[underlying] = [
                {"title": f"News check failed: {exc}", "sentiment": "neutral"}
            ]
    titles = [str(item.get("title") or "") for item in news_cache.get(underlying, [])]
    if not titles:
        return "GREEN", "No recent 5-day news found by the app."
    matched = [
        title
        for title in titles
        if set(re.findall(r"[a-z]+", title.lower())) & EVENT_RISK_TERMS
    ]
    if matched:
        return "RED", f"Recent event/news keyword found: {matched[0][:120]}"
    negative = [title for title in titles if classify_news_sentiment(title) == "negative"]
    if negative:
        return "YELLOW", f"Recent negative headline found: {negative[0][:120]}"
    return "GREEN", "No event-risk keyword found in recent 5-day news."


def trade_validation_for_order(
    order: dict[str, Any], news_cache: dict[str, list[dict[str, str]]]
) -> dict[str, Any]:
    symbol = str(order.get("tradingsymbol") or "").strip().upper()
    transaction_type = str(order.get("transaction_type") or "").strip().upper()
    quantity = abs(int(float(order.get("quantity") or 0)))
    checks: list[dict[str, str]] = []
    try:
        data = option_analytics_for_symbol(symbol)
        decision = data.get("decision", {})
        risk_lights = decision.get("risk_lights", {})
        option_type = str(data.get("option_type") or "").upper()
        underlying = str(data.get("underlying") or underlying_for_symbol(symbol) or "")
        spot = float(data.get("spot") or 0)
        strike = float(data.get("strike") or 0)
        option_price = float(data.get("option_price") or 0)
        sell_pop = float(data.get("sell_pop") or 0)
        delta_abs = abs(float(data.get("delta") or 0))
        dte = int(data.get("dte") or 0)
        otm_distance = decision.get("otm_distance")
        upper_range = float(decision.get("upper_range") or 0)
        lower_range = float(decision.get("lower_range") or 0)
        pcr = data.get("pcr")
        is_sell = transaction_type == "SELL"
        side = (
            "SELL CALL"
            if is_sell and option_type == "CE"
            else "SELL PUT"
            if is_sell and option_type == "PE"
            else f"{transaction_type} {option_type}".strip()
        )
        max_profit = option_price * quantity if is_sell else None

        quality_status = "GREEN" if underlying in TOP_WATCHLIST else "YELLOW"
        quality_detail = (
            "Underlying is in the app watchlist; still confirm you are happy to hold 6-24 months."
            if quality_status == "GREEN"
            else "Manual quality check needed: avoid weak stock chosen only for premium."
        )
        checks.append(
            {
                "point": "Underlying quality",
                "status": quality_status,
                "detail": quality_detail,
            }
        )

        event_status, event_detail = event_risk_check(symbol, news_cache)
        checks.append({"point": "Event risk", "status": event_status, "detail": event_detail})

        if option_type == "CE":
            if pcr is not None and float(pcr) < 0.60:
                trend_status = "GREEN"
                trend_detail = "PCR shows call-writing/resistance setup; better for covered CALL selling."
            elif pcr is not None and float(pcr) > 1.00:
                trend_status = "RED"
                trend_detail = "PCR is bullish/supportive; avoid aggressive CALL selling in possible breakout."
            else:
                trend_status = "YELLOW"
                trend_detail = "Trend is neutral; use smaller size and check price action."
        elif option_type == "PE":
            if pcr is not None and float(pcr) > 0.80:
                trend_status = "GREEN"
                trend_detail = "PCR shows put-writing/support setup; better for cash-secured PUT selling."
            elif pcr is not None and float(pcr) < 0.40:
                trend_status = "RED"
                trend_detail = "PCR is weak/bearish; avoid PUT selling into a falling setup."
            else:
                trend_status = "YELLOW"
                trend_detail = "Trend is neutral; wait for support or reduce size."
        else:
            trend_status = "YELLOW"
            trend_detail = "Trend check needs CE/PE option type."
        checks.append({"point": "Trend structure", "status": trend_status, "detail": trend_detail})

        if otm_distance is None:
            distance_status = "YELLOW"
            distance_detail = "Could not calculate OTM distance."
        elif float(otm_distance) >= 10:
            distance_status = "GREEN"
            distance_detail = f"OTM distance {float(otm_distance):.2f}% gives buffer beyond support/resistance."
        elif float(otm_distance) >= 7:
            distance_status = "YELLOW"
            distance_detail = f"OTM distance {float(otm_distance):.2f}% is acceptable but not wide."
        else:
            distance_status = "RED"
            distance_detail = f"OTM distance {float(otm_distance):.2f}% is close; premium may not justify risk."
        checks.append({"point": "Strike distance", "status": distance_status, "detail": distance_detail})

        if 0.10 <= delta_abs <= 0.25 and sell_pop >= 75:
            delta_status = "GREEN"
        elif delta_abs <= 0.30 and sell_pop >= 70:
            delta_status = "YELLOW"
        else:
            delta_status = "RED"
        checks.append(
            {
                "point": "Delta / POP",
                "status": delta_status,
                "detail": f"Delta {delta_abs:.2f}; SELL POP {sell_pop:.2f}%. Target delta 0.10-0.25 and POP above 75-80%.",
            }
        )

        assignment_capital = strike * quantity
        if option_type == "CE":
            margin_status = "YELLOW"
            margin_detail = f"Covered CALL needs shares ready for delivery/opportunity cost. Quantity {quantity}; strike value about {assignment_capital:.0f}."
        elif option_type == "PE":
            margin_status = "YELLOW"
            margin_detail = f"Cash-secured PUT needs assignment cash. Quantity {quantity}; assignment value about {assignment_capital:.0f}."
        else:
            margin_status = "YELLOW"
            margin_detail = "Margin/assignment check needs option type."
        checks.append(
            {"point": "Margin + assignment readiness", "status": margin_status, "detail": margin_detail}
        )

        theta_yield = float(risk_lights.get("theta_yield_pct") or 0)
        if dte <= 5:
            exit_status = "RED"
            exit_detail = f"{dte} DTE is close to expiry; define exit/roll before entry."
        elif theta_yield >= 5:
            exit_status = "GREEN"
            exit_detail = f"Theta yield {theta_yield:.2f}%/day supports predefined 50-60% profit exit or roll-if-tested rule."
        else:
            exit_status = "YELLOW"
            exit_detail = f"Theta yield {theta_yield:.2f}%/day is modest; confirm exit/roll rule before entry."
        checks.append({"point": "Exit / roll rule before entry", "status": exit_status, "detail": exit_detail})

        score = sum(validation_score(check["status"]) for check in checks)
        overall = "GREEN" if score >= 5.5 else "YELLOW" if score >= 3.5 else "RED"
        if option_type == "CE":
            impact = (
                f"Spot {spot:.2f}; strike {strike:.2f}; expected upper range {upper_range:.2f}. "
                f"CALL risk rises if stock moves up toward/above strike; covered shares cap upside."
            )
        elif option_type == "PE":
            impact = (
                f"Spot {spot:.2f}; strike {strike:.2f}; expected lower range {lower_range:.2f}. "
                f"PUT risk rises if stock falls toward/below strike; assignment can require cash."
            )
        else:
            impact = "Could not calculate stock-price impact."
        return {
            "symbol": symbol,
            "side": side,
            "overall": overall,
            "score": score,
            "max_score": len(checks),
            "max_profit": max_profit,
            "impact": impact,
            "checks": checks,
            "error": "",
        }
    except Exception as exc:
        return {
            "symbol": symbol,
            "side": transaction_type,
            "overall": "RED",
            "score": 0,
            "max_score": 7,
            "max_profit": None,
            "impact": "Validation could not calculate live impact.",
            "checks": [],
            "error": str(exc),
        }


def validate_trade_orders(orders: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    news_cache: dict[str, list[dict[str, str]]] = {}
    return [trade_validation_for_order(order, news_cache) for order in orders or []]


def selected_trade_guardrails(orders: list[dict[str, Any]]) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    sell_orders = [
        order
        for order in orders
        if str(order.get("transaction_type") or "").upper() == "SELL"
        and option_symbol_parts(str(order.get("tradingsymbol") or "").upper())
    ]
    margin_orders = []
    for order in sell_orders:
        quantity = int(float(order.get("quantity") or 0))
        if quantity <= 0:
            continue
        margin_orders.append(
            {
                "exchange": order.get("exchange") or "NFO",
                "tradingsymbol": order.get("tradingsymbol"),
                "transaction_type": "SELL",
                "variety": order.get("variety") or "regular",
                "product": order.get("product") or "NRML",
                "order_type": order.get("order_type") or "LIMIT",
                "quantity": quantity,
                "price": float(order.get("price") or 0),
            }
        )
    selected_margin = 0.0
    if margin_orders:
        try:
            selected_margin = sum(
                float(
                    item.get("total")
                    or item.get("final", {}).get("total")
                    or item.get("initial", {}).get("total")
                    or 0
                )
                for item in kite.order_margins(margin_orders)
            )
        except Exception:
            selected_margin = sum(
                float(order.get("price") or 0) * int(float(order.get("quantity") or 0))
                for order in sell_orders
            )
    existing_margin = 0.0
    sector_amounts: dict[str, float] = {}
    stock_amounts: dict[str, float] = {}
    for position in open_option_positions():
        symbol = str(position.get("tradingsymbol") or "").upper()
        underlying = underlying_for_symbol(symbol)
        deployed = margin_required_for_position(kite, position)
        existing_margin += deployed
        sector = STOCK_SECTORS.get(underlying, "Other")
        sector_amounts[sector] = sector_amounts.get(sector, 0.0) + deployed
        stock_amounts[underlying] = stock_amounts.get(underlying, 0.0) + deployed
    cash_reserved = 0.0
    for order in sell_orders:
        symbol = str(order.get("tradingsymbol") or "").upper()
        parts = option_symbol_parts(symbol)
        if not parts:
            continue
        quantity = abs(int(float(order.get("quantity") or 0)))
        strike = float(parts.get("strike") or 0)
        underlying = str(parts.get("underlying") or underlying_for_symbol(symbol))
        amount = selected_margin / max(len(sell_orders), 1)
        if parts.get("option_type") == "PE":
            amount = strike * quantity * 0.90
            cash_reserved += amount
        sector = STOCK_SECTORS.get(underlying, "Other")
        sector_amounts[sector] = sector_amounts.get(sector, 0.0) + amount
        stock_amounts[underlying] = stock_amounts.get(underlying, 0.0) + amount
    capital_used = existing_margin + selected_margin + cash_reserved
    denominator = capital_used if capital_used > 0 else 1.0
    top_sector, top_sector_value = max(
        sector_amounts.items(), key=lambda item: item[1], default=("N/A", 0.0)
    )
    top_stock, top_stock_value = max(
        stock_amounts.items(), key=lambda item: item[1], default=("N/A", 0.0)
    )
    return {
        "ok": True,
        "sell_count": len(sell_orders),
        "capital_used": fmt_number(capital_used),
        "cash_reserved": fmt_number(cash_reserved),
        "margin_used": fmt_number(existing_margin + selected_margin),
        "selected_margin": fmt_number(selected_margin),
        "sector_exposure": f"{top_sector} {top_sector_value / denominator * 100:.1f}%",
        "single_stock_exposure": f"{top_stock} {top_stock_value / denominator * 100:.1f}%",
    }


def income_selected_expiry(expiries: list[date], today: date) -> tuple[date, date | None, int | None]:
    front_expiry = expiries[0]
    front_trading_days = trading_days_remaining(front_expiry, today)
    if front_trading_days < INCOME_ROLL_TRADING_DAY_THRESHOLD and len(expiries) > 1:
        return expiries[1], front_expiry, front_trading_days
    return front_expiry, None, None


def next_monthly_pe_candidate(kite: Any, underlying: str) -> dict[str, Any]:
    today = datetime.now().date()
    spot_quote = kite.quote([f"NSE:{underlying}"]).get(f"NSE:{underlying}", {})
    spot = quote_ltp(spot_quote)
    if spot <= 0:
        raise ValueError(f"Could not read spot for {underlying}.")
    instruments = [
        item
        for item in kite.instruments("NFO")
        if str(item.get("name", "")).upper() == underlying
        and str(item.get("instrument_type", "")).upper() == "PE"
        and item.get("expiry")
        and item.get("expiry") >= today
    ]
    if not instruments:
        raise ValueError(f"No monthly PE instruments found for {underlying}.")
    expiries = sorted({item["expiry"] for item in instruments})
    expiry, rolled_from_expiry, rolled_from_trading_days = income_selected_expiry(
        expiries,
        today,
    )
    expiry_instruments = [item for item in instruments if item.get("expiry") == expiry]
    target_strike = spot * 0.90
    below_target = [
        item for item in expiry_instruments if float(item.get("strike") or 0) <= target_strike
    ]
    pool = below_target or expiry_instruments
    selected = min(
        pool,
        key=lambda item: abs(float(item.get("strike") or 0) - target_strike),
    )
    return {
        "symbol": str(selected["tradingsymbol"]).upper(),
        "spot": spot,
        "strike": float(selected.get("strike") or 0),
        "expiry": expiry,
        "rolled_from_expiry": rolled_from_expiry,
        "rolled_from_trading_days": rolled_from_trading_days,
        "target_strike": target_strike,
        "lot_size": int(selected.get("lot_size") or 0),
    }


def next_monthly_ce_candidate(kite: Any, underlying: str) -> dict[str, Any]:
    today = datetime.now().date()
    spot_quote = kite.quote([f"NSE:{underlying}"]).get(f"NSE:{underlying}", {})
    spot = quote_ltp(spot_quote)
    if spot <= 0:
        raise ValueError(f"Could not read spot for {underlying}.")
    instruments = [
        item
        for item in kite.instruments("NFO")
        if str(item.get("name", "")).upper() == underlying
        and str(item.get("instrument_type", "")).upper() == "CE"
        and item.get("expiry")
        and item.get("expiry") >= today
    ]
    if not instruments:
        raise ValueError(f"No monthly CE instruments found for {underlying}.")
    expiries = sorted({item["expiry"] for item in instruments})
    expiry, rolled_from_expiry, rolled_from_trading_days = income_selected_expiry(
        expiries,
        today,
    )
    expiry_instruments = [item for item in instruments if item.get("expiry") == expiry]
    target_strike = spot * 1.10
    above_target = [
        item for item in expiry_instruments if float(item.get("strike") or 0) >= target_strike
    ]
    pool = above_target or expiry_instruments
    selected = min(
        pool,
        key=lambda item: abs(float(item.get("strike") or 0) - target_strike),
    )
    return {
        "symbol": str(selected["tradingsymbol"]).upper(),
        "spot": spot,
        "strike": float(selected.get("strike") or 0),
        "expiry": expiry,
        "rolled_from_expiry": rolled_from_expiry,
        "rolled_from_trading_days": rolled_from_trading_days,
        "target_strike": target_strike,
        "lot_size": int(selected.get("lot_size") or 0),
    }


def income_share_holdings(kite: Any) -> dict[str, dict[str, Any]]:
    wanted = {item["symbol"] for item in INCOME_UNDERLYINGS}
    holdings: dict[str, dict[str, Any]] = {}
    quote_keys = [f"NSE:{symbol}" for symbol in wanted]
    quotes = kite.quote(quote_keys)
    for holding in kite.holdings():
        symbol = str(holding.get("tradingsymbol") or "").upper()
        if symbol not in wanted:
            continue
        quantity = int(float(holding.get("quantity") or 0))
        average_price = float(holding.get("average_price") or 0)
        ltp = float(
            quotes.get(f"NSE:{symbol}", {}).get("last_price")
            or holding.get("last_price")
            or 0
        )
        investment = quantity * average_price
        market_value = quantity * ltp
        holdings[symbol] = {
            "quantity": quantity,
            "average_price": average_price,
            "ltp": ltp,
            "investment": investment,
            "market_value": market_value,
            "pnl": market_value - investment,
            "return_pct": ((market_value - investment) / investment * 100)
            if investment > 0
            else None,
        }
    return holdings


def income_pnl_summary(kite: Any, holdings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_symbol = {
        item["symbol"]: {
            "stock_pnl": float(holdings.get(item["symbol"], {}).get("pnl") or 0),
            "option_pnl": 0.0,
            "total_pnl": float(holdings.get(item["symbol"], {}).get("pnl") or 0),
        }
        for item in INCOME_UNDERLYINGS
    }
    positions = kite.positions().get("net", [])
    for position in positions:
        symbol = str(position.get("tradingsymbol") or "").upper()
        underlying = underlying_for_symbol(symbol)
        if underlying in by_symbol:
            pnl = float(position.get("pnl") or 0)
            by_symbol[underlying]["option_pnl"] += pnl
            by_symbol[underlying]["total_pnl"] += pnl
    total = sum(row["total_pnl"] for row in by_symbol.values())
    return {"overall_pnl": total, "by_symbol": by_symbol}


def place_income_covered_call_order(underlying: str) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Covered CE order refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    clean_underlying = underlying.strip().upper()
    if clean_underlying not in {item["symbol"] for item in INCOME_UNDERLYINGS}:
        raise ValueError(f"Unsupported INCOME underlying: {clean_underlying}")
    kite = kite_orders.kite_client()
    holdings = income_share_holdings(kite)
    held_qty = int(holdings.get(clean_underlying, {}).get("quantity") or 0)
    candidate = next_monthly_ce_candidate(kite, clean_underlying)
    lot_size = int(candidate.get("lot_size") or 0)
    if lot_size <= 0:
        raise ValueError(f"Could not read lot size for {candidate['symbol']}.")
    covered_qty = (held_qty // lot_size) * lot_size
    if covered_qty <= 0:
        raise ValueError(
            f"Need at least {lot_size} shares of {clean_underlying} for one covered CE lot. Holding: {held_qty}."
        )
    quote = kite.quote([f"NFO:{candidate['symbol']}"]).get(f"NFO:{candidate['symbol']}", {})
    price = quote_ltp(quote)
    if price <= 0:
        raise ValueError(f"Could not read CE premium for {candidate['symbol']}.")
    order = {
        "variety": "regular",
        "exchange": "NFO",
        "tradingsymbol": candidate["symbol"],
        "transaction_type": "SELL",
        "quantity": covered_qty,
        "product": "NRML",
        "order_type": "LIMIT",
        "price": price,
        "validity": "DAY",
        "tag": "INCOME_CC",
    }
    order_id = kite_orders.place_order(kite, order)
    return {
        "tradingsymbol": candidate["symbol"],
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"SELL covered CE {covered_qty} qty at LIMIT {price:.2f}. "
            f"Holding {held_qty} shares of {clean_underlying}."
        ),
    }


def place_income_cash_secured_put_order(underlying: str) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Cash-secured PE order refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    clean_underlying = underlying.strip().upper()
    if clean_underlying not in {item["symbol"] for item in INCOME_UNDERLYINGS}:
        raise ValueError(f"Unsupported INCOME underlying: {clean_underlying}")
    kite = kite_orders.kite_client()
    candidate = next_monthly_pe_candidate(kite, clean_underlying)
    lot_size = int(candidate.get("lot_size") or 0)
    if lot_size <= 0:
        raise ValueError(f"Could not read lot size for {candidate['symbol']}.")
    quote = kite.quote([f"NFO:{candidate['symbol']}"]).get(f"NFO:{candidate['symbol']}", {})
    current_price = quote_ltp(quote)
    if current_price <= 0:
        raise ValueError(f"Could not read PE premium for {candidate['symbol']}.")
    price = ceil_to_tick(current_price * 1.20, 0.05)
    order = {
        "variety": "regular",
        "exchange": "NFO",
        "tradingsymbol": candidate["symbol"],
        "transaction_type": "SELL",
        "quantity": lot_size,
        "product": "NRML",
        "order_type": "LIMIT",
        "price": price,
        "validity": "DAY",
        "tag": "INCOME_CSP",
    }
    order_id = kite_orders.place_order(kite, order)
    assignment_value = float(candidate.get("strike") or 0) * lot_size
    return {
        "tradingsymbol": candidate["symbol"],
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"SELL cash-secured PE {lot_size} qty at LIMIT {price:.2f}, "
            f"20% above CMP {current_price:.2f}. "
            f"Assignment value about {assignment_value:.0f}."
        ),
    }


def income_strategy_candidates() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    rows: list[dict[str, Any]] = []
    news_cache: dict[str, list[dict[str, str]]] = {}
    holdings = income_share_holdings(kite)
    summary = income_pnl_summary(kite, holdings)
    for config in INCOME_UNDERLYINGS:
        underlying = config["symbol"]
        try:
            candidate = next_monthly_pe_candidate(kite, underlying)
            ce_candidate = next_monthly_ce_candidate(kite, underlying)
            data = option_analytics_for_symbol(candidate["symbol"])
            ce_data = option_analytics_for_symbol(ce_candidate["symbol"])
            decision = data.get("decision", {})
            risk = decision.get("risk_lights", {})
            expiry = candidate["expiry"]
            trading_days = trading_days_remaining(expiry)
            roll_note = ""
            if candidate.get("rolled_from_expiry"):
                rolled_from = candidate["rolled_from_expiry"]
                roll_note = (
                    f"Moved from {rolled_from.strftime('%d %b %Y')} "
                    f"because only {candidate.get('rolled_from_trading_days')} trading days remain."
                )
            ce_roll_note = ""
            if ce_candidate.get("rolled_from_expiry"):
                ce_rolled_from = ce_candidate["rolled_from_expiry"]
                ce_roll_note = (
                    f"Moved from {ce_rolled_from.strftime('%d %b %Y')} "
                    f"because only {ce_candidate.get('rolled_from_trading_days')} trading days remain."
                )
            otm = decision.get("otm_distance")
            iv_percent = data.get("iv_percent")
            sell_pop = data.get("sell_pop")
            pcr = data.get("pcr")
            event_status, event_detail = event_risk_check(candidate["symbol"], news_cache)
            entry_ok = (
                3 <= trading_days <= 7
                and otm is not None
                and float(otm) >= 10
                and sell_pop is not None
                and float(sell_pop) >= 75
                and event_status != "RED"
            )
            action = (
                "READY TO SELL CASH-SECURED PE"
                if entry_ok
                else "WAIT / REVIEW FILTERS"
            )
            if roll_note and not entry_ok:
                action = "NEXT MONTH PE SELECTED - WAIT FOR ENTRY WINDOW"
            holding = holdings.get(underlying, {})
            held_qty = int(holding.get("quantity") or 0)
            ce_lot_size = int(ce_candidate.get("lot_size") or 0)
            pe_lot_size = int(candidate.get("lot_size") or 0)
            covered_lots = (held_qty // ce_lot_size) if ce_lot_size > 0 else 0
            covered_qty = covered_lots * ce_lot_size
            ce_otm = ce_data.get("decision", {}).get("otm_distance")
            ce_sell_pop = ce_data.get("sell_pop")
            ce_action = (
                "READY TO SELL COVERED CE"
                if covered_qty > 0
                else "NEED SHARES FOR COVERED CE"
            )
            rows.append(
                {
                    **config,
                    "candidate": candidate["symbol"],
                    "roll_note": roll_note,
                    "spot": data.get("spot"),
                    "strike": data.get("strike"),
                    "expiry": expiry.strftime("%d %b %Y"),
                    "trading_days": trading_days,
                    "option_price": data.get("option_price"),
                    "sell_limit_price": (
                        ceil_to_tick(float(data.get("option_price") or 0) * 1.20, 0.05)
                        if float(data.get("option_price") or 0) > 0
                        else None
                    ),
                    "lot_size": pe_lot_size,
                    "max_profit": (
                        float(data.get("option_price") or 0) * pe_lot_size
                        if pe_lot_size > 0
                        else None
                    ),
                    "sell_pop": sell_pop,
                    "delta": abs(float(data.get("delta") or 0)),
                    "otm_distance": otm,
                    "iv_percent": iv_percent,
                    "pcr": pcr,
                    "theta_yield_pct": risk.get("theta_yield_pct"),
                    "event_status": event_status,
                    "event_detail": event_detail,
                    "action": action,
                    "action_color": "green" if entry_ok else "yellow",
                    "held_qty": held_qty,
                    "stock_pnl": holding.get("pnl"),
                    "stock_return_pct": holding.get("return_pct"),
                    "ce_candidate": ce_candidate["symbol"],
                    "ce_roll_note": ce_roll_note,
                    "ce_strike": ce_data.get("strike"),
                    "ce_expiry": ce_candidate["expiry"].strftime("%d %b %Y"),
                    "ce_lot_size": ce_lot_size,
                    "covered_qty": covered_qty,
                    "covered_lots": covered_lots,
                    "ce_premium": ce_data.get("option_price"),
                    "ce_max_profit": (
                        float(ce_data.get("option_price") or 0)
                        * (covered_qty if covered_qty > 0 else ce_lot_size)
                        if ce_lot_size > 0
                        else None
                    ),
                    "ce_otm_distance": ce_otm,
                    "ce_sell_pop": ce_sell_pop,
                    "ce_action": ce_action,
                    "ce_action_color": "green" if covered_qty > 0 else "yellow",
                    "error": "",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    **config,
                    "candidate": "",
                    "roll_note": "",
                    "ce_candidate": "",
                    "ce_roll_note": "",
                    "action": "DATA ERROR",
                    "action_color": "red",
                    "ce_action": "DATA ERROR",
                    "ce_action_color": "red",
                    "error": str(exc),
                }
            )
    return rows, summary


def research_csv_symbols() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for csv_row in safe_csv_rows(read_default_csv_text()):
        symbol = (csv_row.get("tradingsymbol") or csv_row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        quantity = int(float(csv_row.get("quantity") or 0))
        try:
            data = option_analytics_for_symbol(symbol)
            decision = data.get("decision", {})
            risk = decision.get("risk_lights", {})
            strength = strategy_strength_lights(data, decision)
            risk_by_name = {row[0]: row for row in risk.get("rows", [])}
            strength_by_name = {row[0]: row for row in strength.get("rows", [])}
            max_profit = float(data.get("option_price") or 0) * abs(quantity)
            rows.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "max_profit": max_profit,
                    "option_type": data.get("option_type"),
                    "spot": data.get("spot"),
                    "strike": data.get("strike"),
                    "expiry": data.get("expiry"),
                    "sell_signal": risk.get("final_sell"),
                    "sell_color": risk.get("final_sell_color"),
                    "buy_signal": risk.get("buy_signal"),
                    "buy_color": risk.get("buy_signal_color"),
                    "strategy_strength": strength.get("final"),
                    "strategy_color": strength.get("color"),
                    "delta": abs(float(data.get("delta") or 0)),
                    "sell_pop": data.get("sell_pop"),
                    "gamma_1pct": risk.get("gamma_1pct"),
                    "theta_yield_pct": risk.get("theta_yield_pct"),
                    "vega_risk_pct": risk.get("vega_risk_pct"),
                    "otm_distance": decision.get("otm_distance"),
                    "iv_percent": data.get("iv_percent"),
                    "pcr": data.get("pcr"),
                    "support": data.get("support"),
                    "resistance": data.get("resistance"),
                    "risk_rows": risk_by_name,
                    "strength_rows": strength_by_name,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "symbol": symbol,
                    "option_type": "",
                    "error": str(exc),
                    "sell_signal": "ERROR",
                    "sell_color": "red",
                    "strategy_strength": "ERROR",
                    "strategy_color": "lightcoral",
                }
            )
    return rows


def margin_required_for_position(kite: Any, position: dict[str, Any]) -> float:
    quantity = int(position.get("quantity") or 0)
    if quantity == 0:
        return 0.0
    order = {
        "exchange": position.get("exchange") or "NFO",
        "tradingsymbol": position["tradingsymbol"],
        "transaction_type": "SELL" if quantity < 0 else "BUY",
        "variety": "regular",
        "product": position.get("product") or "NRML",
        "order_type": "MARKET",
        "quantity": abs(quantity),
    }
    margin_rows = kite.order_margins([order])
    if not margin_rows:
        return 0.0
    margin = margin_rows[0]
    return float(
        margin.get("total")
        or margin.get("final", {}).get("total")
        or margin.get("initial", {}).get("total")
        or 0
    )


def premium_capture_for_position(position: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    quantity = int(position.get("quantity") or 0)
    average_price = float(position.get("average_price") or 0)
    ltp = float(position.get("ltp") or data.get("option_price") or 0)
    if quantity >= 0 or average_price <= 0:
        return {
            "captured_pct": None,
            "remaining_premium": None,
            "remaining_pct": None,
            "capture_action": "N/A",
            "capture_color": "neutral",
            "capture_detail": "Premium capture applies to sold option positions.",
        }
    captured_pct = ((average_price - ltp) / average_price) * 100
    remaining_pct = (ltp / average_price) * 100
    remaining_premium = ltp * abs(quantity)
    dte = int(data.get("dte") or 0)
    if captured_pct >= 70:
        action = "Close now"
        color = "green"
        detail = "70%+ premium captured; book profit cleanly."
    elif captured_pct >= 50:
        action = "Close 50%"
        color = "green"
        detail = "50%+ premium captured; regular income booking zone."
    elif dte <= 5:
        action = "Roll"
        color = "yellow"
        detail = f"{dte} DTE; roll or close before gamma risk rises."
    elif captured_pct < 0:
        action = "Review"
        color = "red"
        detail = "Premium expanded; check strike breach, trend and roll plan."
    else:
        action = "Hold"
        color = "neutral"
        detail = "Premium capture below 50%; continue monitoring."
    return {
        "captured_pct": captured_pct,
        "remaining_premium": remaining_premium,
        "remaining_pct": remaining_pct,
        "capture_action": action,
        "capture_color": color,
        "capture_detail": detail,
    }


def build_position_close_buy_order(symbol: str) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise ValueError("Missing position symbol.")
    kite = kite_orders.kite_client()
    matches = [
        position
        for position in open_option_positions()
        if str(position.get("tradingsymbol") or "").upper() == clean_symbol
        and int(position.get("quantity") or 0) < 0
    ]
    if not matches:
        raise ValueError(f"No open sold option position found for {clean_symbol}.")
    position = matches[0]
    quantity = abs(int(position.get("quantity") or 0))
    ltp = float(position.get("ltp") or 0)
    if ltp <= 0:
        quote = kite.quote([f"{position.get('exchange') or 'NFO'}:{clean_symbol}"]).get(
            f"{position.get('exchange') or 'NFO'}:{clean_symbol}",
            {},
        )
        ltp = quote_ltp(quote)
    if ltp <= 0:
        raise ValueError(f"Could not read LTP for {clean_symbol}.")
    limit_price = floor_to_tick(ltp * 0.90, 0.05)
    return {
        "variety": "regular",
        "exchange": position.get("exchange") or "NFO",
        "tradingsymbol": clean_symbol,
        "transaction_type": "BUY",
        "quantity": quantity,
        "product": position.get("product") or "NRML",
        "order_type": "LIMIT",
        "price": limit_price,
        "validity": "DAY",
        "tag": "CAPTURE_EXIT",
        "ltp": ltp,
    }


def place_position_close_buy_order(symbol: str) -> dict[str, Any]:
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Live placement refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    order = build_position_close_buy_order(symbol)
    kite = kite_orders.kite_client()
    order_id = kite_orders.place_order(kite, order)
    return {
        "tradingsymbol": order["tradingsymbol"],
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"BUY close order {order['quantity']} qty at LIMIT {order['price']:.2f}, "
            f"10% below LTP {order['ltp']:.2f}."
        ),
    }


def positions_research() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    positions = open_option_positions()
    rows: list[dict[str, Any]] = []
    total_pnl = 0.0
    total_deployed = 0.0
    for position in positions:
        symbol = position["tradingsymbol"]
        try:
            data = option_analytics_for_symbol(symbol)
            decision = data.get("decision", {})
            risk = decision.get("risk_lights", {})
            strength = strategy_strength_lights(data, decision)
            capture = premium_capture_for_position(position, data)
            deployed = margin_required_for_position(kite, position)
            pnl = float(position.get("pnl") or 0)
            total_pnl += pnl
            total_deployed += deployed
            rows.append(
                {
                    "symbol": symbol,
                    "quantity": position.get("quantity"),
                    "product": position.get("product"),
                    "average_price": position.get("average_price"),
                    "ltp": position.get("ltp"),
                    "pnl": pnl,
                    "deployed": deployed,
                    "return_pct": (pnl / deployed * 100) if deployed > 0 else None,
                    **capture,
                    "sell_signal": risk.get("final_sell"),
                    "sell_color": risk.get("final_sell_color"),
                    "buy_signal": risk.get("buy_signal"),
                    "buy_color": risk.get("buy_signal_color"),
                    "strategy_strength": strength.get("final"),
                    "strategy_color": strength.get("color"),
                    "delta": abs(float(data.get("delta") or 0)),
                    "sell_pop": data.get("sell_pop"),
                    "otm_distance": decision.get("otm_distance"),
                    "iv_percent": data.get("iv_percent"),
                    "pcr": data.get("pcr"),
                    "support": data.get("support"),
                    "resistance": data.get("resistance"),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "symbol": symbol,
                    "quantity": position.get("quantity"),
                    "product": position.get("product"),
                    "average_price": position.get("average_price"),
                    "ltp": position.get("ltp"),
                    "pnl": position.get("pnl"),
                    "error": str(exc),
                    "strategy_strength": "ERROR",
                    "strategy_color": "lightcoral",
                }
            )
    summary = {
        "count": len(rows),
        "total_pnl": total_pnl,
        "total_deployed": total_deployed,
        "return_pct": (total_pnl / total_deployed * 100) if total_deployed > 0 else None,
    }
    return rows, summary


def load_rows(csv_path: str, csv_text: str) -> tuple[list[dict[str, str]], str]:
    if is_web_csv_source(csv_path):
        text = fetch_csv_text_from_url(csv_path)
        return parse_csv_text(text), text

    if csv_text.strip():
        return parse_csv_text(csv_text), csv_text

    path = Path(csv_path.strip() or DEFAULT_CSV_PATH)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists() and path == DEFAULT_CSV_PATH and DATA_CSV_PATH.exists():
        path = DATA_CSV_PATH
    if not path.exists() and path == DEFAULT_CSV_PATH and LEGACY_CSV_PATH.exists():
        path = LEGACY_CSV_PATH
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
        return f"{DEFAULT_CSV_PATH.name} already has these input details."

    archive_message = ""
    if DEFAULT_CSV_PATH.exists() and current_text.strip():
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        archive_path = DEFAULT_CSV_PATH.with_name(
            f"{DEFAULT_CSV_PATH.stem}_last_input_order_{stamp}.csv"
        )
        DEFAULT_CSV_PATH.replace(archive_path)
        archive_message = f"Archived previous CSV to {archive_path.name}. "

    DEFAULT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CSV_PATH.write_text(normalized_new, encoding="utf-8")
    return f"{archive_message}Updated {DEFAULT_CSV_PATH.name} from the input box."


def save_today_csv_text(csv_text: str) -> tuple[str, str]:
    text = csv_text.strip()
    if not text:
        raise ValueError("CSV text is empty. Paste or upload CSV before saving.")
    parse_csv_text(text)
    today_path = dated_income_csv_path()
    normalized_new = text.rstrip() + "\n"
    archive_message = ""
    if today_path.exists() and today_path.read_text(encoding="utf-8-sig").strip():
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        archive_path = today_path.with_name(f"{today_path.stem}_last_input_order_{stamp}.csv")
        today_path.replace(archive_path)
        archive_message = f"Archived previous CSV to {archive_path.name}. "
    try:
        today_path.parent.mkdir(parents=True, exist_ok=True)
        today_path.write_text(normalized_new, encoding="utf-8")
    except PermissionError:
        today_path = APP_ROOT / today_path.name
        today_path.write_text(normalized_new, encoding="utf-8")
        archive_message += "Repo root was not writable, saved in webapp folder. "
    return str(today_path), f"{archive_message}Saved CSV text to {today_path.name}."


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


def csv_underlyings(csv_text: str) -> list[str]:
    underlyings: list[str] = []
    seen: set[str] = set()
    for symbol in csv_trading_symbols(csv_text):
        underlying = underlying_for_symbol(symbol)
        if underlying and underlying not in seen:
            underlyings.append(underlying)
            seen.add(underlying)
    return underlyings


def fetch_csv_market_quotes() -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")

    quote_items = [{"symbol": symbol, "threshold": None} for symbol in TOP_WATCHLIST]
    quote_items.extend(
        {
            "symbol": str(item["symbol"]),
            "threshold": float(item["threshold"]),
            "allocation": float(item["allocation"]),
        }
        for item in COMMODITY_ETFS
    )
    if not quote_items:
        return {"ok": True, "quotes": []}

    kite = kite_orders.kite_client()
    instruments = [f"NSE:{item['symbol']}" for item in quote_items]
    raw_quotes = kite.quote(instruments)
    quotes: list[dict[str, Any]] = []
    for item in quote_items:
        symbol = str(item["symbol"])
        key = f"NSE:{symbol}"
        quote = raw_quotes.get(key, {})
        ltp = float(quote.get("last_price") or 0)
        close = float((quote.get("ohlc") or {}).get("close") or 0)
        change_percent = ((ltp - close) / close * 100) if close > 0 else None
        threshold = item.get("threshold")
        sizing = (
            commodity_strategy_buy_amount(item, commodity_daily_fall_pct(close, ltp))
            if threshold is not None
            else None
        )
        quotes.append(
            {
                "symbol": symbol,
                "ltp": round(ltp, 2),
                "change_percent": round(change_percent, 2)
                if change_percent is not None
                else None,
                "threshold": threshold,
                "buy_signal": bool(sizing and sizing["buy_signal"]),
                "action": commodity_action_text(sizing["final_buy_amount"])
                if sizing and sizing["buy_signal"]
                else "",
                "buy_amount": sizing["final_buy_amount"] if sizing else None,
                "multiplier": sizing["multiplier"] if sizing else 0,
            }
        )
    return {"ok": True, "quotes": quotes}


def fetch_commodity_etf_quotes() -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")

    kite = kite_orders.kite_client()
    instruments = [f"NSE:{item['symbol']}" for item in COMMODITY_ETFS]
    raw_quotes = kite.quote(instruments)
    quotes: list[dict[str, Any]] = []
    for item in COMMODITY_ETFS:
        key = f"NSE:{item['symbol']}"
        quote = raw_quotes.get(key, {})
        ltp = float(quote.get("last_price") or 0)
        close = float((quote.get("ohlc") or {}).get("close") or 0)
        change_percent = ((ltp - close) / close * 100) if close > 0 else None
        daily_fall_pct = commodity_daily_fall_pct(close, ltp)
        threshold = float(item["threshold"])
        sizing = commodity_strategy_buy_amount(item, daily_fall_pct)
        quotes.append(
            {
                "key": item["key"],
                "label": item["label"],
                "symbol": item["symbol"],
                "ltp": round(ltp, 2),
                "close": round(close, 2),
                "change_percent": round(change_percent, 2)
                if change_percent is not None
                else None,
                "threshold": threshold,
                "allocation": item["allocation"],
                "yearly_base_amount": sizing["yearly_base_amount"],
                "base_buy_amount": round(sizing["base_buy_amount"], 2),
                "daily_fall_pct": round(daily_fall_pct, 2),
                "multiplier": sizing["multiplier"],
                "max_multiplier": sizing["max_multiplier"],
                "buy_signal": sizing["buy_signal"],
                "action": commodity_action_text(sizing["final_buy_amount"])
                if sizing["buy_signal"]
                else "Wait",
                "buy_amount": round(sizing["final_buy_amount"], 2),
            }
        )
    return {"ok": True, "quotes": quotes}


def commodity_etf_by_symbol(symbol: str) -> dict[str, Any]:
    clean = symbol.strip().upper()
    for item in COMMODITY_ETFS:
        if str(item["symbol"]).upper() == clean:
            return item
    raise ValueError(f"Unknown ETF symbol: {symbol}")


def commodity_profit_target_pct(item: dict[str, Any]) -> float:
    return float(item.get("profit_target") or 0.25) * 100


def calculate_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        change = current - previous
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def commodity_etf_rsi(kite: Any, symbol: str) -> float | None:
    try:
        clean_symbol = symbol.strip().upper()
        instrument = next(
            (
                item
                for item in kite.instruments("NSE")
                if str(item.get("tradingsymbol") or "").upper() == clean_symbol
            ),
            None,
        )
        if not instrument:
            return None
        today = datetime.now().date()
        candles = kite.historical_data(
            int(instrument["instrument_token"]),
            today - timedelta(days=120),
            today,
            "day",
        )
        closes = [float(candle.get("close") or 0) for candle in candles if candle.get("close")]
        rsi = calculate_rsi(closes)
        return round(rsi, 2) if rsi is not None else None
    except Exception:
        return None


def place_commodity_etf_order(symbol: str, allow_manual_override: bool = False) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'ETF live order refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    item = commodity_etf_by_symbol(symbol)
    clean_symbol = str(item["symbol"]).upper()
    kite = kite_orders.kite_client()
    quote = kite.quote([f"NSE:{clean_symbol}"]).get(f"NSE:{clean_symbol}", {})
    ltp = float(quote.get("last_price") or 0)
    previous_close = float((quote.get("ohlc") or {}).get("close") or 0)
    if ltp <= 0:
        raise ValueError(f"Could not read live LTP for {clean_symbol}.")
    sizing = commodity_strategy_buy_amount(
        item,
        commodity_daily_fall_pct(previous_close, ltp),
    )
    if not sizing["buy_signal"]:
        if not allow_manual_override:
            raise ValueError(
                f"{clean_symbol} has not hit dip trigger. Fall {sizing['daily_fall_pct']:.2f}% "
                f"is below trigger {sizing['dip_trigger']:.2f}%. Validate again to the price?"
            )
        buy_amount = float(sizing["base_buy_amount"])
        multiplier_text = "manual 1x override"
    else:
        buy_amount = float(sizing["final_buy_amount"])
        multiplier_text = f"{sizing['multiplier']}x"
    quantity = int(buy_amount // ltp)
    if quantity < 1:
        raise ValueError(
            f"Strategy buy amount {format_buy_amount(buy_amount)} is less than one unit at LTP {ltp:.2f}."
        )
    limit_price = limit_price_one_percent_below_ltp(ltp)
    order = {
        "variety": "regular",
        "exchange": "NSE",
        "tradingsymbol": clean_symbol,
        "transaction_type": "BUY",
        "quantity": quantity,
        "product": "CNC",
        "order_type": "LIMIT",
        "price": limit_price,
        "validity": "DAY",
        "tag": "ETF_BUY",
    }
    order_id = kite_orders.place_order(kite, order)
    return {
        "tradingsymbol": clean_symbol,
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"BUY {quantity} {clean_symbol} LIMIT {limit_price:.2f} "
            f"(1% below LTP {ltp:.2f}). Strategy amount {format_buy_amount(buy_amount)} "
            f"({multiplier_text}, fall {sizing['daily_fall_pct']:.2f}%)."
        ),
    }


def commodity_etf_holdings() -> list[dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    symbols = [str(item["symbol"]).upper() for item in COMMODITY_ETFS]
    all_symbols = sorted(
        {
            alias.upper()
            for item in COMMODITY_ETFS
            for alias in [str(item["symbol"])] + [str(value) for value in item.get("aliases", [])]
        }
    )
    by_symbol = {
        str(holding.get("tradingsymbol") or "").upper(): holding
        for holding in kite.holdings()
    }
    positions_by_symbol: dict[str, dict[str, Any]] = {}
    try:
        for position in kite.positions().get("net", []):
            symbol = str(position.get("tradingsymbol") or "").upper()
            if symbol in all_symbols and str(position.get("exchange") or "").upper() == "NSE":
                positions_by_symbol[symbol] = position
    except Exception:
        positions_by_symbol = {}
    quote_keys = [f"NSE:{symbol}" for symbol in symbols]
    quotes = kite.quote(quote_keys)
    rows: list[dict[str, Any]] = []
    for item in COMMODITY_ETFS:
        symbol = str(item["symbol"]).upper()
        aliases = [symbol] + [str(value).upper() for value in item.get("aliases", [])]
        holding = next((by_symbol.get(alias) for alias in aliases if by_symbol.get(alias)), {})
        position = next(
            (positions_by_symbol.get(alias) for alias in aliases if positions_by_symbol.get(alias)),
            {},
        )
        holding_quantity = (
            float(holding.get("quantity") or 0)
            + float(holding.get("t1_quantity") or 0)
        )
        position_quantity = max(float(position.get("quantity") or 0), 0)
        quantity = int(
            max(holding_quantity, position_quantity)
        )
        sellable_quantity = int(max(float(holding.get("quantity") or 0), position_quantity))
        average_price = float(
            holding.get("average_price")
            or position.get("average_price")
            or 0
        )
        quote = quotes.get(f"NSE:{symbol}", {})
        ltp = float(
            quote.get("last_price")
            or position.get("last_price")
            or holding.get("last_price")
            or holding.get("close_price")
            or 0
        )
        if average_price <= 0 and quantity > 0:
            average_price = ltp
        investment = average_price * quantity
        market_value = ltp * quantity
        pnl = market_value - investment
        profit_pct = (pnl / investment * 100) if investment > 0 else None
        profit_target_pct = commodity_profit_target_pct(item)
        rsi = commodity_etf_rsi(kite, symbol) if item.get("key") == "nasdaq" else None
        rsi_book_profit = bool(rsi is not None and rsi > 78)
        book_profit = (
            quantity > 0
            and (
                (profit_pct is not None and profit_pct >= profit_target_pct)
                or rsi_book_profit
            )
        )
        rows.append(
            {
                "label": item["label"],
                "symbol": symbol,
                "sell_trigger": item.get("sell_trigger", f"{profit_target_pct:.0f}% profit"),
                "profit_target_pct": profit_target_pct,
                "rsi": rsi,
                "rsi_book_profit": rsi_book_profit,
                "quantity": quantity,
                "sellable_quantity": sellable_quantity,
                "source": "holding" if holding else ("position" if position else ""),
                "average_price": average_price,
                "ltp": ltp,
                "investment": investment,
                "market_value": market_value,
                "pnl": pnl,
                "profit_pct": profit_pct,
                "book_profit": book_profit,
            }
        )
    return rows


def place_commodity_etf_sell_order(symbol: str) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'ETF sell order refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    item = commodity_etf_by_symbol(symbol)
    clean_symbol = str(item["symbol"]).upper()
    holding = next(
        (row for row in commodity_etf_holdings() if row["symbol"] == clean_symbol),
        None,
    )
    if not holding or int(holding.get("quantity") or 0) <= 0:
        raise ValueError(f"No ETF holding quantity found for {clean_symbol}.")
    if not holding.get("book_profit"):
        target_pct = commodity_profit_target_pct(item)
        raise ValueError(
            f"{clean_symbol} profit is {fmt_number(holding.get('profit_pct'))}%, below BOOK profit threshold {target_pct:.0f}%."
        )
    quantity = int(holding.get("sellable_quantity") or 0)
    if quantity <= 0:
        raise ValueError(f"No sellable ETF holding quantity found for {clean_symbol}.")
    kite = kite_orders.kite_client()
    quote = kite.quote([f"NSE:{clean_symbol}"]).get(f"NSE:{clean_symbol}", {})
    ltp = float(quote.get("last_price") or holding.get("ltp") or 0)
    if ltp <= 0:
        raise ValueError(f"Could not read live LTP for {clean_symbol}.")
    limit_price = limit_price_one_percent_below_ltp(ltp)
    order = {
        "variety": "regular",
        "exchange": "NSE",
        "tradingsymbol": clean_symbol,
        "transaction_type": "SELL",
        "quantity": quantity,
        "product": "CNC",
        "order_type": "LIMIT",
        "price": limit_price,
        "validity": "DAY",
        "tag": "ETF_BOOK",
    }
    order_id = kite_orders.place_order(kite, order)
    return {
        "tradingsymbol": clean_symbol,
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"SELL full holding {quantity} {clean_symbol} LIMIT {limit_price:.2f} "
            f"(1% below LTP {ltp:.2f}). "
            f"Current profit {fmt_number(holding.get('profit_pct'))}%."
        ),
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


KITE_CSV_REQUIRED_FIELDS = [
    "exchange",
    "tradingsymbol",
    "quantity",
    "transaction_type",
    "product",
    "order_type",
    "price",
    "validity",
]
KITE_CSV_HEADER_ALIASES = {
    "symbol": "tradingsymbol",
    "trading_symbol": "tradingsymbol",
    "qty": "quantity",
    "transaction": "transaction_type",
    "side": "transaction_type",
    "type": "transaction_type",
    "ordertype": "order_type",
    "order type": "order_type",
    "limit_price": "price",
    "limit price": "price",
}


def markdown_table_to_csv(text: str) -> str:
    table_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if len(table_lines) < 2:
        return ""
    rows: list[list[str]] = []
    for line in table_lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        rows.append(cells)
    if len(rows) < 2:
        return ""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue().strip()


def canonical_field_name(name: str) -> str:
    clean = re.sub(r"[_\s-]+", "_", name.strip().lower())
    return KITE_CSV_HEADER_ALIASES.get(clean, clean)


def canonicalize_kite_csv(candidate: str) -> str:
    reader = csv.DictReader(io.StringIO(candidate.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise ValueError("CSV is missing a header row.")
    canonical_headers = [canonical_field_name(name or "") for name in reader.fieldnames]
    row_count = 0
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=KITE_CSV_REQUIRED_FIELDS, lineterminator="\n")
    writer.writeheader()
    for raw_row in reader:
        normalized = {
            canonical_field_name(key or ""): (value or "").strip()
            for key, value in raw_row.items()
        }
        if not any(normalized.values()):
            continue
        row = {field: normalized.get(field, "") for field in KITE_CSV_REQUIRED_FIELDS}
        if not row["exchange"]:
            row["exchange"] = "NFO"
        if not row["product"]:
            row["product"] = "NRML"
        if not row["order_type"]:
            row["order_type"] = "LIMIT"
        if not row["validity"]:
            row["validity"] = "DAY"
        if not row["price"]:
            row["price"] = "0"
        if not {"tradingsymbol", "quantity", "transaction_type"}.issubset(
            {field for field, value in row.items() if value}
        ):
            raise ValueError("CSV is missing tradingsymbol, quantity, or transaction_type.")
        writer.writerow(row)
        row_count += 1
    if row_count == 0:
        raise ValueError("CSV has no order rows.")
    return output.getvalue()


def extract_csv_from_text(text: str) -> str:
    fenced_blocks = re.findall(r"```(?:csv)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    candidates = [normalize_csv_candidate(block) for block in fenced_blocks]
    markdown_csv = markdown_table_to_csv(text)
    if markdown_csv:
        candidates.append(normalize_csv_candidate(markdown_csv))

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
            canonical = canonicalize_kite_csv(candidate)
            parse_csv_text(canonical)
            return canonical.rstrip() + "\n"
        except Exception:
            continue
    raise ValueError(
        "Could not find a valid Kite order CSV. Paste the GPT CSV output into the text box and try again."
    )


def response_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def call_openai_responses_api(
    api_key: str,
    model: str,
    system_prompt: str,
    prompt: str,
) -> tuple[str, str]:
    body = {
        "model": model.strip() or DEFAULT_OPENAI_MODEL,
        "input": [
            {
                "role": "system",
                "content": system_prompt.strip() or DEFAULT_OPENAI_SYSTEM_PROMPT,
            },
            {"role": "user", "content": prompt},
        ],
        "max_output_tokens": 2500,
    }
    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI API error {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI API network error: {exc}") from exc

    output = response_output_text(payload)
    if not output:
        raise RuntimeError("OpenAI returned an empty response.")
    return output, str(payload.get("id") or "")


def generate_csv_with_openai(prompt: str, model: str, system_prompt: str) -> tuple[str, str, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY. Enter it in the GPT CSV Generator tab.")

    output, response_id = call_openai_responses_api(api_key, model, system_prompt, prompt)
    try:
        return extract_csv_from_text(output), output, response_id
    except ValueError as first_error:
        repair_prompt = (
            "Convert the previous response into valid Kite CSV only. "
            "Use exactly this header: "
            "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n"
            "No explanation, no markdown, no notes. If price is unknown, use 0.\n\n"
            f"Previous response:\n{output}"
        )
        repaired, repair_response_id = call_openai_responses_api(
            api_key,
            model,
            DEFAULT_OPENAI_SYSTEM_PROMPT,
            repair_prompt,
        )
        try:
            return extract_csv_from_text(repaired), repaired, repair_response_id or response_id
        except ValueError as second_error:
            raise ValueError(
                f"{first_error}\n\nOpenAI raw output preview:\n{output[:1200]}\n\n"
                f"Repair attempt also failed:\n{second_error}\n\n"
                f"Repair raw output preview:\n{repaired[:1200]}"
            ) from second_error


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


def should_fallback_to_new_order(error: Exception) -> bool:
    text = str(error).lower()
    fallback_terms = [
        "not found",
        "not modifiable",
        "cannot be modified",
        "order not open",
        "completed",
        "cancelled",
        "rejected",
        "no pending quantity",
    ]
    return any(term in text for term in fallback_terms)


def modify_or_place_order_with_new_fallback(kite: Any, order: dict[str, Any]) -> tuple[str, str]:
    similar_orders = kite_orders.find_similar_open_orders(kite, order)
    if not similar_orders:
        order_id = kite_orders.place_order(kite, order)
        return order_id, "placed_new_no_similar_open_order"
    try:
        order_id = kite_orders.modify_order(kite, similar_orders[-1], order)
        return order_id, "modified_similar_open_order"
    except Exception as exc:
        if not should_fallback_to_new_order(exc):
            raise
        print(
            "Similar order could not be modified; placing a new order instead. "
            f"Reason: {exc}"
        )
        order_id = kite_orders.place_order(kite, order)
        return order_id, "placed_new_after_modify_failed"


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
                action = "placed_new_requested"
            else:
                order_id, action = modify_or_place_order_with_new_fallback(kite, order)
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


CANCELLABLE_ORDER_STATUSES = {
    "OPEN",
    "TRIGGER PENDING",
    "VALIDATION PENDING",
    "PUT ORDER REQ RECEIVED",
}


def kite_order_book() -> list[dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    rows: list[dict[str, Any]] = []
    orders = list(reversed(kite.orders()))
    quote_keys = sorted(
        {
            f"{str(order.get('exchange') or '').upper()}:{str(order.get('tradingsymbol') or '').upper()}"
            for order in orders
            if order.get("exchange") and order.get("tradingsymbol")
        }
    )
    quotes = kite.quote(quote_keys) if quote_keys else {}
    for order in orders:
        status = str(order.get("status") or "").upper()
        exchange = str(order.get("exchange") or "")
        symbol = str(order.get("tradingsymbol") or "")
        quote_key = f"{exchange.upper()}:{symbol.upper()}"
        ltp = quote_ltp(quotes.get(quote_key, {})) if quote_key in quotes else None
        price = order.get("price") or ""
        price_diff_pct = None
        try:
            order_price = float(price or 0)
            live_price = float(ltp or 0)
            if order_price > 0 and live_price > 0:
                price_diff_pct = ((order_price - live_price) / live_price) * 100
        except Exception:
            price_diff_pct = None
        rows.append(
            {
                "order_id": str(order.get("order_id") or ""),
                "variety": str(order.get("variety") or "regular"),
                "exchange": exchange,
                "tradingsymbol": symbol,
                "transaction_type": str(order.get("transaction_type") or ""),
                "quantity": order.get("quantity") or "",
                "pending_quantity": order.get("pending_quantity") or "",
                "product": str(order.get("product") or ""),
                "order_type": str(order.get("order_type") or ""),
                "price": price,
                "ltp": ltp,
                "price_diff_pct": price_diff_pct,
                "status": status,
                "status_message": str(order.get("status_message") or ""),
                "is_cancellable": status in CANCELLABLE_ORDER_STATUSES,
            }
        )
    return rows


def order_form_key(order_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", order_key)


def cancel_selected_orders(order_keys: list[str]) -> list[dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Cancel selected refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    selected = set(order_keys)
    if not selected:
        raise ValueError("Select at least one order to cancel.")
    kite = kite_orders.kite_client()
    by_key = {
        f"{str(order.get('variety') or 'regular')}|{str(order.get('order_id') or '')}": order
        for order in kite.orders()
    }
    results: list[dict[str, Any]] = []
    for key in selected:
        order = by_key.get(key)
        if not order:
            results.append(
                {
                    "tradingsymbol": key,
                    "status": "ERROR",
                    "order_id": key.split("|")[-1],
                    "detail": "Order not found in current Kite order book.",
                }
            )
            continue
        status = str(order.get("status") or "").upper()
        order_id = str(order.get("order_id") or "")
        variety = str(order.get("variety") or "regular")
        symbol = str(order.get("tradingsymbol") or "")
        if status not in CANCELLABLE_ORDER_STATUSES:
            results.append(
                {
                    "tradingsymbol": symbol,
                    "status": "SKIPPED",
                    "order_id": order_id,
                    "detail": f"Order status {status} is not cancellable.",
                }
            )
            continue
        try:
            kite.cancel_order(variety=variety, order_id=order_id)
            results.append(
                {
                    "tradingsymbol": symbol,
                    "status": "CANCELLED",
                    "order_id": order_id,
                    "detail": f"Cancelled {status} order.",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "tradingsymbol": symbol,
                    "status": "ERROR",
                    "order_id": order_id,
                    "detail": str(exc),
                }
            )
    return results


def modify_selected_orders(order_keys: list[str], form: dict[str, list[str]]) -> list[dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Modify selected refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    selected = set(order_keys)
    if not selected:
        raise ValueError("Select at least one order to modify.")
    kite = kite_orders.kite_client()
    by_key = {
        f"{str(order.get('variety') or 'regular')}|{str(order.get('order_id') or '')}": order
        for order in kite.orders()
    }
    results: list[dict[str, Any]] = []
    for key in selected:
        order = by_key.get(key)
        if not order:
            results.append(
                {
                    "tradingsymbol": key,
                    "status": "ERROR",
                    "order_id": key.split("|")[-1],
                    "detail": "Order not found in current Kite order book.",
                }
            )
            continue
        status = str(order.get("status") or "").upper()
        order_id = str(order.get("order_id") or "")
        variety = str(order.get("variety") or "regular")
        symbol = str(order.get("tradingsymbol") or "")
        order_type = str(order.get("order_type") or "").upper()
        if status not in CANCELLABLE_ORDER_STATUSES:
            results.append(
                {
                    "tradingsymbol": symbol,
                    "status": "SKIPPED",
                    "order_id": order_id,
                    "detail": f"Order status {status} is not modifiable.",
                }
            )
            continue

        field_key = order_form_key(key)
        payload: dict[str, Any] = {}
        quantity_text = first(form, f"modify_quantity_{field_key}")
        price_text = first(form, f"modify_price_{field_key}")
        if quantity_text:
            quantity = int(float(quantity_text))
            if quantity <= 0:
                raise ValueError(f"Quantity must be positive for {symbol}.")
            payload["quantity"] = quantity
        if price_text and order_type in {"LIMIT", "SL"}:
            price = float(price_text)
            if price <= 0:
                raise ValueError(f"Price must be positive for {symbol}.")
            payload["price"] = price
        if not payload:
            results.append(
                {
                    "tradingsymbol": symbol,
                    "status": "SKIPPED",
                    "order_id": order_id,
                    "detail": "No quantity or limit price change was provided.",
                }
            )
            continue

        try:
            kite.modify_order(variety=variety, order_id=order_id, **payload)
            changed = ", ".join(f"{name}={value}" for name, value in payload.items())
            results.append(
                {
                    "tradingsymbol": symbol,
                    "status": "MODIFIED",
                    "order_id": order_id,
                    "detail": f"Modified {changed}.",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "tradingsymbol": symbol,
                    "status": "ERROR",
                    "order_id": order_id,
                    "detail": str(exc),
                }
            )
    return results


def cancel_all_open_orders() -> list[dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Cancel all refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    kite = kite_orders.kite_client()
    results: list[dict[str, Any]] = []
    for order in kite.orders():
        status = str(order.get("status") or "").upper()
        if status not in CANCELLABLE_ORDER_STATUSES:
            continue
        order_id = str(order.get("order_id") or "")
        variety = str(order.get("variety") or "regular")
        symbol = str(order.get("tradingsymbol") or "")
        try:
            kite.cancel_order(variety=variety, order_id=order_id)
            results.append(
                {
                    "tradingsymbol": symbol,
                    "status": "CANCELLED",
                    "order_id": order_id,
                    "detail": f"Cancelled {status} order.",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "tradingsymbol": symbol,
                    "status": "ERROR",
                    "order_id": order_id,
                    "detail": str(exc),
                }
            )
    if not results:
        results.append(
            {
                "tradingsymbol": "ALL",
                "status": "NO_OPEN_ORDERS",
                "order_id": "",
                "detail": "No open/pending orders found to cancel.",
            }
        )
    return results


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


def display_cell(field: str, value: Any) -> str:
    if field.lower() == "pnl":
        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def render_symbol_value(field: str, value: Any) -> str:
    text = display_cell(field, value)
    if field == "tradingsymbol" and text:
        return (
            f'<a class="symbol-link" href="/analytics?symbol={html.escape(text, quote=True)}">'
            f"{html.escape(text)}</a>"
        )
    return html.escape(text)


def render_orders_table(orders: list[dict[str, Any]] | None, selected: set[int] | None = None) -> str:
    if not orders:
        return ""
    selected = selected or set(range(len(orders)))
    active_underlyings = active_position_underlyings()
    header = "".join(f"<th>{html.escape(field)}</th>" for field in DISPLAY_FIELDS)
    rows = []
    for index, order in enumerate(orders):
        checked_attr = " checked" if index in selected else ""
        symbol = str(order.get("tradingsymbol") or "").strip().upper()
        underlying = underlying_for_symbol(symbol) if symbol else ""
        has_active_position = bool(
            symbol and (symbol in active_underlyings or underlying in active_underlyings)
        )
        row_class = ' class="order-existing-position"' if has_active_position else ""
        row_title = (
            f' title="Existing Kite position found for {html.escape(underlying or symbol, quote=True)}"'
            if has_active_position
            else ""
        )
        cells = "".join(
            f"<td>{render_symbol_value(field, order.get(field, ''))}</td>"
            for field in DISPLAY_FIELDS
        )
        rows.append(
            f"<tr{row_class}{row_title}>"
            f'<td><input type="checkbox" name="selected" value="{index}"{checked_attr}></td>'
            f"{cells}</tr>"
        )
    return (
        '<section class="panel"><div class="panel-title">Orders</div>'
        '<div class="status order-position-note">Rows in light red already have an active Kite position for the same underlying.</div>'
        '<div class="table-wrap"><table><thead><tr><th>Select</th>'
        f"{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"
    )


def render_trade_validation_table(validations: list[dict[str, Any]] | None) -> str:
    if not validations:
        return ""
    rows: list[str] = []
    for item in validations:
        overall_class = validation_status_class(str(item.get("overall") or ""))
        score = fmt_number(item.get("score"), 1)
        max_score = fmt_number(item.get("max_score"), 0)
        max_profit = item.get("max_profit")
        profit_text = fmt_number(max_profit) if max_profit is not None else "N/A"
        if item.get("error"):
            rows.append(
                "<tr>"
                f'<td class="validation-symbol">{render_symbol_value("tradingsymbol", item.get("symbol", ""))}<span>{html.escape(str(item.get("side", "")))}</span></td>'
                f'<td class="validation-overall {overall_class}"><strong>{html.escape(str(item.get("overall", "RED")))}</strong><small>{score}/{max_score}</small></td>'
                f'<td class="validation-profit">{html.escape(profit_text)}</td>'
                f'<td class="validation-checks validation-red">{html.escape(str(item.get("error")))}</td>'
                f'<td class="validation-impact">{html.escape(str(item.get("impact", "")))}</td>'
                "</tr>"
            )
            continue
        checks = item.get("checks") or []
        check_html = "".join(
            f'<div class="validation-check {validation_status_class(str(check.get("status", "")))}">'
            f'<strong>{html.escape(str(check.get("point", "")))}: {html.escape(str(check.get("status", "")))}</strong>'
            f'<span>{html.escape(str(check.get("detail", "")))}</span>'
            "</div>"
            for check in checks
        )
        rows.append(
            "<tr>"
            f'<td class="validation-symbol">{render_symbol_value("tradingsymbol", item.get("symbol", ""))}<span>{html.escape(str(item.get("side", "")))}</span></td>'
            f'<td class="validation-overall {overall_class}"><strong>{html.escape(str(item.get("overall", "")))}</strong><small>{score}/{max_score}</small></td>'
            f'<td class="validation-profit">{html.escape(profit_text)}</td>'
            f'<td class="validation-checks">{check_html}</td>'
            f'<td class="validation-impact">{html.escape(str(item.get("impact", "")))}</td>'
            "</tr>"
        )
    return (
        '<section class="panel validation-panel">'
        '<div class="panel-title">Pre-Trade Wheel Validation Engine</div>'
        '<div class="status">Top 7 checks before selling CALL / PUT. Use this to judge stock-price impact and CE/PE assignment risk before live order placement.</div>'
        '<div class="table-wrap"><table class="validation-table"><thead><tr>'
        '<th>Symbol</th><th>Overall</th><th>Max Profit</th><th>7 Checks</th><th>Stock Price Impact / CE-PE Risk</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>"
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
        cells = "".join(
            f"<td>{render_symbol_value(field, order.get(field, ''))}</td>"
            for field in fields
        )
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


def render_graceful_error(error: str, title: str = "Error") -> str:
    if not error:
        return ""
    lines = str(error).strip().splitlines()
    top_lines = "\n".join(lines[:4]).strip()
    remaining = "\n".join(lines[4:]).strip()
    if not remaining:
        return (
            '<div class="alert error graceful-error">'
            '<button type="button" class="alert-close" aria-label="Close error" onclick="this.parentElement.style.display=\'none\'">x</button>'
            f"<strong>{html.escape(title)}</strong>"
            f"<pre>{html.escape(top_lines)}</pre>"
            "</div>"
        )
    return (
        '<div class="alert error graceful-error">'
        '<button type="button" class="alert-close" aria-label="Close error" onclick="this.parentElement.style.display=\'none\'">x</button>'
        f"<strong>{html.escape(title)}</strong>"
        f"<pre>{html.escape(top_lines)}</pre>"
        "<details>"
        "<summary>Show full details</summary>"
        f'<textarea class="error-details" readonly>{html.escape(str(error))}</textarea>'
        "</details>"
        "</div>"
    )


def render_order_book(state: PageState) -> str:
    orders = state.order_book
    error = state.order_book_error
    if orders is None:
        try:
            orders = kite_order_book()
        except Exception as exc:
            orders = []
            error = str(exc)
    rows: list[str] = []
    for order in orders:
        checked_attr = " checked" if order.get("is_cancellable") else ""
        disabled_attr = "" if order.get("is_cancellable") else " disabled"
        key = f"{order.get('variety', 'regular')}|{order.get('order_id', '')}"
        field_key = order_form_key(key)
        quantity = html.escape(str(order.get("quantity", "")), quote=True)
        price = html.escape(str(order.get("price", "")), quote=True)
        qty_cell = (
            f'<input class="order-edit-input" type="number" min="1" step="1" '
            f'name="modify_quantity_{field_key}" value="{quantity}"{disabled_attr}>'
        )
        price_cell = (
            f'<input class="order-edit-input" type="number" min="0" step="0.01" '
            f'name="modify_price_{field_key}" value="{price}"{disabled_attr}>'
        )
        price_diff = order.get("price_diff_pct")
        diff_class = ""
        if price_diff is not None:
            diff_value = float(price_diff)
            diff_class = "pnl-positive" if diff_value >= 0 else "pnl-negative"
        rows.append(
            "<tr>"
            f'<td><input type="checkbox" name="order_key" value="{html.escape(key, quote=True)}"{checked_attr}{disabled_attr}></td>'
            f"<td>{html.escape(str(order.get('order_id', '')))}</td>"
            f"<td>{html.escape(str(order.get('tradingsymbol', '')))}</td>"
            f"<td>{html.escape(str(order.get('transaction_type', '')))}</td>"
            f"<td>{qty_cell}</td>"
            f"<td>{html.escape(str(order.get('pending_quantity', '')))}</td>"
            f"<td>{html.escape(str(order.get('product', '')))}</td>"
            f"<td>{html.escape(str(order.get('order_type', '')))}</td>"
            f"<td>{price_cell}</td>"
            f"<td>{html.escape(fmt_number(order.get('ltp')))}</td>"
            f'<td class="{diff_class}">{html.escape(fmt_number(price_diff))}%</td>'
            f"<td>{html.escape(str(order.get('status', '')))}</td>"
            "</tr>"
        )
    body = (
        "".join(rows)
        if rows
        else '<tr><td colspan="12" class="status">No Kite orders found.</td></tr>'
    )
    error_html = render_graceful_error(error, "Kite Orders Error")
    return (
        '<section class="panel order-book-panel"><div class="panel-title">Kite Orders</div>'
        '<p class="status">Select open / pending orders, edit quantity or limit price, then modify or cancel them.</p>'
        f"{error_html}"
        '<div class="actions"><button type="submit" formaction="/orders/modify-selected">Modify Selected Orders</button>'
        '<button type="submit" formaction="/orders/cancel-selected" class="cancel-all-button">Cancel Selected Orders</button>'
        '<button type="submit" formaction="/orders/refresh">Refresh Orders</button></div>'
        '<div class="table-wrap"><table class="order-book-table"><thead><tr>'
        '<th>Select</th><th>Order ID</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Pending</th>'
        '<th>Product</th><th>Type</th><th>Price</th><th>LTP</th><th>% Diff</th><th>Status</th>'
        f"</tr></thead><tbody>{body}</tbody></table></div></section>"
    )


def render_order_management_panel(state: PageState) -> str:
    panel_style = "" if state.active_tab == "order-management" else ' style="display:none"'
    return f"""
    <form id="order-management-panel" method="post" action="/orders/refresh"{panel_style}>
      {env_hidden_fields_for_render()}
      <section class="panel cancel-all-panel">
        <div>
          <div class="panel-title">Modify / Cancel Kite Orders</div>
          <p class="status">Manage open Kite orders separately from new trade execution.</p>
        </div>
        <button type="submit" formaction="/orders/cancel-all" class="cancel-all-button">Cancel All Orders</button>
      </section>
      {render_order_book(state)}
      {render_results(state.results)}
      {render_console(state.console_log)}
    </form>
    """


def render_signal_cell(value: str) -> str:
    class_name = "signal-good" if value.strip().lower() == "good" else ""
    return f'<td class="{class_name}">{html.escape(value)}</td>'


def fmt_number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def ceil_to_tick(value: float, tick_size: float = 0.05) -> float:
    if tick_size <= 0:
        return round(value, 2)
    return round(math.ceil(value / tick_size) * tick_size, 2)


def floor_to_tick(value: float, tick_size: float = 0.05) -> float:
    if tick_size <= 0:
        return round(value, 2)
    return round(math.floor(value / tick_size) * tick_size, 2)


def render_analytics_panel(state: PageState) -> str:
    symbols = csv_trading_symbols(read_default_csv_text())
    active_positions: list[dict[str, Any]] = []
    active_error = ""
    if state.active_tab == "analytics":
        try:
            active_positions = open_option_positions()
        except Exception as exc:
            active_error = str(exc)
    links = "".join(
        f'<a class="analytics-chip" href="/analytics?symbol={html.escape(symbol, quote=True)}">{html.escape(symbol)}</a>'
        for symbol in symbols
    )
    active_total_pnl = sum(float(position.get("pnl") or 0) for position in active_positions)
    active_total_class = (
        "pnl-positive" if active_total_pnl > 0 else "pnl-negative" if active_total_pnl < 0 else ""
    )
    active_total_html = (
        '<div class="active-pnl-summary">'
        '<span>Overall P&L</span>'
        f'<strong class="{active_total_class}">{html.escape(display_cell("pnl", active_total_pnl))}</strong>'
        "</div>"
        if active_positions
        else ""
    )
    active_rows = "".join(
        "<tr>"
        f"<td>{render_symbol_value('tradingsymbol', position['tradingsymbol'])}</td>"
        f"<td>{html.escape(str(position['quantity']))}</td>"
        f"<td>{html.escape(position['product'])}</td>"
        f"<td>{html.escape(fmt_number(position['average_price']))}</td>"
        f"<td>{html.escape(fmt_number(position['ltp']))}</td>"
        f"<td>{html.escape(display_cell('pnl', position['pnl']))}</td>"
        "</tr>"
        for position in active_positions
    )
    active_total_row = (
        "<tr class=\"total-row\">"
        "<td><strong>Total</strong></td><td></td><td></td><td></td><td></td>"
        f'<td><strong class="{active_total_class}">{html.escape(display_cell("pnl", active_total_pnl))}</strong></td>'
        "</tr>"
        if active_rows
        else ""
    )
    active_section = (
        '<section class="panel active-trades-panel"><div class="panel-title">Active Option Trades</div>'
        f"{active_total_html}"
        '<div class="table-wrap"><table><thead><tr><th>Symbol</th><th>Qty</th><th>Product</th>'
        '<th>Avg</th><th>LTP</th><th>P&L</th></tr></thead>'
        f"<tbody>{active_rows}{active_total_row}</tbody></table></div></section>"
        if active_rows
        else (
            '<section class="panel active-trades-panel"><div class="panel-title">Active Option Trades</div>'
            f'<div class="status">{html.escape(active_error or "No active option trades found.")}</div></section>'
        )
    )
    selected = state.analytics_symbol or (symbols[0] if symbols else "")
    data = state.analytics_data
    detail = ""
    if data:
        decision = data.get("decision", {})
        risk_lights = decision.get("risk_lights", {})
        strength_lights = strategy_strength_lights(data, decision)
        option_type = str(data.get("option_type", "")).upper()
        sell_recommendation = (
            "CALL SELL"
            if option_type == "CE"
            else "PUT SELL"
            if option_type == "PE"
            else "SELL"
        )
        decision_title = (
            f"Decision Labels - {data.get('symbol', '')} - {sell_recommendation} Recommendation"
        )
        if option_type == "CE":
            decision_items = [
                ("SELL CALL", decision.get("sell_call", "N/A")),
                ("BUY CALL", decision.get("buy_call", "N/A")),
            ]
            matrix_headers = "<th>Indicator</th><th>SELL CALL</th><th>BUY CALL</th>"
            signal_rows = "".join(
                "<tr>"
                f"<th>{html.escape(row['indicator'])}</th>"
                f"{render_signal_cell(row['sell_call'])}"
                f"{render_signal_cell(row['buy_call'])}"
                "</tr>"
                for row in decision.get("summary", [])
            )
        elif option_type == "PE":
            decision_items = [
                ("SELL PUT", decision.get("sell_put", "N/A")),
                ("BUY PUT", decision.get("buy_put", "N/A")),
            ]
            matrix_headers = "<th>Indicator</th><th>SELL PUT</th><th>BUY PUT</th>"
            signal_rows = "".join(
                "<tr>"
                f"<th>{html.escape(row['indicator'])}</th>"
                f"{render_signal_cell(row['sell_put'])}"
                f"{render_signal_cell(row['buy_put'])}"
                "</tr>"
                for row in decision.get("summary", [])
            )
        else:
            decision_items = [("Decision", "UNKNOWN")]
            matrix_headers = "<th>Indicator</th><th>Decision</th>"
            signal_rows = ""
        decision_cards = "".join(
            f'<div class="decision-card"><div class="decision-label">{html.escape(label)}</div>'
            f'<div class="decision-value">{html.escape(str(value))}</div></div>'
            for label, value in decision_items
        )
        risk_cards = "".join(
            '<div class="decision-card">'
            f'<div class="decision-label">{html.escape(label)}</div>'
            f'<div class="decision-value signal-{html.escape(color)}">{html.escape(str(value))}</div>'
            "</div>"
            for label, value, color in [
                ("Final SELL signal", risk_lights.get("final_sell", "N/A"), risk_lights.get("final_sell_color", "neutral")),
                ("BUY signal", risk_lights.get("buy_signal", "N/A"), risk_lights.get("buy_signal_color", "neutral")),
                ("Naked CE rule", risk_lights.get("naked_ce_signal", "N/A"), "red" if risk_lights.get("naked_ce_signal", "").startswith("RED") else "neutral"),
                ("Cash rule", risk_lights.get("cash_rule", "N/A"), "neutral"),
            ]
        )
        risk_rows = "".join(
            "<tr>"
            f"<th>{html.escape(str(name))}</th>"
            f"<td>{html.escape(fmt_number(value) if isinstance(value, (int, float)) else str(value))}</td>"
            f'<td class="signal-{html.escape(color)}">{html.escape(color.upper())}</td>'
            f"<td>{html.escape(str(note))}</td>"
            "</tr>"
            for name, value, color, note in risk_lights.get("rows", [])
        )
        seller_rows = "".join(
            f"<tr><th>{label}</th><td>{html.escape(fmt_number(value, 6))}</td></tr>"
            for label, value in [
                ("Seller Delta", risk_lights.get("seller_delta")),
                ("Seller Gamma", risk_lights.get("seller_gamma")),
                ("Seller Theta / day", risk_lights.get("seller_theta")),
                ("Seller Vega / 1% IV", risk_lights.get("seller_vega")),
                ("Theta yield %", risk_lights.get("theta_yield_pct")),
                ("Vega risk %", risk_lights.get("vega_risk_pct")),
                ("Gamma 1% delta change", risk_lights.get("gamma_1pct")),
            ]
        )
        strength_rows = "".join(
            "<tr>"
            f"<th>{html.escape(str(name))}</th>"
            f'<td class="strength-{html.escape(color)}">{html.escape(str(value))}</td>'
            f'<td class="strength-{html.escape(color)}">{html.escape(color.upper())}</td>'
            f"<td>{html.escape(str(note))}</td>"
            "</tr>"
            for name, value, color, note in strength_lights["rows"]
        )
        rows = [
            ("Underlying", data["underlying"]),
            ("Spot", fmt_number(data["spot"])),
            ("Option LTP", fmt_number(data["option_price"])),
            ("Strike", fmt_number(data["strike"])),
            ("OTM distance", f'{fmt_number(decision.get("otm_distance"))}%'),
            ("Expiry", data["expiry"]),
            ("DTE", data["dte"]),
            ("OI", data["oi"]),
            ("Implied Volatility", f'{fmt_number(data["iv_percent"])}%'),
            ("Delta", fmt_number(data["delta"], 4)),
            ("Gamma", fmt_number(data["gamma"], 6)),
            ("Theta / day", fmt_number(data["theta"], 4)),
            ("Vega / 1% IV", fmt_number(data["vega"], 4)),
            ("BUY Probability of Profit", f'{fmt_number(data["buy_pop"])}%'),
            ("SELL Probability of Profit", f'{fmt_number(data["sell_pop"])}%'),
            ("Expected Move", fmt_number(data["expected_move"])),
            ("Expected Upper Range", fmt_number(decision.get("upper_range"))),
            ("Expected Lower Range", fmt_number(decision.get("lower_range"))),
            ("Breakeven", fmt_number(decision.get("breakeven"))),
            ("PCR", fmt_number(data["pcr"])),
            ("Max Pain", fmt_number(data["max_pain"])),
            ("Support from OI", fmt_number(data["support"])),
            ("Resistance from OI", fmt_number(data["resistance"])),
            ("Chain strikes used", data["chain_rows"]),
            ("IV Rank", data["iv_rank"]),
            ("IV Percentile", data["iv_percentile"]),
        ]
        cells = "".join(
            f"<tr><th>{html.escape(str(label))}</th><td>{html.escape(str(value))}</td></tr>"
            for label, value in rows
        )
        final_sell = risk_lights.get("final_sell", "N/A")
        final_sell_color = risk_lights.get("final_sell_color", "neutral")
        buy_signal = risk_lights.get("buy_signal", "N/A")
        buy_signal_color = risk_lights.get("buy_signal_color", "neutral")
        final_strength = strength_lights.get("final", "N/A")
        final_strength_color = strength_lights.get("color", "neutral")
        headline_action = (
            final_strength
            if str(final_strength).upper() not in {"N/A", "NONE", ""}
            else final_sell
        )
        support_resistance = (
            f'{fmt_number(data.get("support"))} / {fmt_number(data.get("resistance"))}'
        )
        analytics_metric_cards = "".join(
            '<div class="analytics-metric">'
            f'<span>{html.escape(label)}</span>'
            f'<strong class="{html.escape(css_class)}">{html.escape(str(value))}</strong>'
            f'<small>{html.escape(note)}</small>'
            "</div>"
            for label, value, css_class, note in [
                ("Spot", fmt_number(data["spot"]), "", f'Underlying {data["underlying"]}'),
                ("Strike", fmt_number(data["strike"]), "", f'{option_type} contract'),
                ("SELL POP", f'{fmt_number(data["sell_pop"])}%', "pnl-positive", "Income probability"),
                ("OTM", f'{fmt_number(decision.get("otm_distance"))}%', "pnl-positive", "Distance from spot"),
                ("IV", f'{fmt_number(data["iv_percent"])}%', "", "Premium quality"),
                ("PCR", fmt_number(data["pcr"]), "", "OI pressure"),
                ("DTE", str(data["dte"]), "", f'Expiry {data["expiry"]}'),
                ("Support / Resistance", support_resistance, "", "OI levels"),
            ]
        )
        primary_action_cards = "".join(
            '<div class="analytics-action-card">'
            f'<span>{html.escape(label)}</span>'
            f'<strong class="signal-{html.escape(color)}">{html.escape(str(value))}</strong>'
            "</div>"
            for label, value, color in [
                ("SELL decision", final_sell, final_sell_color),
                ("BUY decision", buy_signal, buy_signal_color),
                ("Strategy strength", final_strength, final_strength_color),
            ]
        )
        detail = (
            '<section class="panel analytics-command-panel">'
            '<div class="analytics-command-head">'
            '<div>'
            '<div class="panel-title">Option Analytics</div>'
            f'<h2>{html.escape(str(data.get("symbol", "")))}</h2>'
            f'<p>{html.escape(sell_recommendation)} review for wheel/income decision making.</p>'
            '</div>'
            f'<div class="analytics-verdict strength-{html.escape(final_strength_color)}">'
            '<span>Primary read</span>'
            f'<strong>{html.escape(str(headline_action))}</strong>'
            '</div>'
            '</div>'
            f'<div class="analytics-action-row">{primary_action_cards}</div>'
            f'<div class="analytics-metric-grid">{analytics_metric_cards}</div>'
            '</section>'
            '<section class="analytics-two-column">'
            '<div class="panel analytics-compact-panel">'
            '<div class="panel-title">Decision Labels</div>'
            f'<div class="decision-grid compact-decisions">{decision_cards}</div>'
            '</div>'
            '<div class="panel analytics-compact-panel">'
            '<div class="panel-title">Risk Summary</div>'
            f'<div class="decision-grid compact-decisions">{risk_cards}</div>'
            '</div>'
            '</section>'
            '<section class="panel analytics-review-panel"><div class="panel-title">Risk Lights</div>'
            '<div class="table-wrap"><table class="analytics-table analytics-review-table">'
            "<tr><th>Indicator</th><th>Value</th><th>Strength</th><th>Meaning</th></tr>"
            f"{risk_rows}</table></div></section>"
            '<section class="panel analytics-review-panel"><div class="panel-title">Strategy Strength</div>'
            '<div class="table-wrap"><table class="analytics-table analytics-review-table">'
            "<tr><th>Indicator</th><th>Value</th><th>Strength</th><th>Rule</th></tr>"
            f"{strength_rows}</table></div></section>"
            '<section class="analytics-two-column">'
            '<div class="panel analytics-compact-panel"><div class="panel-title">Seller Greeks</div>'
            '<div class="table-wrap"><table class="analytics-table analytics-mini-table">'
            f"{seller_rows}</table></div></div>"
            '<div class="panel analytics-compact-panel"><div class="panel-title">Decision Matrix</div>'
            '<div class="table-wrap"><table class="analytics-table analytics-mini-table">'
            f"<tr>{matrix_headers}</tr>"
            f"{signal_rows}</table></div></div>"
            '</section>'
            '<section class="panel analytics-review-panel"><div class="panel-title">Full Contract Details</div>'
            '<div class="table-wrap"><table class="analytics-table analytics-details-table">'
            f"{cells}</table></div></section>"
        )

    return f"""
    <form id="analytics-panel" method="post" action="/analytics/load"{'' if state.active_tab == 'analytics' else ' style="display:none"'}>
      <section class="panel analytics-picker-panel">
        <div class="panel-title">Load Option Analytics</div>
        <div class="analytics-links">{links or '<span class="status">No CSV symbols found.</span>'}</div>
        <div class="analytics-form">
          {render_input("analytics_symbol", "Trading symbol", selected)}
          {env_hidden_fields_for_render()}
          <button type="submit" formaction="/analytics/load">Load Analytics</button>
        </div>
      </section>
      {detail}
      {active_section}
      {render_console(state.console_log)}
    </form>"""


def strength_class(color: Any) -> str:
    text = str(color or "neutral").lower()
    if text == "green":
        return "signal-green"
    if text == "yellow":
        return "signal-yellow"
    if text == "red":
        return "signal-red"
    if text in {"lightgreen", "lightcoral", "orange"}:
        return f"strength-{text}"
    return "signal-neutral"


def indicator_text_from_color(color: Any) -> str:
    text = str(color or "neutral").lower()
    if text in {"green", "lightgreen"}:
        return "GREEN"
    if text == "yellow":
        return "YELLOW"
    if text in {"red", "lightcoral"}:
        return "RED"
    if text == "orange":
        return "ORANGE"
    return "N/A"


def compact_indicator_cell(color: Any, detail: Any) -> str:
    return (
        f'<td class="{strength_class(color)} compact-indicator" '
        f'title="{html.escape(str(detail or ""), quote=True)}">'
        f"{indicator_text_from_color(color)}</td>"
    )


def color_profit(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if amount > 7500:
        return "green"
    if amount >= 5000:
        return "yellow"
    return "red"


def color_pop(value: Any) -> str:
    try:
        pop = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if pop > 85:
        return "green"
    if pop >= 70:
        return "yellow"
    return "red"


def research_indicator_cell(row: dict[str, Any], group: str, name: str) -> str:
    source = row.get(group) or {}
    item = source.get(name)
    if not item:
        return '<td class="signal-neutral">N/A</td>'
    _, value, color, note = item
    if isinstance(value, (int, float)):
        value_text = fmt_number(value)
    else:
        value_text = str(value)
    return (
        f'<td class="{strength_class(color)}" title="{html.escape(str(note), quote=True)}">'
        f"{html.escape(value_text)}<br><small>{html.escape(str(color).upper())}</small></td>"
    )


def research_indicator_color(row: dict[str, Any], group: str, name: str) -> str:
    source = row.get(group) or {}
    item = source.get(name)
    if not item:
        return "neutral"
    return str(item[2])


def color_score_value(color: str) -> float:
    color = str(color or "").lower()
    if color in {"green", "lightgreen"}:
        return 1.0
    if color == "yellow":
        return 0.5
    return 0.2


def row_sell_score(row: dict[str, Any]) -> tuple[str, str]:
    colors = [
        row.get("sell_color"),
        row.get("strategy_color"),
        color_profit(row.get("max_profit")),
        color_pop(row.get("sell_pop")),
        research_indicator_color(row, "risk_rows", "Delta / POP"),
        research_indicator_color(row, "risk_rows", "Gamma 1% move risk"),
        research_indicator_color(row, "risk_rows", "Theta / premium / day"),
        research_indicator_color(row, "risk_rows", "Vega / premium"),
        research_indicator_color(row, "risk_rows", "Coverage / cash backing"),
        research_indicator_color(row, "strength_rows", "OTM distance"),
        research_indicator_color(row, "strength_rows", "Implied Volatility"),
        research_indicator_color(row, "strength_rows", "PCR"),
        research_indicator_color(row, "strength_rows", "Strike vs OI"),
    ]
    raw_score = sum(color_score_value(color) for color in colors)
    score = raw_score * 2
    max_score = len(colors) * 2
    ratio = score / max_score if max_score else 0
    score_text = f"{score:.1f}/{max_score}"
    if ratio >= 0.75:
        return "lightgreen", f"SELL score {score_text}"
    if ratio >= 0.55:
        return "yellow", f"SELL score {score_text}"
    return "lightcoral", f"SELL score {score_text}"


def render_research_panel(state: PageState) -> str:
    rows = state.research_rows or []
    table_rows = "".join(
        "<tr>"
        f'<td class="{strength_class(row_sell_score(row)[0])}" title="{html.escape(row_sell_score(row)[1], quote=True)}">{render_symbol_value("tradingsymbol", row.get("symbol", ""))}</td>'
        f'<td class="{strength_class(row_sell_score(row)[0])}">{html.escape(row_sell_score(row)[1].replace("SELL score ", ""))}</td>'
        f"<td>{html.escape(str(row.get('option_type', '')))}</td>"
        f"{compact_indicator_cell(row.get('sell_color'), row.get('sell_signal'))}"
        f"{compact_indicator_cell(row.get('buy_color'), row.get('buy_signal'))}"
        f"{compact_indicator_cell(row.get('strategy_color'), row.get('strategy_strength'))}"
        f'<td class="{strength_class(research_indicator_color(row, "risk_rows", "Delta / POP"))}">{html.escape(fmt_number(row.get("delta")))}</td>'
        f'<td class="{strength_class(color_profit(row.get("max_profit")))}">{html.escape(fmt_number(row.get("max_profit")))}</td>'
        f'<td class="{strength_class(color_pop(row.get("sell_pop")))}">{html.escape(fmt_number(row.get("sell_pop")))}%</td>'
        f'<td class="{strength_class(research_indicator_color(row, "risk_rows", "Gamma 1% move risk"))}">{html.escape(fmt_number(row.get("gamma_1pct")))}</td>'
        f'<td class="{strength_class(research_indicator_color(row, "risk_rows", "Theta / premium / day"))}">{html.escape(fmt_number(row.get("theta_yield_pct")))}%</td>'
        f'<td class="{strength_class(research_indicator_color(row, "risk_rows", "Vega / premium"))}">{html.escape(fmt_number(row.get("vega_risk_pct")))}%</td>'
        f'<td class="{strength_class(research_indicator_color(row, "strength_rows", "OTM distance"))}">{html.escape(fmt_number(row.get("otm_distance")))}%</td>'
        f'<td class="{strength_class(research_indicator_color(row, "strength_rows", "Implied Volatility"))}">{html.escape(fmt_number(row.get("iv_percent")))}%</td>'
        f'<td class="{strength_class(research_indicator_color(row, "strength_rows", "PCR"))}">{html.escape(fmt_number(row.get("pcr")))}</td>'
        f'<td class="{strength_class(research_indicator_color(row, "strength_rows", "Strike vs OI"))}">{html.escape(fmt_number(row.get("support")))} / {html.escape(fmt_number(row.get("resistance")))}</td>'
        f"{research_indicator_cell(row, 'risk_rows', 'Delta / POP')}"
        f"{research_indicator_cell(row, 'risk_rows', 'SELL POP')}"
        f"{research_indicator_cell(row, 'risk_rows', 'Gamma 1% move risk')}"
        f"{research_indicator_cell(row, 'risk_rows', 'Theta / premium / day')}"
        f"{research_indicator_cell(row, 'risk_rows', 'Vega / premium')}"
        f"{research_indicator_cell(row, 'risk_rows', 'Coverage / cash backing')}"
        f"{research_indicator_cell(row, 'strength_rows', 'OTM distance')}"
        f"{research_indicator_cell(row, 'strength_rows', 'Implied Volatility')}"
        f"{research_indicator_cell(row, 'strength_rows', 'SELL Probability of Profit')}"
        f"{research_indicator_cell(row, 'strength_rows', 'PCR')}"
        f"{research_indicator_cell(row, 'strength_rows', 'Strike vs OI')}"
        f"<td>{html.escape(str(row.get('error', '')))}</td>"
        "</tr>"
        for row in rows
    )
    table = (
        '<section class="panel research-scorecard-panel"><div class="panel-title">CSV Symbol Research Comparison</div>'
        '<div class="research-table-hint">Color guide: green is preferred, yellow means reduce size / wait, red means avoid or review.</div>'
        '<div class="table-wrap research-table-wrap"><table class="research-table"><thead><tr>'
        '<th>Symbol</th><th>Score /26</th><th>Type</th><th>SELL Decision</th><th>BUY Decision</th>'
        '<th>Strategy Strength</th><th>Delta</th><th>Maximum Profit</th><th>SELL POP</th><th>Gamma 1%</th>'
        '<th>Theta/Premium</th><th>Vega/Premium</th><th>OTM</th><th>IV</th><th>PCR</th>'
        '<th>Support / Resistance</th>'
        '<th>Risk: Delta / POP</th><th>Risk: SELL POP</th><th>Risk: Gamma</th>'
        '<th>Risk: Theta</th><th>Risk: Vega</th><th>Risk: Coverage/Cash</th>'
        '<th>Strength: OTM</th><th>Strength: IV</th><th>Strength: SELL POP</th>'
        '<th>Strength: PCR</th><th>Strength: Strike vs OI</th><th>Error</th></tr></thead>'
        f"<tbody>{table_rows}</tbody></table></div></section>"
        if rows
        else ""
    )
    return f"""
    <form id="research-panel" method="post" action="/research/load"{'' if state.active_tab == 'research' else ' style="display:none"'}>
      {env_hidden_fields_for_render()}
      <section class="panel">
        <div class="panel-title">Research</div>
        <p class="status">Compare every trading symbol from {html.escape(default_csv_label())} for SELL CALL / SELL PUT decisions using live Kite analytics.</p>
        <div class="actions">
          <button type="submit" formaction="/research/load">Run Research on CSV Symbols</button>
        </div>
      </section>
      {table}
      {render_console(state.console_log)}
    </form>"""


def render_positions_panel(
    state: PageState,
    position_orders_payload: str = "",
    position_orders_table: str = "",
    position_execute_button: str = "",
) -> str:
    if state.active_tab == "positions" and state.positions_rows is None:
        try:
            state.positions_rows, state.positions_summary = positions_research()
        except Exception as exc:
            state.error = f"{exc}\n\n{traceback.format_exc()}"
    rows = state.positions_rows or []
    summary = state.positions_summary or {}
    def compact_signal(value: Any) -> str:
        text = str(value or "").upper()
        if "GREEN" in text:
            return "GREEN"
        if "YELLOW" in text:
            return "YELLOW"
        if "RED" in text:
            return "RED"
        if "AVOID" in text:
            return "AVOID"
        return text or "N/A"

    def metric_class(value: Any) -> str:
        try:
            return "pnl-positive" if float(value or 0) >= 0 else "pnl-negative"
        except (TypeError, ValueError):
            return ""

    summary_cards = "".join(
        f'<div class="decision-card"><div class="decision-label">{html.escape(label)}</div>'
        f'<div class="decision-value">{html.escape(value)}</div></div>'
        for label, value in [
            ("Active option trades", str(summary.get("count", 0))),
            ("Current P&L", fmt_number(summary.get("total_pnl"))),
            ("Margin required", fmt_number(summary.get("total_deployed"))),
            ("Return on margin", f"{fmt_number(summary.get('return_pct'))}%"),
        ]
    )
    table_rows = "".join(
        (
        "<tr>"
        f"<td class=\"position-symbol-cell\">{render_symbol_value('tradingsymbol', row.get('symbol', ''))}<span>{html.escape(str(row.get('product', '')))} | Qty {html.escape(str(row.get('quantity', '')))}</span></td>"
        f"<td><strong>{html.escape(fmt_number(row.get('ltp')))}</strong><span>Avg {html.escape(fmt_number(row.get('average_price')))}</span></td>"
        f'<td class="{metric_class(row.get("pnl"))}"><strong>{html.escape(display_cell("pnl", row.get("pnl", "")))}</strong><span>{html.escape(fmt_number(row.get("return_pct")))}% on margin</span></td>'
        f'<td class="{strength_class("green" if (row.get("captured_pct") is not None and float(row.get("captured_pct") or 0) >= 50) else row.get("capture_color"))}"><strong>{html.escape(fmt_number(row.get("captured_pct")))}%</strong><span>Captured</span></td>'
        f"<td><strong>{html.escape(fmt_number(row.get('remaining_premium')))}</strong><span>{html.escape(fmt_number(row.get('remaining_pct')))}% remaining</span></td>"
        f'<td class="{strength_class(row.get("capture_color"))}"><strong>{html.escape(str(row.get("capture_action", "")))}</strong><span>{html.escape(str(row.get("capture_detail", "")))}</span></td>'
        "<td>"
        + (
            f'<button type="submit" class="book-profit-button compact-action-button" formaction="/positions/close-buy" name="close_symbol" value="{html.escape(str(row.get("symbol", "")), quote=True)}">BUY -10%</button>'
            if int(row.get("quantity") or 0) < 0
            and (
                (row.get("captured_pct") is not None and abs(float(row.get("captured_pct") or 0)) >= 50)
                or float(row.get("return_pct") or 0) <= -40
            )
            else '<span class="commodity-wait">Wait</span>'
        )
        + "</td>"
        f"<td><strong>{html.escape(fmt_number(row.get('deployed')))}</strong><span>Required</span></td>"
        f'<td class="{strength_class(row.get("buy_color"))}"><strong>{html.escape(compact_signal(row.get("buy_signal")))}</strong><span>{html.escape(str(row.get("buy_signal", "")))}</span></td>'
        f'<td><strong>{html.escape(fmt_number(row.get("sell_pop")))}%</strong><span>SELL POP</span></td>'
        f'<td><strong>{html.escape(fmt_number(row.get("otm_distance")))}%</strong><span>OTM</span></td>'
        f'<td class="{strength_class(row.get("sell_color"))}"><strong>{html.escape(compact_signal(row.get("sell_signal")))}</strong><span>{html.escape(str(row.get("sell_signal", "")))}</span></td>'
        f'<td class="{strength_class(row.get("strategy_color"))}"><strong>{html.escape(compact_signal(row.get("strategy_strength")))}</strong><span>{html.escape(str(row.get("strategy_strength", "")))}</span></td>'
        f"<td><strong>{html.escape(fmt_number(row.get('delta')))}</strong><span>Delta</span></td>"
        f"<td><strong>{html.escape(fmt_number(row.get('iv_percent')))}%</strong><span>IV</span></td>"
        f"<td><strong>{html.escape(fmt_number(row.get('pcr')))}</strong><span>PCR</span></td>"
        f"<td><strong>{html.escape(fmt_number(row.get('support')))} / {html.escape(fmt_number(row.get('resistance')))}</strong><span>Support / resistance</span></td>"
        f"<td>{html.escape(str(row.get('error', '')))}</td>"
        "</tr>"
        )
        for row in rows
    )
    table = (
        '<section class="panel positions-analytics-panel"><div class="panel-title">Active Position Analytics</div>'
        '<div class="research-table-hint">Premium capture: book sold options at 50-70% decay; roll near expiry if capture is not enough.</div>'
        '<div class="table-wrap positions-table-wrap"><table class="positions-table"><thead><tr>'
        '<th>Position</th><th>LTP / Avg</th><th>P&L</th><th>Captured</th><th>Remaining</th><th>Exit</th><th>Action</th><th>Margin</th><th>Buy</th>'
        '<th>POP</th><th>OTM</th><th>Sell</th><th>Strength</th><th>Delta</th>'
        '<th>IV</th><th>PCR</th><th>S / R</th><th>Error</th></tr></thead>'
        f"<tbody>{table_rows}</tbody></table></div></section>"
        if rows
        else ""
    )
    return f"""
    <form id="positions-panel" method="post" action="/positions-research/load"{'' if state.active_tab == 'positions' else ' style="display:none"'}>
      {env_hidden_fields_for_render()}
      <input type="hidden" name="position_orders_payload" value="{html.escape(position_orders_payload, quote=True)}">
      <section class="panel calm-hero-panel">
        <div>
          <p class="calm-quote">"Small drops makes the ocean"</p>
          <p class="status">Analysis of current Positions | P&L, margin, premium capture and roll signals.</p>
        </div>
        <div class="actions">
          <button type="submit" formaction="/positions-research/load">Load Active Positions</button>
          <button type="submit" formaction="/positions/load">Get Current Position / Preview BUY</button>
          {position_execute_button}
        </div>
      </section>
      <section class="panel"><div class="panel-title">Positions Summary</div><div class="decision-grid">{summary_cards}</div></section>
      {table}
      {position_orders_table}
      {render_results(state.position_results)}
      <section class="panel calm-options-panel">
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
      {render_console(state.console_log)}
    </form>"""


def render_commodity_panel(state: PageState) -> str:
    panel_style = "" if state.active_tab == "commodity" else ' style="display:none"'
    holdings = state.commodity_holdings
    holdings_error = state.commodity_error
    if holdings is None and state.active_tab == "commodity":
        try:
            holdings = commodity_etf_holdings()
        except Exception as exc:
            holdings = []
            holdings_error = str(exc)
    holding_rows = "".join(
        "<tr>"
        f"<td><strong>{html.escape(str(row.get('symbol', '')))}</strong><span>{html.escape(str(row.get('label', '')))}</span></td>"
        f"<td>{html.escape(str(row.get('quantity', 0)))}</td>"
        f"<td>{html.escape(str(row.get('source', '')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('investment')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('market_value')))}</td>"
        f"<td class=\"{'pnl-positive' if float(row.get('pnl') or 0) >= 0 else 'pnl-negative'}\">{html.escape(fmt_number(row.get('pnl')))}</td>"
        f"<td class=\"{'pnl-positive' if (row.get('profit_pct') or 0) >= 0 else 'pnl-negative'}\">{html.escape(fmt_number(row.get('profit_pct')))}%</td>"
        "<td>"
        + (
            '<form class="commodity-confirm-form" method="post" action="/commodity/sell">'
            f"{env_hidden_fields_for_render()}"
            f'<input type="hidden" name="commodity_symbol" value="{html.escape(str(row.get("symbol", "")), quote=True)}">'
            '<input type="hidden" name="commodity_confirmed" value="0">'
            '<button type="submit" class="book-profit-button">BOOK profit</button>'
            "</form>"
            if row.get("book_profit")
            else (
                f'<span class="commodity-wait">Hold / wait | Target {html.escape(fmt_number(row.get("profit_target_pct"), 0))}%'
                + (
                    f' | RSI {html.escape(fmt_number(row.get("rsi")))}'
                    if row.get("rsi") is not None
                    else ""
                )
                + "</span>"
            )
        )
        + "</td>"
        "</tr>"
        for row in holdings or []
    )
    holdings_error_html = f'<div class="status">{html.escape(holdings_error)}</div>' if holdings_error else ""
    holdings_empty_html = (
        '<tr><td colspan="8" class="status">No commodity ETF holdings found.</td></tr>'
        if not holding_rows and not holdings_error
        else ""
    )
    holdings_block = (
        '<section class="panel commodity-holdings-panel">'
        '<div class="panel-title">Current ETF Holdings</div>'
        '<form method="post" action="/commodity/refresh">'
        f"{env_hidden_fields_for_render()}"
        '<div class="actions"><button type="submit">Refresh Current Holdings</button></div>'
        '</form>'
        '<div class="table-wrap"><table class="commodity-holdings-table"><thead><tr>'
        '<th>ETF</th><th>Unit</th><th>Source</th><th>Investment Amount</th><th>Market Value</th><th>Profit</th><th>% Profit</th><th>Action</th>'
        f'</tr></thead><tbody>{holding_rows}{holdings_empty_html}</tbody></table></div>'
        f"{holdings_error_html}"
        "</section>"
    )
    strategy_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['label']))}<strong>{html.escape(str(item['symbol']))}</strong></td>"
        f"<td>{int(float(item['allocation']) * 100)}%</td>"
        f"<td>{html.escape(str(item['threshold']))}%</td>"
        f"<td>{html.escape(format_buy_amount(commodity_yearly_base_amount() * float(item['allocation'])))}</td>"
        f"<td>{html.escape(format_buy_amount(commodity_yearly_base_amount() * float(item['allocation']) * COMMODITY_MAX_MULTIPLIER))}</td>"
        f"<td>{html.escape(str(item.get('sell_trigger') or (str(int(float(item['profit_target']) * 100)) + '%')))}</td>"
        "</tr>"
        for item in COMMODITY_ETFS
    )
    strategy_block = (
        '<section class="panel commodity-strategy-panel">'
        '<div class="panel-title">ETF Dip-Buy Multiplier Strategy</div>'
        f'<div class="status">Yearly base for {datetime.now().year}: <strong>{html.escape(format_buy_amount(commodity_yearly_base_amount()))}</strong>. Multiplier = floor(day fall / trigger), capped at {COMMODITY_MAX_MULTIPLIER}x. Profit booking target: 25% full basket exit.</div>'
        '<div class="table-wrap"><table class="commodity-holdings-table"><thead><tr>'
        '<th>ETF</th><th>Allocation</th><th>Dip Trigger</th><th>1x Buy Amount</th><th>2x Capped Buy</th><th>Core Sell Trigger</th>'
        f'</tr></thead><tbody>{strategy_rows}</tbody></table></div></section>'
    )
    commodity_action_names = {
        "nasdaq": "NASDAQ",
        "gold": "GOLD",
        "silver": "Silver",
    }
    cards = "".join(
        f"""
        <article class="commodity-card" data-symbol="{html.escape(str(item['symbol']), quote=True)}" data-asset-name="{html.escape(commodity_action_names.get(str(item.get('key')), str(item['symbol'])), quote=True)}" data-threshold="{html.escape(str(item['threshold']), quote=True)}">
          <div class="commodity-meta">
            <span class="commodity-label">{html.escape(str(item['label']))}</span>
            <strong>{html.escape(str(item['symbol']))}</strong>
          </div>
          <div class="commodity-price">...</div>
          <div class="commodity-change">--</div>
          <div class="commodity-threshold">Buy trigger: down {html.escape(str(item['threshold']))}% | Allocation {int(float(item['allocation']) * 100)}% | 1x {html.escape(format_buy_amount(commodity_yearly_base_amount() * float(item['allocation'])))}</div>
          <div class="commodity-action">Wait</div>
          <form class="commodity-buy-form commodity-confirm-form" method="post" action="/commodity/buy">
            {env_hidden_fields_for_render()}
            <input type="hidden" name="commodity_symbol" value="{html.escape(str(item['symbol']), quote=True)}">
            <input type="hidden" name="commodity_confirmed" value="0">
            <button type="submit" class="commodity-buy-button">Add more {html.escape(commodity_action_names.get(str(item.get('key')), str(item['symbol'])))}</button>
          </form>
        </article>
        """
        for item in COMMODITY_ETFS
    )
    return f"""
    <div id="commodity-panel"{panel_style}>
      <section class="panel commodity-panel">
        <div class="panel-title">Commodity ETF Watch</div>
        <div class="status">Tracks ETF day change. Buy amount = yearly base x ETF allocation x dip multiplier, capped at {COMMODITY_MAX_MULTIPLIER}x. Current yearly base: {html.escape(format_buy_amount(commodity_yearly_base_amount()))}.</div>
        <div class="quote-error" id="commodity-error"></div>
        <div class="commodity-grid" id="commodity-grid">{cards}</div>
      </section>
      {render_results(state.commodity_results)}
      {holdings_block}
      {strategy_block}
    </div>"""


def render_income_panel(state: PageState) -> str:
    rows = state.income_rows or []
    summary = state.income_summary or {"overall_pnl": 0, "by_symbol": {}}
    panel_style = "" if state.active_tab == "income" else ' style="display:none"'
    pnl_cards = [
        (
            "Overall monthly P&L",
            fmt_number(summary.get("overall_pnl")),
            "pnl-positive" if float(summary.get("overall_pnl") or 0) >= 0 else "pnl-negative",
        )
    ]
    for item in INCOME_UNDERLYINGS:
        symbol = item["symbol"]
        symbol_summary = (summary.get("by_symbol") or {}).get(symbol, {})
        total_pnl = float(symbol_summary.get("total_pnl") or 0)
        pnl_cards.append(
            (
                f"{symbol} monthly P&L",
                fmt_number(total_pnl),
                "pnl-positive" if total_pnl >= 0 else "pnl-negative",
            )
        )
    pnl_summary_html = "".join(
        f'<div class="income-pnl-card"><span>{html.escape(label)}</span><strong class="{css_class}">{html.escape(value)}</strong></div>'
        for label, value, css_class in pnl_cards
    )
    rule_cards = "".join(
        f'<div class="income-rule"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'
        for label, value in [
            ("Strategy", "Sell monthly 10% OTM PUT"),
            ("Entry", "~5 trading days before monthly expiry"),
            ("Exit", "50-70% premium decay OR roll 5 days before next expiry"),
            ("Position", "Cash-secured, assignment allowed"),
            ("Capital", "Start 15L conservative, 20L comfortable, 25L+ scaling"),
            ("Risk", "Active deployed <=60%, emergency reserve >=40%"),
        ]
    )
    stock_cards = "".join(
        f"""
        <article class="income-stock">
          <div><span>{html.escape(item['symbol'])}</span><strong>{html.escape(item['name'])}</strong></div>
          <p>{html.escape(item['notes'])}</p>
          <div class="income-stock-metrics">
            <span>Capital {html.escape(item['capital'])}</span>
            <span>Return {html.escape(item['annual_return'])}</span>
            <span>Stress {html.escape(item['stress'])}</span>
          </div>
        </article>
        """
        for item in INCOME_UNDERLYINGS
    )
    candidate_rows = "".join(
        "<tr>"
        f"<td><strong>{html.escape(str(row.get('symbol', '')))}</strong><span>{html.escape(str(row.get('name', '')))}</span></td>"
        f"<td>{render_symbol_value('tradingsymbol', row.get('candidate', ''))}<small>{html.escape(str(row.get('roll_note', '')))}</small></td>"
        f"<td>{html.escape(fmt_number(row.get('spot')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('strike')))}</td>"
        f"<td>{html.escape(str(row.get('expiry', '')))}</td>"
        f"<td>{html.escape(str(row.get('trading_days', '')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('option_price')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('sell_limit_price')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('max_profit')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('otm_distance')))}%</td>"
        f"<td>{html.escape(fmt_number(row.get('sell_pop')))}%</td>"
        f"<td>{html.escape(fmt_number(row.get('delta')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('iv_percent')))}%</td>"
        f"<td>{html.escape(fmt_number(row.get('pcr')))}</td>"
        f"<td>{html.escape(str(row.get('event_status', '')))}<small>{html.escape(str(row.get('event_detail', '')))}</small></td>"
        "<td>"
        + (
            f'<button type="submit" class="book-profit-button" formaction="/income/sell-pe" name="income_underlying" value="{html.escape(str(row.get("symbol", "")), quote=True)}">SELL PE</button>'
            if not row.get("error")
            else '<span class="commodity-wait">Review error</span>'
        )
        + f'<small>{html.escape(str(row.get("action", "")))}</small>'
        + f'<small>{html.escape(str(row.get("error", "")))}</small>'
        + "</td>"
        "</tr>"
        for row in rows
    )
    candidate_table = (
        '<section class="panel income-candidates"><div class="panel-title">PFC / CAMS Monthly PE Candidates</div>'
        '<div class="table-wrap"><table><thead><tr>'
        '<th>Stock</th><th>Candidate PE</th><th>CMP</th><th>Strike</th><th>Expiry</th><th>Trading Days</th>'
        '<th>Premium</th><th>Sell Limit +20%</th><th>Maximum Profit</th><th>OTM</th><th>SELL POP</th><th>Delta</th><th>IV</th><th>PCR</th><th>Event Risk</th><th>Action</th>'
        f'</tr></thead><tbody>{candidate_rows}</tbody></table></div></section>'
        if rows
        else ""
    )
    ce_rows = "".join(
        "<tr>"
        f"<td><strong>{html.escape(str(row.get('symbol', '')))}</strong><span>{html.escape(str(row.get('name', '')))}</span></td>"
        f"<td>{html.escape(fmt_number(row.get('spot')))}</td>"
        f"<td>{html.escape(str(row.get('held_qty', '')))}</td>"
        f"<td class=\"{'pnl-positive' if (row.get('stock_pnl') or 0) >= 0 else 'pnl-negative'}\">{html.escape(fmt_number(row.get('stock_pnl')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('stock_return_pct')))}%</td>"
        f"<td>{render_symbol_value('tradingsymbol', row.get('ce_candidate', ''))}<small>{html.escape(str(row.get('ce_roll_note', '')))}</small></td>"
        f"<td>{html.escape(fmt_number(row.get('ce_strike')))}</td>"
        f"<td>{html.escape(str(row.get('ce_expiry', '')))}</td>"
        f"<td>{html.escape(str(row.get('ce_lot_size', '')))}</td>"
        f"<td>{html.escape(str(row.get('covered_qty', '')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('ce_premium')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('ce_max_profit')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('ce_otm_distance')))}%</td>"
        f"<td>{html.escape(fmt_number(row.get('ce_sell_pop')))}%</td>"
        f'<td class="{strength_class(row.get("ce_action_color"))}"><strong>{html.escape(str(row.get("ce_action", "")))}</strong></td>'
        "<td>"
        + (
            f'<button type="submit" class="book-profit-button" formaction="/income/sell-ce" name="income_underlying" value="{html.escape(str(row.get("symbol", "")), quote=True)}">SELL CE</button>'
            if int(row.get("covered_qty") or 0) > 0
            else '<span class="commodity-wait">Need shares</span>'
        )
        + "</td>"
        "</tr>"
        for row in rows
    )
    ce_table = (
        '<section class="panel income-candidates"><div class="panel-title">Covered CALL Candidates From Current Holdings</div>'
        '<div class="status">SELL CE only when actual share holding covers the full option quantity.</div>'
        '<div class="table-wrap"><table><thead><tr>'
        '<th>Stock</th><th>CMP</th><th>Held Shares</th><th>Stock P&L</th><th>Stock Return</th><th>Candidate CE</th><th>Strike</th><th>Expiry</th>'
        '<th>Lot Size</th><th>Covered Qty</th><th>Premium</th><th>Maximum Profit</th><th>OTM</th><th>SELL POP</th><th>Status</th><th>Action</th>'
        f'</tr></thead><tbody>{ce_rows}</tbody></table></div></section>'
        if rows
        else ""
    )
    filters = [
        ("OTM distance", ">=10%", "Do not chase premium at close strikes."),
        ("Timing", "Around 5 trading days before expiry", "Avoid weekly expiry and high gamma pressure."),
        ("Event risk", "No results/dividend/split/news in next 5 days", "Mandatory gap-risk filter."),
        ("Structure", "Neutral/bullish, above 200 DMA preferred", "Avoid vertical breakdown and macro panic."),
        ("Exit", "Close at 50-70% premium decay", "Roll 5 trading days before next expiry if tested."),
        ("Assignment", "Allowed, cash secured", "If assigned, hold shares; later covered calls are allowed."),
    ]
    filter_html = "".join(
        f'<div class="income-filter"><strong>{html.escape(name)}</strong><span>{html.escape(rule)}</span><small>{html.escape(note)}</small></div>'
        for name, rule, note in filters
    )
    return f"""
    <form id="income-panel" method="post" action="/income/load"{panel_style}>
      {env_hidden_fields_for_render()}
      <section class="panel income-hero">
        <div>
          <div class="panel-title">INCOME - Monthly PE Sell Strategy</div>
          <p class="status">Low-stress cash-secured monthly PUT selling for PFC and CAMS. Built for disciplined theta income, assignment readiness, and monthly review.</p>
        </div>
        <div class="actions">
          <button type="submit" formaction="/income/load">Refresh PFC / CAMS Candidates</button>
        </div>
      </section>
      <section class="panel income-pnl-panel"><div class="panel-title">Monthly P&L Summary</div><div class="income-pnl-grid">{pnl_summary_html}</div></section>
      {candidate_table}
      {render_results(state.income_results)}
      <section class="panel income-guideline-panel"><div class="income-rule-grid">{rule_cards}</div></section>
      <section class="panel income-stock-panel"><div class="panel-title">Strategy Stocks</div><div class="income-stock-grid">{stock_cards}</div></section>
      {ce_table}
      <section class="panel"><div class="panel-title">Entry / Exit Validation</div><div class="income-filter-grid">{filter_html}</div></section>
      <section class="panel"><div class="panel-title">Expected Portfolio Behavior</div>
        <div class="income-rule-grid">
          <div class="income-rule"><span>PFC</span><strong>18-22% annualized, moderate stress</strong></div>
          <div class="income-rule"><span>CAMS</span><strong>15-18% annualized, low stress</strong></div>
          <div class="income-rule"><span>Combined</span><strong>~16-20% CAGR, ~1.3-1.7% monthly average</strong></div>
          <div class="income-rule"><span>Best setups</span><strong>After 5-8% correction, IV spike, sideways market, panic week</strong></div>
        </div>
      </section>
      {('<section class="panel">' + render_graceful_error(state.income_error, "INCOME Error") + '</section>') if state.income_error else ''}
      {render_console(state.console_log)}
    </form>"""


def env_hidden_fields_for_render() -> str:
    return (
        f'<input type="hidden" name="api_key" value="{html.escape(env_value("KITE_API_KEY"), quote=True)}">'
        f'<input type="hidden" name="api_secret" value="{html.escape(env_value("KITE_API_SECRET"), quote=True)}">'
        f'<input type="hidden" name="access_token" value="{html.escape(env_value("KITE_ACCESS_TOKEN"), quote=True)}">'
        f'<input type="hidden" name="confirm_live_order" value="{html.escape(env_value("KITE_CONFIRM_LIVE_ORDER"), quote=True)}">'
    )


def render_console(console_log: str) -> str:
    if not console_log.strip():
        return ""
    return (
        '<section class="panel"><div class="panel-title">Kite Console</div>'
        f'<pre class="console">{html.escape(console_log)}</pre></section>'
    )


def render_kite_ip_data(ip_data: list[dict[str, str]] | None) -> str:
    if not ip_data:
        return ""
    rows = "".join(
        "<tr>"
        f"<th>{html.escape(item.get('label', ''))}</th>"
        f"<td><code>{html.escape(item.get('ip') or 'N/A')}</code></td>"
        f"<td>{html.escape(item.get('error') or '')}</td>"
        "</tr>"
        for item in ip_data
    )
    return (
        '<div class="table-wrap"><table class="ip-table">'
        "<thead><tr><th>Type</th><th>IP to allow in Kite</th><th>Error</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def render_market_topper(state: PageState) -> str:
    csv_text = state.csv_text or read_default_csv_text()
    order_symbols = csv_trading_symbols(csv_text)
    underlyings = TOP_WATCHLIST
    stock_quote_cards = "".join(
        '<div class="quote-card" data-symbol="'
        f'{html.escape(underlying, quote=True)}">'
        f'<span class="quote-symbol">{html.escape(underlying)}</span>'
        '<span class="quote-ltp">...</span>'
        '<span class="quote-change">--</span>'
        "</div>"
        for underlying in underlyings
    )
    etf_quote_cards = "".join(
        '<div class="quote-card etf-quote-card" data-symbol="'
        f'{html.escape(str(item["symbol"]), quote=True)}" data-threshold="{html.escape(str(item["threshold"]), quote=True)}">'
        f'<span class="quote-symbol">{html.escape(str(item["symbol"]))}</span>'
        '<span class="quote-ltp">...</span>'
        '<span class="quote-change">--</span>'
        "</div>"
        for item in COMMODITY_ETFS
    )
    quote_cards = stock_quote_cards + etf_quote_cards
    if not quote_cards:
        quote_cards = (
            '<div class="quote-card"><div class="quote-symbol">No tickers</div>'
            '<div class="quote-ltp">Load CSV</div><div class="quote-change">--</div></div>'
        )
    summaries = expiry_summaries(order_symbols)
    if summaries:
        expiry_cards = "".join(
            '<div class="expiry-card">'
            f'<span class="expiry-month">{html.escape(summary["month"])}</span>'
            '<span class="expiry-sep">|</span>'
            f'<span class="expiry-day">Expiry: {html.escape(summary["day"])}</span>'
            '<span class="expiry-sep">|</span>'
            f'<span class="expiry-days">{summary["trading_days"]} trading days remaining</span>'
            "</div>"
            for summary in summaries
        )
        near_expiry = any(0 < summary["trading_days"] <= 5 for summary in summaries)
    else:
        expiry_cards = (
            '<div class="expiry-card"><span class="expiry-month">EXPIRY</span>'
            '<span class="expiry-sep">|</span>'
            '<span class="expiry-day">No option expiry found in CSV symbols</span>'
            '<span class="expiry-sep">|</span>'
            '<span class="expiry-days">Load option symbols like ETERNAL26MAY260CE</span></div>'
        )
        near_expiry = False
    warning_html = (
        '<div class="expiry-warning active">DO NOT take new position 5 trading DAYS near to expiry</div>'
        if near_expiry
        else ""
    )
    quote_date = datetime.now().strftime("%d %b %Y")
    return f"""
    <section class="market-shell top-command-center">
      <div class="rule-strip">
        <div class="rule-card sell-stock">
          <div class="rule-kicker">Rule 1</div>
          <div class="rule-title">SELL CALL only when you hold the stock with lot size</div>
        </div>
        <div class="rule-card sell-put">
          <div class="rule-kicker">Rule 2</div>
          <div class="rule-title">SELL PUT only when you have cash to buy all lots</div>
        </div>
        <div class="mmi-card">
          <div class="rule-kicker">Market Mood Index</div>
          <div class="mmi-value" id="mmi-value">Loading...</div>
          <div class="mmi-line"><span id="mmi-zone">Tickertape MMI</span><span id="mmi-action">| Signal: <strong>Checking...</strong></span></div>
          <a href="{MMI_URL}" target="_blank" rel="noopener">Open MMI</a>
        </div>
      </div>
      <div class="expiry-strip">
        {expiry_cards}
        {warning_html}
      </div>
      <div class="ticker-panel">
        <div class="ticker-title live-title">Kite LTP and Day Change | {quote_date}</div>
        <div class="quote-error" id="quote-error"></div>
        <div class="quote-grid" id="quote-grid">{quote_cards}</div>
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
    etf_buy_amount = state.etf_buy_amount or etf_buy_amount_setting()
    etf_buy_action = etf_buy_action_text(etf_buy_amount)
    alert = ""
    if state.message:
        alert += f'<div class="alert ok">{html.escape(state.message)}</div>'
    if state.error:
        alert += render_graceful_error(state.error)

    orders_table = render_orders_table(state.orders, state.selected_indexes)
    trade_validation_table = render_trade_validation_table(state.trade_validations)
    position_orders_table = render_position_orders_table(
        state.position_orders, state.position_selected_indexes
    )
    execute_button = (
        '<button type="submit" formaction="/execute" class="danger" id="execute-selected-button">Execute Selected</button>'
        if state.rows
        else ""
    )
    execute_after_orders = (
        f'<div class="actions order-execute-actions">{execute_button}</div>'
        if execute_button
        else ""
    )
    position_execute_button = (
        '<button type="submit" formaction="/positions/execute" class="danger">Execute Selected BUY</button>'
        if state.position_orders
        else ""
    )
    place_tab_class = "active" if state.active_tab == "place" else ""
    positions_tab_class = "active" if state.active_tab in {"positions", "positions-research"} else ""
    gpt_tab_class = "active" if state.active_tab == "gpt" else ""
    kite_setup_tab_class = "active" if state.active_tab == "kite-setup" else ""
    analytics_tab_class = "active" if state.active_tab == "analytics" else ""
    research_tab_class = "active" if state.active_tab == "research" else ""
    commodity_tab_class = "active" if state.active_tab == "commodity" else ""
    income_tab_class = "active" if state.active_tab == "income" else ""
    order_management_tab_class = "active" if state.active_tab == "order-management" else ""
    place_panel_style = "" if state.active_tab == "place" else ' style="display:none"'
    gpt_panel_style = "" if state.active_tab == "gpt" else ' style="display:none"'
    kite_setup_panel_style = "" if state.active_tab == "kite-setup" else ' style="display:none"'
    env_panel = f"""
        <section class="panel kite-setup-hero">
          <div>
            <div class="panel-title">Kite Setup</div>
            <p class="status">A calm control room for credentials, access token, ETF amount, and allowed IP checks.</p>
          </div>
          <div class="kite-status-pill">{status}</div>
        </section>
        <div class="kite-setup-grid">
          <section class="panel kite-setup-card credential-card">
            <div class="setup-card-kicker">01</div>
            <div class="panel-title">Environment</div>
            <div class="compact-grid">
              {render_input("api_key", "KITE_API_KEY", state.api_key or env_value("KITE_API_KEY"))}
              {render_input("confirm_live_order", "KITE_CONFIRM_LIVE_ORDER", state.confirm_live_order or env_value("KITE_CONFIRM_LIVE_ORDER"))}
              {render_input("api_secret", "KITE_API_SECRET", state.api_secret or env_value("KITE_API_SECRET"), "password")}
              {render_input("access_token", "KITE_ACCESS_TOKEN", state.access_token or env_value("KITE_ACCESS_TOKEN"), "password")}
            </div>
            {render_checkbox("show_credentials", "Show credential values", False, "Reveals KITE_API_SECRET and KITE_ACCESS_TOKEN in this local browser page.")}
          </section>
          <section class="panel kite-setup-card token-card">
            <div class="setup-card-kicker">02</div>
            <div class="panel-title">Access Token</div>
            <p class="status">Open Kite login, paste the full redirected URL or only <code>request_token</code>, then generate and save today's token.</p>
            <div class="actions">
              <a class="button-link" href="{html.escape(kite_login_url(), quote=True)}" target="_blank" rel="noopener">Open Kite Login</a>
            </div>
            {render_input("kite_request_token", "Redirected URL or request_token", state.kite_request_token)}
            <div class="actions">
              <button type="submit" formaction="/kite-token/generate">Generate and Save Access Token</button>
            </div>
            <p class="status">Saved to <code>.env</code> and applied immediately to this running app.</p>
          </section>
          <section class="panel kite-setup-card etf-card">
            <div class="setup-card-kicker">03</div>
            <div class="panel-title">ETF Buy Setup</div>
            {render_number_input("etf_buy_amount", "ETF buy amount", etf_buy_amount, "100")}
            <div class="kite-action-preview">{html.escape(etf_buy_action)}</div>
            <p class="status">Saved in <code>{html.escape(str(SETTINGS_PATH.name))}</code>.</p>
          </section>
          <section class="panel kite-setup-card ip-card">
            <div class="setup-card-kicker">04</div>
            <div class="panel-title">OpenAI Setup</div>
            <p class="status">Used by the GPT tab to generate Kite-ready CSV from your strategy prompt.</p>
            {render_input("openai_api_key", "OPENAI_API_KEY", state.openai_api_key or env_value("OPENAI_API_KEY"), "password")}
            <p class="status">Saved to <code>.env</code> when you click Save Kite Setup.</p>
          </section>
          <section class="panel kite-setup-card ip-card">
            <div class="setup-card-kicker">05</div>
            <div class="panel-title">Allowed IP</div>
            <p class="status">If Kite blocks orders by IP, add your current public IP in the Kite developer console.</p>
            <div class="actions">
              <button type="submit" formaction="/kite-ip/check">Check Current Public IP</button>
              <a class="inline-link" href="https://developers.kite.trade" target="_blank" rel="noopener">Open Kite Developer Console</a>
            </div>
            {render_kite_ip_data(state.kite_ip_data)}
          </section>
        </div>"""
    env_hidden = env_hidden_fields_for_render()
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kite CSV Trader</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #eef7f6;
      --ink: #17202a;
      --muted: #627084;
      --line: #d6e6e3;
      --panel: #ffffff;
      --panel-soft: #f8fdfc;
      --accent: #0f766e;
      --accent-blue: #1769aa;
      --accent-soft: #ccfbf1;
      --danger: #b42318;
      --ok: #0f766e;
      --warn: #a16207;
      --shadow: 0 14px 34px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background:
        linear-gradient(135deg, #eef7f6 0%, #f7fbff 42%, #f2fbf4 100%);
      color: var(--ink);
    }}
    header {{
      background:
        radial-gradient(circle at 16% 12%, rgba(45, 212, 191, 0.20), transparent 26%),
        linear-gradient(120deg, #0b1220 0%, #123b52 48%, #0f766e 100%);
      border-bottom: 1px solid rgba(153, 246, 228, 0.34);
      padding: 7px 18px;
      color: #ffffff;
      box-shadow: 0 10px 26px rgba(15, 23, 42, 0.16);
    }}
    .header-inner {{
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      display: grid;
      grid-template-columns: minmax(220px, 0.85fr) minmax(300px, 1fr) minmax(280px, 0.95fr);
      align-items: center;
      gap: 14px;
    }}
    .brand-block {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .brand-mark {{
      display: grid;
      place-items: center;
      width: 92px;
      height: 38px;
      border-radius: 12px;
      background: linear-gradient(135deg, #38bdf8, #14b8a6);
      color: #ecfeff;
      font-size: 21px;
      font-weight: 950;
      box-shadow: 0 12px 24px rgba(20, 184, 166, 0.24);
    }}
    header h1 {{ margin: 0 0 2px; font-size: 22px; letter-spacing: 0; }}
    header p {{ margin: 0; color: #d5eef3; font-size: 11.5px; }}
    .naval-quote {{
      margin: 0;
      color: #e0f2fe;
      font-size: 12px;
      font-weight: 800;
      text-align: right;
      line-height: 1.25;
      padding: 8px 10px;
      border: 1px solid rgba(186, 230, 253, 0.2);
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.08);
    }}
    .blessing {{
      color: #fef3c7;
      font-size: 15px;
      font-weight: 900;
      text-align: center;
      white-space: nowrap;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(254, 243, 199, 0.18);
    }}
    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 22px auto 40px;
    }}
    .market-shell {{
      margin-bottom: 18px;
      padding: 12px;
      border: 1px solid #bde8e3;
      border-radius: 18px;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(236, 254, 255, 0.78)),
        #ffffff;
      box-shadow: 0 22px 54px rgba(15, 23, 42, 0.10);
    }}
    .rule-strip {{
      display: grid;
      grid-template-columns: 1.1fr 1.1fr 0.9fr;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .rule-card, .mmi-card {{
      border-radius: 14px;
      padding: 10px 14px;
      color: #ffffff;
      min-height: 78px;
      box-shadow: 0 14px 30px rgba(15, 23, 42, 0.10);
      border: 1px solid rgba(255, 255, 255, 0.18);
    }}
    .sell-stock {{
      background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
      color: #0f3b65;
    }}
    .sell-put {{
      background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
      color: #064e3b;
    }}
    .mmi-card {{
      background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%);
      color: #4c1d95;
    }}
    .rule-kicker {{
      font-size: 10px;
      text-transform: uppercase;
      font-weight: 700;
      color: currentColor;
      opacity: 0.72;
      margin-bottom: 3px;
    }}
    .rule-title {{
      font-size: 17px;
      line-height: 1.04;
      font-weight: 950;
    }}
    .mmi-value {{
      font-size: 18px;
      font-weight: 800;
      line-height: 1;
      margin-bottom: 1px;
    }}
    .mmi-line {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin: 1px 0 2px;
    }}
    .mmi-line span:first-child {{
      color: currentColor;
      opacity: 0.82;
      font-weight: 700;
      font-size: 12px;
    }}
    .mmi-action {{
      color: #4c1d95;
      font-size: 12px;
      font-weight: 700;
    }}
    .mmi-action strong {{
      font-weight: 950;
    }}
    .mmi-card a {{
      color: #5b21b6;
      font-size: 11px;
      font-weight: 700;
    }}
    .ticker-panel {{
      background: rgba(255, 255, 255, 0.94);
      color: var(--ink);
      border-radius: 14px;
      border: 1px solid var(--line);
      overflow: hidden;
      box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
    }}
    .ticker-title {{
      padding: 8px 10px 0;
      color: #0f766e;
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .live-title {{
      padding-top: 8px;
      color: #1769aa;
    }}
    .ticker-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 10px 14px 2px;
    }}
    .ticker-pill {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      border-radius: 999px;
      padding: 5px 10px;
      background: #eef6fb;
      border: 1px solid #cfe4f3;
      color: #0f3b65;
      font-size: 12px;
      font-weight: 800;
    }}
    .quote-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      padding: 4px 8px 8px;
    }}
    .quote-error {{
      display: none;
      margin: 6px 10px 0;
      padding: 8px 10px;
      border-radius: 6px;
      background: #fee2e2;
      color: #991b1b;
      font-size: 12px;
      font-weight: 800;
    }}
    .quote-card {{
      display: inline-flex;
      align-items: baseline;
      gap: 5px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 7px;
      background: #f8fafc;
      min-height: 24px;
    }}
    .quote-card.strong-up {{
      background: #dcfce7;
      border-color: #86efac;
    }}
    .quote-card.strong-down {{
      background: #fee2e2;
      border-color: #fca5a5;
    }}
    .quote-card.etf-quote-card {{
      border-color: #bae6fd;
      background: #f0f9ff;
    }}
    .quote-card.etf-buy {{
      background: #fee2e2;
      border-color: #ef4444;
      box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.18);
    }}
    .quote-symbol {{
      color: var(--muted);
      font-size: 9px;
      font-weight: 800;
    }}
    .quote-ltp {{
      font-size: 12px;
      font-weight: 900;
    }}
    .quote-change {{ 
      font-size: 10px;
      font-weight: 800;
      color: var(--muted);
    }}
    .quote-change.up {{ color: #047857; }}
    .quote-change.down {{ color: #b42318; }}
    header {{
      padding: 7px 18px;
      box-shadow: 0 10px 26px rgba(15, 23, 42, 0.16);
    }}
    .brand-mark {{
      width: 38px;
      height: 38px;
      border-radius: 11px;
      font-size: 17px;
      letter-spacing: 0.02em;
    }}
    header h1 {{ font-size: 22px; margin-bottom: 2px; }}
    header p {{ font-size: 11.5px; }}
    .naval-quote {{
      font-size: 11.5px;
      padding: 6px 10px;
      border-color: rgba(186, 230, 253, 0.28);
    }}
    .blessing {{
      font-size: 14px;
      padding: 7px 12px;
    }}
    main {{
      margin-top: 16px;
    }}
    .top-command-center {{
      padding: 10px;
      margin-bottom: 14px;
      border-radius: 16px;
      background:
        radial-gradient(circle at top left, rgba(34, 211, 238, 0.12), transparent 28%),
        linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(236, 254, 255, 0.82)),
        #ffffff;
      box-shadow: 0 18px 42px rgba(15, 23, 42, 0.09);
    }}
    .top-command-center .rule-strip {{
      grid-template-columns: minmax(230px, 1fr) minmax(260px, 1.05fr) minmax(230px, 0.86fr);
      gap: 10px;
      margin-bottom: 8px;
    }}
    .top-command-center .rule-card,
    .top-command-center .mmi-card {{
      min-height: 58px;
      padding: 8px 12px;
      border-radius: 13px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
    }}
    .top-command-center .rule-kicker {{
      margin-bottom: 2px;
      font-size: 9.5px;
      letter-spacing: 0.03em;
    }}
    .top-command-center .rule-title {{
      max-width: 420px;
      font-size: 15px;
      line-height: 1.02;
    }}
    .top-command-center .mmi-value {{
      font-size: 19px;
    }}
    .top-command-center .mmi-line {{
      margin: 0 0 1px;
    }}
    .top-command-center .mmi-card a {{
      font-size: 10.5px;
    }}
    .top-command-center .expiry-strip {{
      margin-bottom: 8px;
    }}
    .top-command-center .expiry-card {{
      padding: 8px 12px;
      border-radius: 12px;
      box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
    }}
    .top-command-center .expiry-month {{
      font-size: 13px;
    }}
    .top-command-center .expiry-day,
    .top-command-center .expiry-days {{
      font-size: 16px;
    }}
    .top-command-center .ticker-panel {{
      border-radius: 13px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
    }}
    .top-command-center .ticker-title {{
      padding: 6px 10px 0;
      font-size: 10.5px;
    }}
    .top-command-center .quote-grid {{
      gap: 3px;
      padding: 4px 8px 7px;
    }}
    .top-command-center .quote-card {{
      min-height: 22px;
      gap: 4px;
      padding: 2px 6px;
    }}
    .top-command-center .quote-symbol {{
      font-size: 8.5px;
    }}
    .top-command-center .quote-ltp {{
      font-size: 11.5px;
    }}
    .top-command-center .quote-change {{
      font-size: 9.5px;
    }}
    .commodity-panel {{
      border-color: #fed7aa;
      background: linear-gradient(135deg, #ffffff 0%, #fff7ed 44%, #f0fdfa 100%);
    }}
    .commodity-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }}
    .commodity-card {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      background: rgba(255, 255, 255, 0.95);
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
      display: flex;
      flex-direction: column;
      min-height: 270px;
    }}
    .commodity-card.buy-now {{
      background: #fee2e2;
      border-color: #f87171;
      box-shadow: 0 0 0 3px rgba(248, 113, 113, 0.22), 0 16px 36px rgba(185, 28, 28, 0.16);
    }}
    .commodity-meta {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
      min-height: 44px;
    }}
    .commodity-label {{
      color: #475569;
      font-size: 12px;
      font-weight: 800;
      line-height: 1.25;
    }}
    .commodity-meta strong {{
      color: #075985;
      font-size: 13px;
      white-space: nowrap;
    }}
    .commodity-price {{
      margin-top: 10px;
      font-size: 28px;
      line-height: 1;
      font-weight: 950;
      color: #0f172a;
    }}
    .commodity-change {{
      margin-top: 5px;
      font-size: 14px;
      font-weight: 900;
    }}
    .commodity-change.up {{ color: #047857; }}
    .commodity-change.down {{ color: #b91c1c; }}
    .commodity-threshold {{
      margin-top: 8px;
      color: #64748b;
      font-size: 12px;
      font-weight: 800;
      min-height: 34px;
    }}
    .commodity-action {{
      margin-top: auto;
      padding: 8px 10px;
      border-radius: 8px;
      background: #f1f5f9;
      color: #475569;
      font-weight: 900;
      text-align: center;
    }}
    .commodity-card.buy-now .commodity-action {{
      background: #b91c1c;
      color: #ffffff;
      font-size: 16px;
      text-transform: uppercase;
    }}
    .commodity-buy-form {{
      margin-top: 8px;
      width: 100%;
    }}
    .commodity-buy-button {{
      width: 100%;
      border: 0;
      border-radius: 8px;
      padding: 9px 10px;
      background: linear-gradient(135deg, #1769aa, #0f766e);
      color: #ffffff;
      font-weight: 950;
      cursor: pointer;
    }}
    .commodity-card.buy-now .commodity-buy-button {{
      background: linear-gradient(135deg, #b91c1c, #ef4444);
      box-shadow: 0 8px 22px rgba(185, 28, 28, 0.2);
    }}
    .commodity-holdings-panel {{
      border-color: #bbf7d0;
      background: linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%);
    }}
    .commodity-strategy-panel {{
      border-color: #bae6fd;
      background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
    }}
    .commodity-holdings-table {{
      min-width: 980px;
    }}
    .commodity-holdings-table td:first-child strong,
    .commodity-holdings-table td:first-child span {{
      display: block;
    }}
    .commodity-holdings-table td:first-child span {{
      margin-top: 2px;
      color: #64748b;
      font-size: 11px;
      font-weight: 700;
    }}
    .commodity-holdings-table td:first-child strong {{
      margin-top: 2px;
      color: #075985;
    }}
    .book-profit-button {{
      border: 0;
      border-radius: 8px;
      padding: 8px 12px;
      background: linear-gradient(135deg, #047857, #16a34a);
      color: #ffffff;
      font-weight: 950;
      cursor: pointer;
      white-space: nowrap;
    }}
    .commodity-wait {{
      display: inline-block;
      border-radius: 999px;
      padding: 5px 8px;
      background: #f1f5f9;
      color: #64748b;
      font-size: 12px;
      font-weight: 900;
    }}
    .income-hero {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      border-color: #bbf7d0;
      background:
        radial-gradient(circle at top right, rgba(34, 197, 94, 0.15), transparent 26%),
        linear-gradient(135deg, #f0fdf4, #ffffff);
      margin-bottom: 10px;
    }}
    .income-hero .panel-title {{
      color: #064e3b;
      font-size: 18px;
      margin-bottom: 7px;
    }}
    .income-pnl-panel {{
      border-color: #86efac;
      background:
        radial-gradient(circle at top left, rgba(187, 247, 208, 0.45), transparent 32%),
        linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%);
      margin-bottom: 10px;
    }}
    .income-rule-grid,
    .income-stock-grid,
    .income-filter-grid,
    .income-pnl-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 10px;
    }}
    .income-rule,
    .income-stock,
    .income-filter {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.94);
      box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
    }}
    .income-rule span,
    .income-stock span {{
      display: block;
      color: #64748b;
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
      margin-bottom: 5px;
    }}
    .income-rule strong,
    .income-stock strong {{
      display: block;
      color: #0f172a;
      font-size: 14px;
      line-height: 1.3;
    }}
    .income-stock p {{
      color: #334155;
      font-size: 12px;
      line-height: 1.4;
      margin: 8px 0;
    }}
    .income-stock-metrics {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .income-stock-metrics span {{
      border-radius: 999px;
      background: #ecfdf5;
      color: #047857;
      padding: 4px 7px;
      font-size: 11px;
      margin: 0;
      text-transform: none;
    }}
    .income-candidates table {{
      min-width: 1380px;
    }}
    .income-candidates {{
      border-color: #a7f3d0;
      background:
        linear-gradient(135deg, #ffffff 0%, #f8fffd 100%);
      box-shadow: 0 16px 38px rgba(15, 118, 110, 0.08);
    }}
    .income-candidates .panel-title {{
      color: #0f3b65;
      font-size: 17px;
      margin-bottom: 10px;
    }}
    .income-candidates th {{
      background: linear-gradient(135deg, #0f3b65 0%, #0f766e 100%);
      color: #ffffff;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }}
    .income-candidates td {{
      font-size: 12px;
      font-weight: 780;
      vertical-align: middle;
    }}
    .income-candidates td:first-child span,
    .income-candidates small {{
      display: block;
      margin-top: 3px;
      color: #64748b;
      font-size: 11px;
      font-weight: 700;
      max-width: 260px;
      white-space: normal;
    }}
    .income-filter strong,
    .income-filter span,
    .income-filter small {{
      display: block;
    }}
    .income-filter strong {{
      color: #075985;
      margin-bottom: 5px;
    }}
    .income-filter span {{
      color: #0f172a;
      font-weight: 900;
      margin-bottom: 4px;
    }}
    .income-filter small {{
      color: #64748b;
      line-height: 1.35;
    }}
    .income-pnl-card {{
      border: 1px solid #bbf7d0;
      border-radius: 12px;
      padding: 12px;
      background: linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%);
      box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
    }}
    .income-pnl-card:first-child {{
      background: linear-gradient(135deg, #ecfdf5 0%, #ccfbf1 100%);
      border-color: #86efac;
    }}
    .income-pnl-card span {{
      display: block;
      color: #64748b;
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
      margin-bottom: 5px;
    }}
    .income-pnl-card strong {{
      display: block;
      font-size: 22px;
      line-height: 1;
      font-weight: 950;
    }}
    .income-guideline-panel,
    .income-stock-panel {{
      background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
      box-shadow: 0 8px 22px rgba(15, 23, 42, 0.04);
    }}
    .expiry-strip {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .expiry-card {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: 7px;
      background: linear-gradient(135deg, #ffffff 0%, #f0fdfa 100%);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 10px 14px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
    }}
    .expiry-month {{
      color: var(--accent);
      font-size: 15px;
      font-weight: 800;
    }}
    .expiry-day {{
      font-weight: 800;
      font-size: 18px;
    }}
    .expiry-days {{
      color: var(--ink);
      font-weight: 700;
      font-size: 18px;
    }}
    .expiry-sep {{
      color: var(--muted);
      font-weight: 800;
    }}
    .expiry-warning {{
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 8px;
      padding: 14px 16px;
      background: #fff7ed;
      color: #9a3412;
      border: 1px solid #fed7aa;
      font-weight: 900;
      text-align: center;
      max-width: 360px;
    }}
    .expiry-warning.active {{
      background: #fee2e2;
      color: #991b1b;
      border-color: #fecaca;
      animation: expiryFlash 1s infinite alternate;
    }}
    @keyframes expiryFlash {{
      from {{ box-shadow: 0 0 0 rgba(185, 28, 28, 0); transform: scale(1); }}
      to {{ box-shadow: 0 0 18px rgba(185, 28, 28, 0.35); transform: scale(1.01); }}
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
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(248, 253, 252, 0.96));
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: var(--shadow);
    }}
    .trading-actions-panel {{
      border-color: #bae6fd;
      background: linear-gradient(135deg, #ffffff 0%, #eff6ff 46%, #f0fdfa 100%);
    }}
    .trading-actions-panel .panel {{
      box-shadow: none;
      margin: 12px 0;
    }}
    .panel-title {{
      font-weight: 700;
      margin-bottom: 14px;
      font-size: 16px;
      color: #0f3b65;
    }}
    .tabs {{
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      padding: 10px;
      border: 1px solid #bde8e3;
      border-radius: 16px;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(236, 254, 255, 0.84)),
        #ffffff;
      box-shadow: 0 16px 38px rgba(15, 23, 42, 0.08);
      overflow-x: auto;
    }}
    .tab-button {{
      --tab-a: #e2e8f0;
      --tab-b: #f8fafc;
      --tab-ink: #0f172a;
      --tab-shadow: rgba(15, 23, 42, 0.08);
      border: 1px solid rgba(148, 163, 184, 0.34);
      border-radius: 12px;
      background: linear-gradient(135deg, var(--tab-a), var(--tab-b));
      color: var(--ink);
      padding: 10px 14px;
      box-shadow: 0 8px 18px var(--tab-shadow);
      transition: transform 120ms ease, box-shadow 120ms ease, filter 120ms ease;
    }}
    .tab-button:hover {{
      transform: translateY(-1px);
      filter: saturate(1.08);
    }}
    .tab-button[data-tab="place"] {{
      --tab-a: #dbeafe;
      --tab-b: #ecfeff;
      --tab-ink: #075985;
      --tab-shadow: rgba(14, 165, 233, 0.14);
    }}
    .tab-button[data-tab="positions"] {{
      --tab-a: #dcfce7;
      --tab-b: #f0fdf4;
      --tab-ink: #166534;
      --tab-shadow: rgba(34, 197, 94, 0.14);
    }}
    .tab-button[data-tab="analytics"] {{
      --tab-a: #ede9fe;
      --tab-b: #eff6ff;
      --tab-ink: #4338ca;
      --tab-shadow: rgba(99, 102, 241, 0.14);
    }}
    .tab-button[data-tab="research"] {{
      --tab-a: #e0f2fe;
      --tab-b: #f0f9ff;
      --tab-ink: #0369a1;
      --tab-shadow: rgba(2, 132, 199, 0.14);
    }}
    .tab-button[data-tab="income"] {{
      --tab-a: #bbf7d0;
      --tab-b: #fef9c3;
      --tab-ink: #047857;
      --tab-shadow: rgba(22, 163, 74, 0.16);
    }}
    .tab-button[data-tab="commodity"] {{
      --tab-a: #fed7aa;
      --tab-b: #fef3c7;
      --tab-ink: #92400e;
      --tab-shadow: rgba(245, 158, 11, 0.18);
    }}
    .tab-button[data-tab="order-management"] {{
      --tab-a: #fee2e2;
      --tab-b: #fff1f2;
      --tab-ink: #991b1b;
      --tab-shadow: rgba(239, 68, 68, 0.16);
    }}
    .tab-button[data-tab="gpt"] {{
      --tab-a: #ccfbf1;
      --tab-b: #e0f2fe;
      --tab-ink: #0f766e;
      --tab-shadow: rgba(20, 184, 166, 0.16);
    }}
    .tab-button[data-tab="kite-setup"] {{
      --tab-a: #cffafe;
      --tab-b: #ecfeff;
      --tab-ink: #155e75;
      --tab-shadow: rgba(6, 182, 212, 0.16);
    }}
    .tab-button.primary-action {{
      padding: 14px 24px;
      font-size: 16px;
      font-weight: 900;
      color: var(--tab-ink);
    }}
    .tab-button.utility-action {{
      padding: 10px 14px;
      font-size: 13px;
    }}
    .tab-button.active {{
      color: var(--tab-ink);
      border-color: rgba(15, 23, 42, 0.12);
      box-shadow:
        inset 0 0 0 2px rgba(255, 255, 255, 0.58),
        inset 0 -4px 0 rgba(15, 23, 42, 0.12),
        0 12px 26px var(--tab-shadow);
      transform: translateY(-1px);
    }}
    .tab-button.active::after {{
      content: "";
      display: block;
      height: 3px;
      margin-top: 7px;
      border-radius: 999px;
      background: currentColor;
      opacity: 0.72;
    }}
    .tabs {{
      display: grid;
      grid-template-columns: repeat(9, minmax(0, 1fr));
      gap: 6px;
      padding: 8px;
      align-items: stretch;
    }}
    .tab-button,
    .tab-button.primary-action,
    .tab-button.utility-action {{
      --tab-a: #e0f2fe;
      --tab-b: #ecfeff;
      --tab-ink: #0f3b65;
      --tab-shadow: rgba(6, 182, 212, 0.12);
      width: 100%;
      min-height: 46px;
      padding: 9px 8px;
      color: var(--tab-ink);
      font-size: 13px;
      font-weight: 800;
      text-align: center;
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    .tab-button.primary-action {{
      font-size: 13px;
      font-weight: 800;
    }}
    .tab-button.active {{
      transform: none;
      filter: saturate(1.08);
    }}
    .tab-button.active::after {{
      margin-top: 5px;
    }}
    #place-panel,
    #positions-panel,
    #analytics-panel,
    #research-panel,
    #income-panel,
    #commodity-panel,
    #order-management-panel,
    #gpt-panel,
    #kite-setup-panel {{
      padding: 12px;
      border: 1px solid #d7f2ee;
      border-radius: 16px;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.72), rgba(240, 253, 250, 0.72));
      box-shadow: 0 18px 46px rgba(15, 23, 42, 0.06);
      margin-bottom: 18px;
    }}
    #place-panel {{ border-left: 5px solid #38bdf8; }}
    #positions-panel {{ border-left: 5px solid #0f766e; }}
    #analytics-panel, #research-panel {{ border-left: 5px solid #2563eb; }}
    #income-panel {{ border-left: 5px solid #22c55e; }}
    #commodity-panel {{ border-left: 5px solid #f59e0b; }}
    #order-management-panel {{ border-left: 5px solid #ef4444; }}
    #gpt-panel {{ border-left: 5px solid #14b8a6; }}
    #kite-setup-panel {{ border-left: 5px solid #06b6d4; }}
    #place-panel {{
      background: linear-gradient(135deg, rgba(239, 246, 255, 0.9), rgba(236, 254, 255, 0.82));
    }}
    #positions-panel {{
      background: linear-gradient(135deg, rgba(240, 253, 244, 0.92), rgba(236, 254, 255, 0.82));
    }}
    #analytics-panel {{
      background: linear-gradient(135deg, rgba(245, 243, 255, 0.92), rgba(239, 246, 255, 0.84));
    }}
    #research-panel {{
      background: linear-gradient(135deg, rgba(240, 249, 255, 0.92), rgba(236, 254, 255, 0.84));
    }}
    #income-panel {{
      background: linear-gradient(135deg, rgba(240, 253, 244, 0.92), rgba(254, 252, 232, 0.86));
    }}
    #commodity-panel {{
      background: linear-gradient(135deg, rgba(255, 247, 237, 0.94), rgba(254, 243, 199, 0.76));
    }}
    #order-management-panel {{
      background: linear-gradient(135deg, rgba(255, 241, 242, 0.92), rgba(255, 255, 255, 0.82));
    }}
    #gpt-panel {{
      background: linear-gradient(135deg, rgba(240, 253, 250, 0.94), rgba(236, 254, 255, 0.82));
    }}
    #kite-setup-panel {{
      background: linear-gradient(135deg, rgba(236, 254, 255, 0.94), rgba(240, 249, 255, 0.84));
    }}
    label {{ display: block; margin-bottom: 12px; }}
    label span {{ display: block; font-size: 13px; color: var(--muted); margin-bottom: 5px; }}
    input[type="text"], input[type="password"], textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 9px;
      padding: 9px 10px;
      font-size: 14px;
      background: rgba(255, 255, 255, 0.94);
      color: var(--ink);
      box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.04);
    }}
    input[type="text"]:focus, input[type="password"]:focus, textarea:focus {{
      outline: 2px solid rgba(20, 184, 166, 0.18);
      border-color: #5eead4;
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
    .order-execute-actions {{
      justify-content: flex-end;
      padding-top: 8px;
      margin: 4px 0 12px;
      border-top: 1px solid rgba(15, 118, 110, 0.14);
    }}
    .order-position-note {{
      display: inline-block;
      margin: -4px 0 10px;
      padding: 6px 10px;
      border-radius: 999px;
      background: #fff1f2;
      color: #991b1b;
      border: 1px solid #fecdd3;
      font-weight: 850;
    }}
    tr.order-existing-position td {{
      background: #ffe4e6 !important;
      color: #7f1d1d;
    }}
    tr.order-existing-position td a {{
      color: #9f1239;
    }}
    .execution-checks {{
      margin-top: 12px;
      padding-top: 10px;
      border-top: 1px solid var(--line);
    }}
    button {{
      border: 0;
      border-radius: 9px;
      padding: 10px 14px;
      background: linear-gradient(135deg, #1769aa 0%, #0f766e 100%);
      color: #ffffff;
      cursor: pointer;
      font-weight: 700;
      box-shadow: 0 10px 22px rgba(15, 118, 110, 0.18);
    }}
    button.secondary {{ background: #4b5563; }}
    button.danger {{ background: linear-gradient(135deg, #b42318 0%, #7f1d1d 100%); }}
    button:hover, .button-link:hover {{
      transform: translateY(-1px);
      filter: saturate(1.05);
    }}
    .button-link {{
      display: inline-block;
      border-radius: 9px;
      padding: 10px 14px;
      background: linear-gradient(135deg, #1769aa 0%, #0f766e 100%);
      color: #ffffff;
      cursor: pointer;
      font-weight: 700;
      text-decoration: none;
      box-shadow: 0 10px 22px rgba(15, 118, 110, 0.18);
    }}
    .token-title {{
      margin-top: 18px;
    }}
    .kite-setup-hero {{
      display: grid;
      grid-template-columns: 1fr minmax(260px, 0.8fr);
      gap: 14px;
      align-items: center;
      border-color: #a7f3d0;
      background:
        radial-gradient(circle at 12% 0%, rgba(191, 219, 254, 0.86), transparent 34%),
        radial-gradient(circle at 90% 20%, rgba(187, 247, 208, 0.84), transparent 30%),
        linear-gradient(135deg, #f8fafc 0%, #ecfeff 46%, #f0fdf4 100%);
    }}
    .kite-setup-hero .panel-title {{
      color: #064e3b;
      font-size: 22px;
    }}
    .kite-status-pill {{
      padding: 12px;
      border: 1px solid #99f6e4;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.88);
      color: #0f766e;
      font-size: 12px;
      font-weight: 850;
      line-height: 1.55;
      overflow-wrap: anywhere;
    }}
    .kite-setup-grid {{
      display: grid;
      grid-template-columns: minmax(340px, 1.1fr) minmax(320px, 0.9fr);
      gap: 12px;
      padding: 12px;
      border-radius: 12px;
      border: 1px solid #ccfbf1;
      background:
        linear-gradient(135deg, rgba(240, 253, 250, 0.96), rgba(239, 246, 255, 0.96)),
        #f8fafc;
      margin-bottom: 14px;
    }}
    .kite-setup-card {{
      position: relative;
      margin: 0;
      overflow: hidden;
      border-color: #bae6fd;
      background: rgba(255, 255, 255, 0.94);
    }}
    .kite-setup-card::after {{
      content: "";
      position: absolute;
      width: 110px;
      height: 110px;
      right: -42px;
      top: -46px;
      border-radius: 50%;
      background: rgba(167, 243, 208, 0.42);
      pointer-events: none;
    }}
    .setup-card-kicker {{
      display: inline-grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      margin-bottom: 8px;
      background: #ccfbf1;
      color: #0f766e;
      font-weight: 950;
      font-size: 12px;
    }}
    .credential-card {{ grid-row: span 2; }}
    .token-card {{ border-color: #bfdbfe; }}
    .etf-card {{ border-color: #bbf7d0; }}
    .ip-card {{ border-color: #fde68a; }}
    .kite-action-preview {{
      margin-top: 8px;
      padding: 12px;
      border-radius: 10px;
      border: 1px solid #86efac;
      background: #f0fdf4;
      color: #065f46;
      font-weight: 950;
    }}
    .alert {{
      position: relative;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 16px;
      border: 1px solid;
    }}
    .alert.ok {{ color: var(--ok); background: #ecfdf5; border-color: #99f6e4; }}
    .alert.error {{ color: var(--danger); background: #fff1f2; border-color: #fecdd3; }}
    .alert pre {{ margin: 0; white-space: pre-wrap; font-family: Consolas, "Courier New", monospace; }}
    .alert-close {{
      position: absolute;
      top: 8px;
      right: 8px;
      width: 26px;
      height: 26px;
      padding: 0;
      border-radius: 50%;
      background: #fee2e2;
      color: #991b1b;
      border: 1px solid #fecaca;
      font-size: 14px;
      font-weight: 950;
      line-height: 1;
    }}
    .alert-close:hover {{
      background: #fecaca;
    }}
    .graceful-error strong {{
      display: block;
      margin-bottom: 6px;
      padding-right: 34px;
    }}
    .graceful-error details {{
      margin-top: 10px;
      color: var(--text);
    }}
    .graceful-error summary {{
      cursor: pointer;
      font-weight: 900;
      color: #991b1b;
      margin-bottom: 8px;
    }}
    .error-details {{
      width: 100%;
      min-height: 190px;
      resize: vertical;
      padding: 10px;
      border: 1px solid #fecdd3;
      border-radius: 6px;
      background: #fff7f7;
      color: #7f1d1d;
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
      white-space: pre;
    }}
    .live-modal-backdrop {{
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      background: rgba(15, 23, 42, 0.58);
      z-index: 50;
      padding: 20px;
    }}
    .live-modal {{
      width: min(520px, 100%);
      border-radius: 8px;
      background: #ffffff;
      border: 1px solid var(--line);
      box-shadow: 0 24px 80px rgba(15, 23, 42, 0.3);
      padding: 20px;
      text-align: center;
    }}
    .breath-circle {{
      width: 118px;
      height: 118px;
      border-radius: 50%;
      margin: 12px auto;
      background: radial-gradient(circle, #d1fae5 0%, #60a5fa 100%);
      animation: breathe 4s ease-in-out infinite;
    }}
    @keyframes breathe {{
      0%, 100% {{ transform: scale(0.78); opacity: 0.78; }}
      50% {{ transform: scale(1); opacity: 1; }}
    }}
    .breath-text {{
      font-size: 18px;
      font-weight: 900;
      color: var(--accent);
      margin: 8px 0;
    }}
    .countdown {{
      font-size: 34px;
      font-weight: 900;
      color: var(--danger);
    }}
    .modal-actions {{
      display: flex;
      justify-content: center;
      gap: 12px;
      margin-top: 18px;
    }}
    .modal-actions button:disabled {{
      opacity: 0.5;
      cursor: not-allowed;
    }}
    .news-box {{
      margin-top: 14px;
      text-align: left;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #f8fafc;
      max-height: 190px;
      overflow: auto;
    }}
    .news-box h3 {{
      margin: 0 0 8px;
      font-size: 14px;
    }}
    .news-box a {{
      color: var(--accent);
      font-weight: 800;
      text-decoration: none;
    }}
    .news-date {{
      display: block;
      margin-top: 3px;
      font-size: 10px;
      font-weight: 800;
      color: #64748b;
    }}
    .news-box li {{
      margin-bottom: 8px;
      font-size: 12px;
      line-height: 1.35;
      border-radius: 7px;
      padding: 7px 8px;
      list-style-position: inside;
    }}
    .news-sentiment-positive {{
      background: #dcfce7;
      border: 1px solid #86efac;
    }}
    .news-sentiment-negative {{
      background: #fee2e2;
      border: 1px solid #fca5a5;
    }}
    .news-sentiment-neutral {{
      background: #fef9c3;
      border: 1px solid #fde68a;
    }}
    .news-tag {{
      display: inline-block;
      margin-left: 6px;
      font-size: 10px;
      font-weight: 900;
      text-transform: uppercase;
      color: #475569;
    }}
    .guardrail-box {{
      border-color: #bae6fd;
      background: #f8fbff;
      max-height: none;
    }}
    .guardrail-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 7px;
    }}
    .guardrail-grid div {{
      border: 1px solid #cde7e2;
      border-radius: 8px;
      padding: 7px 8px;
      background: #ffffff;
    }}
    .guardrail-grid span {{
      display: block;
      color: #64748b;
      font-size: 10px;
      font-weight: 850;
      text-transform: uppercase;
      margin-bottom: 3px;
    }}
    .guardrail-grid strong {{
      color: #0f3b65;
      font-size: 13px;
      font-weight: 950;
    }}
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
    .symbol-link, .analytics-chip {{
      color: var(--accent);
      font-weight: 800;
      text-decoration: none;
    }}
    .analytics-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .analytics-chip {{
      border: 1px solid #cfe4f3;
      border-radius: 999px;
      background: #eef6fb;
      padding: 6px 10px;
      font-size: 12px;
    }}
    .analytics-form {{
      display: grid;
      grid-template-columns: minmax(240px, 1fr) auto;
      gap: 10px;
      align-items: end;
    }}
    .analytics-table th {{
      width: 260px;
    }}
    .analytics-picker-panel {{
      border-color: #bfdbfe;
      background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
    }}
    .analytics-command-panel {{
      border-color: #c4b5fd;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, rgba(245, 243, 255, 0.95) 48%, rgba(236, 254, 255, 0.92) 100%);
    }}
    .analytics-command-head {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(260px, 0.42fr);
      gap: 16px;
      align-items: stretch;
      margin-bottom: 12px;
    }}
    .analytics-command-head h2 {{
      margin: 0 0 4px;
      font-size: 28px;
      color: #0f172a;
      letter-spacing: 0;
    }}
    .analytics-command-head p {{
      margin: 0;
      color: #526173;
      font-size: 13px;
      font-weight: 700;
    }}
    .analytics-verdict {{
      border-radius: 14px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      border: 1px solid rgba(15, 23, 42, 0.08);
    }}
    .analytics-verdict span,
    .analytics-action-card span,
    .analytics-metric span {{
      display: block;
      color: #64748b;
      font-size: 11px;
      font-weight: 950;
      text-transform: uppercase;
      margin-bottom: 5px;
    }}
    .analytics-verdict strong {{
      display: block;
      font-size: 22px;
      line-height: 1.08;
      overflow-wrap: anywhere;
    }}
    .analytics-action-row,
    .analytics-metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }}
    .analytics-action-card,
    .analytics-metric {{
      border: 1px solid var(--line);
      border-radius: 11px;
      padding: 11px 12px;
      background: rgba(255, 255, 255, 0.88);
      box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
      min-height: 76px;
    }}
    .analytics-action-card strong {{
      display: block;
      font-size: 15px;
      line-height: 1.18;
      overflow-wrap: anywhere;
    }}
    .analytics-metric strong {{
      display: block;
      color: #0f172a;
      font-size: 19px;
      line-height: 1.05;
      font-weight: 950;
    }}
    .analytics-metric small {{
      display: block;
      margin-top: 5px;
      color: #64748b;
      font-size: 11px;
      line-height: 1.25;
      font-weight: 700;
    }}
    .analytics-two-column {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .analytics-compact-panel,
    .analytics-review-panel {{
      border-color: #c7d2fe;
      background: linear-gradient(135deg, #ffffff 0%, #f8fbff 100%);
    }}
    .compact-decisions {{
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }}
    .compact-decisions .decision-card {{
      min-height: 88px;
    }}
    .analytics-review-table th,
    .analytics-review-table td,
    .analytics-mini-table th,
    .analytics-mini-table td,
    .analytics-details-table th,
    .analytics-details-table td {{
      white-space: normal;
      vertical-align: top;
    }}
    .analytics-review-table th:first-child,
    .analytics-details-table th:first-child {{
      width: 220px;
    }}
    .analytics-mini-table {{
      min-width: 520px;
    }}
    .signal-lightgreen {{
      color: #047857;
      font-weight: 900;
      background: #dcfce7;
      border-radius: 4px;
      padding: 2px 4px;
    }}
    .signal-lightcoral {{
      color: #b42318;
      font-weight: 900;
      background: #fee2e2;
      border-radius: 4px;
      padding: 2px 4px;
    }}
    .signal-orange {{
      color: #c2410c;
      font-weight: 900;
      background: #ffedd5;
      border-radius: 4px;
      padding: 2px 4px;
    }}
    .research-table {{
      min-width: 2600px;
      border-collapse: separate;
      border-spacing: 0;
      background: #ffffff;
      box-shadow: none;
    }}
    .research-scorecard-panel {{
      border-color: #a7f3d0;
      background: linear-gradient(135deg, #ffffff 0%, #f0fdfa 100%);
    }}
    .research-table-hint {{
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      margin: -4px 0 10px;
      border-radius: 999px;
      background: #ecfeff;
      color: #155e75;
      border: 1px solid #a5f3fc;
      font-size: 11.5px;
      font-weight: 850;
    }}
    .research-table-wrap {{
      border: 1px solid #cde7e2;
      border-radius: 12px;
      background: #ffffff;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
    }}
    .research-table th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: linear-gradient(135deg, #0f3b65 0%, #0f766e 100%);
      color: #ffffff;
      border-bottom: 0;
      font-size: 12px;
      line-height: 1.15;
      letter-spacing: 0.01em;
      text-transform: uppercase;
      white-space: nowrap;
      padding: 11px 9px;
    }}
    .research-table th:first-child {{
      border-top-left-radius: 10px;
    }}
    .research-table th:last-child {{
      border-top-right-radius: 10px;
    }}
    .research-table td {{
      border-bottom: 1px solid #dbece8;
      border-right: 1px solid rgba(219, 236, 232, 0.72);
      color: #0f172a;
      font-size: 13px;
      font-weight: 750;
      padding: 10px 9px;
    }}
    .research-table td:first-child {{
      font-weight: 950;
      color: #075985;
    }}
    .research-table tbody tr:nth-child(even) td:not(.signal-green):not(.signal-yellow):not(.signal-red):not(.signal-neutral):not(.strength-lightgreen):not(.strength-yellow):not(.strength-orange):not(.strength-lightcoral):not(.strength-neutral) {{
      background: #fbfefd;
    }}
    .research-table tbody tr:hover td {{
      background-color: #e0f2fe;
    }}
    .research-table small {{
      font-size: 10px;
      opacity: 0.9;
    }}
    .positions-analytics-panel {{
      border-color: #a7f3d0;
      background:
        radial-gradient(circle at top left, rgba(204, 251, 241, 0.55), transparent 34%),
        linear-gradient(135deg, #ffffff 0%, #f8fffd 100%);
    }}
    .positions-table-wrap {{
      border: 1px solid #b7e4da;
      border-radius: 14px;
      background: #ffffff;
      box-shadow: 0 14px 30px rgba(15, 118, 110, 0.08);
    }}
    .positions-table {{
      min-width: 1180px;
      border-collapse: separate;
      border-spacing: 0;
      background: #ffffff;
      table-layout: auto;
    }}
    .positions-table th {{
      position: sticky;
      top: 0;
      z-index: 1;
      padding: 7px 8px;
      background: linear-gradient(135deg, #12395b 0%, #0f766e 100%);
      color: #f8fafc;
      border-bottom: 0;
      font-size: 10px;
      line-height: 1.1;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .positions-table th:first-child {{
      border-top-left-radius: 12px;
    }}
    .positions-table th:last-child {{
      border-top-right-radius: 12px;
    }}
    .positions-table td {{
      padding: 6px 8px;
      border-bottom: 1px solid #d8ebe7;
      border-right: 1px solid rgba(216, 235, 231, 0.75);
      color: #0f172a;
      font-size: 12px;
      font-weight: 850;
      vertical-align: middle;
      white-space: nowrap;
    }}
    .positions-table tbody tr:nth-child(even) td:not(.strength-lightgreen):not(.strength-yellow):not(.strength-orange):not(.strength-lightcoral) {{
      background: #fbfefd;
    }}
    .positions-table tbody tr:hover td {{
      background-color: #ecfeff;
    }}
    .positions-table td span,
    .position-symbol-cell span {{
      display: block;
      margin-top: 1px;
      color: #64748b;
      font-size: 9.5px;
      font-weight: 750;
      white-space: normal;
      line-height: 1.15;
    }}
    .positions-table td strong {{
      display: inline-block;
      font-size: 12.5px;
      font-weight: 950;
    }}
    .position-symbol-cell {{
      min-width: 190px;
      max-width: 230px;
    }}
    .position-symbol-cell a,
    .position-symbol-cell strong {{
      color: #006c67;
      font-size: 12.5px;
      font-weight: 950;
      overflow-wrap: anywhere;
    }}
    .positions-table .pnl-positive {{
      background: #ecfdf5;
      color: #047857;
    }}
    .positions-table .pnl-negative {{
      background: #fef2f2;
      color: #b91c1c;
    }}
    .positions-table .strength-lightgreen,
    .positions-table .strength-green {{
      background: #dcfce7;
      color: #047857;
    }}
    .positions-table .strength-yellow {{
      background: #fef9c3;
      color: #a16207;
    }}
    .positions-table .strength-orange {{
      background: #ffedd5;
      color: #c2410c;
    }}
    .positions-table .strength-lightcoral,
    .positions-table .strength-red {{
      background: #fee2e2;
      color: #b91c1c;
    }}
    .validation-panel {{
      border-color: #bfdbfe;
      background: #f8fbff;
    }}
    .cancel-all-panel {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-color: #fecaca;
      background: #fff7f7;
      padding: 12px 16px;
    }}
    .cancel-all-panel .panel-title {{
      margin: 0;
      color: #991b1b;
    }}
    .cancel-all-panel .status {{
      margin: 3px 0 0;
    }}
    .cancel-all-button {{
      min-width: 180px;
      padding: 10px 14px;
      border-radius: 8px;
      border: 0;
      background: #b42318;
      color: #ffffff;
      font-size: 14px;
      font-weight: 950;
      cursor: pointer;
      white-space: nowrap;
    }}
    .order-book-panel {{
      border-color: #bfdbfe;
      background: #f8fbff;
    }}
    .order-book-table {{
      min-width: 1180px;
    }}
    .order-book-table td,
    .order-book-table th {{
      white-space: normal;
      overflow-wrap: anywhere;
      vertical-align: top;
    }}
    .order-edit-input {{
      width: 96px;
      padding: 6px 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font-size: 13px;
      font-weight: 800;
      background: #ffffff;
    }}
    .order-edit-input:disabled {{
      color: var(--muted);
      background: #f1f5f9;
    }}
    .validation-table {{
      min-width: 1040px;
      table-layout: fixed;
    }}
    .validation-table th:nth-child(1) {{ width: 160px; }}
    .validation-table th:nth-child(2) {{ width: 90px; }}
    .validation-table th:nth-child(3) {{ width: 95px; }}
    .validation-table th:nth-child(4) {{ width: 52%; }}
    .validation-table th:nth-child(5) {{ width: 28%; }}
    .validation-table th,
    .validation-table td {{
      vertical-align: top;
      white-space: normal;
      overflow-wrap: anywhere;
      word-break: normal;
    }}
    .validation-table small {{
      font-size: 11px;
      color: #475569;
    }}
    .validation-symbol a {{
      display: block;
      font-weight: 900;
      line-height: 1.2;
    }}
    .validation-symbol span {{
      display: inline-block;
      margin-top: 5px;
      padding: 3px 6px;
      border-radius: 999px;
      background: #e0f2fe;
      color: #075985;
      font-size: 11px;
      font-weight: 900;
    }}
    .validation-overall {{
      text-align: center;
      border-radius: 0;
    }}
    .validation-overall strong,
    .validation-overall small {{
      display: block;
    }}
    .validation-profit {{
      font-weight: 900;
    }}
    .validation-impact {{
      line-height: 1.45;
      color: #334155;
      font-weight: 700;
    }}
    .validation-checks {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 6px;
    }}
    .validation-green {{
      background: #dcfce7;
      color: #047857;
    }}
    .validation-yellow {{
      background: #fef9c3;
      color: #a16207;
    }}
    .validation-red {{
      background: #fee2e2;
      color: #b91c1c;
    }}
    .validation-neutral {{
      background: #f1f5f9;
      color: #475569;
    }}
    .validation-check {{
      border: 1px solid rgba(100, 116, 139, 0.24);
      border-radius: 7px;
      padding: 6px 8px;
      min-height: 58px;
    }}
    .validation-check strong {{
      display: block;
      font-size: 12px;
    }}
    .validation-check span {{
      display: block;
      margin-top: 2px;
      color: #1f2937;
      font-size: 12px;
      line-height: 1.3;
    }}
    .compact-indicator {{
      text-align: center;
      min-width: 76px;
      font-weight: 900;
      letter-spacing: 0.02em;
    }}
    .ip-table th {{
      width: 190px;
    }}
    .ip-table code {{
      background: #f1f5f9;
      border-radius: 4px;
      padding: 3px 5px;
      font-weight: 800;
    }}
    .active-trades-panel {{
      background: #f0fdf4;
      border-color: #86efac;
    }}
    .active-trades-panel .panel-title {{
      color: #047857;
    }}
    .active-pnl-summary {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      margin: 2px 0 10px;
      padding: 7px 10px;
      border: 1px solid #86efac;
      border-radius: 8px;
      background: #ffffff;
      font-weight: 900;
    }}
    .active-pnl-summary span {{
      color: #475569;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .pnl-positive {{
      color: #047857;
    }}
    .pnl-negative {{
      color: #b91c1c;
    }}
    .total-row td {{
      background: #ecfdf5;
      border-top: 2px solid #86efac;
      font-weight: 900;
    }}
    .decision-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }}
    .decision-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #f8fafc;
    }}
    .decision-label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      margin-bottom: 6px;
    }}
    .decision-value {{
      color: var(--ink);
      font-size: 17px;
      font-weight: 900;
      overflow-wrap: anywhere;
    }}
    .calm-hero-panel {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-color: #bfdbfe;
      background:
        linear-gradient(135deg, #f8fafc 0%, #ecfeff 46%, #f0fdf4 100%);
      padding: 10px 14px;
      margin-bottom: 10px;
    }}
    .calm-quote {{
      margin: 0 0 3px;
      color: #0f766e;
      font-size: 15px;
      font-weight: 950;
    }}
    .calm-hero-panel .status {{
      margin: 0;
      font-size: 12px;
    }}
    .calm-hero-panel .actions {{
      margin: 0;
      flex-wrap: nowrap;
      justify-content: flex-end;
    }}
    .calm-hero-panel button {{
      min-height: 34px;
      padding: 8px 12px;
      font-size: 12px;
    }}
    .compact-action-button {{
      min-height: 28px;
      padding: 6px 9px;
      font-size: 11px;
      white-space: nowrap;
    }}
    .calm-options-panel {{
      border-color: #ccfbf1;
      background: linear-gradient(135deg, #ffffff 0%, #f0fdfa 100%);
    }}
    .gpt-hero-panel {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      border-color: #a7f3d0;
      background:
        linear-gradient(135deg, #ecfeff 0%, #f0fdf4 52%, #fff7ed 100%);
    }}
    .gpt-hero-panel .panel-title {{
      color: #065f46;
      font-size: 19px;
    }}
    .gpt-hero-chip {{
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid #99f6e4;
      background: #ffffff;
      color: #0f766e;
      font-size: 12px;
      font-weight: 950;
      white-space: nowrap;
    }}
    .gpt-workspace {{
      display: grid;
      grid-template-columns: minmax(300px, 0.92fr) minmax(360px, 1.08fr);
      gap: 12px;
      padding: 12px;
      border-radius: 12px;
      background:
        linear-gradient(135deg, rgba(240, 253, 244, 0.95), rgba(239, 246, 255, 0.95)),
        #f8fafc;
      border: 1px solid #ccfbf1;
      margin-bottom: 14px;
    }}
    .gpt-card {{
      margin: 0;
      border-color: #bae6fd;
      background: rgba(255, 255, 255, 0.94);
    }}
    .gpt-result-card {{
      border-color: #86efac;
      background: #f0fdf4;
    }}
    .gpt-api-response-card {{
      border-color: #a7f3d0;
      background:
        radial-gradient(circle at top left, rgba(20, 184, 166, 0.12), transparent 32%),
        #ffffff;
    }}
    .compact-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }}
    .gpt-prompt-box {{ min-height: 160px; }}
    .gpt-system-box {{ min-height: 260px; }}
    .gpt-api-output {{ min-height: 240px; background: #f8fafc; }}
    .gpt-fallback-box {{ min-height: 130px; }}
    .gpt-response-meta {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin: 4px 0 10px;
      padding: 8px 10px;
      border-radius: 8px;
      border: 1px solid #bbf7d0;
      background: #f0fdf4;
      color: #166534;
      font-size: 12px;
      font-weight: 800;
      overflow-wrap: anywhere;
    }}
    .signal-good {{
      color: #047857;
      font-weight: 900;
      background: #ecfdf5;
    }}
    .signal-green {{
      color: #006b4f;
      font-weight: 900;
      background: #d9fbe7;
      border-radius: 4px;
      padding: 2px 4px;
    }}
    .signal-yellow {{
      color: #8a5200;
      font-weight: 900;
      background: #fff7b8;
      border-radius: 4px;
      padding: 2px 4px;
    }}
    .signal-red {{
      color: #a51212;
      font-weight: 900;
      background: #ffe0de;
      border-radius: 4px;
      padding: 2px 4px;
    }}
    .signal-neutral {{
      color: var(--muted);
      font-weight: 800;
    }}
    .strength-lightgreen {{
      background: #d7fbe5;
      color: #006b4f;
      font-weight: 900;
    }}
    .strength-yellow {{
      background: #fff7b8;
      color: #8a5200;
      font-weight: 900;
    }}
    .strength-orange {{
      background: #ffedd5;
      color: #c2410c;
      font-weight: 900;
    }}
    .strength-lightcoral {{
      background: #ffe0de;
      color: #a51212;
      font-weight: 900;
    }}
    .strength-neutral {{
      background: #f8fafc;
      color: var(--muted);
      font-weight: 800;
    }}
    .table-wrap {{ overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      background: rgba(255, 255, 255, 0.9);
      border-radius: 10px;
      overflow: hidden;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      text-align: left;
      white-space: nowrap;
    }}
    th {{
      color: #49627d;
      font-weight: 800;
      background: linear-gradient(135deg, #f8fafc, #eef7f6);
    }}
    tbody tr:hover td {{
      background: rgba(236, 254, 255, 0.46);
    }}
    @media (max-width: 820px) {{
      .rule-strip {{ grid-template-columns: 1fr; }}
      .expiry-strip {{ grid-template-columns: 1fr; }}
      .expiry-warning {{ max-width: none; }}
      .grid {{ grid-template-columns: 1fr; }}
      .gpt-workspace {{ grid-template-columns: 1fr; }}
      .gpt-hero-panel {{ align-items: flex-start; flex-direction: column; }}
      .kite-setup-hero {{ grid-template-columns: 1fr; }}
      .kite-setup-grid {{ grid-template-columns: 1fr; }}
      .analytics-form {{ grid-template-columns: 1fr; }}
      .analytics-command-head {{ grid-template-columns: 1fr; }}
      .analytics-two-column {{ grid-template-columns: 1fr; }}
      .tabs {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .tab-button,
      .tab-button.primary-action,
      .tab-button.utility-action {{ white-space: normal; }}
      .calm-hero-panel {{ align-items: flex-start; flex-direction: column; }}
      .calm-hero-panel .actions {{ flex-wrap: wrap; justify-content: flex-start; }}
      header {{ padding: 10px 12px; }}
      .header-inner {{ width: 100%; grid-template-columns: 1fr; align-items: flex-start; }}
      .blessing {{ text-align: left; white-space: normal; }}
      .naval-quote {{ text-align: left; max-width: none; }}
      main {{ width: calc(100vw - 20px); }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
    <div class="brand-block">
      <div class="brand-mark">विकल्प</div>
      <div>
        <h1>Income Desk</h1>
        <p>Wheel income, positions, ETF actions, and calm execution.</p>
      </div>
    </div>
    <div class="blessing">&#2384; | Jai Sri Ram | Jai Laxmi Mata</div>
    <p class="naval-quote">"Trade money for time, not time for money. You're going to run out of time first." <strong>- Naval</strong></p>
    </div>
  </header>
  <main>
    {render_market_topper(state)}
    {alert}
    <div class="tabs">
      <button class="tab-button primary-action {place_tab_class}" type="button" data-tab="place">Trading</button>
      <button class="tab-button primary-action {positions_tab_class}" type="button" data-tab="positions">Positions</button>
      <button class="tab-button utility-action {analytics_tab_class}" type="button" data-tab="analytics">Analytics</button>
      <button class="tab-button utility-action {research_tab_class}" type="button" data-tab="research">Research</button>
      <button class="tab-button utility-action {income_tab_class}" type="button" data-tab="income">INCOME</button>
      <button class="tab-button utility-action {commodity_tab_class}" type="button" data-tab="commodity">Commodity</button>
      <button class="tab-button utility-action {order_management_tab_class}" type="button" data-tab="order-management">Mofify / Cancel</button>
      <button class="tab-button utility-action {gpt_tab_class}" type="button" data-tab="gpt">GPT</button>
      <button class="tab-button utility-action {kite_setup_tab_class}" type="button" data-tab="kite-setup">Kite Setup</button>
    </div>
    <form id="place-panel" method="post" action="/load"{place_panel_style}>
      {env_hidden}
      <input type="hidden" name="live_confirmed" id="live-confirmed" value="0">
      <input type="hidden" name="rows_payload" value="{html.escape(rows_payload, quote=True)}">
      <section class="panel trading-actions-panel">
        <div class="panel-title">Execution Options</div>
        {orders_table}
        {execute_after_orders}
        {trade_validation_table}
        <div class="actions">
          <button type="submit" formaction="/load">Load / Preview CSV</button>
        </div>
        {render_results(state.results)}
        <div class="execution-checks">
          {render_checkbox("dry_run", "Dry run", state.dry_run, "Build orders and show what would happen without sending anything to Kite.")}
          {render_checkbox("no_ltp_price", "Use CSV/manual price only", state.no_ltp_price, "Leave this on when the CSV already has prices or lot_size. Turn off to fetch LTP/lot size from Kite.")}
          {render_checkbox("keep_existing_orders", "Always place new order", state.keep_existing_orders, "Turn off to modify a similar open order when found; if no modifiable order exists, the app places a new order.")}
        </div>
      </section>
      <div>
        <section class="panel">
          <div class="panel-title">CSV Source</div>
          {render_input("csv_path", "CSV path", state.csv_path)}
          <div class="status">CSV path can be a local file or a public Google Sheets link. Google Sheets must be shared as viewable by anyone with the link.</div>
          <label><span>Upload CSV</span><input id="csv-file" type="file" accept=".csv,text/csv"></label>
          <label><span>CSV text</span><textarea id="csv-text" name="csv_text" placeholder="Paste CSV here or choose a file above">{html.escape(state.csv_text)}</textarea></label>
          <div class="actions">
            <button type="submit" formaction="/csv/save-today">Save as Today CSV</button>
          </div>
          <div class="status">Saves CSV text to {html.escape(str(dated_income_csv_path()))} and updates CSV path.</div>
        </section>
      </div>
      {render_console(state.console_log)}
    </form>
    {render_order_management_panel(state)}
    {render_positions_panel(state, position_orders_payload, position_orders_table, position_execute_button)}
    <form id="kite-setup-panel" method="post" action="/kite-setup"{kite_setup_panel_style}>
      {env_panel}
      <div class="actions">
        <button type="submit" formaction="/kite-setup">Save Kite Setup</button>
      </div>
    </form>
    <form id="gpt-panel" method="post" action="/gpt/load"{gpt_panel_style}>
      {env_hidden}
      <section class="panel gpt-hero-panel">
        <div>
          <div class="panel-title">GPT CSV Generator</div>
          <p class="status">OpenAI API turns your strategy prompt into Kite-ready CSV. Review every row before saving or trading.</p>
        </div>
        <div class="gpt-hero-chip">Prompt file: {html.escape(OPENAI_CSV_PROMPT_PATH.name)}</div>
      </section>
      <div class="gpt-workspace">
        <section class="panel gpt-card gpt-setup-card">
          <div class="panel-title">API Setup</div>
          <div class="compact-grid">
            {render_input("openai_api_key", "OPENAI_API_KEY", state.openai_api_key or env_value("OPENAI_API_KEY"), "password")}
            {render_input("openai_model", "Model", state.openai_model)}
          </div>
          <div class="actions">
            <button type="submit" formaction="/gpt/generate">Generate CSV with OpenAI</button>
          </div>
        </section>
        <section class="panel gpt-card">
          <div class="panel-title">User Request</div>
          <label><span>Ask GPT what CSV to build</span><textarea class="conversation gpt-prompt-box" name="openai_prompt" placeholder="Describe holdings, cash, expiry, symbols, strikes, lots, prices, and risk preference">{html.escape(state.openai_prompt)}</textarea></label>
        </section>
        <section class="panel gpt-card">
          <div class="panel-title">System Prompt</div>
          <label><span>Loaded from openai_csv_prompt.md</span><textarea class="conversation gpt-system-box" name="openai_system_prompt" placeholder="System instructions for CSV generation">{html.escape(state.openai_system_prompt)}</textarea></label>
        </section>
        <section class="panel gpt-card gpt-api-response-card">
          <div class="panel-title">OpenAI Prompt Response</div>
          <p class="status">This is the direct text returned by the OpenAI API before the app extracts and validates Kite CSV.</p>
          <input type="hidden" name="gpt_api_response_id" value="{html.escape(state.gpt_api_response_id, quote=True)}">
          <div class="gpt-response-meta">
            <span>Response ID: <strong>{html.escape(state.gpt_api_response_id or 'Not generated yet')}</strong></span>
            <a class="inline-link" href="https://platform.openai.com/logs" target="_blank" rel="noopener">Open OpenAI API logs</a>
          </div>
          <label><span>Prompt response from OpenAI API</span><textarea class="conversation gpt-api-output" name="gpt_api_output" readonly placeholder="Generate CSV with OpenAI to see the full prompt response here.">{html.escape(state.gpt_api_output)}</textarea></label>
        </section>
        <section class="panel gpt-card gpt-result-card">
          <div class="panel-title">CSV To Save</div>
          <label><span>Validated Kite CSV</span><textarea class="csv-output" name="gpt_csv_text" placeholder="CSV generated from GPT appears here">{html.escape(state.gpt_csv_text)}</textarea></label>
          <div class="actions">
            <button type="submit" formaction="/gpt/save">Save to kite_orders.csv</button>
            <button type="submit" formaction="/gpt/save-preview">Save and Preview Orders</button>
          </div>
          <div class="status">Saved CSV uses the same archive flow as Trading, so the previous {html.escape(DEFAULT_CSV_PATH.name)} is kept as a last input order record.</div>
        </section>
        <section class="panel gpt-card">
          <div class="panel-title">Manual Paste Fallback</div>
          <div class="status">Custom GPT share URLs cannot be called as an app API. Use OpenAI API above, or paste CSV/GPT output here manually.</div>
          {render_input("gpt_url", "GPT share URL", state.gpt_url)}
          <a class="inline-link" href="{html.escape(state.gpt_url, quote=True)}" target="_blank" rel="noopener">Open GPT Share</a>
          <label><span>Conversation / GPT output</span><textarea class="conversation gpt-fallback-box" name="gpt_conversation" placeholder="Paste GPT output here">{html.escape(state.gpt_conversation)}</textarea></label>
          <div class="actions">
            <button type="submit" formaction="/gpt/extract">Extract CSV</button>
          </div>
        </section>
      </div>
      {orders_table}
      {render_console(state.console_log)}
    </form>
    {render_analytics_panel(state)}
    {render_research_panel(state)}
    {render_income_panel(state)}
    {render_commodity_panel(state)}
  </main>
  <div class="live-modal-backdrop" id="live-confirm-modal">
    <div class="live-modal">
      <h2>Pause Before Live Trade</h2>
      <p>Live order placement is about to run. Breathe in, breathe out, then confirm.</p>
      <div class="breath-circle"></div>
      <div class="breath-text" id="breath-text">Breathe in</div>
      <div class="countdown" id="live-countdown">20</div>
      <div class="news-box guardrail-box">
        <h3>Capital Allocation Guardrail</h3>
        <div id="trade-guardrails">Loading capital guardrails...</div>
      </div>
      <div class="news-box">
        <h3>Top Stock News Before Trade - Last 5 Days</h3>
        <div id="trade-news">Loading selected stock news...</div>
      </div>
      <div class="modal-actions">
        <button type="button" class="secondary" id="live-cancel">Cancel</button>
        <button type="button" class="danger" id="live-good" disabled>Good to go</button>
      </div>
    </div>
  </div>
  <div class="live-modal-backdrop" id="commodity-confirm-modal">
    <div class="live-modal">
      <h2>Validate again to the price?</h2>
      <p>This commodity ETF order will be sent to Kite. Breathe in, breathe out, then confirm.</p>
      <div class="breath-circle"></div>
      <div class="breath-text" id="commodity-breath-text">Breathe in</div>
      <div class="countdown" id="commodity-countdown">10</div>
      <div class="modal-actions">
        <button type="button" class="secondary" id="commodity-cancel">Cancel</button>
        <button type="button" class="danger" id="commodity-good" disabled>Good to go</button>
      </div>
    </div>
  </div>
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
    if (showCredentials.some((toggle) => toggle.checked)) {{
      for (const field of secretFields) {{
        field.type = 'text';
      }}
    }}
    for (const button of document.querySelectorAll('.tab-button')) {{
      button.addEventListener('click', () => {{
        const active = button.dataset.tab;
        if (active === 'commodity' && window.location.pathname !== '/commodity') {{
          window.location.href = '/commodity';
          return;
        }}
        if (active === 'positions' && window.location.pathname !== '/positions') {{
          window.location.href = '/positions';
          return;
        }}
        document.getElementById('place-panel').style.display = active === 'place' ? '' : 'none';
        document.getElementById('positions-panel').style.display = active === 'positions' ? '' : 'none';
        document.getElementById('gpt-panel').style.display = active === 'gpt' ? '' : 'none';
        document.getElementById('kite-setup-panel').style.display = active === 'kite-setup' ? '' : 'none';
        document.getElementById('order-management-panel').style.display = active === 'order-management' ? '' : 'none';
        document.getElementById('analytics-panel').style.display = active === 'analytics' ? '' : 'none';
        document.getElementById('research-panel').style.display = active === 'research' ? '' : 'none';
        document.getElementById('income-panel').style.display = active === 'income' ? '' : 'none';
        document.getElementById('commodity-panel').style.display = active === 'commodity' ? '' : 'none';
        for (const item of document.querySelectorAll('.tab-button')) {{
          item.classList.toggle('active', item.dataset.tab === active);
        }}
      }});
    }}
    function isKiteSetupError(message) {{
      const text = String(message || '').toLowerCase();
      return text.includes('api_key')
        || text.includes('access_token')
        || text.includes('api secret')
        || text.includes('token')
        || text.includes('kite setup')
        || text.includes('invalid session')
        || text.includes('permission')
        || text.includes('could not import kite_place_order');
    }}
    function openKiteSetupForError(message) {{
      if (!isKiteSetupError(message)) return;
      const setupTab = document.querySelector('.tab-button[data-tab="kite-setup"]');
      if (setupTab) setupTab.click();
    }}
    const executeButton = document.getElementById('execute-selected-button');
    const placeForm = document.getElementById('place-panel');
    const liveModal = document.getElementById('live-confirm-modal');
    const liveCancel = document.getElementById('live-cancel');
    const liveGood = document.getElementById('live-good');
    const liveCountdown = document.getElementById('live-countdown');
    const breathText = document.getElementById('breath-text');
    const liveConfirmed = document.getElementById('live-confirmed');
    const tradeNews = document.getElementById('trade-news');
    const tradeGuardrails = document.getElementById('trade-guardrails');
    const commodityModal = document.getElementById('commodity-confirm-modal');
    const commodityCancel = document.getElementById('commodity-cancel');
    const commodityGood = document.getElementById('commodity-good');
    const commodityCountdown = document.getElementById('commodity-countdown');
    const commodityBreathText = document.getElementById('commodity-breath-text');
    let pendingLiveSubmit = false;
    let countdownTimer = null;
    let pendingCommodityForm = null;
    let commodityCountdownTimer = null;
    function stopLiveCountdown() {{
      if (countdownTimer) {{
        clearInterval(countdownTimer);
        countdownTimer = null;
      }}
    }}
    function openLiveModal() {{
      const stocks = selectedTradingStocks();
      let remaining = Math.min(40, Math.max(10, stocks.length * 5));
      pendingLiveSubmit = true;
      liveGood.disabled = true;
      liveCountdown.textContent = String(remaining);
      breathText.textContent = 'Breathe in';
      liveModal.style.display = 'flex';
      loadTradeNews(stocks);
      loadTradeGuardrails();
      stopLiveCountdown();
      countdownTimer = setInterval(() => {{
        remaining -= 1;
        liveCountdown.textContent = String(Math.max(remaining, 0));
        breathText.textContent = remaining % 2 === 0 ? 'Breathe in' : 'Breathe out';
        if (remaining <= 0) {{
          stopLiveCountdown();
          breathText.textContent = 'Ready';
          liveGood.disabled = false;
        }}
      }}, 1000);
    }}
    function optionUnderlying(symbol) {{
      const clean = String(symbol || '').trim().toUpperCase();
      const match = clean.match(/^(.+?)(\\d{{2}})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\\d+(?:\\.\\d+)?)(CE|PE)$/);
      return match ? match[1] : clean;
    }}
    function selectedTradingStocks() {{
      const stocks = [];
      const seen = new Set();
      const rows = placeForm.querySelectorAll('table tbody tr');
      for (const row of rows) {{
        const checkbox = row.querySelector('input[name="selected"]');
        if (checkbox && checkbox.checked && row.cells.length > 2) {{
          const stock = optionUnderlying(row.cells[2].innerText);
          if (stock && !seen.has(stock)) {{
            stocks.push(stock);
            seen.add(stock);
          }}
        }}
      }}
      return stocks;
    }}
    function selectedTradingOrders() {{
      const orders = [];
      const rows = placeForm.querySelectorAll('table tbody tr');
      for (const row of rows) {{
        const checkbox = row.querySelector('input[name="selected"]');
        if (!checkbox || !checkbox.checked || row.cells.length < 10) continue;
        orders.push({{
          exchange: row.cells[1].innerText.trim(),
          tradingsymbol: row.cells[2].innerText.trim(),
          transaction_type: row.cells[3].innerText.trim(),
          quantity: row.cells[4].innerText.trim(),
          product: row.cells[5].innerText.trim(),
          order_type: row.cells[6].innerText.trim(),
          price: row.cells[7].innerText.trim(),
          validity: row.cells[8].innerText.trim(),
          tag: row.cells[9].innerText.trim()
        }});
      }}
      return orders;
    }}
    async function loadTradeGuardrails() {{
      if (!tradeGuardrails) return;
      const orders = selectedTradingOrders();
      if (!orders.length) {{
        tradeGuardrails.textContent = 'No selected SELL CALL / PUT orders found.';
        return;
      }}
      tradeGuardrails.textContent = 'Calculating capital, cash and exposure...';
      try {{
        const response = await fetch(`/trade-guardrails?orders=${{encodeURIComponent(JSON.stringify(orders))}}`, {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Could not load guardrails');
        tradeGuardrails.innerHTML = `
          <div class="guardrail-grid">
            <div><span>Capital used</span><strong>${{escapeHtml(data.capital_used)}}</strong></div>
            <div><span>Cash reserved</span><strong>${{escapeHtml(data.cash_reserved)}}</strong></div>
            <div><span>Margin used</span><strong>${{escapeHtml(data.margin_used)}}</strong></div>
            <div><span>Sector exposure</span><strong>${{escapeHtml(data.sector_exposure)}}</strong></div>
            <div><span>Single stock exposure</span><strong>${{escapeHtml(data.single_stock_exposure)}}</strong></div>
          </div>`;
      }} catch (error) {{
        tradeGuardrails.textContent = `Guardrail error: ${{error.message}}`;
      }}
    }}
    async function loadTradeNews(stocks) {{
      if (!tradeNews) return;
      const selectedStocks = stocks && stocks.length ? stocks : selectedTradingStocks();
      if (!selectedStocks.length) {{
        tradeNews.textContent = 'No selected stocks found.';
        return;
      }}
      tradeNews.textContent = `Loading latest news for ${{selectedStocks.join(', ')}}...`;
      try {{
        const response = await fetch(`/trade-news?stocks=${{encodeURIComponent(selectedStocks.join(','))}}`, {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Could not load news');
        if (!data.news || !data.news.length) {{
          tradeNews.textContent = 'No recent news found.';
          return;
        }}
        tradeNews.innerHTML = '<ol>' + data.news.map((item) => {{
          const title = escapeHtml(item.title || 'News item');
          const symbol = item.symbol ? `<strong>${{escapeHtml(item.symbol)}}</strong>: ` : '';
          const link = escapeHtml(item.link || '');
          const publishedDate = item.published_date ? `<span class="news-date">${{escapeHtml(item.published_date)}}</span>` : '';
          const sentiment = ['positive', 'negative', 'neutral'].includes(item.sentiment) ? item.sentiment : 'neutral';
          const tag = `<span class="news-tag">${{sentiment}}</span>`;
          if (item.link) {{
            return `<li class="news-sentiment-${{sentiment}}">${{symbol}}<a href="${{link}}" target="_blank" rel="noopener">${{title}}</a>${{tag}}${{publishedDate}}</li>`;
          }}
          return `<li class="news-sentiment-${{sentiment}}">${{symbol}}${{title}}${{tag}}${{publishedDate}}</li>`;
        }}).join('') + '</ol>';
      }} catch (error) {{
        tradeNews.textContent = `News error: ${{error.message}}`;
      }}
    }}
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, (char) => ({{
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }}[char]));
    }}
    function closeLiveModal() {{
      pendingLiveSubmit = false;
      if (liveConfirmed) liveConfirmed.value = '0';
      liveModal.style.display = 'none';
      stopLiveCountdown();
    }}
    function stopCommodityCountdown() {{
      if (commodityCountdownTimer) {{
        clearInterval(commodityCountdownTimer);
        commodityCountdownTimer = null;
      }}
    }}
    function openCommodityModal(form) {{
      let remaining = 10;
      pendingCommodityForm = form;
      commodityGood.disabled = true;
      commodityCountdown.textContent = String(remaining);
      commodityBreathText.textContent = 'Breathe in';
      commodityModal.style.display = 'flex';
      stopCommodityCountdown();
      commodityCountdownTimer = setInterval(() => {{
        remaining -= 1;
        commodityCountdown.textContent = String(Math.max(remaining, 0));
        commodityBreathText.textContent = remaining % 2 === 0 ? 'Breathe in' : 'Breathe out';
        if (remaining <= 0) {{
          stopCommodityCountdown();
          commodityBreathText.textContent = 'Ready';
          commodityGood.disabled = false;
        }}
      }}, 1000);
    }}
    function closeCommodityModal() {{
      if (pendingCommodityForm) {{
        const confirmed = pendingCommodityForm.querySelector('input[name="commodity_confirmed"]');
        if (confirmed) confirmed.value = '0';
      }}
      pendingCommodityForm = null;
      commodityModal.style.display = 'none';
      stopCommodityCountdown();
    }}
    placeForm && placeForm.addEventListener('submit', (event) => {{
      const submitter = event.submitter;
      if (!submitter || submitter.id !== 'execute-selected-button') {{
        return;
      }}
      const dryRun = placeForm.querySelector('input[name="dry_run"]');
      if (dryRun && dryRun.checked) {{
        return;
      }}
      if (liveConfirmed && liveConfirmed.value === '1') {{
        return;
      }}
      event.preventDefault();
      openLiveModal();
    }});
    liveCancel && liveCancel.addEventListener('click', closeLiveModal);
    liveGood && liveGood.addEventListener('click', () => {{
      if (liveGood.disabled || !pendingLiveSubmit) return;
      pendingLiveSubmit = false;
      stopLiveCountdown();
      liveModal.style.display = 'none';
      if (liveConfirmed) liveConfirmed.value = '1';
      executeButton.setAttribute('formaction', '/execute');
      placeForm.requestSubmit(executeButton);
    }});
    for (const form of document.querySelectorAll('.commodity-confirm-form')) {{
      form.addEventListener('submit', (event) => {{
        const confirmed = form.querySelector('input[name="commodity_confirmed"]');
        if (confirmed && confirmed.value === '1') return;
        event.preventDefault();
        openCommodityModal(form);
      }});
    }}
    commodityCancel && commodityCancel.addEventListener('click', closeCommodityModal);
    commodityGood && commodityGood.addEventListener('click', () => {{
      if (commodityGood.disabled || !pendingCommodityForm) return;
      const form = pendingCommodityForm;
      const confirmed = form.querySelector('input[name="commodity_confirmed"]');
      if (confirmed) confirmed.value = '1';
      pendingCommodityForm = null;
      commodityModal.style.display = 'none';
      stopCommodityCountdown();
      form.requestSubmit();
    }});
    async function refreshMmi() {{
      const value = document.getElementById('mmi-value');
      const zone = document.getElementById('mmi-zone');
      const action = document.getElementById('mmi-action');
      if (!value || !zone || !action) return;
      try {{
        const response = await fetch('/market-mmi', {{ cache: 'no-store' }});
        const data = await response.json();
        if (data.ok) {{
          value.textContent = data.value;
          zone.textContent = data.zone;
          const mmi = Number(data.value);
          if (mmi > 60) {{
            action.innerHTML = '| Signal: <strong>SELL CALL</strong>';
          }} else if (mmi < 40) {{
            action.innerHTML = '| Signal: <strong>SELL PUT</strong>';
          }} else {{
            action.innerHTML = '| Signal: <strong>WAIT / NEUTRAL</strong>';
          }}
        }} else {{
          value.textContent = 'Open';
          zone.textContent = 'Tickertape live MMI';
          action.innerHTML = '| Signal: <strong>unavailable</strong>';
        }}
      }} catch (error) {{
        value.textContent = 'Open';
        zone.textContent = 'Tickertape live MMI';
        action.innerHTML = '| Signal: <strong>unavailable</strong>';
      }}
    }}
    refreshMmi();
    async function refreshQuotes() {{
      const cards = Array.from(document.querySelectorAll('.quote-card[data-symbol]'));
      if (!cards.length) return;
      const quoteError = document.getElementById('quote-error');
      try {{
        const response = await fetch('/market-quotes', {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Could not load quotes');
        if (quoteError) {{
          quoteError.style.display = 'none';
          quoteError.textContent = '';
        }}
        const bySymbol = new Map((data.quotes || []).map((quote) => [quote.symbol, quote]));
        for (const card of cards) {{
          const symbol = card.dataset.symbol;
          const assetName = card.dataset.assetName || symbol;
          const quote = bySymbol.get(symbol);
          const ltp = card.querySelector('.quote-ltp');
          const change = card.querySelector('.quote-change');
          if (!quote || !quote.ltp) {{
            ltp.textContent = 'N/A';
            change.textContent = 'Quote unavailable';
            change.className = 'quote-change';
            continue;
          }}
          ltp.textContent = Number(quote.ltp).toFixed(2);
          if (quote.change_percent === null || quote.change_percent === undefined) {{
            change.textContent = '--';
            change.className = 'quote-change';
          }} else {{
            const pct = Number(quote.change_percent);
            const sign = pct > 0 ? '+' : '';
            change.textContent = `${{sign}}${{pct.toFixed(2)}}%`;
            change.className = `quote-change ${{pct >= 0 ? 'up' : 'down'}}`;
            const threshold = card.dataset.threshold ? Number(card.dataset.threshold) : null;
            const etfBuy = threshold !== null && pct <= -threshold;
            card.classList.toggle('etf-buy', etfBuy);
            card.title = etfBuy ? (quote.action || 'Action: buy the ETF today') : '';
            card.classList.toggle('strong-up', !threshold && pct > 2);
            card.classList.toggle('strong-down', threshold ? etfBuy : pct < -2);
          }}
        }}
      }} catch (error) {{
        openKiteSetupForError(error.message);
        if (quoteError) {{
          quoteError.style.display = 'block';
          quoteError.textContent = `Kite quote error: ${{error.message}}`;
        }}
        for (const card of cards) {{
          card.querySelector('.quote-ltp').textContent = 'N/A';
          card.querySelector('.quote-change').textContent = error.message.includes('api_key') || error.message.includes('access_token')
            ? 'Auth error'
            : 'Kite quote error';
        }}
      }}
    }}
    refreshQuotes();
    setInterval(refreshQuotes, 30000);
    async function refreshCommodityQuotes() {{
      const cards = Array.from(document.querySelectorAll('.commodity-card[data-symbol]'));
      if (!cards.length) return;
      const errorBox = document.getElementById('commodity-error');
      try {{
        const response = await fetch('/commodity-quotes', {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Could not load commodity ETF quotes');
        if (errorBox) {{
          errorBox.style.display = 'none';
          errorBox.textContent = '';
        }}
        const bySymbol = new Map((data.quotes || []).map((quote) => [quote.symbol, quote]));
        for (const card of cards) {{
          const symbol = card.dataset.symbol;
          const assetName = card.dataset.assetName || symbol;
          const quote = bySymbol.get(symbol);
          const price = card.querySelector('.commodity-price');
          const change = card.querySelector('.commodity-change');
          const action = card.querySelector('.commodity-action');
          const buyButton = card.querySelector('.commodity-buy-button');
          if (!quote || !quote.ltp) {{
            price.textContent = 'N/A';
            change.textContent = 'Quote unavailable';
            change.className = 'commodity-change';
            action.textContent = 'Wait';
            if (buyButton) buyButton.textContent = `Add more ${{assetName}}`;
            card.classList.remove('buy-now');
            continue;
          }}
          price.textContent = Number(quote.ltp).toFixed(2);
          const pct = quote.change_percent === null || quote.change_percent === undefined
            ? null
            : Number(quote.change_percent);
          if (pct === null) {{
            change.textContent = '--';
            change.className = 'commodity-change';
          }} else {{
            const sign = pct > 0 ? '+' : '';
            change.textContent = `${{sign}}${{pct.toFixed(2)}}%`;
            change.className = `commodity-change ${{pct >= 0 ? 'up' : 'down'}}`;
          }}
          card.classList.toggle('buy-now', Boolean(quote.buy_signal));
          action.innerHTML = quote.buy_signal
            ? `<strong>Action: ${{escapeHtml(quote.action || 'buy the ETF today')}} (${{quote.multiplier}}x)</strong>`
            : `Wait | fall ${{Number(quote.daily_fall_pct || 0).toFixed(2)}}%`;
          if (buyButton) {{
            buyButton.textContent = `Add more ${{assetName}}`;
          }}
        }}
      }} catch (error) {{
        openKiteSetupForError(error.message);
        if (errorBox) {{
          errorBox.style.display = 'block';
          errorBox.textContent = `ETF quote error: ${{error.message}}`;
        }}
      }}
    }}
    refreshCommodityQuotes();
    setInterval(refreshCommodityQuotes, 30000);
  </script>
</body>
</html>"""
    return html_doc.encode("utf-8")


class KiteWebHandler(BaseHTTPRequestHandler):
    server_version = "KiteCSVTrader/1.0"

    def auth_cookie_value(self) -> str:
        raw_cookie = self.headers.get("Cookie", "")
        for part in raw_cookie.split(";"):
            if "=" not in part:
                continue
            key, value = part.strip().split("=", 1)
            if key == AUTH_COOKIE_NAME:
                return value.strip()
        return ""

    def is_authenticated(self) -> bool:
        return valid_auth_token(self.auth_cookie_value())

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/login":
            self.send_login()
            return
        if parsed_url.path == "/logout":
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header(
                "Set-Cookie",
                f"{AUTH_COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
            )
            self.end_headers()
            return
        if not self.is_authenticated():
            self.send_login()
            return
        if parsed_url.path == "/analytics":
            query = parse_qs(parsed_url.query, keep_blank_values=True)
            symbol = first(query, "symbol")
            state = PageState(active_tab="analytics", analytics_symbol=symbol)
            if symbol:
                try:
                    state.analytics_data, state.console_log = call_with_console(
                        option_analytics_for_symbol,
                        symbol,
                    )
                except Exception as exc:
                    state.error = f"{exc}\n\n{traceback.format_exc()}"
            self.send_page(state)
            return
        if parsed_url.path == "/commodity":
            self.send_page(PageState(active_tab="commodity"))
            return
        if parsed_url.path == "/positions":
            self.send_page(PageState(active_tab="positions"))
            return
        if parsed_url.path == "/trade-news":
            query = parse_qs(parsed_url.query, keep_blank_values=True)
            symbols_text = first(query, "stocks") or first(query, "symbols")
            symbols = [item for item in symbols_text.split(",") if item.strip()]
            try:
                self.send_json({"ok": True, "news": fetch_stock_news(symbols)})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc), "news": []})
            return
        if parsed_url.path == "/trade-guardrails":
            query = parse_qs(parsed_url.query, keep_blank_values=True)
            try:
                orders = json.loads(first(query, "orders") or "[]")
                self.send_json(selected_trade_guardrails(orders))
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)})
            return
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
        if self.path == "/market-quotes":
            try:
                self.send_json(fetch_csv_market_quotes())
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                        "quotes": [],
                    }
                )
            return
        if self.path == "/commodity-quotes":
            try:
                self.send_json(fetch_commodity_etf_quotes())
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                        "quotes": [],
                    }
                )
            return
        setup_issue = kite_setup_issue()
        self.send_page(
            PageState(
                active_tab=default_active_tab(),
                error=setup_issue,
            )
        )

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(body, keep_blank_values=True)
        if self.path == "/login":
            username = first(form, "username")
            password = first(form, "password")
            if verify_login(username, password):
                token = make_auth_token(username)
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header(
                    "Set-Cookie",
                    f"{AUTH_COOKIE_NAME}={token}; Path=/; Max-Age={AUTH_SESSION_SECONDS}; HttpOnly; SameSite=Lax",
                )
                self.end_headers()
            else:
                self.send_login("Invalid username or password.")
            return
        if not self.is_authenticated():
            self.send_login()
            return
        set_kite_env(form)

        state = PageState(
            active_tab=(
                "positions"
                if self.path.startswith("/positions")
                else "place"
                if self.path.startswith("/csv")
                else "commodity"
                if self.path.startswith("/commodity")
                else "income"
                if self.path.startswith("/income")
                else "gpt"
                if self.path.startswith("/gpt")
                else "kite-setup"
                if self.path.startswith("/kite-setup") or self.path.startswith("/kite-token") or self.path.startswith("/kite-ip")
                else "order-management"
                if self.path.startswith("/orders")
                else "analytics"
                if self.path.startswith("/analytics")
                else "research"
                if self.path.startswith("/research")
                else default_active_tab()
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
            gpt_api_output=first(form, "gpt_api_output"),
            gpt_api_response_id=first(form, "gpt_api_response_id"),
            openai_api_key=first(form, "openai_api_key"),
            openai_model=first(form, "openai_model", DEFAULT_OPENAI_MODEL),
            openai_system_prompt=first(form, "openai_system_prompt", read_openai_csv_system_prompt()),
            openai_prompt=first(form, "openai_prompt", DEFAULT_OPENAI_PROMPT),
            analytics_symbol=first(form, "analytics_symbol"),
            kite_request_token=first(form, "kite_request_token"),
            etf_buy_amount=float(first(form, "etf_buy_amount", str(etf_buy_amount_setting())) or etf_buy_amount_setting()),
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
                state.trade_validations = validate_trade_orders(state.orders)
                state.selected_indexes = set(range(len(state.orders)))
                state.message = f"{persist_message} Loaded {len(state.orders)} order(s).".strip()
            elif self.path == "/csv/save-today":
                state.csv_path, state.message = save_today_csv_text(state.csv_text)
                state.csv_text = Path(state.csv_path).read_text(encoding="utf-8-sig")
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
                state.trade_validations = validate_trade_orders(state.orders)
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
            elif self.path == "/orders/cancel-all":
                state.results, state.console_log = call_with_console(cancel_all_open_orders)
                try:
                    state.order_book = kite_order_book()
                except Exception as exc:
                    state.order_book_error = str(exc)
                cancelled = sum(1 for item in state.results if item.get("status") == "CANCELLED")
                errors = sum(1 for item in state.results if item.get("status") == "ERROR")
                state.message = f"Cancel all completed. Cancelled {cancelled} order(s); errors {errors}."
            elif self.path == "/orders/cancel-selected":
                selected_order_keys = form.get("order_key", [])
                state.results, state.console_log = call_with_console(
                    cancel_selected_orders,
                    selected_order_keys,
                )
                try:
                    state.order_book = kite_order_book()
                except Exception as exc:
                    state.order_book_error = str(exc)
                cancelled = sum(1 for item in state.results if item.get("status") == "CANCELLED")
                errors = sum(1 for item in state.results if item.get("status") == "ERROR")
                skipped = sum(1 for item in state.results if item.get("status") == "SKIPPED")
                state.message = (
                    f"Cancel selected completed. Cancelled {cancelled}; skipped {skipped}; errors {errors}."
                )
            elif self.path == "/orders/modify-selected":
                selected_order_keys = form.get("order_key", [])
                state.results, state.console_log = call_with_console(
                    modify_selected_orders,
                    selected_order_keys,
                    form,
                )
                try:
                    state.order_book = kite_order_book()
                except Exception as exc:
                    state.order_book_error = str(exc)
                modified = sum(1 for item in state.results if item.get("status") == "MODIFIED")
                errors = sum(1 for item in state.results if item.get("status") == "ERROR")
                skipped = sum(1 for item in state.results if item.get("status") == "SKIPPED")
                state.message = (
                    f"Modify selected completed. Modified {modified}; skipped {skipped}; errors {errors}."
                )
            elif self.path == "/orders/refresh":
                state.order_book, state.console_log = call_with_console(kite_order_book)
                state.message = f"Loaded {len(state.order_book)} Kite order(s)."
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
            elif self.path == "/positions/close-buy":
                close_symbol = first(form, "close_symbol")
                result, state.console_log = call_with_console(
                    place_position_close_buy_order,
                    close_symbol,
                )
                state.position_results = [result]
                (
                    state.positions_rows,
                    state.positions_summary,
                ), refresh_log = call_with_console(positions_research)
                state.console_log = f"{state.console_log}{refresh_log}"
                state.message = f"Submitted BUY close order for {close_symbol.upper()}."
            elif self.path == "/gpt/load":
                state.gpt_conversation, state.console_log = call_with_console(
                    fetch_gpt_conversation,
                    state.gpt_url,
                )
                state.message = "Fetched GPT share conversation. Review it, then extract CSV."
            elif self.path == "/gpt/extract":
                state.gpt_csv_text = extract_csv_from_text(state.gpt_conversation)
                state.message = "Extracted CSV from GPT conversation."
            elif self.path == "/gpt/generate":
                (
                    state.gpt_csv_text,
                    state.gpt_api_output,
                    state.gpt_api_response_id,
                ), state.console_log = call_with_console(
                    generate_csv_with_openai,
                    state.openai_prompt,
                    state.openai_model,
                    state.openai_system_prompt,
                )
                state.message = "Generated Kite order CSV with OpenAI. Review before saving or placing orders."
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
            elif self.path == "/kite-setup":
                save_env_values(
                    {
                        "KITE_CONFIRM_LIVE_ORDER": state.confirm_live_order or env_value("KITE_CONFIRM_LIVE_ORDER"),
                        "KITE_API_KEY": state.api_key or env_value("KITE_API_KEY"),
                        "KITE_API_SECRET": state.api_secret or env_value("KITE_API_SECRET"),
                        "KITE_ACCESS_TOKEN": state.access_token or env_value("KITE_ACCESS_TOKEN"),
                        "OPENAI_API_KEY": state.openai_api_key or env_value("OPENAI_API_KEY"),
                    }
                )
                save_app_settings({"etf_buy_amount": state.etf_buy_amount})
                state.message = (
                    f"Kite setup saved to .env. ETF buy amount saved as {format_buy_amount(state.etf_buy_amount)}."
                )
            elif self.path == "/kite-token/generate":
                access_token, state.console_log = call_with_console(
                    generate_kite_access_token,
                    state.kite_request_token,
                )
                state.access_token = access_token
                state.message = "Generated today's KITE_ACCESS_TOKEN, saved it to .env, and applied it to this running app."
            elif self.path == "/kite-ip/check":
                state.kite_ip_data, state.console_log = call_with_console(fetch_public_ip_data)
                ips = [item["ip"] for item in state.kite_ip_data if item.get("ip")]
                state.message = (
                    "Fetched current public IP. Add the matching IP to Kite developer console."
                    if ips
                    else "Could not fetch public IP. Check network and try again."
                )
            elif self.path == "/analytics/load":
                state.analytics_data, state.console_log = call_with_console(
                    option_analytics_for_symbol,
                    state.analytics_symbol,
                )
                state.message = f"Loaded analytics for {state.analytics_symbol.upper()}."
            elif self.path == "/research/load":
                state.research_rows, state.console_log = call_with_console(research_csv_symbols)
                state.message = f"Research completed for {len(state.research_rows)} CSV symbol(s)."
            elif self.path == "/income/load":
                (
                    state.income_rows,
                    state.income_summary,
                ), state.console_log = call_with_console(income_strategy_candidates)
                state.message = f"Income strategy refreshed for {len(state.income_rows)} stock(s)."
            elif self.path == "/income/sell-ce":
                underlying = first(form, "income_underlying")
                result, state.console_log = call_with_console(
                    place_income_covered_call_order,
                    underlying,
                )
                state.income_results = [result]
                (
                    state.income_rows,
                    state.income_summary,
                ), refresh_log = call_with_console(income_strategy_candidates)
                state.console_log = f"{state.console_log}{refresh_log}"
                state.message = f"Submitted covered CE order for {underlying.upper()}."
            elif self.path == "/income/sell-pe":
                underlying = first(form, "income_underlying")
                result, state.console_log = call_with_console(
                    place_income_cash_secured_put_order,
                    underlying,
                )
                state.income_results = [result]
                (
                    state.income_rows,
                    state.income_summary,
                ), refresh_log = call_with_console(income_strategy_candidates)
                state.console_log = f"{state.console_log}{refresh_log}"
                state.message = f"Submitted cash-secured PE order for {underlying.upper()}."
            elif self.path == "/positions-research/load":
                (
                    state.positions_rows,
                    state.positions_summary,
                ), state.console_log = call_with_console(positions_research)
                state.message = (
                    f"Loaded analytics for {len(state.positions_rows)} active option position(s)."
                )
            elif self.path == "/commodity/refresh":
                state.commodity_holdings, state.console_log = call_with_console(
                    commodity_etf_holdings
                )
                non_zero = sum(1 for item in state.commodity_holdings if item.get("quantity"))
                state.message = f"Refreshed commodity ETF holdings. Found {non_zero} holding(s)."
            elif self.path == "/commodity/buy":
                symbol = first(form, "commodity_symbol")
                try:
                    result, state.console_log = call_with_console(
                        place_commodity_etf_order,
                        symbol,
                        checked(form, "commodity_confirmed"),
                    )
                    state.commodity_results = [result]
                    state.message = f"Submitted ETF BUY order for {symbol.upper()}."
                except Exception as exc:
                    state.commodity_results = [
                        {
                            "tradingsymbol": symbol.upper(),
                            "status": "ERROR",
                            "order_id": "",
                            "detail": str(exc),
                        }
                    ]
                    state.console_log = traceback.format_exc()
                    state.message = "Commodity ETF BUY was not submitted. Review the execution result."
                try:
                    state.commodity_holdings = commodity_etf_holdings()
                except Exception as exc:
                    state.commodity_error = f"Holdings refresh failed: {exc}"
            elif self.path == "/commodity/sell":
                symbol = first(form, "commodity_symbol")
                try:
                    if not checked(form, "commodity_confirmed"):
                        raise PermissionError(
                            "ETF SELL needs 10-second breathe confirmation before order placement."
                        )
                    result, state.console_log = call_with_console(
                        place_commodity_etf_sell_order,
                        symbol,
                    )
                    state.commodity_results = [result]
                    state.message = f"Submitted ETF SELL order for full {symbol.upper()} holding."
                except Exception as exc:
                    state.commodity_results = [
                        {
                            "tradingsymbol": symbol.upper(),
                            "status": "ERROR",
                            "order_id": "",
                            "detail": str(exc),
                        }
                    ]
                    state.console_log = traceback.format_exc()
                    state.message = "Commodity ETF SELL was not submitted. Review the execution result."
                try:
                    state.commodity_holdings = commodity_etf_holdings()
                except Exception as exc:
                    state.commodity_error = f"Holdings refresh failed: {exc}"
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

    def send_login(self, error: str = "") -> None:
        content = render_login_page(error)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
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
