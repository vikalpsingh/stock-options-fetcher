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
import math
import os
import re
import sys
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


DEFAULT_CSV_PATH = PROJECT_ROOT / "src" / "script" / "kite_orders.csv"
DEFAULT_KITE_ENV = {
    "KITE_CONFIRM_LIVE_ORDER": "YES",
    "KITE_API_KEY": "vr6yz47r650vum8p",
    "KITE_API_SECRET": "vgbk58nvcdmtjc68mbrwoebkbldmm4oj",
    "KITE_ACCESS_TOKEN": "TqL81HKQXjdi6KQ9jxsYUz5AIUgrrwxB",
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
DEFAULT_OPENAI_MODEL = "gpt-5.2"
KITE_CALLBACK_HOST = "127.0.0.1"
KITE_CALLBACK_PORT = 8000
PUBLIC_IP_ENDPOINTS = [
    ("Current public IP", "https://api64.ipify.org?format=json"),
    ("IPv4 public IP", "https://api.ipify.org?format=json"),
    ("IPv6 public IP", "https://api6.ipify.org?format=json"),
]
DEFAULT_OPENAI_PROMPT = (
    "Generate a Kite order CSV for a conservative income options basket. "
    "Return only CSV with header: exchange,tradingsymbol,quantity,"
    "transaction_type,product,order_type,price,validity."
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
    openai_api_key: str = ""
    openai_model: str = DEFAULT_OPENAI_MODEL
    openai_prompt: str = DEFAULT_OPENAI_PROMPT
    analytics_symbol: str = ""
    analytics_data: dict[str, Any] | None = None
    research_rows: list[dict[str, Any]] | None = None
    positions_rows: list[dict[str, Any]] | None = None
    positions_summary: dict[str, Any] | None = None
    kite_request_token: str = ""
    kite_ip_data: list[dict[str, str]] | None = None


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
    openai_api_key = first(form, "openai_api_key")
    if openai_api_key:
        os.environ["OPENAI_API_KEY"] = openai_api_key.strip()


def kite_login_url() -> str:
    api_key = env_value("KITE_API_KEY") or DEFAULT_KITE_ENV["KITE_API_KEY"]
    return f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"


def generate_kite_access_token(request_token: str) -> str:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    token = request_token.strip()
    if not token:
        raise ValueError("request_token cannot be empty.")
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
    for underlying in underlyings[:5]:
        query = quote_plus(f"{underlying} NSE stock")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            request = Request(url, headers={"User-Agent": "KiteTraderLocalApp/1.0"})
            with urlopen(request, timeout=8) as response:
                xml_text = response.read().decode("utf-8", errors="ignore")
            root = ElementTree.fromstring(xml_text)
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
                if len(news) >= 3:
                    return news
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
    return news[:3]


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

    underlyings = TOP_WATCHLIST
    if not underlyings:
        return {"ok": True, "quotes": []}

    kite = kite_orders.kite_client()
    instruments = [f"NSE:{symbol}" for symbol in underlyings]
    raw_quotes = kite.quote(instruments)
    quotes: list[dict[str, Any]] = []
    for symbol in underlyings:
        key = f"NSE:{symbol}"
        quote = raw_quotes.get(key, {})
        ltp = float(quote.get("last_price") or 0)
        close = float((quote.get("ohlc") or {}).get("close") or 0)
        change_percent = ((ltp - close) / close * 100) if close > 0 else None
        quotes.append(
            {
                "symbol": symbol,
                "ltp": round(ltp, 2),
                "change_percent": round(change_percent, 2)
                if change_percent is not None
                else None,
            }
        )
    return {"ok": True, "quotes": quotes}


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


def response_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def generate_csv_with_openai(prompt: str, model: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY. Enter it in the GPT CSV Generator tab.")

    instructions = (
        "You generate Zerodha Kite order CSV only. "
        "Output must be plain CSV text, no markdown, no explanation. "
        "Required header exactly: exchange,tradingsymbol,quantity,transaction_type,"
        "product,order_type,price,validity. "
        "Use exchange NFO for options unless the user explicitly says otherwise. "
        "transaction_type must be BUY or SELL. product should usually be NRML. "
        "order_type should usually be LIMIT. validity should usually be DAY. "
        "Follow these risk rules: SELL only when the user says stock is held; "
        "SELL PUT only when the user says cash is available."
    )
    body = {
        "model": model.strip() or DEFAULT_OPENAI_MODEL,
        "instructions": instructions,
        "input": prompt,
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
    return extract_csv_from_text(output)


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
    header = "".join(f"<th>{html.escape(field)}</th>" for field in DISPLAY_FIELDS)
    rows = []
    for index, order in enumerate(orders):
        checked_attr = " checked" if index in selected else ""
        cells = "".join(
            f"<td>{render_symbol_value(field, order.get(field, ''))}</td>"
            for field in DISPLAY_FIELDS
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
        detail = (
            f'<section class="panel"><div class="panel-title">{html.escape(decision_title)}</div>'
            f'<div class="decision-grid">{decision_cards}</div></section>'
            '<section class="panel"><div class="panel-title">Greek Risk Lights</div>'
            f'<div class="decision-grid">{risk_cards}</div>'
            '<div class="table-wrap"><table class="analytics-table">'
            "<tr><th>Indicator</th><th>Value</th><th>Strength</th><th>Meaning</th></tr>"
            f"{risk_rows}</table></div></section>"
            '<section class="panel"><div class="panel-title">Strategy Strength Indicators</div>'
            '<div class="decision-grid">'
            f'<div class="decision-card strength-{html.escape(strength_lights["color"])}">'
            '<div class="decision-label">Final Strategy Strength</div>'
            f'<div class="decision-value">{html.escape(strength_lights["final"])}</div></div></div>'
            '<div class="table-wrap"><table class="analytics-table">'
            "<tr><th>Indicator</th><th>Value</th><th>Strength</th><th>Rule</th></tr>"
            f"{strength_rows}</table></div></section>"
            '<section class="panel"><div class="panel-title">Seller View Greeks</div>'
            '<div class="table-wrap"><table class="analytics-table">'
            f"{seller_rows}</table></div></section>"
            '<section class="panel"><div class="panel-title">Analytics Details</div>'
            '<div class="table-wrap"><table class="analytics-table">'
            f"{cells}</table></div></section>"
            '<section class="panel"><div class="panel-title">Decision Signal Matrix</div>'
            '<div class="table-wrap"><table class="analytics-table">'
            f"<tr>{matrix_headers}</tr>"
            f"{signal_rows}</table></div></section>"
        )

    return f"""
    <form id="analytics-panel" method="post" action="/analytics/load"{'' if state.active_tab == 'analytics' else ' style="display:none"'}>
      <section class="panel">
        <div class="panel-title">Option Analytics</div>
        <div class="analytics-links">{links or '<span class="status">No CSV symbols found.</span>'}</div>
        <div class="analytics-form">
          {render_input("analytics_symbol", "Trading symbol", selected)}
          {env_hidden_fields_for_render()}
          <button type="submit" formaction="/analytics/load">Load Analytics</button>
        </div>
      </section>
      {active_section}
      {detail}
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
        '<section class="panel"><div class="panel-title">CSV Symbol Research Comparison</div>'
        '<div class="table-wrap"><table class="research-table"><thead><tr>'
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
        <p class="status">Compare every trading symbol from kite_orders.csv for SELL CALL / SELL PUT decisions using live Kite analytics.</p>
        <div class="actions">
          <button type="submit" formaction="/research/load">Run Research on CSV Symbols</button>
        </div>
      </section>
      {table}
      {render_console(state.console_log)}
    </form>"""


def render_positions_panel(state: PageState) -> str:
    rows = state.positions_rows or []
    summary = state.positions_summary or {}
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
        "<tr>"
        f"<td>{render_symbol_value('tradingsymbol', row.get('symbol', ''))}</td>"
        f"<td>{html.escape(str(row.get('quantity', '')))}</td>"
        f"<td>{html.escape(str(row.get('product', '')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('average_price')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('ltp')))}</td>"
        f"<td>{html.escape(display_cell('pnl', row.get('pnl', '')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('deployed')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('return_pct')))}%</td>"
        f'<td class="{strength_class(row.get("buy_color"))}">{html.escape(str(row.get("buy_signal", "")))}</td>'
        f"<td>{html.escape(fmt_number(row.get('sell_pop')))}%</td>"
        f"<td>{html.escape(fmt_number(row.get('otm_distance')))}%</td>"
        f'<td class="{strength_class(row.get("sell_color"))}">{html.escape(str(row.get("sell_signal", "")))}</td>'
        f'<td class="{strength_class(row.get("strategy_color"))}">{html.escape(str(row.get("strategy_strength", "")))}</td>'
        f"<td>{html.escape(fmt_number(row.get('delta')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('iv_percent')))}%</td>"
        f"<td>{html.escape(fmt_number(row.get('pcr')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('support')))} / {html.escape(fmt_number(row.get('resistance')))}</td>"
        f"<td>{html.escape(str(row.get('error', '')))}</td>"
        "</tr>"
        for row in rows
    )
    table = (
        '<section class="panel"><div class="panel-title">Active Position Analytics</div>'
        '<div class="table-wrap"><table class="research-table"><thead><tr>'
        '<th>Symbol</th><th>Qty</th><th>Product</th><th>Avg</th><th>LTP</th><th>P&L</th>'
        '<th>Margin required</th><th>Return %</th><th>BUY Decision</th><th>SELL POP</th><th>OTM</th>'
        '<th>SELL Decision</th><th>Strategy Strength</th><th>Delta</th><th>IV</th>'
        '<th>PCR</th><th>Support / Resistance</th><th>Error</th></tr></thead>'
        f"<tbody>{table_rows}</tbody></table></div></section>"
        if rows
        else ""
    )
    return f"""
    <form id="positions-research-panel" method="post" action="/positions-research/load"{'' if state.active_tab == 'positions-research' else ' style="display:none"'}>
      {env_hidden_fields_for_render()}
      <section class="panel">
        <div class="panel-title">Positions</div>
        <p class="status">Evaluate active Kite option trades with the same analytics and summarize current P&L / Kite margin required.</p>
        <div class="actions">
          <button type="submit" formaction="/positions-research/load">Load Active Positions</button>
        </div>
      </section>
      <section class="panel"><div class="panel-title">Positions Summary</div><div class="decision-grid">{summary_cards}</div></section>
      {table}
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
    quote_cards = "".join(
        '<div class="quote-card" data-symbol="'
        f'{html.escape(underlying, quote=True)}">'
        f'<span class="quote-symbol">{html.escape(underlying)}</span>'
        '<span class="quote-ltp">...</span>'
        '<span class="quote-change">--</span>'
        "</div>"
        for underlying in underlyings
    )
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
    <section class="market-shell">
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
        '<button type="submit" formaction="/execute" class="danger" id="execute-selected-button">Execute Selected</button>'
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
    kite_setup_tab_class = "active" if state.active_tab == "kite-setup" else ""
    analytics_tab_class = "active" if state.active_tab == "analytics" else ""
    research_tab_class = "active" if state.active_tab == "research" else ""
    positions_research_tab_class = "active" if state.active_tab == "positions-research" else ""
    place_panel_style = "" if state.active_tab == "place" else ' style="display:none"'
    positions_panel_style = "" if state.active_tab == "positions" else ' style="display:none"'
    gpt_panel_style = "" if state.active_tab == "gpt" else ' style="display:none"'
    kite_setup_panel_style = "" if state.active_tab == "kite-setup" else ' style="display:none"'
    env_panel = f"""
        <section class="panel">
          <div class="panel-title">Kite Environment</div>
          {render_input("api_key", "KITE_API_KEY", state.api_key or env_value("KITE_API_KEY"))}
          {render_input("api_secret", "KITE_API_SECRET", state.api_secret or env_value("KITE_API_SECRET"), "password")}
          {render_input("access_token", "KITE_ACCESS_TOKEN", state.access_token or env_value("KITE_ACCESS_TOKEN"), "password")}
          {render_input("confirm_live_order", "KITE_CONFIRM_LIVE_ORDER", state.confirm_live_order or env_value("KITE_CONFIRM_LIVE_ORDER"))}
          {render_checkbox("show_credentials", "Show credential values", True, "Reveals KITE_API_SECRET and KITE_ACCESS_TOKEN in this local browser page.")}
          <div class="status">{status}</div>
          <div class="panel-title token-title">Generate Kite Access Token</div>
          <div class="actions">
            <a class="button-link" href="{html.escape(kite_login_url(), quote=True)}" target="_blank" rel="noopener">Open Kite Login</a>
          </div>
          <div class="status">After login, copy <code>request_token</code> from the redirected URL and paste it below.</div>
          {render_input("kite_request_token", "Manual request_token fallback", state.kite_request_token)}
          <div class="actions">
            <button type="submit" formaction="/kite-token/generate">Generate Access Token</button>
          </div>
          <div class="panel-title token-title">Allowed IP for Kite Orders</div>
          <div class="status">If Kite says your IP is not allowed, add the matching public IP below in the Kite developer console allowed IP list.</div>
          <div class="actions">
            <button type="submit" formaction="/kite-ip/check">Check Current Public IP</button>
            <a class="inline-link" href="https://developers.kite.trade" target="_blank" rel="noopener">Open Kite Developer Console</a>
          </div>
          {render_kite_ip_data(state.kite_ip_data)}
        </section>"""
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
      padding: 10px 18px;
      color: #ffffff;
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 18px;
    }}
    header h1 {{ margin: 0 0 3px; font-size: 22px; letter-spacing: 0; }}
    header p {{ margin: 0; color: #d5eef3; font-size: 12px; }}
    .naval-quote {{
      margin: 0;
      color: #d1fae5;
      font-size: 13px;
      font-weight: 700;
      text-align: right;
      max-width: 520px;
      line-height: 1.25;
    }}
    .blessing {{
      color: #fef3c7;
      font-size: 17px;
      font-weight: 900;
      text-align: center;
      white-space: nowrap;
    }}
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
      gap: 12px;
      margin-bottom: 10px;
    }}
    .rule-card, .mmi-card {{
      border-radius: 8px;
      padding: 6px 12px;
      color: #ffffff;
      min-height: 42px;
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
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
      font-size: 16px;
      line-height: 1;
      font-weight: 800;
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
      background: #ffffff;
      color: var(--ink);
      border-radius: 8px;
      border: 1px solid var(--line);
      overflow: hidden;
      box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
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
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 14px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
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
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
    }}
    .trading-actions-panel {{
      border-color: #bfdbfe;
      background: #f8fbff;
    }}
    .trading-actions-panel .panel {{
      box-shadow: none;
      margin: 12px 0;
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
    .tab-button.primary-action {{
      padding: 14px 24px;
      font-size: 16px;
      font-weight: 900;
      background: #ffffff;
      color: #0f3b65;
    }}
    .tab-button.utility-action {{
      padding: 10px 14px;
      font-size: 13px;
    }}
    .tab-button.active {{
      background: #ffffff;
      color: var(--accent);
      box-shadow: inset 0 3px 0 var(--accent);
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
    .execution-checks {{
      margin-top: 12px;
      padding-top: 10px;
      border-top: 1px solid var(--line);
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
    .button-link {{
      display: inline-block;
      border-radius: 6px;
      padding: 10px 14px;
      background: linear-gradient(135deg, #1769aa 0%, #0f766e 100%);
      color: #ffffff;
      cursor: pointer;
      font-weight: 700;
      text-decoration: none;
    }}
    .token-title {{
      margin-top: 18px;
    }}
    .alert {{
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 16px;
      border: 1px solid;
    }}
    .alert.ok {{ color: var(--ok); background: #ecfdf5; border-color: #99f6e4; }}
    .alert.error {{ color: var(--danger); background: #fff1f2; border-color: #fecdd3; }}
    .alert pre {{ margin: 0; white-space: pre-wrap; font-family: Consolas, "Courier New", monospace; }}
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
    .research-table {{
      min-width: 2600px;
    }}
    .research-table small {{
      font-size: 10px;
      opacity: 0.9;
    }}
    .compact-indicator {{
      text-align: center;
      min-width: 76px;
      font-weight: 900;
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
    .signal-good {{
      color: #047857;
      font-weight: 900;
      background: #ecfdf5;
    }}
    .signal-green {{
      color: #047857;
      font-weight: 900;
      background: #ecfdf5;
      border-radius: 4px;
      padding: 2px 4px;
    }}
    .signal-yellow {{
      color: #a16207;
      font-weight: 900;
      background: #fef9c3;
      border-radius: 4px;
      padding: 2px 4px;
    }}
    .signal-red {{
      color: #b42318;
      font-weight: 900;
      background: #fee2e2;
      border-radius: 4px;
      padding: 2px 4px;
    }}
    .signal-neutral {{
      color: var(--muted);
      font-weight: 800;
    }}
    .strength-lightgreen {{
      background: #dcfce7;
      color: #047857;
      font-weight: 900;
    }}
    .strength-yellow {{
      background: #fef9c3;
      color: #a16207;
      font-weight: 900;
    }}
    .strength-orange {{
      background: #ffedd5;
      color: #c2410c;
      font-weight: 900;
    }}
    .strength-lightcoral {{
      background: #fee2e2;
      color: #b42318;
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
      .expiry-strip {{ grid-template-columns: 1fr; }}
      .expiry-warning {{ max-width: none; }}
      .grid {{ grid-template-columns: 1fr; }}
      .analytics-form {{ grid-template-columns: 1fr; }}
      header {{ padding: 10px 12px; grid-template-columns: 1fr; align-items: flex-start; }}
      .blessing {{ text-align: left; white-space: normal; }}
      .naval-quote {{ text-align: left; max-width: none; }}
      main {{ width: calc(100vw - 20px); }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Kite Trader</h1>
      <p>Place CSV orders or build BUY orders from existing Kite positions.</p>
    </div>
    <div class="blessing">ॐ | Jai Sri Ram | Jai Laxmi Mata</div>
    <p class="naval-quote">"Trade money for time, not time for money. You're going to run out of time first." - Naval</p>
  </header>
  <main>
    {render_market_topper(state)}
    {alert}
    <div class="tabs">
      <button class="tab-button primary-action {place_tab_class}" type="button" data-tab="place">Trading</button>
      <button class="tab-button primary-action {positions_tab_class}" type="button" data-tab="positions">CLOSE Positions</button>
      <button class="tab-button utility-action {positions_research_tab_class}" type="button" data-tab="positions-research">Positions</button>
      <button class="tab-button utility-action {analytics_tab_class}" type="button" data-tab="analytics">Analytics</button>
      <button class="tab-button utility-action {research_tab_class}" type="button" data-tab="research">Research</button>
      <button class="tab-button utility-action {gpt_tab_class}" type="button" data-tab="gpt">GPT CSV Generator</button>
      <button class="tab-button utility-action {kite_setup_tab_class}" type="button" data-tab="kite-setup">Kite Setup</button>
    </div>
    <form id="place-panel" method="post" action="/load"{place_panel_style}>
      {env_hidden}
      <input type="hidden" name="live_confirmed" id="live-confirmed" value="0">
      <input type="hidden" name="rows_payload" value="{html.escape(rows_payload, quote=True)}">
      <section class="panel trading-actions-panel">
        <div class="panel-title">Execution Options</div>
        {orders_table}
        <div class="actions">
          <button type="submit" formaction="/load">Load / Preview CSV</button>
          {execute_button}
        </div>
        <div class="execution-checks">
          {render_checkbox("dry_run", "Dry run", state.dry_run, "Build orders and show what would happen without sending anything to Kite.")}
          {render_checkbox("no_ltp_price", "Use CSV/manual price only", state.no_ltp_price, "Leave this on when the CSV already has prices or lot_size. Turn off to fetch LTP/lot size from Kite.")}
          {render_checkbox("keep_existing_orders", "Place new order instead of modifying similar open order", state.keep_existing_orders)}
        </div>
      </section>
      <div>
        <section class="panel">
          <div class="panel-title">CSV Source</div>
          {render_input("csv_path", "CSV path", state.csv_path)}
          <label><span>Upload CSV</span><input id="csv-file" type="file" accept=".csv,text/csv"></label>
          <label><span>CSV text</span><textarea id="csv-text" name="csv_text" placeholder="Paste CSV here or choose a file above">{html.escape(state.csv_text)}</textarea></label>
        </section>
      </div>
      {render_results(state.results)}
      {render_console(state.console_log)}
    </form>
    <form id="positions-panel" method="post" action="/positions/load"{positions_panel_style}>
      {env_hidden}
      <input type="hidden" name="position_orders_payload" value="{html.escape(position_orders_payload, quote=True)}">
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
    </form>
    <form id="kite-setup-panel" method="post" action="/kite-setup"{kite_setup_panel_style}>
      {env_panel}
      <div class="actions">
        <button type="submit" formaction="/kite-setup">Save Kite Setup</button>
      </div>
    </form>
    <form id="gpt-panel" method="post" action="/gpt/load"{gpt_panel_style}>
      {env_hidden}
      <div class="grid">
        <section class="panel">
          <div class="panel-title">OpenAI CSV Generator</div>
          {render_input("openai_api_key", "OPENAI_API_KEY", state.openai_api_key or env_value("OPENAI_API_KEY"), "password")}
          {render_input("openai_model", "Model", state.openai_model)}
          <label><span>Prompt for CSV generation</span><textarea class="conversation" name="openai_prompt" placeholder="Describe holdings, cash, expiry, symbols, strikes, lots, prices, and risk preference">{html.escape(state.openai_prompt)}</textarea></label>
          <div class="actions">
            <button type="submit" formaction="/gpt/generate">Generate CSV with OpenAI</button>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title">GPT Share / Paste Fallback</div>
          {render_input("gpt_url", "GPT share URL", state.gpt_url)}
          <a class="inline-link" href="{html.escape(state.gpt_url, quote=True)}" target="_blank" rel="noopener">Open GPT Share</a>
          <label><span>Conversation / GPT output</span><textarea class="conversation" name="gpt_conversation" placeholder="Fetch the share link, or paste GPT output here">{html.escape(state.gpt_conversation)}</textarea></label>
          <div class="actions">
            <button type="submit" formaction="/gpt/load">Fetch GPT Share</button>
            <button type="submit" formaction="/gpt/extract">Extract CSV</button>
          </div>
        </section>
      </div>
      <div class="grid">
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
    {render_analytics_panel(state)}
    {render_research_panel(state)}
    {render_positions_panel(state)}
  </main>
  <div class="live-modal-backdrop" id="live-confirm-modal">
    <div class="live-modal">
      <h2>Pause Before Live Trade</h2>
      <p>Live order placement is about to run. Breathe in, breathe out, then confirm.</p>
      <div class="breath-circle"></div>
      <div class="breath-text" id="breath-text">Breathe in</div>
      <div class="countdown" id="live-countdown">20</div>
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
        document.getElementById('place-panel').style.display = active === 'place' ? '' : 'none';
        document.getElementById('positions-panel').style.display = active === 'positions' ? '' : 'none';
        document.getElementById('gpt-panel').style.display = active === 'gpt' ? '' : 'none';
        document.getElementById('kite-setup-panel').style.display = active === 'kite-setup' ? '' : 'none';
        document.getElementById('analytics-panel').style.display = active === 'analytics' ? '' : 'none';
        document.getElementById('research-panel').style.display = active === 'research' ? '' : 'none';
        document.getElementById('positions-research-panel').style.display = active === 'positions-research' ? '' : 'none';
        for (const item of document.querySelectorAll('.tab-button')) {{
          item.classList.toggle('active', item.dataset.tab === active);
        }}
      }});
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
    let pendingLiveSubmit = false;
    let countdownTimer = null;
    function stopLiveCountdown() {{
      if (countdownTimer) {{
        clearInterval(countdownTimer);
        countdownTimer = null;
      }}
    }}
    function openLiveModal() {{
      let remaining = 20;
      pendingLiveSubmit = true;
      liveGood.disabled = true;
      liveCountdown.textContent = String(remaining);
      breathText.textContent = 'Breathe in';
      liveModal.style.display = 'flex';
      loadTradeNews();
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
    function selectedTradingSymbols() {{
      const symbols = [];
      const rows = placeForm.querySelectorAll('table tbody tr');
      for (const row of rows) {{
        const checkbox = row.querySelector('input[name="selected"]');
        if (checkbox && checkbox.checked && row.cells.length > 2) {{
          symbols.push(row.cells[2].innerText.trim());
        }}
      }}
      return symbols;
    }}
    async function loadTradeNews() {{
      if (!tradeNews) return;
      const symbols = selectedTradingSymbols();
      if (!symbols.length) {{
        tradeNews.textContent = 'No selected symbols found.';
        return;
      }}
      tradeNews.textContent = 'Loading selected stock news...';
      try {{
        const response = await fetch(`/trade-news?symbols=${{encodeURIComponent(symbols.join(','))}}`, {{ cache: 'no-store' }});
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
            card.classList.toggle('strong-up', pct > 2);
            card.classList.toggle('strong-down', pct < -2);
          }}
        }}
      }} catch (error) {{
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
    setInterval(refreshQuotes, 10000);
  </script>
</body>
</html>"""
    return html_doc.encode("utf-8")


class KiteWebHandler(BaseHTTPRequestHandler):
    server_version = "KiteCSVTrader/1.0"

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
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
        if parsed_url.path == "/trade-news":
            query = parse_qs(parsed_url.query, keep_blank_values=True)
            symbols_text = first(query, "symbols")
            symbols = [item for item in symbols_text.split(",") if item.strip()]
            try:
                self.send_json({"ok": True, "news": fetch_stock_news(symbols)})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc), "news": []})
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
                else "kite-setup"
                if self.path.startswith("/kite-setup") or self.path.startswith("/kite-token") or self.path.startswith("/kite-ip")
                else "analytics"
                if self.path.startswith("/analytics")
                else "research"
                if self.path.startswith("/research")
                else "positions-research"
                if self.path.startswith("/positions-research")
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
            openai_api_key=first(form, "openai_api_key"),
            openai_model=first(form, "openai_model", DEFAULT_OPENAI_MODEL),
            openai_prompt=first(form, "openai_prompt", DEFAULT_OPENAI_PROMPT),
            analytics_symbol=first(form, "analytics_symbol"),
            kite_request_token=first(form, "kite_request_token"),
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
            elif self.path == "/gpt/generate":
                state.gpt_csv_text, state.console_log = call_with_console(
                    generate_csv_with_openai,
                    state.openai_prompt,
                    state.openai_model,
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
                state.message = "Kite setup saved for this running web app session."
            elif self.path == "/kite-token/generate":
                access_token, state.console_log = call_with_console(
                    generate_kite_access_token,
                    state.kite_request_token,
                )
                state.access_token = access_token
                state.message = "Generated and saved KITE_ACCESS_TOKEN for this running web app session."
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
            elif self.path == "/positions-research/load":
                (
                    state.positions_rows,
                    state.positions_summary,
                ), state.console_log = call_with_console(positions_research)
                state.message = (
                    f"Loaded analytics for {len(state.positions_rows)} active option position(s)."
                )
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
