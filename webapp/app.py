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
import copy
import csv
import hashlib
import hmac
import html
import io
import json
import math
import os
import re
import sqlite3
import sys
import threading
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
from zoneinfo import ZoneInfo


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
PE_SELL_SETTINGS_PATH = APP_ROOT / "pe_sell_strategy.json"
CE_SELL_SETTINGS_PATH = APP_ROOT / "ce_sell_strategy.json"
APP_DB_PATH = APP_ROOT / "vikalp_income.db"
OPENAI_CSV_PROMPT_PATH = APP_ROOT / "openai_csv_prompt.md"
DEFAULT_ETF_BUY_AMOUNT = 10000.0
DEFAULT_OPTION_SELL_MARKUP_PERCENT = 20.0
POSITION_CLOSE_SCHEDULE_TIME = "09:20"
POSITION_CLOSE_SCHEDULE_WINDOW_MINUTES = 10
INCOME_GROWTH_GPT_SCHEDULE_TIME = "09:30"
INCOME_GROWTH_GPT_SCHEDULE_WINDOW_MINUTES = 15
INTRADAY_POSITION_CLOSE_START_TIME = "09:30"
INTRADAY_POSITION_CLOSE_END_TIME = "15:15"
INTRADAY_POSITION_CLOSE_INTERVAL_MINUTES = 15
INDIA_TIME_ZONE = ZoneInfo("Asia/Kolkata")
DEFAULT_KITE_ENV = {
    "KITE_CONFIRM_LIVE_ORDER": "YES",
    "KITE_API_KEY": "vr6yz47r650vum8p",
    "KITE_API_SECRET": "vgbk58nvcdmtjc68mbrwoebkbldmm4oj",
    "KITE_ACCESS_TOKEN": "TqL81HKQXjdi6KQ9jxsYUz5AIUgrrwxB",
}
KITE_PROFILE_NAMES = ["Vikalp", "Monika", "Shanti", "Aanya"]
DEFAULT_KITE_PROFILE = "Shanti"
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
MAX_TRADING_ORDER_OTM_PERCENT = 12.5
MAX_TOP3_CE_SELL_LOTS = 1
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
GLOBAL_MARKET_WATCHLIST = [
    {"label": "NIFTY", "symbol": "KITE:NIFTY_50", "source": "kite_quote", "kite_key": "NSE:NIFTY 50", "fallback_symbol": "^NSEI"},
    {"label": "NIFTY FUT", "symbol": "KITE:NIFTY_FUT", "source": "kite_nifty_fut", "fallback_symbol": "^NSEI"},
    {"label": "INDIA VIX", "symbol": "KITE:INDIA_VIX", "source": "kite_quote", "kite_key": "NSE:INDIA VIX", "fallback_symbol": "^INDIAVIX"},
    {"label": "USD/INR", "symbol": "INR=X"},
    {"label": "NASDAQ FUT", "symbol": "NQ=F"},
    {"label": "Nasdaq", "symbol": "^IXIC"},
    {"label": "FTSE", "symbol": "^FTSE"},
    {"label": "Hang Seng", "symbol": "^HSI"},
    {"label": "Nikkei", "symbol": "^N225"},
    {"label": "Gold", "symbol": "GC=F"},
    {"label": "Crude", "symbol": "CL=F"},
]
TOP_QUOTE_REFRESH_MS = 300000
TOP_QUOTE_CACHE_SECONDS = 300
APP_CACHE: dict[str, tuple[float, Any]] = {}
APP_CACHE_LOCK = threading.Lock()
APP_CACHE_KEY_LOCKS: dict[str, threading.Lock] = {}
SETTINGS_LOCK = threading.RLock()
POSITION_CLOSE_SCHEDULER_LOCK = threading.Lock()
INCOME_GROWTH_GPT_SCHEDULER_LOCK = threading.Lock()
INTRADAY_POSITION_CLOSE_SCHEDULER_LOCK = threading.Lock()
KITE_READ_CACHE_SECONDS = 60
KITE_QUOTE_CACHE_SECONDS = 60
KITE_INSTRUMENT_CACHE_SECONDS = 3600
INVESTING_NEWS_CACHE_SECONDS = 12 * 60 * 60
INVESTING_52W_CACHE_SECONDS = 24 * 60 * 60
COMMODITY_DMA_CACHE_SECONDS = 12 * 60 * 60
INCOME_GROWTH_GPT_CACHE_SECONDS = 30 * 60
INCOME_DASHBOARD_CACHE_SECONDS = 15 * 60
CE_SELL_DASHBOARD_CACHE_SECONDS = 15 * 60
DEFAULT_PE_SELL_SETTINGS = {
    "max_assignment_cash_per_stock": 600000,
    "min_otm_percent": 8,
    "max_otm_percent": 12,
    "min_premium_yield_percent": 0.30,
    "min_sell_pop_percent": 88,
    "max_delta": 0.20,
    "min_option_oi": 0,
    "min_option_volume": 0,
    "max_bid_ask_spread_percent": 25,
    "event_lookahead_trading_days": 5,
    "preferred_dte_min": 12,
    "preferred_dte_max": 28,
    "price_markup_percent": DEFAULT_OPTION_SELL_MARKUP_PERCENT,
}
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
INVESTING_HOLDINGS = [
    {"code": "NSE:SCHNEIDER", "company": "Schneider", "sector": "Elec Infra", "core": "Y", "quantity": 3435, "avg_price": 475.37},
    {"code": "NSE:PGEL", "company": "PG Electroplast Ltd", "sector": "Manf", "core": "Y", "quantity": 7350, "avg_price": 107.40},
    {"code": "BSE:501423", "company": "Shaily Engg", "sector": "Manf", "core": "N", "quantity": 1206, "avg_price": 174.98},
    {"code": "NSE:ETERNAL", "company": "Eternal Ltd", "sector": "Quick Comm", "core": "N", "quantity": 11500, "avg_price": 63.59},
    {"code": "NSE:CAPLIPOINT", "company": "Caplin Point Laboratories Ltd", "sector": "Pharma", "core": "Y", "quantity": 1099, "avg_price": 532.00},
    {"code": "NSE:BAJFINANCE", "company": "Bajaj Finance Ltd", "sector": "NBFC", "core": "Y", "quantity": 2310, "avg_price": 666.45},
    {"code": "NSE:BANCOINDIA", "company": "Banco Products (India) Ltd", "sector": "Auto", "core": "Y", "quantity": 3577, "avg_price": 91.97},
    {"code": "NSE:UNITDSPR", "company": "United Spirits Ltd", "sector": "FMCG", "core": "Y", "quantity": 1522, "avg_price": 883.67},
    {"code": "NSE:JAYKAY", "company": "Jaykay", "sector": "Manf", "core": "N", "quantity": 12000, "avg_price": 38.40},
    {"code": "NSE:E2E", "company": "E2E Networks", "sector": "Data Center", "core": "", "quantity": 4630, "avg_price": 213.00},
    {"code": "NSE:PFC", "company": "Power Finance Corporation Ltd", "sector": "Power", "core": "Y", "quantity": 3515, "avg_price": 167.71},
    {"code": "NSE:NAZARA", "company": "Nazara Tech", "sector": "EGAME", "core": "Y", "quantity": 4412, "avg_price": 162.65},
    {"code": "NSE:ZENTEC", "company": "Zen Tech", "sector": "Defence", "core": "N", "quantity": 794, "avg_price": 417.36},
    {"code": "NSE:MAZDOCK", "company": "Mazagon Dock Shipbuilders Ltd", "sector": "Service", "core": "", "quantity": 475, "avg_price": 290.53},
    {"code": "NSE:TATACONSUM", "company": "Tata Consumer Products Ltd", "sector": "FMCG", "core": "Y", "quantity": 650, "avg_price": 828.00},
    {"code": "NSE:MAXIND", "company": "Max India Ltd", "sector": "Health", "core": "N", "quantity": 4900, "avg_price": 152.13},
    {"code": "NSE:TITAN", "company": "Titan", "sector": "Cosmetic", "core": "Y", "quantity": 182, "avg_price": 3409.78},
    {"code": "NSE:JSWINFRA", "company": "JSW Infra", "sector": "Infra", "core": "Y", "quantity": 2755, "avg_price": 184.63},
    {"code": "NSE:FIEMIND", "company": "Fiem Industries Ltd", "sector": "Auto", "core": "N", "quantity": 333, "avg_price": 677.39},
    {"code": "NSE:HAVELLS", "company": "Havells India Ltd", "sector": "Good", "core": "Y", "quantity": 520, "avg_price": 1375.19},
    {"code": "NSE:NAUKRI", "company": "Info Edge", "sector": "Start ups", "core": "Y", "quantity": 615, "avg_price": 771.21},
    {"code": "NSE:CDSL", "company": "Central Depository Services (India) Ltd", "sector": "Capital Market", "core": "Y", "quantity": 410, "avg_price": 678.05},
    {"code": "NSE:EPACK", "company": "Epack Durable Ltd", "sector": "Manf", "core": "", "quantity": 1750, "avg_price": 176.00},
    {"code": "BSE:516030", "company": "Pakka Limited", "sector": "Manf", "core": "N", "quantity": 4400, "avg_price": 184.00},
    {"code": "NSE:LATENTVIEW", "company": "Latent View", "sector": "IT", "core": "N", "quantity": 1250, "avg_price": 373.40},
    {"code": "NSE:URBANCO", "company": "Urban Company", "sector": "Services", "core": "", "quantity": 3411, "avg_price": 168.89},
    {"code": "NSE:WAAREEENER", "company": "Waaree Energies", "sector": "Energy", "core": "", "quantity": 130, "avg_price": 1503.00},
    {"code": "NSE:NTPC", "company": "NTPC Ltd", "sector": "Manf", "core": "", "quantity": 927, "avg_price": 214.53},
    {"code": "NSE:NSE", "company": "NSE", "sector": "Capital Market", "core": "", "quantity": 175, "avg_price": 2000.00},
    {"code": "NSE:CAMS", "company": "Computer Age Management Services Ltd", "sector": "Capital Market", "core": "", "quantity": 410, "avg_price": 582.00},
    {"code": "NSE:NIFTYBEES", "company": "Nifty INDEX", "sector": "Index", "core": "", "quantity": 1175, "avg_price": 265.00},
    {"code": "NSE:OLAELEC", "company": "OLA Elec", "sector": "EV", "core": "", "quantity": 8265, "avg_price": 73.91},
    {"code": "NSE:FRESHARA", "company": "Freshara", "sector": "Food", "core": "", "quantity": 1200, "avg_price": 180.00},
    {"code": "BSE:543940", "company": "Beacon Trusteeship", "sector": "Capital Market", "core": "", "quantity": 2000, "avg_price": 82.00},
    {"code": "NSE:JYOTICNC", "company": "Jyoti CNC Automation Ltd", "sector": "CNC Auto", "core": "", "quantity": 245, "avg_price": 389.00},
    {"code": "NSE:ANANTRAJ", "company": "Anant Raj", "sector": "Capital Market", "core": "", "quantity": 250, "avg_price": 495.00},
    {"code": "NSE:PROTEAN", "company": "Protean EGov", "sector": "IT", "core": "Y", "quantity": 200, "avg_price": 883.00},
    {"code": "BSE:544278", "company": "Addictive Learning", "sector": "EDU TECH", "core": "", "quantity": 1000, "avg_price": 114.00},
    {"code": "NSE:MEGATHERM", "company": "Megatherm", "sector": "Metal", "core": "", "quantity": 400, "avg_price": 300.00},
    {"code": "NSE:NUVAMA", "company": "NUVAMA", "sector": "Capital Market", "core": "", "quantity": 0, "avg_price": 0.0},
]
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
CURRENT_FNO_LOT_SIZES = {
    "ETERNAL": 2425,
    "CAMS": 750,
    "PGEL": 950,
    "PFC": 1300,
    "TITAN": 175,
    "HAVELLS": 500,
    "CDSL": 475,
    "MAZDOCK": 200,
    "WAAREEENER": 175,
    "UNITDSPR": 400,
    "BAJFINANCE": 750,
    "TATACONSUM": 550,
    "NAUKRI": 375,
    "NTPC": 1500,
}


def current_lot_metrics(symbol: str, holding: Any, requested_lots: Any) -> dict[str, Any]:
    lot_size = int(CURRENT_FNO_LOT_SIZES.get(str(symbol or "").upper()) or 0)
    holding_qty = int(float(holding or 0))
    configured_lots = max(0, int(float(requested_lots or 0)))
    covered_lots = holding_qty // lot_size if lot_size > 0 else 0
    lots_can_sell = min(configured_lots, covered_lots)
    return {
        "lot_size": lot_size,
        "times_lot": round(holding_qty / lot_size, 2) if lot_size > 0 else 0.0,
        "lots_can_sell": float(lots_can_sell),
        "to_sell": lot_size * 1.10 if lot_size > 0 else 0.0,
    }


INCOME_GROWTH_SHEET = [
    {"symbol": "BAJFINANCE", "holding": 2310, "times_lot": 3.08, "lots_can_sell": 1.0, "cmp": 909.3, "call_strike": 982, "value": 2100483, "to_sell": 825, "lot_size": 750, "gap_pct": 8, "put_down_pct": 29.8, "pe": 837, "week_52": -21.25, "one_year": 1.78, "month": -4.3, "week_1": -3.46, "today": -2.4},
    {"symbol": "TATACONSUM", "holding": 650, "times_lot": 1.18, "lots_can_sell": 1.0, "cmp": 1173.4, "call_strike": 1267, "value": 762710, "to_sell": 605, "lot_size": 550, "gap_pct": 8, "put_down_pct": 75.33, "pe": 1080, "week_52": -9.31, "one_year": 5.53, "month": 1.12, "week_1": -1.16, "today": -2.6},
    {"symbol": "PGEL", "holding": 7350, "times_lot": 8.17, "lots_can_sell": 3.0, "cmp": 483, "call_strike": 522, "value": 3550050, "to_sell": 990, "lot_size": 950, "gap_pct": 8, "put_down_pct": 50.06, "pe": 444, "week_52": -73.18, "one_year": -37.95, "month": -9.64, "week_1": 2.49, "today": 1.5},
    {"symbol": "TITAN", "holding": 182, "times_lot": 1.04, "lots_can_sell": 1.0, "cmp": 4112.1, "call_strike": 4441, "value": 748402.2, "to_sell": 192.5, "lot_size": 175, "gap_pct": 8, "put_down_pct": 71.94, "pe": 3783, "week_52": -11.99, "one_year": 17.35, "month": -5.75, "week_1": -1.13, "today": -0.6},
    {"symbol": "ETERNAL", "holding": 11500, "times_lot": 4.69, "lots_can_sell": 2.0, "cmp": 251.99, "call_strike": 272, "value": 2897885, "to_sell": 2695, "lot_size": 2425, "gap_pct": 8, "put_down_pct": 646.13, "pe": 232, "week_52": -46.22, "one_year": -1.78, "month": 0.04, "week_1": 1.74, "today": -1.8},
    {"symbol": "UNITDSPR", "holding": 1522, "times_lot": 4.35, "lots_can_sell": 2.0, "cmp": 1271, "call_strike": 1373, "value": 1934462, "to_sell": 385, "lot_size": 400, "gap_pct": 8, "put_down_pct": None, "pe": 1169, "week_52": -29.43, "one_year": -21.06, "month": -3.84, "week_1": -1.02, "today": -2.4},
    {"symbol": "HAVELLS", "holding": 520, "times_lot": 1.04, "lots_can_sell": 1.0, "cmp": 1186, "call_strike": 1281, "value": 616720, "to_sell": 550, "lot_size": 500, "gap_pct": 8, "put_down_pct": 44.02, "pe": 1091, "week_52": -36.69, "one_year": -20.3, "month": -5.62, "week_1": -1.48, "today": -2.1},
    {"symbol": "NAUKRI", "holding": 615, "times_lot": 1.64, "lots_can_sell": 1.0, "cmp": 1002, "call_strike": 1082, "value": 616230, "to_sell": 412.5, "lot_size": 375, "gap_pct": 8, "put_down_pct": 44.81, "pe": 922, "week_52": -54.69, "one_year": -32.04, "month": 2.6, "week_1": 6.77, "today": -0.4},
    {"symbol": "PFC", "holding": 3515, "times_lot": 2.70, "lots_can_sell": 2.0, "cmp": 431, "call_strike": 465, "value": 1514965, "to_sell": 1430, "lot_size": 1300, "gap_pct": 8, "put_down_pct": 5.49, "pe": 397, "week_52": -12.88, "one_year": 5.66, "month": -3.85, "week_1": -1.8, "today": -0.6},
    {"symbol": "CAMS", "holding": 410, "times_lot": 1.03, "lots_can_sell": 1.0, "cmp": 790, "call_strike": 853, "value": 323900, "to_sell": 440, "lot_size": 750, "gap_pct": 8, "put_down_pct": 41.3, "pe": 727, "week_52": -10.76, "one_year": -7.02, "month": 8.09, "week_1": 2.64, "today": 0.4},
    {"symbol": "CDSL", "holding": 410, "times_lot": 0.86, "lots_can_sell": 1.0, "cmp": 1245, "call_strike": 1345, "value": 510450, "to_sell": 522.5, "lot_size": 475, "gap_pct": 8, "put_down_pct": 57.06, "pe": 1145, "week_52": -46.90, "one_year": -30.01, "month": 0.54, "week_1": 2.27, "today": 0.1},
    {"symbol": "MAZDOCK", "holding": 475, "times_lot": 1.58, "lots_can_sell": 1.0, "cmp": 2460, "call_strike": 2657, "value": 1168500, "to_sell": 330, "lot_size": 200, "gap_pct": 8, "put_down_pct": 38.41, "pe": 2263, "week_52": -53.46, "one_year": -28.28, "month": -5.8, "week_1": -0.41, "today": 0.2},
    {"symbol": "NUVAMA", "holding": 0, "times_lot": 0.0, "lots_can_sell": 0.0, "cmp": 1563, "call_strike": 1688, "value": 0, "to_sell": 550, "lot_size": 500, "gap_pct": 8, "put_down_pct": 27.88, "pe": 1438, "week_52": -8.87, "one_year": 8.34, "month": 17.58, "week_1": 3.87, "today": 1.7},
    {"symbol": "NTPC", "holding": 927, "times_lot": 0.62, "lots_can_sell": 1.0, "cmp": 389.5, "call_strike": 421, "value": 361066.5, "to_sell": 1650, "lot_size": 1500, "gap_pct": 8, "put_down_pct": 13.96, "pe": 358, "week_52": -6.39, "one_year": 18.52, "month": -2.64, "week_1": -0.14, "today": -2.2},
    {"symbol": "WAAREEENER", "holding": 130, "times_lot": 0.74, "lots_can_sell": 1.0, "cmp": 3129.1, "call_strike": 3379, "value": 406783, "to_sell": 192.5, "lot_size": 175, "gap_pct": 8, "put_down_pct": 24.29, "pe": 2879, "week_52": -23.52, "one_year": 9.7, "month": -0.23, "week_1": 4.86, "today": 0.0},
]
INCOME_GROWTH_LOT_CAPS = {
    str(item.get("symbol") or "").upper(): float(item.get("lots_can_sell") or 0)
    for item in INCOME_GROWTH_SHEET
}
for income_growth_item in INCOME_GROWTH_SHEET:
    income_growth_symbol = str(income_growth_item.get("symbol") or "").upper()
    if income_growth_symbol in CURRENT_FNO_LOT_SIZES:
        income_growth_item.update(
            current_lot_metrics(
                income_growth_symbol,
                income_growth_item.get("holding"),
                income_growth_item.get("lots_can_sell"),
            )
        )
INCOME_GROWTH_BY_SYMBOL = {
    str(item["symbol"]).upper().replace("NSE:", "").replace("BSE:", ""): item
    for item in INCOME_GROWTH_SHEET
}
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


def app_now() -> datetime:
    return datetime.now()


def normalize_income_growth_symbol(value: Any) -> str:
    return str(value or "").upper().replace("NSE:", "").replace("BSE:", "").strip()


def app_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(APP_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS booked_pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booked_date TEXT NOT NULL,
            month_key TEXT NOT NULL,
            source TEXT NOT NULL,
            tradingsymbol TEXT NOT NULL,
            order_id TEXT NOT NULL UNIQUE,
            close_qty INTEGER NOT NULL,
            sell_avg REAL NOT NULL,
            buy_avg REAL NOT NULL,
            pnl REAL NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_booked_pnl_month ON booked_pnl(month_key, source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_booked_pnl_date ON booked_pnl(booked_date)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS income_growth_holdings (
            symbol TEXT PRIMARY KEY,
            holding REAL NOT NULL DEFAULT 0,
            times_lot REAL,
            lots_can_sell REAL,
            cmp REAL,
            call_strike REAL,
            value REAL,
            to_sell REAL,
            lot_size REAL,
            gap_pct REAL,
            put_down_pct REAL,
            pe REAL,
            week_52 REAL,
            one_year REAL,
            month REAL,
            week_1 REAL,
            today REAL,
            updated_at TEXT NOT NULL
        )
        """
    )
    existing_income_growth = conn.execute("SELECT COUNT(*) FROM income_growth_holdings").fetchone()[0]
    if existing_income_growth == 0:
        now_text = app_now().isoformat(timespec="seconds")
        for item in INCOME_GROWTH_SHEET:
            conn.execute(
                """
                INSERT INTO income_growth_holdings (
                    symbol, holding, times_lot, lots_can_sell, cmp, call_strike, value,
                    to_sell, lot_size, gap_pct, put_down_pct, pe, week_52, one_year,
                    month, week_1, today, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalize_income_growth_symbol(item.get("symbol")),
                    item.get("holding") or 0,
                    item.get("times_lot"),
                    item.get("lots_can_sell"),
                    item.get("cmp"),
                    item.get("call_strike"),
                    item.get("value"),
                    item.get("to_sell"),
                    item.get("lot_size"),
                    item.get("gap_pct"),
                    item.get("put_down_pct"),
                    item.get("pe"),
                    item.get("week_52"),
                    item.get("one_year"),
                    item.get("month"),
                    item.get("week_1"),
                    item.get("today"),
                    now_text,
                ),
            )
    for symbol in INCOME_GROWTH_BY_SYMBOL:
        if symbol not in CURRENT_FNO_LOT_SIZES:
            continue
        saved = conn.execute(
            "SELECT holding FROM income_growth_holdings WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if saved is None:
            continue
        metrics = current_lot_metrics(
            symbol,
            saved["holding"],
            INCOME_GROWTH_LOT_CAPS.get(symbol),
        )
        conn.execute(
            """
            UPDATE income_growth_holdings
            SET lot_size = ?, times_lot = ?, lots_can_sell = ?, to_sell = ?
            WHERE symbol = ?
            """,
            (
                metrics["lot_size"],
                metrics["times_lot"],
                metrics["lots_can_sell"],
                metrics["to_sell"],
                symbol,
            ),
        )
    conn.commit()
    return conn


def parse_order_date(order: dict[str, Any]) -> date:
    for key in ("order_timestamp", "exchange_timestamp", "exchange_update_timestamp"):
        value = order.get(key)
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if value:
            text = str(value).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M:%S"):
                try:
                    return datetime.strptime(text[:19], fmt).date()
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
            except ValueError:
                pass
    return app_now().date()


def booked_pnl_source(symbol: str) -> str:
    underlying = underlying_for_symbol(symbol)
    return "income" if underlying in {item["symbol"] for item in INCOME_UNDERLYINGS} else "trading"


def save_booked_pnl_records(records: list[dict[str, Any]]) -> int:
    if not records:
        return 0
    saved = 0
    now_text = app_now().isoformat(timespec="seconds")
    conn = app_db_connection()
    try:
        for record in records:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO booked_pnl (
                    booked_date, month_key, source, tradingsymbol, order_id,
                    close_qty, sell_avg, buy_avg, pnl, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["booked_date"],
                    record["month_key"],
                    record["source"],
                    record["tradingsymbol"],
                    record["order_id"],
                    int(record["close_qty"]),
                    float(record["sell_avg"]),
                    float(record["buy_avg"]),
                    float(record["pnl"]),
                    record.get("note") or "",
                    now_text,
                ),
            )
            saved += int(cursor.rowcount or 0)
        conn.commit()
    finally:
        conn.close()
    return saved


def monthly_booked_pnl_summary(day: date | None = None) -> dict[str, Any]:
    day = day or app_now().date()
    month_key = day.strftime("%Y-%m")
    summary = {
        "month_key": month_key,
        "month_label": day.strftime("%b %Y"),
        "trading_pnl": 0.0,
        "income_pnl": 0.0,
        "overall_pnl": 0.0,
        "today_pnl": 0.0,
        "trade_count": 0,
        "today_count": 0,
    }
    if not APP_DB_PATH.exists():
        return summary
    try:
        conn = app_db_connection()
        try:
            rows = conn.execute(
                "SELECT source, SUM(pnl) AS pnl, COUNT(*) AS count FROM booked_pnl WHERE month_key = ? GROUP BY source",
                (month_key,),
            ).fetchall()
            for row in rows:
                source = str(row["source"])
                pnl = float(row["pnl"] or 0)
                if source == "income":
                    summary["income_pnl"] = pnl
                else:
                    summary["trading_pnl"] += pnl
                summary["trade_count"] += int(row["count"] or 0)
            today_row = conn.execute(
                "SELECT SUM(pnl) AS pnl, COUNT(*) AS count FROM booked_pnl WHERE booked_date = ?",
                (day.isoformat(),),
            ).fetchone()
            summary["today_pnl"] = float(today_row["pnl"] or 0) if today_row else 0.0
            summary["today_count"] = int(today_row["count"] or 0) if today_row else 0
        finally:
            conn.close()
    except Exception:
        return summary
    summary["overall_pnl"] = float(summary["trading_pnl"]) + float(summary["income_pnl"])
    return summary


def place_order_allowing_autoslice(kite: Any, order: dict[str, Any]) -> str:
    try:
        return kite_orders.place_order(kite, order)
    except Exception as exc:
        message = str(exc).lower()
        if "autoslice" in order and "autoslice" in message and "unexpected" in message:
            fallback = dict(order)
            fallback.pop("autoslice", None)
            return kite_orders.place_order(kite, fallback)
        raise


def load_app_settings() -> dict[str, Any]:
    with SETTINGS_LOCK:
        if not SETTINGS_PATH.exists():
            return {}
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}


def save_app_settings(settings: dict[str, Any]) -> None:
    with SETTINGS_LOCK:
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


def blank_kite_profile() -> dict[str, str]:
    return {
        "KITE_CONFIRM_LIVE_ORDER": "YES",
        "KITE_API_KEY": "",
        "KITE_API_SECRET": "",
        "KITE_ACCESS_TOKEN": "",
    }


def shanti_default_kite_profile() -> dict[str, str]:
    return {
        "KITE_CONFIRM_LIVE_ORDER": env_value("KITE_CONFIRM_LIVE_ORDER")
        or DEFAULT_KITE_ENV["KITE_CONFIRM_LIVE_ORDER"],
        "KITE_API_KEY": env_value("KITE_API_KEY") or DEFAULT_KITE_ENV["KITE_API_KEY"],
        "KITE_API_SECRET": env_value("KITE_API_SECRET") or DEFAULT_KITE_ENV["KITE_API_SECRET"],
        "KITE_ACCESS_TOKEN": env_value("KITE_ACCESS_TOKEN")
        or DEFAULT_KITE_ENV["KITE_ACCESS_TOKEN"],
    }


def normalize_kite_profile_name(value: str | None) -> str:
    text = str(value or "").strip()
    for name in KITE_PROFILE_NAMES:
        if text.lower() == name.lower():
            return name
    saved = str(load_app_settings().get("selected_kite_profile") or "").strip()
    for name in KITE_PROFILE_NAMES:
        if saved.lower() == name.lower():
            return name
    return DEFAULT_KITE_PROFILE


def load_kite_profiles() -> dict[str, dict[str, str]]:
    settings = load_app_settings()
    saved_profiles = settings.get("kite_profiles")
    profiles = {name: blank_kite_profile() for name in KITE_PROFILE_NAMES}
    profiles[DEFAULT_KITE_PROFILE] = shanti_default_kite_profile()
    if isinstance(saved_profiles, dict):
        for name in KITE_PROFILE_NAMES:
            saved_profile = saved_profiles.get(name)
            if not isinstance(saved_profile, dict):
                continue
            merged = blank_kite_profile()
            if name == DEFAULT_KITE_PROFILE:
                merged.update(shanti_default_kite_profile())
            for key in DEFAULT_KITE_ENV:
                if key in saved_profile:
                    merged[key] = str(saved_profile.get(key) or "").strip()
            profiles[name] = merged
    return profiles


def selected_kite_profile_name(value: str | None = None) -> str:
    return normalize_kite_profile_name(value)


def save_kite_profile(profile_name: str, values: dict[str, str]) -> dict[str, str]:
    clean_name = selected_kite_profile_name(profile_name)
    profiles = load_kite_profiles()
    current = profiles.get(clean_name, blank_kite_profile())
    for key in DEFAULT_KITE_ENV:
        if key in values:
            current[key] = str(values.get(key) or "").strip()
    if not current.get("KITE_CONFIRM_LIVE_ORDER"):
        current["KITE_CONFIRM_LIVE_ORDER"] = "YES"
    profiles[clean_name] = current
    save_app_settings(
        {
            "kite_profiles": profiles,
            "selected_kite_profile": clean_name,
        }
    )
    return current


def kite_profile_values_from_state(state: Any, access_token: str | None = None) -> dict[str, str]:
    return {
        "KITE_CONFIRM_LIVE_ORDER": str(state.confirm_live_order or "").strip() or "YES",
        "KITE_API_KEY": str(state.api_key or "").strip(),
        "KITE_API_SECRET": str(state.api_secret or "").strip(),
        "KITE_ACCESS_TOKEN": str(
            access_token if access_token is not None else state.access_token or ""
        ).strip(),
    }


def apply_kite_profile_to_env(values: dict[str, str]) -> None:
    for key in DEFAULT_KITE_ENV:
        os.environ[key] = str(values.get(key) or "").strip()


def etf_buy_amount_setting() -> float:
    value = load_app_settings().get("etf_buy_amount", DEFAULT_ETF_BUY_AMOUNT)
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return DEFAULT_ETF_BUY_AMOUNT
    return amount if amount > 0 else DEFAULT_ETF_BUY_AMOUNT


def option_sell_markup_percent_setting() -> float:
    value = load_app_settings().get(
        "option_sell_markup_percent",
        DEFAULT_OPTION_SELL_MARKUP_PERCENT,
    )
    try:
        markup = float(value)
    except (TypeError, ValueError):
        return DEFAULT_OPTION_SELL_MARKUP_PERCENT
    return markup if markup >= 0 else DEFAULT_OPTION_SELL_MARKUP_PERCENT


def normalize_home_tickers(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\s,]+", value)
    elif isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        raw_items = []
    tickers: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        clean = item.strip().upper()
        if not clean:
            continue
        clean = clean.removeprefix("NSE:")
        if clean not in seen:
            tickers.append(clean)
            seen.add(clean)
    return tickers


def home_tickers_setting() -> list[str]:
    saved = normalize_home_tickers(load_app_settings().get("home_tickers", []))
    return saved or TOP_WATCHLIST


def home_tickers_text() -> str:
    return "\n".join(home_tickers_setting())


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


def apply_option_sell_markup_setting(settings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(settings)
    merged["price_markup_percent"] = option_sell_markup_percent_setting()
    return merged


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
    kite_profile: str = field(default_factory=selected_kite_profile_name)
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
    position_live_confirmed: bool = False
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
    ce_sell_top: list[dict[str, Any]] | None = None
    ce_sell_watch: list[dict[str, Any]] | None = None
    ce_sell_avoid: list[dict[str, Any]] | None = None
    research_rows: list[dict[str, Any]] | None = None
    positions_rows: list[dict[str, Any]] | None = None
    positions_summary: dict[str, Any] | None = None
    commodity_results: list[dict[str, Any]] | None = None
    commodity_holdings: list[dict[str, Any]] | None = None
    commodity_error: str = ""
    investing_rows: list[dict[str, Any]] | None = None
    investing_summary: dict[str, Any] | None = None
    income_growth_rows: list[dict[str, Any]] | None = None
    income_growth_summary: dict[str, Any] | None = None
    income_growth_gpt_csv: str = ""
    income_growth_gpt_output: str = ""
    income_growth_gpt_response_id: str = ""
    income_growth_gpt_prompt: str = ""
    income_growth_gpt_cached: bool = False
    income_growth_equity_results: list[dict[str, Any]] | None = None
    equity_rows: list[dict[str, Any]] | None = None
    equity_summary: dict[str, Any] | None = None
    equity_results: list[dict[str, Any]] | None = None
    income_rows: list[dict[str, Any]] | None = None
    income_summary: dict[str, Any] | None = None
    income_results: list[dict[str, Any]] | None = None
    income_pe_top: list[dict[str, Any]] | None = None
    income_pe_watch: list[dict[str, Any]] | None = None
    income_pe_avoid: list[dict[str, Any]] | None = None
    income_positions: list[dict[str, Any]] | None = None
    income_error: str = ""
    kite_request_token: str = ""
    kite_ip_data: list[dict[str, str]] | None = None
    etf_buy_amount: float = field(default_factory=etf_buy_amount_setting)
    option_sell_markup_percent: float = field(default_factory=option_sell_markup_percent_setting)
    home_tickers: str = field(default_factory=home_tickers_text)


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
    .show-password {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: -2px 0 14px;
      color: #475569;
      font-size: 13px;
      font-weight: 800;
      cursor: pointer;
    }}
    .show-password input {{
      width: auto;
      margin: 0;
      accent-color: #0f766e;
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
    <label>Password<input id="login-password" name="password" type="password" autocomplete="current-password"></label>
    <label class="show-password"><input id="show-login-password" type="checkbox"> Show password</label>
    <button type="submit">Log in</button>
  </form>
  <script>
    const showPassword = document.getElementById('show-login-password');
    const password = document.getElementById('login-password');
    showPassword && password && showPassword.addEventListener('change', () => {{
      password.type = showPassword.checked ? 'text' : 'password';
    }});
  </script>
</body>
</html>""".encode("utf-8")


def env_value(name: str) -> str:
    return os.getenv(name, "")


try:
    apply_kite_profile_to_env(
        load_kite_profiles().get(selected_kite_profile_name(), shanti_default_kite_profile())
    )
except Exception:
    pass


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


def is_kite_related_error(error: Any) -> bool:
    """Return True only for failures that require attention in Kite Setup."""
    text = str(error or "").strip().lower()
    if not text:
        return False
    direct_markers = (
        "api.kite.trade",
        "kiteconnect",
        "kite api",
        "kite quote",
        "kite positions",
        "kite orders",
        "kite setup",
        "kite_place_order",
        "missing kite setup",
        "missing kite_api",
        "kite_access_token",
        "kite_api_key",
        "kite_api_secret",
    )
    authentication_markers = (
        "incorrect `api_key` or `access_token`",
        "incorrect api_key or access_token",
        "invalid session",
        "tokenexception",
        "access token is invalid",
        "access_token is invalid",
    )
    return any(marker in text for marker in direct_markers + authentication_markers)


def redirect_state_to_kite_setup_on_error(state: "PageState") -> bool:
    """Open Kite Setup when any rendered tab reports a Kite-related failure."""
    error_values = (
        state.error,
        state.order_book_error,
        state.commodity_error,
        state.income_error,
    )
    setup_issue = kite_setup_issue()
    should_redirect = bool(setup_issue) or any(
        is_kite_related_error(error) for error in error_values
    )
    if not should_redirect:
        return False
    state.active_tab = "kite-setup"
    if setup_issue and not state.error:
        state.error = setup_issue
    state.message = "Kite needs attention. Review the selected profile and access token."
    return True


def set_kite_env(form: dict[str, list[str]]) -> None:
    env_names = {
        "api_key": "KITE_API_KEY",
        "api_secret": "KITE_API_SECRET",
        "access_token": "KITE_ACCESS_TOKEN",
        "confirm_live_order": "KITE_CONFIRM_LIVE_ORDER",
    }
    for field, env_name in env_names.items():
        if field not in form:
            continue
        clean_value = first(form, field).strip()
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


def save_kite_access_token(access_token: str) -> str:
    token = str(access_token or "").strip()
    if not token:
        raise ValueError("Paste KITE_ACCESS_TOKEN before saving.")
    os.environ["KITE_ACCESS_TOKEN"] = token
    DEFAULT_KITE_ENV["KITE_ACCESS_TOKEN"] = token
    save_env_values(
        {
            "KITE_CONFIRM_LIVE_ORDER": env_value("KITE_CONFIRM_LIVE_ORDER") or "YES",
            "KITE_API_KEY": env_value("KITE_API_KEY") or DEFAULT_KITE_ENV["KITE_API_KEY"],
            "KITE_API_SECRET": env_value("KITE_API_SECRET") or DEFAULT_KITE_ENV["KITE_API_SECRET"],
            "KITE_ACCESS_TOKEN": token,
        }
    )
    return token


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
    if any(item.get("status") == "CANCELLED" for item in results):
        invalidate_kite_trade_cache()
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


def optional_float_text(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text or text.upper() in {"N/A", "NA", "#DIV/0!"}:
        return None
    return float(text.replace(",", "").replace("%", ""))


def optional_int_text(value: str) -> int | None:
    text = value.strip()
    return int(text) if text else None


def load_income_growth_holding_map() -> dict[str, dict[str, Any]]:
    conn = app_db_connection()
    rows = conn.execute(
        """
        SELECT symbol, holding, times_lot, lots_can_sell, cmp, call_strike, value,
               to_sell, lot_size, gap_pct, put_down_pct, pe, week_52, one_year,
               month, week_1, today, updated_at
        FROM income_growth_holdings
        ORDER BY symbol
        """
    ).fetchall()
    return {str(row["symbol"]).upper(): dict(row) for row in rows}


def save_income_growth_holding_from_form(form: dict[str, list[str]]) -> tuple[str, dict[str, Any]]:
    symbol = normalize_income_growth_symbol(first(form, "income_growth_symbol"))
    if not symbol:
        raise ValueError("Enter a stock symbol to update Income Growth holding data.")
    current = load_income_growth_holding_map().get(symbol, {})

    def number_field(name: str, current_key: str) -> float | None:
        text = first(form, name).strip()
        if text == "":
            current_value = current.get(current_key)
            return float(current_value) if isinstance(current_value, (int, float)) else None
        return optional_float_text(text)

    holding = number_field("income_growth_holding", "holding") or 0.0
    cmp_value = number_field("income_growth_cmp", "cmp")
    explicit_value = number_field("income_growth_value", "value")
    value = explicit_value
    if value is None and cmp_value is not None:
        value = holding * cmp_value
    payload = {
        "symbol": symbol,
        "holding": holding,
        "times_lot": number_field("income_growth_times_lot", "times_lot"),
        "lots_can_sell": number_field("income_growth_lots_can_sell", "lots_can_sell"),
        "cmp": cmp_value,
        "call_strike": number_field("income_growth_call_strike", "call_strike"),
        "value": value,
        "to_sell": number_field("income_growth_to_sell", "to_sell"),
        "lot_size": number_field("income_growth_lot_size", "lot_size"),
        "gap_pct": number_field("income_growth_gap_pct", "gap_pct"),
        "put_down_pct": number_field("income_growth_put_down_pct", "put_down_pct"),
        "pe": number_field("income_growth_pe", "pe"),
        "week_52": number_field("income_growth_week_52", "week_52"),
        "one_year": number_field("income_growth_one_year", "one_year"),
        "month": number_field("income_growth_month", "month"),
        "week_1": number_field("income_growth_week_1", "week_1"),
        "today": number_field("income_growth_today", "today"),
        "updated_at": app_now().isoformat(timespec="seconds"),
    }
    conn = app_db_connection()
    conn.execute(
        """
        INSERT INTO income_growth_holdings (
            symbol, holding, times_lot, lots_can_sell, cmp, call_strike, value,
            to_sell, lot_size, gap_pct, put_down_pct, pe, week_52, one_year,
            month, week_1, today, updated_at
        ) VALUES (
            :symbol, :holding, :times_lot, :lots_can_sell, :cmp, :call_strike, :value,
            :to_sell, :lot_size, :gap_pct, :put_down_pct, :pe, :week_52, :one_year,
            :month, :week_1, :today, :updated_at
        )
        ON CONFLICT(symbol) DO UPDATE SET
            holding = excluded.holding,
            times_lot = excluded.times_lot,
            lots_can_sell = excluded.lots_can_sell,
            cmp = excluded.cmp,
            call_strike = excluded.call_strike,
            value = excluded.value,
            to_sell = excluded.to_sell,
            lot_size = excluded.lot_size,
            gap_pct = excluded.gap_pct,
            put_down_pct = excluded.put_down_pct,
            pe = excluded.pe,
            week_52 = excluded.week_52,
            one_year = excluded.one_year,
            month = excluded.month,
            week_1 = excluded.week_1,
            today = excluded.today,
            updated_at = excluded.updated_at
        """,
        payload,
    )
    conn.commit()
    return symbol, payload


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
    quotes = cached_kite_quote(kite, [option_key, spot_key])
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
        for item in cached_kite_instruments(kite, "NFO")
        if str(item.get("name", "")).upper() == parts["underlying"]
        and str(item.get("instrument_type", "")).upper() in {"CE", "PE"}
        and item.get("expiry") == expiry_date_for_parts(parts)
    ]
    if not instruments:
        return {}

    keys = [f"NFO:{item['tradingsymbol']}" for item in instruments]
    quotes: dict[str, Any] = {}
    for index in range(0, len(keys), 400):
        quotes.update(cached_kite_quote(kite, keys[index : index + 400]))

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


def open_option_positions(use_cache: bool = True) -> list[dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    positions = cached_kite_positions(kite) if use_cache else kite.positions().get("net", [])
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


def fresh_kite_ltp_map(kite: Any, instruments: list[str] | tuple[str, ...]) -> dict[str, float]:
    clean = [str(item).strip().upper() for item in instruments if str(item).strip()]
    if not clean:
        return {}
    quotes = kite.ltp(clean)
    result: dict[str, float] = {}
    for key in clean:
        quote = quotes.get(key) or quotes.get(key.upper()) or {}
        ltp = float(quote.get("last_price") or 0)
        if ltp > 0:
            result[key] = ltp
    return result


def option_position_pnl(quantity: int, average_price: float, ltp: float) -> float:
    if quantity < 0:
        return (average_price - ltp) * abs(quantity)
    return (ltp - average_price) * quantity


def refresh_option_positions_with_live_ltp(
    positions: list[dict[str, Any]],
    kite: Any,
) -> list[dict[str, Any]]:
    keys = [
        f"{position.get('exchange') or 'NFO'}:{position.get('tradingsymbol')}"
        for position in positions
        if position.get("tradingsymbol")
    ]
    live_ltp = fresh_kite_ltp_map(kite, keys)
    refreshed: list[dict[str, Any]] = []
    for position in positions:
        updated = dict(position)
        key = f"{updated.get('exchange') or 'NFO'}:{updated.get('tradingsymbol')}".upper()
        ltp = live_ltp.get(key)
        if ltp is not None:
            quantity = int(updated.get("quantity") or 0)
            average_price = float(updated.get("average_price") or 0)
            updated["ltp"] = ltp
            updated["last_price"] = ltp
            if average_price > 0 and quantity:
                updated["pnl"] = option_position_pnl(quantity, average_price, ltp)
        refreshed.append(updated)
    return refreshed


def active_position_underlyings() -> set[str]:
    if kite_orders is None:
        return set()
    try:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            kite = kite_orders.kite_client()
            positions = cached_kite_positions(kite)
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


def active_position_option_block_keys(
    force_refresh: bool = False, strict: bool = False
) -> set[str]:
    if kite_orders is None:
        return set()
    try:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            kite = kite_orders.kite_client()
            if force_refresh:
                clear_app_cache(("kite:positions",))
            positions = cached_kite_positions(kite)
    except Exception:
        if strict:
            raise
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
        parts = option_symbol_parts(symbol)
        if not symbol or not parts:
            continue
        active.add(symbol)
        active.add(f"{parts['underlying']}:{parts['option_type']}")
    return active


def active_open_order_option_block_keys(
    force_refresh: bool = False, strict: bool = False
) -> set[str]:
    if kite_orders is None:
        return set()
    try:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            kite = kite_orders.kite_client()
            if force_refresh:
                clear_app_cache(("kite:orders",))
            orders = cached_kite_orders(kite)
    except Exception:
        if strict:
            raise
        return set()
    active: set[str] = set()
    for order in orders:
        symbol = str(order.get("tradingsymbol") or "").strip().upper()
        side = str(order.get("transaction_type") or "").strip().upper()
        status = str(order.get("status") or "").strip().upper()
        try:
            pending = int(float(order.get("pending_quantity") or order.get("quantity") or 0))
        except (TypeError, ValueError):
            pending = 0
        if (
            symbol
            and side in {"BUY", "SELL"}
            and status in CANCELLABLE_ORDER_STATUSES
            and pending > 0
        ):
            active.add(f"{symbol}:{side}")
    return active


def active_pe_position_underlyings(force_refresh: bool = False) -> set[str]:
    if kite_orders is None:
        return set()
    if force_refresh:
        kite = kite_orders.kite_client()
        positions = kite.positions().get("net", [])
    else:
        try:
            kite = kite_orders.kite_client()
            positions = cached_kite_positions(kite)
        except Exception:
            return set()
    result: set[str] = set()
    for position in positions:
        if int(float(position.get("quantity") or 0)) == 0:
            continue
        parts = option_symbol_parts(str(position.get("tradingsymbol") or "").upper())
        if parts and parts["option_type"] == "PE":
            result.add(str(parts["underlying"]).upper())
    return result


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
                for item in cached_value(
                    "kite:margin:selected:" + json.dumps(margin_orders, sort_keys=True, default=str),
                    lambda: kite.order_margins(margin_orders),
                    KITE_READ_CACHE_SECONDS,
                )
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


def select_valid_pe_contract(
    instruments: list[dict[str, Any]],
    target_strike: float,
) -> dict[str, Any]:
    valid = [
        item
        for item in instruments
        if str(item.get("instrument_type") or "").upper() == "PE"
        and float(item.get("strike") or 0) > 0
        and float(item.get("strike") or 0) <= target_strike
        and str(item.get("tradingsymbol") or "").strip()
    ]
    if not valid:
        raise ValueError("No valid PE strike available below target")
    return max(valid, key=lambda item: float(item.get("strike") or 0))


def next_monthly_pe_candidate(kite: Any, underlying: str) -> dict[str, Any]:
    today = datetime.now().date()
    spot_quote = cached_kite_quote(kite, [f"NSE:{underlying}"]).get(f"NSE:{underlying}", {})
    spot = quote_ltp(spot_quote)
    if spot <= 0:
        raise ValueError(f"Could not read spot for {underlying}.")
    instruments = [
        item
        for item in cached_kite_instruments(kite, "NFO")
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
    selected = select_valid_pe_contract(expiry_instruments, target_strike)
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


def income_pe_order_snapshot(underlying: str, target_strike: Any = None) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    clean_underlying = str(underlying or "").strip().upper()
    if not clean_underlying:
        raise ValueError("Select a PE candidate first.")
    if clean_underlying in active_pe_position_underlyings(True):
        raise PermissionError(
            f"{clean_underlying} already has an active PE position. New PE SELL is blocked."
        )
    kite = kite_orders.kite_client()
    candidate = next_monthly_pe_candidate(kite, clean_underlying)
    requested_strike = float(target_strike or 0)
    if requested_strike > 0:
        instruments = [
            item
            for item in cached_kite_instruments(kite, "NFO")
            if str(item.get("name") or "").upper() == clean_underlying
            and str(item.get("instrument_type") or "").upper() == "PE"
            and item.get("expiry") == candidate["expiry"]
        ]
        if instruments:
            selected = select_valid_pe_contract(instruments, requested_strike)
            candidate = {
                **candidate,
                "symbol": str(selected.get("tradingsymbol") or "").upper(),
                "strike": float(selected.get("strike") or 0),
                "lot_size": int(selected.get("lot_size") or 0),
            }
    quote_key = f"NFO:{candidate['symbol']}"
    try:
        quote = kite.quote([quote_key]).get(quote_key, {})
    except Exception as exc:
        raise RuntimeError(friendly_external_error(exc, f"{candidate['symbol']} PE quote")) from exc
    ltp = quote_ltp(quote)
    if ltp <= 0:
        raise ValueError(f"Could not read fresh PE premium for {candidate['symbol']}.")
    lot_size = int(candidate.get("lot_size") or 0)
    markup = option_sell_markup_percent_setting()
    limit_price = ceil_to_tick(ltp * (1 + markup / 100), 0.05)
    assignment_value = float(candidate.get("strike") or 0) * lot_size
    max_profit = limit_price * lot_size
    return {
        "underlying": clean_underlying,
        "symbol": candidate["symbol"],
        "strike": float(candidate.get("strike") or 0),
        "expiry": candidate["expiry"].strftime("%d %b %Y"),
        "quantity": lot_size,
        "ltp": ltp,
        "limit_price": limit_price,
        "markup_percent": markup,
        "assignment_value": assignment_value,
        "max_profit": max_profit,
        "premium_yield_percent": (
            max_profit / assignment_value * 100 if assignment_value > 0 else 0
        ),
    }


def next_monthly_ce_candidate(kite: Any, underlying: str) -> dict[str, Any]:
    today = datetime.now().date()
    spot_quote = cached_kite_quote(kite, [f"NSE:{underlying}"]).get(f"NSE:{underlying}", {})
    spot = quote_ltp(spot_quote)
    if spot <= 0:
        raise ValueError(f"Could not read spot for {underlying}.")
    instruments = [
        item
        for item in cached_kite_instruments(kite, "NFO")
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
    quotes = cached_kite_quote(kite, quote_keys)
    for holding in cached_value("kite:holdings", kite.holdings, KITE_READ_CACHE_SECONDS):
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
    positions = cached_kite_positions(kite)
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
    quote_key = f"NFO:{candidate['symbol']}"
    quote = cached_kite_quote(kite, [quote_key]).get(quote_key, {})
    current_price = quote_ltp(quote)
    if current_price <= 0:
        raise ValueError(f"Could not read CE premium for {candidate['symbol']}.")
    markup = option_sell_markup_percent_setting()
    price = ceil_to_tick(current_price * (1 + markup / 100), 0.05)
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
        "autoslice": True,
    }
    order_id = kite_orders.place_order(kite, order)
    return {
        "tradingsymbol": candidate["symbol"],
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"SELL covered CE {covered_qty} qty at LIMIT {price:.2f}. "
            f"{markup:.2f}% above current premium {current_price:.2f}. "
            f"Holding {held_qty} shares of {clean_underlying}."
        ),
    }


def place_income_cash_secured_put_order(underlying: str, target_strike: Any = None) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Cash-secured PE order refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    clean_underlying = underlying.strip().upper()
    kite = kite_orders.kite_client()
    snapshot = income_pe_order_snapshot(clean_underlying, target_strike)
    lot_size = int(snapshot.get("quantity") or 0)
    if lot_size <= 0:
        raise ValueError(f"Could not read lot size for {snapshot['symbol']}.")
    current_price = float(snapshot.get("ltp") or 0)
    price = float(snapshot.get("limit_price") or 0)
    order = {
        "variety": "regular",
        "exchange": "NFO",
        "tradingsymbol": snapshot["symbol"],
        "transaction_type": "SELL",
        "quantity": lot_size,
        "product": "NRML",
        "order_type": "LIMIT",
        "price": price,
        "validity": "DAY",
        "tag": "INCOME_CSP",
        "autoslice": True,
    }
    try:
        order_id = place_order_allowing_autoslice(kite, order)
    except Exception as exc:
        raise RuntimeError(friendly_external_error(exc, f"{snapshot['symbol']} PE SELL")) from exc
    invalidate_kite_trade_cache()
    assignment_value = float(snapshot.get("assignment_value") or 0)
    return {
        "tradingsymbol": snapshot["symbol"],
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"SELL cash-secured PE {lot_size} qty at LIMIT {price:.2f}, "
            f"{float(snapshot.get('markup_percent') or option_sell_markup_percent_setting()):.2f}% above current premium {current_price:.2f}. "
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


def research_csv_symbols(csv_text: str = "", csv_path: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_text = ""
    if csv_text.strip():
        source_text = normalize_kite_csv_input(csv_text)
    elif csv_path.strip():
        try:
            _, source_text = load_rows(csv_path, "")
        except Exception:
            source_text = read_default_csv_text()
    else:
        source_text = read_default_csv_text()
    for csv_row in safe_csv_rows(source_text):
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
    cache_key = (
        f"kite:margin:{order['exchange']}:{order['tradingsymbol']}:"
        f"{order['transaction_type']}:{order['product']}:{order['quantity']}"
    )
    margin_rows = cached_value(
        cache_key,
        lambda: kite.order_margins([order]),
        KITE_READ_CACHE_SECONDS,
    )
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


def open_option_buy_orders_by_symbol(kite: Any, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    if force_refresh:
        clear_app_cache(("kite:orders",))
    matches: dict[str, dict[str, Any]] = {}
    for order in cached_kite_orders(kite):
        symbol = str(order.get("tradingsymbol") or "").strip().upper()
        status = str(order.get("status") or "").strip().upper()
        side = str(order.get("transaction_type") or "").strip().upper()
        if not symbol or side != "BUY" or status not in CANCELLABLE_ORDER_STATUSES:
            continue
        pending_quantity = int(float(order.get("pending_quantity") or order.get("quantity") or 0))
        if pending_quantity <= 0:
            continue
        matches[symbol] = {
            "order_id": str(order.get("order_id") or ""),
            "quantity": pending_quantity,
            "price": float(order.get("price") or 0),
            "status": status,
        }
    return matches


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
    existing_buy = open_option_buy_orders_by_symbol(kite, True).get(clean_symbol)
    if existing_buy:
        raise ValueError(
            f"BUY close order already placed for {clean_symbol}: "
            f"{existing_buy['quantity']} qty at LIMIT {existing_buy['price']:.2f} "
            f"({existing_buy['status']})."
        )
    quantity = abs(int(position.get("quantity") or 0))
    ltp = float(position.get("ltp") or 0)
    if ltp <= 0:
        quote_key = f"{position.get('exchange') or 'NFO'}:{clean_symbol}"
        quote = cached_kite_quote(kite, [quote_key]).get(
            quote_key,
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
    order_id = place_order_allowing_autoslice(kite, order)
    invalidate_kite_trade_cache()
    return {
        "tradingsymbol": order["tradingsymbol"],
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"BUY close order {order['quantity']} qty at LIMIT {order['price']:.2f}, "
            f"10% below LTP {order['ltp']:.2f}."
        ),
    }


def positions_research(force_refresh: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    now = time.time()
    if force_refresh:
        clear_app_cache(("kite:positions", "kite:quote", "positions-research"))
    else:
        cached = APP_CACHE.get("positions-research")
        if cached and now - cached[0] < KITE_READ_CACHE_SECONDS:
            return copy.deepcopy(cached[1])
    kite = kite_orders.kite_client()
    positions = open_option_positions(use_cache=not force_refresh)
    if force_refresh:
        positions = refresh_option_positions_with_live_ltp(positions, kite)
    order_lookup_error = ""
    try:
        open_buy_orders = open_option_buy_orders_by_symbol(kite, force_refresh)
    except Exception as exc:
        open_buy_orders = {}
        order_lookup_error = friendly_external_error(exc, "Open BUY order check")
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
            existing_buy_order = open_buy_orders.get(symbol.upper())
            rows.append(
                {
                    "symbol": symbol,
                    "quantity": position.get("quantity"),
                    "product": position.get("product"),
                    "average_price": position.get("average_price"),
                    "ltp": position.get("ltp"),
                    "stock_cmp": data.get("spot"),
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
                    "existing_buy_order": existing_buy_order,
                }
            )
        except Exception as exc:
            existing_buy_order = open_buy_orders.get(symbol.upper())
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
                    "existing_buy_order": existing_buy_order,
                }
            )
    summary = {
        "count": len(rows),
        "total_pnl": total_pnl,
        "total_deployed": total_deployed,
        "return_pct": (total_pnl / total_deployed * 100) if total_deployed > 0 else None,
        "as_of": app_now().strftime("%d %b %Y %H:%M:%S"),
        "fresh": force_refresh,
        "order_lookup_error": order_lookup_error,
    }
    result = (rows, summary)
    APP_CACHE["positions-research"] = (now, copy.deepcopy(result))
    return result


def load_rows(csv_path: str, csv_text: str) -> tuple[list[dict[str, str]], str]:
    if is_web_csv_source(csv_path):
        text = fetch_csv_text_from_url(csv_path)
        text = normalize_kite_csv_input(text)
        return parse_csv_text(text), text

    if csv_text.strip():
        text = normalize_kite_csv_input(csv_text)
        return parse_csv_text(text), text

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
    text = normalize_kite_csv_input(text)
    return parse_csv_text(text), text


def validate_kite_order_rows(rows: list[dict[str, str]]) -> None:
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        symbol = (row.get("tradingsymbol") or row.get("symbol") or "").strip().upper()
        transaction_type = (row.get("transaction_type") or "").strip().upper()
        quantity_text = (row.get("quantity") or "").strip()
        if not symbol:
            errors.append(f"Row {index}: missing tradingsymbol.")
        if transaction_type not in {"BUY", "SELL"}:
            errors.append(f"Row {index}: transaction_type must be BUY or SELL.")
        try:
            quantity = int(float(quantity_text or "0"))
        except ValueError:
            errors.append(f"Row {index}: quantity must be numeric.")
            continue
        if quantity <= 0:
            errors.append(f"Row {index}: quantity must be greater than 0 for {symbol or 'this order'}.")
    if errors:
        preview = "\n".join(errors[:8])
        more = f"\n...and {len(errors) - 8} more issue(s)." if len(errors) > 8 else ""
        raise ValueError(f"CSV order validation failed:\n{preview}{more}")


def persist_default_csv_text(csv_text: str) -> str:
    text = normalize_kite_csv_input(csv_text).strip()
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
    text = normalize_kite_csv_input(csv_text).strip()
    if not text:
        raise ValueError("CSV text is empty. Paste or upload CSV before saving.")
    parse_csv_text(text)
    today_path = dated_income_csv_path()
    normalized_new = text.rstrip() + "\n"
    archive_message = ""
    archive_path = None
    if today_path.exists() and today_path.read_text(encoding="utf-8-sig").strip():
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        archive_path = today_path.with_name(f"{today_path.stem}_last_input_order_{stamp}.csv")
        today_path.replace(archive_path)
        archive_message = f"Archived previous CSV to {archive_path.name}. "
    try:
        today_path.parent.mkdir(parents=True, exist_ok=True)
        today_path.write_text(normalized_new, encoding="utf-8")
    except PermissionError:
        if archive_path and archive_path.exists() and not today_path.exists():
            archive_path.replace(today_path)
        today_path = APP_ROOT / today_path.name
        today_path.write_text(normalized_new, encoding="utf-8")
        archive_message += "Repo root was not writable, saved in webapp folder. "
    except Exception:
        if archive_path and archive_path.exists() and not today_path.exists():
            archive_path.replace(today_path)
        raise
    return str(today_path), f"{archive_message}Saved CSV text to {today_path.name}."


def restore_csv_text_after_save_error(csv_path: str) -> tuple[str, str]:
    candidates = [
        Path(csv_path).expanduser() if csv_path else None,
        dated_income_csv_path(),
        DEFAULT_CSV_PATH,
        LEGACY_CSV_PATH,
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return str(candidate), candidate.read_text(encoding="utf-8-sig")
    return str(DEFAULT_CSV_PATH), ""


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


def friendly_external_error(exc: Exception, service: str = "Market data") -> str:
    raw = str(exc or "").strip()
    lower = raw.lower()
    if "api_key" in lower or "access_token" in lower or "invalid session" in lower:
        return (
            f"{service} authentication failed: open Kite Setup, confirm the active profile, "
            "and regenerate today's access token."
        )
    if (
        "getaddrinfo failed" in lower
        or "name resolution" in lower
        or "failed to resolve" in lower
        or "nodename nor servname" in lower
        or "temporary failure in name resolution" in lower
    ):
        return (
            f"{service} connection failed: DNS could not resolve the market-data host. "
            "Check internet/DNS on this laptop/server, then refresh."
        )
    if (
        "api.kite.trade" in lower
        and (
            "connection" in lower
            or "failed to establish" in lower
            or "max retries exceeded" in lower
            or "network is unreachable" in lower
        )
    ):
        return (
            f"{service} connection failed: Kite API is unreachable from this machine. "
            "Verify network, DNS, firewall, and the selected Kite profile token."
        )
    if "timed out" in lower or "timeout" in lower:
        return f"{service} connection timed out. Retry after a few seconds."
    if "max retries exceeded" in lower:
        return f"{service} connection failed after retries. Check network/DNS and retry."
    return raw[:260] if raw else f"{service} unavailable."


def compact_error_list(errors: list[str], limit: int = 3) -> str:
    clean = [str(error).strip() for error in errors if str(error).strip()]
    if not clean:
        return ""
    visible = clean[:limit]
    suffix = f" + {len(clean) - limit} more" if len(clean) > limit else ""
    return "; ".join(visible) + suffix


def cached_value(cache_key: str, fetcher: Any, ttl_seconds: int) -> Any:
    now = time.time()
    with APP_CACHE_LOCK:
        cached = APP_CACHE.get(cache_key)
        if cached and now - cached[0] < ttl_seconds:
            return copy.deepcopy(cached[1])
        key_lock = APP_CACHE_KEY_LOCKS.setdefault(cache_key, threading.Lock())
    with key_lock:
        now = time.time()
        with APP_CACHE_LOCK:
            cached = APP_CACHE.get(cache_key)
            if cached and now - cached[0] < ttl_seconds:
                return copy.deepcopy(cached[1])
        value = fetcher()
        with APP_CACHE_LOCK:
            APP_CACHE[cache_key] = (time.time(), copy.deepcopy(value))
    return value


def cached_payload(cache_key: str, fetcher: Any, ttl_seconds: int = TOP_QUOTE_CACHE_SECONDS) -> dict[str, Any]:
    now = time.time()
    with APP_CACHE_LOCK:
        cached = APP_CACHE.get(cache_key)
        if cached and now - cached[0] < ttl_seconds:
            payload = copy.deepcopy(cached[1])
            payload["cached"] = True
            payload["cache_age_seconds"] = int(now - cached[0])
            return payload
        key_lock = APP_CACHE_KEY_LOCKS.setdefault(cache_key, threading.Lock())
    with key_lock:
        now = time.time()
        with APP_CACHE_LOCK:
            cached = APP_CACHE.get(cache_key)
            if cached and now - cached[0] < ttl_seconds:
                payload = copy.deepcopy(cached[1])
                payload["cached"] = True
                payload["cache_age_seconds"] = int(now - cached[0])
                return payload
        payload = fetcher()
        payload["cached"] = False
        payload["cache_age_seconds"] = 0
        with APP_CACHE_LOCK:
            APP_CACHE[cache_key] = (time.time(), copy.deepcopy(payload))
    return payload


def clear_app_cache(prefixes: tuple[str, ...] = ()) -> None:
    with APP_CACHE_LOCK:
        if not prefixes:
            APP_CACHE.clear()
            return
        for key in list(APP_CACHE):
            if key.startswith(prefixes):
                APP_CACHE.pop(key, None)


def cached_kite_quote(kite: Any, keys: list[str] | tuple[str, ...], ttl_seconds: int = KITE_QUOTE_CACHE_SECONDS) -> dict[str, Any]:
    clean_keys = tuple(sorted(str(key) for key in keys if key))
    if not clean_keys:
        return {}
    try:
        return cached_value(
            "kite:quote:" + "|".join(clean_keys),
            lambda: kite.quote(list(clean_keys)),
            ttl_seconds,
        )
    except Exception as exc:
        raise RuntimeError(friendly_external_error(exc, "Kite quote")) from exc


def cached_kite_positions(kite: Any) -> list[dict[str, Any]]:
    try:
        return cached_value(
            "kite:positions",
            lambda: kite.positions().get("net", []),
            KITE_READ_CACHE_SECONDS,
        )
    except Exception as exc:
        raise RuntimeError(friendly_external_error(exc, "Kite positions")) from exc


def cached_kite_orders(kite: Any) -> list[dict[str, Any]]:
    try:
        return cached_value("kite:orders", kite.orders, KITE_READ_CACHE_SECONDS)
    except Exception as exc:
        raise RuntimeError(friendly_external_error(exc, "Kite orders")) from exc


def cached_kite_instruments(kite: Any, exchange: str) -> list[dict[str, Any]]:
    clean_exchange = exchange.strip().upper()
    try:
        return cached_value(
            f"kite:instruments:{clean_exchange}",
            lambda: kite.instruments(clean_exchange),
            KITE_INSTRUMENT_CACHE_SECONDS,
        )
    except Exception as exc:
        raise RuntimeError(friendly_external_error(exc, f"Kite {clean_exchange} instruments")) from exc


def invalidate_kite_trade_cache() -> None:
    clear_app_cache(("kite:orders", "kite:positions", "kite:holdings", "kite:margin", "kite:quote", "positions-research"))


def fetch_mmi_snapshot_uncached() -> dict[str, Any]:
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


def fetch_mmi_snapshot() -> dict[str, Any]:
    return cached_payload("mmi", fetch_mmi_snapshot_uncached)


def csv_underlyings(csv_text: str) -> list[str]:
    underlyings: list[str] = []
    seen: set[str] = set()
    for symbol in csv_trading_symbols(csv_text):
        underlying = underlying_for_symbol(symbol)
        if underlying and underlying not in seen:
            underlyings.append(underlying)
            seen.add(underlying)
    return underlyings


def fetch_csv_market_quotes_uncached() -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")

    quote_items = [{"symbol": symbol, "threshold": None} for symbol in home_tickers_setting()]
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
    raw_quotes = cached_kite_quote(kite, instruments)
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


def fetch_csv_market_quotes() -> dict[str, Any]:
    return cached_payload("market-quotes", fetch_csv_market_quotes_uncached)


def fetch_yahoo_quote(symbol: str, label: str) -> dict[str, Any]:
    encoded_symbol = quote_plus(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=5d&interval=1d"
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    result = ((payload.get("chart") or {}).get("result") or [{}])[0]
    meta = result.get("meta") or {}
    current = float(
        meta.get("regularMarketPrice")
        or meta.get("previousClose")
        or meta.get("chartPreviousClose")
        or 0
    )
    previous = float(meta.get("chartPreviousClose") or meta.get("previousClose") or 0)
    close_values = (
        ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    )
    valid_closes = [float(value) for value in close_values if value is not None]
    if current <= 0 and valid_closes:
        current = valid_closes[-1]
    if previous <= 0 and len(valid_closes) >= 2:
        previous = valid_closes[-2]
    change_percent = ((current - previous) / previous * 100) if previous > 0 else None
    return {
        "label": label,
        "symbol": symbol,
        "ltp": round(current, 2) if current > 0 else None,
        "change_percent": round(change_percent, 2) if change_percent is not None else None,
    }


def kite_quote_from_key(label: str, symbol: str, kite_key: str) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    quote = cached_kite_quote(kite, [kite_key]).get(kite_key, {})
    ltp = quote_ltp(quote)
    previous_close = float(
        ((quote.get("ohlc") or {}).get("close"))
        or quote.get("close")
        or 0
    )
    change_percent = ((ltp - previous_close) / previous_close * 100) if ltp and previous_close else None
    return {
        "label": label,
        "symbol": symbol,
        "ltp": round(float(ltp), 2) if ltp else None,
        "change_percent": round(change_percent, 2) if change_percent is not None else None,
        "source": "Kite",
        "quote_key": kite_key,
    }


def nearest_nifty_future_quote() -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    today = datetime.now().date()
    futures: list[dict[str, Any]] = []
    for item in cached_kite_instruments(kite, "NFO"):
        if str(item.get("name") or "").upper() != "NIFTY":
            continue
        if str(item.get("instrument_type") or "").upper() != "FUT":
            continue
        expiry_value = item.get("expiry")
        if isinstance(expiry_value, datetime):
            expiry_day = expiry_value.date()
        elif isinstance(expiry_value, date):
            expiry_day = expiry_value
        elif expiry_value:
            try:
                expiry_day = datetime.fromisoformat(str(expiry_value)).date()
            except ValueError:
                continue
        else:
            continue
        if expiry_day >= today:
            futures.append({**item, "_expiry_day": expiry_day})
    if not futures:
        raise ValueError("No active NIFTY futures contract found in Kite NFO instruments.")
    instrument = min(futures, key=lambda item: item.get("_expiry_day"))
    tradingsymbol = str(instrument.get("tradingsymbol") or "")
    quote_key = f"NFO:{tradingsymbol}"
    quote = cached_kite_quote(kite, [quote_key]).get(quote_key, {})
    ltp = quote_ltp(quote)
    previous_close = float(
        ((quote.get("ohlc") or {}).get("close"))
        or quote.get("close")
        or quote.get("last_price")
        or 0
    )
    change_percent = ((ltp - previous_close) / previous_close * 100) if ltp and previous_close else None
    return {
        "label": "NIFTY FUT",
        "symbol": "KITE:NIFTY_FUT",
        "contract": tradingsymbol or "NIFTY FUT",
        "ltp": round(float(ltp), 2) if ltp else None,
        "change_percent": round(change_percent, 2) if change_percent is not None else None,
        "source": "Kite",
        "quote_key": quote_key,
    }


def global_quote_with_fallback(item: dict[str, Any]) -> dict[str, Any]:
    label = str(item["label"])
    display_symbol = str(item["symbol"])
    try:
        if item.get("source") == "kite_quote":
            return kite_quote_from_key(label, display_symbol, str(item["kite_key"]))
        if item.get("source") == "kite_nifty_fut":
            return nearest_nifty_future_quote()
        return fetch_yahoo_quote(display_symbol, label)
    except Exception as kite_exc:
        fallback_symbol = str(item.get("fallback_symbol") or "")
        if not fallback_symbol:
            raise
        fallback = fetch_yahoo_quote(fallback_symbol, label)
        fallback["symbol"] = display_symbol
        fallback["fallback_symbol"] = fallback_symbol
        fallback["warning"] = f"Kite quote unavailable, using fallback {fallback_symbol}: {kite_exc}"
        return fallback


def fetch_global_market_quotes_uncached() -> dict[str, Any]:
    quotes: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    for item in GLOBAL_MARKET_WATCHLIST:
        try:
            quote = global_quote_with_fallback(item)
            if quote.get("warning"):
                warnings.append(str(quote["warning"]))
            quotes.append(quote)
        except Exception as exc:
            errors.append(f"{item['label']}: {friendly_external_error(exc, str(item['label']))}")
            quotes.append(
                {
                    "label": str(item["label"]),
                    "symbol": str(item["symbol"]),
                    "ltp": None,
                    "change_percent": None,
                }
            )
    return {
        "ok": not errors,
        "quotes": quotes,
        "error": compact_error_list(errors),
        "warning": compact_error_list(warnings),
    }


def fetch_global_market_quotes() -> dict[str, Any]:
    return cached_payload("global-quotes", fetch_global_market_quotes_uncached)


def fetch_yahoo_moving_averages(symbol: str) -> dict[str, float | None]:
    yahoo_symbol = f"{symbol.upper()}.NS"
    encoded_symbol = quote_plus(yahoo_symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=1y&interval=1d"
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    result = ((payload.get("chart") or {}).get("result") or [{}])[0]
    close_values = (
        ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    )
    closes = [float(value) for value in close_values if value is not None and float(value) > 0]
    return {
        "dma_50": round(sum(closes[-50:]) / 50, 2) if len(closes) >= 50 else None,
        "dma_200": round(sum(closes[-200:]) / 200, 2) if len(closes) >= 200 else None,
    }


def commodity_moving_averages(symbol: str) -> dict[str, float | None]:
    return cached_value(
        f"commodity:dma:{symbol.upper()}",
        lambda: fetch_yahoo_moving_averages(symbol),
        COMMODITY_DMA_CACHE_SECONDS,
    )


def commodity_below_200_dma(ltp: Any, dma_200: Any) -> bool:
    try:
        price = float(ltp or 0)
        average = float(dma_200 or 0)
    except (TypeError, ValueError):
        return False
    return price > 0 and average > 0 and price < average


def fetch_commodity_etf_quotes_uncached() -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")

    kite = kite_orders.kite_client()
    instruments = [f"NSE:{item['symbol']}" for item in COMMODITY_ETFS]
    raw_quotes = cached_kite_quote(kite, instruments)
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
        try:
            dma = commodity_moving_averages(str(item["symbol"]))
            dma_error = ""
        except Exception as exc:
            dma = {"dma_50": None, "dma_200": None}
            dma_error = str(exc)
        below_200_dma = commodity_below_200_dma(ltp, dma.get("dma_200"))
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
                "dma_50": dma.get("dma_50"),
                "dma_200": dma.get("dma_200"),
                "below_200_dma": below_200_dma,
                "dma_error": dma_error,
            }
        )
    return {"ok": True, "quotes": quotes}


def fetch_commodity_etf_quotes() -> dict[str, Any]:
    return cached_payload("commodity-quotes", fetch_commodity_etf_quotes_uncached)


def investing_quote_key(code: str) -> str:
    clean = code.strip().replace('"', "").upper()
    exchange, _, symbol = clean.partition(":")
    if not symbol:
        symbol = exchange
        exchange = "NSE"
    if exchange in {"BOM", "BSE"}:
        exchange = "BSE"
    return f"{exchange}:{symbol.strip()}"


def investing_quote_candidates(code: str) -> list[str]:
    primary = investing_quote_key(code)
    exchange, symbol = primary.split(":", 1)
    alternate_exchange = "NSE" if exchange == "BSE" else "BSE"
    candidates = [primary, f"{alternate_exchange}:{symbol}"]
    seen: set[str] = set()
    return [item for item in candidates if not (item in seen or seen.add(item))]


def google_finance_link_for_code(code: str) -> str:
    quote_key = investing_quote_key(code)
    exchange, symbol = quote_key.split(":", 1)
    google_exchange = "BOM" if exchange == "BSE" else "NSE"
    return f"https://www.google.com/finance/quote/{quote_plus(symbol)}:{google_exchange}"


def screener_link_for_code(code: str) -> str:
    quote_key = investing_quote_key(code)
    _, symbol = quote_key.split(":", 1)
    return f"https://www.screener.in/company/{quote_plus(symbol)}/"


def yahoo_symbol_for_investing_code(code: str) -> str:
    quote_key = investing_quote_key(code)
    exchange, symbol = quote_key.split(":", 1)
    suffix = ".BO" if exchange == "BSE" else ".NS"
    return f"{symbol}{suffix}"


def fetch_yahoo_52_week_uncached(code: str) -> dict[str, float | None]:
    yahoo_symbol = yahoo_symbol_for_investing_code(code)
    encoded_symbol = quote_plus(yahoo_symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=1y&interval=1d"
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    result = ((payload.get("chart") or {}).get("result") or [{}])[0]
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    highs = [float(value) for value in quotes.get("high", []) if value is not None]
    lows = [float(value) for value in quotes.get("low", []) if value is not None]
    return {
        "high": max(highs) if highs else None,
        "low": min(lows) if lows else None,
    }


def investing_52_week_levels(code: str) -> dict[str, float | None]:
    return cached_value(
        f"investing:52week:{investing_quote_key(code)}",
        lambda: fetch_yahoo_52_week_uncached(code),
        INVESTING_52W_CACHE_SECONDS,
    )


def fetch_investing_news(rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    news_by_symbol: dict[str, dict[str, str]] = {}
    # Keep this intentionally small; news RSS calls can otherwise dominate tab load.
    watch_rows = sorted(
        [row for row in rows if row.get("quantity")],
        key=lambda row: float(row.get("market_value") or row.get("cost_value") or 0),
        reverse=True,
    )[:8]
    for row in watch_rows:
        symbol = str(row.get("symbol") or "")
        company = str(row.get("company") or symbol)
        sector = str(row.get("sector") or "")
        query = quote_plus(f"{company} {sector} NSE stock news")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            request = Request(url, headers={"User-Agent": "KiteTraderLocalApp/1.0"})
            with urlopen(request, timeout=5) as response:
                xml_text = response.read().decode("utf-8", errors="ignore")
            root = ElementTree.fromstring(xml_text)
            item = root.find(".//item")
            if item is None:
                continue
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            published = item.findtext("pubDate") or ""
            published_at = parse_news_pubdate(published)
            news_by_symbol[symbol] = {
                "title": title,
                "link": link,
                "date": published_at.strftime("%d %b") if published_at else "",
                "sentiment": classify_news_sentiment(title),
            }
        except Exception as exc:
            news_by_symbol[symbol] = {
                "title": f"News unavailable: {exc}",
                "link": "",
                "date": "",
                "sentiment": "neutral",
            }
    return news_by_symbol


def investing_holdings_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    quote_keys: list[str] = []
    for item in INVESTING_HOLDINGS:
        quote_keys.extend(investing_quote_candidates(str(item["code"])))
    quote_keys = list(dict.fromkeys(quote_keys))
    raw_quotes: dict[str, Any] = {}
    quote_error = ""
    if kite_orders is not None:
        try:
            raw_quotes = cached_kite_quote(kite_orders.kite_client(), quote_keys)
        except Exception as exc:
            quote_error = str(exc)
    else:
        quote_error = f"Could not import kite_place_order.py: {IMPORT_ERROR}"

    for item in INVESTING_HOLDINGS:
        code = str(item["code"])
        key = investing_quote_key(code)
        symbol = key.split(":", 1)[1]
        quantity = int(float(item.get("quantity") or 0))
        avg_price = float(item.get("avg_price") or 0)
        quote = {}
        resolved_key = key
        for candidate_key in investing_quote_candidates(code):
            candidate_quote = raw_quotes.get(candidate_key, {})
            if quote_ltp(candidate_quote) > 0:
                quote = candidate_quote
                resolved_key = candidate_key
                break
        cmp_value = quote_ltp(quote) if quote else 0.0
        close = float((quote.get("ohlc") or {}).get("close") or 0)
        daily_change_pct = ((cmp_value - close) / close * 100) if cmp_value > 0 and close > 0 else None
        week_52_high = float(
            quote.get("yearly_high")
            or quote.get("52_week_high")
            or quote.get("fifty_two_week_high")
            or 0
        )
        week_52_low = float(
            quote.get("yearly_low")
            or quote.get("52_week_low")
            or quote.get("fifty_two_week_low")
            or 0
        )
        if (week_52_high <= 0 or week_52_low <= 0) and cmp_value > 0:
            try:
                levels_52_week = investing_52_week_levels(code)
                week_52_high = week_52_high or float(levels_52_week.get("high") or 0)
                week_52_low = week_52_low or float(levels_52_week.get("low") or 0)
            except Exception:
                pass
        cost_value = quantity * avg_price
        market_value = quantity * cmp_value if cmp_value > 0 else 0.0
        pnl = market_value - cost_value if cmp_value > 0 else None
        pnl_pct = (pnl / cost_value * 100) if pnl is not None and cost_value > 0 else None
        pct_to_52_high = ((cmp_value - week_52_high) / week_52_high * 100) if cmp_value > 0 and week_52_high > 0 else None
        pct_from_52_low = ((cmp_value - week_52_low) / week_52_low * 100) if cmp_value > 0 and week_52_low > 0 else None
        rows.append(
            {
                "code": code,
                "quote_key": resolved_key,
                "finance_url": google_finance_link_for_code(code),
                "screener_url": screener_link_for_code(code),
                "symbol": symbol,
                "company": item["company"],
                "sector": item["sector"],
                "core": item.get("core") or "",
                "quantity": quantity,
                "avg_price": avg_price,
                "cmp": cmp_value if cmp_value > 0 else None,
                "daily_change_pct": daily_change_pct,
                "cost_value": cost_value,
                "market_value": market_value if cmp_value > 0 else None,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "pct_to_52_high": pct_to_52_high,
                "pct_from_52_low": pct_from_52_low,
                "portfolio_pct": None,
                "pe": "N/A",
                "sector_pe": "N/A",
                "opm": "N/A",
                "mcap": "N/A",
                "debt": "N/A",
                "news": None,
                "error": "" if quote else quote_error or "Quote unavailable",
            }
        )
    news_by_symbol = fetch_investing_news(rows)
    for row in rows:
        row["news"] = news_by_symbol.get(str(row["symbol"]), None)
    total_cost = sum(float(row.get("cost_value") or 0) for row in rows)
    total_market = sum(float(row.get("market_value") or 0) for row in rows)
    for row in rows:
        market_value = float(row.get("market_value") or 0)
        row["portfolio_pct"] = (market_value / total_market * 100) if total_market > 0 and market_value > 0 else None
    total_pnl = total_market - total_cost if total_market > 0 else None
    core_value = sum(float(row.get("market_value") or 0) for row in rows if row.get("core") == "Y")
    return rows, {
        "total_cost": total_cost,
        "total_market": total_market,
        "total_pnl": total_pnl,
        "total_pnl_pct": (total_pnl / total_cost * 100) if total_pnl is not None and total_cost > 0 else None,
        "core_value": core_value,
        "core_pct": (core_value / total_market * 100) if total_market > 0 else None,
        "quote_error": quote_error,
    }


def income_growth_candidates() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    income_growth_by_symbol = load_income_growth_holding_map()
    investing_rows, investing_summary = investing_holdings_rows()
    kite = kite_orders.kite_client()
    today = app_now().date()
    option_rows_by_name: dict[str, list[dict[str, Any]]] = {}
    for item in cached_kite_instruments(kite, "NFO"):
        if str(item.get("instrument_type") or "").upper() != "CE":
            continue
        name = str(item.get("name") or "").upper().strip()
        if not name:
            continue
        expiry_value = item.get("expiry")
        if isinstance(expiry_value, datetime):
            expiry_day = expiry_value.date()
        elif isinstance(expiry_value, date):
            expiry_day = expiry_value
        elif expiry_value:
            try:
                expiry_day = datetime.fromisoformat(str(expiry_value)).date()
            except ValueError:
                continue
        else:
            continue
        if expiry_day >= today:
            option_rows_by_name.setdefault(name, []).append({**item, "_expiry_day": expiry_day})

    quote_keys: list[str] = []
    selected_by_symbol: dict[str, dict[str, Any]] = {}
    for row in investing_rows:
        symbol = str(row.get("symbol") or "").upper()
        sheet = income_growth_by_symbol.get(symbol)
        cmp_value = float((sheet or {}).get("cmp") or row.get("cmp") or 0)
        quantity = int(float((sheet or {}).get("holding") or row.get("quantity") or 0))
        if cmp_value <= 0 or quantity <= 0:
            continue
        target_strike = float((sheet or {}).get("call_strike") or (cmp_value * 1.10))
        options = [
            item
            for item in option_rows_by_name.get(symbol, [])
            if float(item.get("strike") or 0) >= target_strike
        ]
        if not options:
            continue
        nearest_expiry = min(item["_expiry_day"] for item in options)
        same_expiry = [item for item in options if item["_expiry_day"] == nearest_expiry]
        candidate = min(same_expiry, key=lambda item: float(item.get("strike") or 0))
        quote_key = f"NFO:{candidate.get('tradingsymbol')}"
        selected_by_symbol[symbol] = {**candidate, "_quote_key": quote_key}
        quote_keys.append(quote_key)

    option_quotes = cached_kite_quote(kite, quote_keys) if quote_keys else {}
    rows: list[dict[str, Any]] = []
    total_existing_income = 0.0
    best_additional = 0.0
    for row in investing_rows:
        symbol = str(row.get("symbol") or "").upper()
        sheet = income_growth_by_symbol.get(symbol)
        cmp_value = float((sheet or {}).get("cmp") or row.get("cmp") or 0)
        quantity = int(float((sheet or {}).get("holding") or row.get("quantity") or 0))
        market_value = float((sheet or {}).get("value") or (quantity * cmp_value if cmp_value else 0))
        candidate = selected_by_symbol.get(symbol)
        core = str(row.get("core") or "").upper()
        quality_score = 1.0 if core == "Y" else 0.75 if quantity > 0 else 0.4
        pct_to_high = (sheet or {}).get("week_52") if sheet else row.get("pct_to_52_high")
        pct_from_low = row.get("pct_from_52_low")
        valuation_score = 0.7
        if isinstance(pct_to_high, (int, float)) and pct_to_high >= -5:
            valuation_score = 0.45
        elif isinstance(pct_from_low, (int, float)) and pct_from_low <= 15:
            valuation_score = 0.9
        pe_value = (sheet or {}).get("put_down_pct")
        if isinstance(pe_value, (int, float)) and pe_value > 60:
            valuation_score = min(valuation_score, 0.45)
        elif pe_value is None:
            valuation_score = min(valuation_score, 0.65)
        today_change = float((sheet or {}).get("today") or 0)
        week_change = float((sheet or {}).get("week_1") or 0)
        month_change = float((sheet or {}).get("month") or 0)
        trend_score = 0.75
        if today_change <= 0 and week_change <= 0:
            trend_score = 1.0
        elif today_change > 2 or week_change > 5:
            trend_score = 0.45
        elif month_change < -8:
            trend_score = 0.6
        input_lot_size = int(float((sheet or {}).get("lot_size") or 0))
        input_lots_can_sell = int(float((sheet or {}).get("lots_can_sell") or 0))
        input_call_strike = (sheet or {}).get("call_strike")
        input_put_strike = (sheet or {}).get("pe")
        input_to_sell = (sheet or {}).get("to_sell")
        input_gap_pct = (sheet or {}).get("gap_pct")
        input_put_down_pct = (
            ((cmp_value - float(input_put_strike)) / cmp_value * 100)
            if cmp_value > 0 and isinstance(input_put_strike, (int, float))
            else None
        )
        input_times_lot = (sheet or {}).get("times_lot")
        base_row = {
            **row,
            "quantity": quantity,
            "cmp": cmp_value if cmp_value > 0 else row.get("cmp"),
            "market_value": market_value,
            "sheet_source": bool(sheet),
            "times_lot": input_times_lot,
            "lots_can_sell_input": input_lots_can_sell,
            "input_call_strike": input_call_strike,
            "input_put_strike": input_put_strike,
            "input_to_sell": input_to_sell,
            "input_lot_size": input_lot_size,
            "input_gap_pct": input_gap_pct,
            "input_put_down_pct": input_put_down_pct,
            "input_pe": pe_value,
            "input_52w": pct_to_high,
            "input_1y": (sheet or {}).get("one_year"),
            "input_month": (sheet or {}).get("month"),
            "input_1w": (sheet or {}).get("week_1"),
            "input_today": (sheet or {}).get("today"),
        }
        if not candidate or cmp_value <= 0:
            # Income Growth is only useful for F&O names where covered CALLs can be researched.
            continue
        lot_size = input_lot_size or int(candidate.get("lot_size") or 0)
        premium = quote_ltp(option_quotes.get(str(candidate.get("_quote_key")), {}))
        covered_lots = input_lots_can_sell if sheet else (quantity // lot_size if lot_size > 0 else 0)
        remainder = quantity % lot_size if lot_size > 0 else 0
        extra_shares = (lot_size - remainder) if lot_size > 0 and remainder else 0
        capital_for_next_lot = extra_shares * cmp_value if extra_shares else 0.0
        monthly_income = covered_lots * lot_size * premium
        premium_yield_pct = (premium / cmp_value * 100) if cmp_value > 0 and premium > 0 else 0.0
        liquidity_score = 1.0 if premium > 0 and monthly_income >= 5000 else 0.7 if premium > 0 else 0.25
        gap_score = 1.0 if isinstance(input_gap_pct, (int, float)) and input_gap_pct >= 8 else 0.7
        cc_capacity_score = covered_lots * premium_yield_pct * liquidity_score * quality_score * valuation_score * trend_score * gap_score
        additional_income = lot_size * premium
        additional_capacity_per_lakh = additional_income / (capital_for_next_lot / 100000) if capital_for_next_lot and premium > 0 else 0.0
        coverage_ok = quantity >= lot_size and (not isinstance(input_times_lot, (int, float)) or input_times_lot >= 1)
        if quantity <= 0:
            decision, color = "NO_HOLDING_NO_CC", "red"
        elif not coverage_ok:
            decision, color = "NEED_MORE_SHARES_FOR_LOT", "red"
        elif capital_for_next_lot and capital_for_next_lot <= 100000 and additional_capacity_per_lakh > 1500:
            decision, color = "BUY_TO_COMPLETE_NEXT_LOT", "green"
        elif covered_lots > 0 and premium > 0:
            decision, color = "SELL_COVERED_CALL_CANDIDATE", "green"
        elif premium <= 0:
            decision, color = "CHECK_LIVE_PREMIUM", "yellow"
        elif valuation_score < 0.6:
            decision, color = "WAIT_VALUATION_RISK", "yellow"
        else:
            decision, color = "ACCUMULATE_SLOWLY", "yellow"
        total_existing_income += monthly_income
        best_additional = max(best_additional, additional_capacity_per_lakh)
        rows.append({**base_row, "candidate_ce": str(candidate.get("tradingsymbol") or f"{symbol} CALL {fmt_number(input_call_strike)}"), "lot_size": lot_size, "covered_lots": covered_lots, "extra_shares": extra_shares, "capital_for_next_lot": capital_for_next_lot, "premium": premium if premium > 0 else None, "monthly_income": monthly_income, "premium_yield_pct": premium_yield_pct, "liquidity_score": liquidity_score, "quality_score": quality_score, "valuation_score": valuation_score, "trend_score": trend_score, "cc_capacity_score": cc_capacity_score, "additional_capacity_per_lakh": additional_capacity_per_lakh, "decision": decision, "decision_color": color})
    rows.sort(key=lambda row: (float(row.get("additional_capacity_per_lakh") or 0), float(row.get("cc_capacity_score") or 0)), reverse=True)
    return rows, {
        "existing_monthly_income": total_existing_income,
        "best_additional_per_lakh": best_additional,
        "portfolio_market": investing_summary.get("total_market"),
        "count": len(rows),
        "as_of": app_now().strftime("%d %b %Y %H:%M:%S"),
    }


def income_growth_gpt_user_prompt(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Stock",
            "Holding shares",
            "Times of lot size",
            "Lots can be sold",
            "CMP",
            "CALL STRIKE",
            "Value",
            "TO SELL",
            "Lot Size",
            "GAP for %",
            "% down for PUT",
            "PUT Strike",
            "PE",
            "52W",
            "1Y R",
            "Month",
            "1W",
            "Today",
            "Kite CE",
            "Live Premium",
            "App Decision",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.get("symbol"),
                row.get("quantity"),
                row.get("times_lot"),
                row.get("covered_lots"),
                row.get("cmp"),
                row.get("input_call_strike"),
                row.get("market_value"),
                row.get("input_to_sell"),
                row.get("lot_size") or row.get("input_lot_size"),
                row.get("input_gap_pct"),
                row.get("input_put_down_pct"),
                row.get("input_put_strike"),
                row.get("input_pe"),
                row.get("input_52w"),
                row.get("input_1y"),
                row.get("input_month"),
                row.get("input_1w"),
                row.get("input_today"),
                row.get("candidate_ce"),
                row.get("premium"),
                row.get("decision"),
            ]
        )
    return (
        "Provide best shares to take position today and generate CSV file in the exact format "
        "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity.\n"
        "Use the Monthly Income by Trading GPT rules from the system prompt. Prefer conservative covered CALLs "
        "from this Income Growth table. Skip any row that is not fully covered, has no valid option symbol, "
        "or violates conservative monthly income rules. If live premium is unavailable, use price as 0.\n\n"
        f"Income Growth summary: {json.dumps(summary, default=str)}\n\n"
        f"Income Growth candidate table:\n{output.getvalue()}"
    )


def validate_income_growth_with_openai(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    model: str,
    system_prompt: str,
    prompt: str = "",
    force_refresh: bool = False,
) -> tuple[str, str, str, bool]:
    final_prompt = prompt.strip() or income_growth_gpt_user_prompt(rows, summary)
    cache_seed = json.dumps(
        {
            "model": model.strip() or DEFAULT_OPENAI_MODEL,
            "system_prompt": system_prompt.strip() or DEFAULT_OPENAI_SYSTEM_PROMPT,
            "prompt": final_prompt,
        },
        sort_keys=True,
    )
    cache_key = "income-growth:gpt:" + hashlib.sha256(cache_seed.encode("utf-8")).hexdigest()
    now = time.time()
    cached = APP_CACHE.get(cache_key)
    if cached and not force_refresh and now - cached[0] < INCOME_GROWTH_GPT_CACHE_SECONDS:
        csv_text, output, response_id = copy.deepcopy(cached[1])
        return csv_text, output, response_id, True
    result = generate_csv_with_openai(final_prompt, model, system_prompt)
    APP_CACHE[cache_key] = (now, copy.deepcopy(result))
    return result[0], result[1], result[2], False


def income_growth_gpt_schedule_state() -> dict[str, Any]:
    saved = load_app_settings().get("income_growth_gpt_scheduler")
    state = dict(saved) if isinstance(saved, dict) else {}
    state.setdefault("enabled", True)
    state.setdefault("schedule_time", INCOME_GROWTH_GPT_SCHEDULE_TIME)
    state.setdefault("status", "WAITING")
    state.setdefault("message", "Waiting for the next weekday 09:30 IST validation.")
    return state


def save_income_growth_gpt_schedule_state(**updates: Any) -> dict[str, Any]:
    state = income_growth_gpt_schedule_state()
    state.update(updates)
    save_app_settings({"income_growth_gpt_scheduler": state})
    return state


def activate_today_csv_path(csv_path: str) -> None:
    global DEFAULT_CSV_PATH
    DEFAULT_CSV_PATH = Path(csv_path)


def run_scheduled_income_growth_gpt_job(now: datetime | None = None) -> dict[str, Any] | None:
    now = now.astimezone(INDIA_TIME_ZONE) if now and now.tzinfo else (
        now.replace(tzinfo=INDIA_TIME_ZONE) if now else datetime.now(INDIA_TIME_ZONE)
    )
    schedule_state = income_growth_gpt_schedule_state()
    if (
        not schedule_state.get("enabled", True)
        or scheduled_job_is_paused(schedule_state, now)
        or now.weekday() >= 5
    ):
        return None
    schedule_hour, schedule_minute = (
        int(part) for part in str(schedule_state.get("schedule_time") or INCOME_GROWTH_GPT_SCHEDULE_TIME).split(":", 1)
    )
    scheduled_at = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
    window_ends = scheduled_at + timedelta(minutes=INCOME_GROWTH_GPT_SCHEDULE_WINDOW_MINUTES)
    if now < scheduled_at or now >= window_ends:
        return None
    today_key = now.strftime("%Y-%m-%d")
    if str(schedule_state.get("last_attempt_date") or "") == today_key:
        return None
    if not INCOME_GROWTH_GPT_SCHEDULER_LOCK.acquire(blocking=False):
        return None
    try:
        schedule_state = income_growth_gpt_schedule_state()
        if str(schedule_state.get("last_attempt_date") or "") == today_key:
            return None
        profile_name = selected_kite_profile_name()
        started_at = now.strftime("%d %b %Y %H:%M:%S IST")
        save_income_growth_gpt_schedule_state(
            last_attempt_date=today_key,
            last_run_at=started_at,
            profile=profile_name,
            status="RUNNING",
            message="Refreshing Income Growth candidates and requesting fresh GPT validation.",
        )
        try:
            profile = load_kite_profiles().get(profile_name, blank_kite_profile())
            apply_kite_profile_to_env(profile)
            setup_issue = kite_setup_issue()
            if setup_issue:
                raise RuntimeError(setup_issue)
            kite = kite_orders.kite_client()
            market_open, market_message = verify_scheduled_position_market_open(kite, now)
            if not market_open:
                return save_income_growth_gpt_schedule_state(
                    status="MARKET_CLOSED",
                    message=market_message,
                )
            rows, summary = income_growth_candidates()
            csv_text, output, response_id, _ = validate_income_growth_with_openai(
                rows,
                summary,
                DEFAULT_OPENAI_MODEL,
                read_openai_csv_system_prompt(),
                "",
                True,
            )
            normalized_csv = normalize_kite_csv_input(csv_text)
            parsed_rows = parse_csv_text(normalized_csv)
            validate_kite_order_rows(parsed_rows)
            saved_path, save_message = save_today_csv_text(normalized_csv)
            activate_today_csv_path(saved_path)
            return save_income_growth_gpt_schedule_state(
                status="SAVED",
                message=f"{market_message} {save_message} Ready for Research and Trading preview.",
                csv_path=saved_path,
                order_count=len(parsed_rows),
                response_id=response_id,
                output_preview=str(output or "")[:600],
            )
        except Exception as exc:
            return save_income_growth_gpt_schedule_state(
                status="ERROR",
                message=friendly_external_error(exc, "Scheduled Income Growth GPT validation"),
            )
    finally:
        INCOME_GROWTH_GPT_SCHEDULER_LOCK.release()


def load_pe_sell_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_PE_SELL_SETTINGS)
    if PE_SELL_SETTINGS_PATH.exists():
        try:
            saved = json.loads(PE_SELL_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                settings.update(saved)
        except (OSError, ValueError, TypeError):
            pass
    return apply_option_sell_markup_setting(settings)


def quote_bid_ask(quote: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    depth = quote.get("depth") or {}
    buy = depth.get("buy") or []
    sell = depth.get("sell") or []
    bid = float((buy[0] if buy else {}).get("price") or 0) or None
    ask = float((sell[0] if sell else {}).get("price") or 0) or None
    if bid and ask and ask >= bid:
        midpoint = (bid + ask) / 2
        spread = ((ask - bid) / midpoint * 100) if midpoint > 0 else None
    else:
        spread = None
    return bid, ask, spread


def classify_pe_event_risk(symbol: str, news_cache: dict[str, list[dict[str, str]]]) -> tuple[str, str]:
    underlying = underlying_for_symbol(symbol) or str(symbol or "").upper()
    if underlying not in news_cache:
        try:
            news_cache[underlying] = fetch_stock_news([underlying])
        except Exception as exc:
            return "AMBER", f"News check unavailable: {friendly_external_error(exc, underlying)}"
    titles = [str(item.get("title") or "").strip() for item in news_cache.get(underlying, [])]
    if not titles:
        return "GREEN", "No relevant company event found in recent news."
    red_terms = {
        "quarterly result",
        "results today",
        "board meeting",
        "record date",
        "ex-dividend",
        "regulatory action",
        "regulator",
        "pledge",
        "governance",
        "order cancellation",
        "earnings miss",
        "downgrade",
        "f&o ban",
        "fo ban",
    }
    amber_terms = {"dividend", "analyst", "sector", "management", "interview", "rating"}
    for title in titles:
        lowered = title.lower()
        if any(term in lowered for term in red_terms):
            return "RED", f"Direct company event risk: {title[:150]}"
    for title in titles:
        lowered = title.lower()
        if any(term in lowered for term in amber_terms) or classify_news_sentiment(title) == "negative":
            return "AMBER", f"Review recent company/news context: {title[:150]}"
    return "GREEN", "Only generic or non-adverse recent articles found."


def score_pe_sell_candidate(
    candidate: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = {**DEFAULT_PE_SELL_SETTINGS, **(settings or {})}
    result = dict(candidate)
    cmp_value = float(result.get("cmp") or 0)
    strike = float(result.get("strike") or 0)
    lot_size = int(float(result.get("lot_size") or 0))
    premium = float(result.get("premium") or 0)
    sell_limit_price = float(result.get("sell_limit_price") or 0)
    assignment_cash = strike * lot_size
    max_profit = sell_limit_price * lot_size
    premium_yield = (max_profit / assignment_cash * 100) if assignment_cash > 0 else 0
    otm = ((cmp_value - strike) / cmp_value * 100) if cmp_value > 0 else 0
    delta = abs(float(result.get("delta") or 0))
    sell_pop = float(result.get("sell_pop") or 0)
    iv = float(result.get("iv") or 0)
    oi = int(float(result.get("oi") or 0))
    volume = int(float(result.get("volume") or 0))
    spread = result.get("bid_ask_spread_percent")
    spread_value = float(spread) if isinstance(spread, (int, float)) else None
    dte = int(float(result.get("dte") or 0))
    event_risk = str(result.get("event_risk") or "AMBER").upper()
    reject_reasons = [str(item) for item in result.get("reject_reasons", []) if str(item)]

    if assignment_cash > float(settings["max_assignment_cash_per_stock"]):
        reject_reasons.append("Assignment cash exceeds configured per-stock limit")
    if not result.get("contract_valid"):
        reject_reasons.append("Option contract not found in active Kite instrument list")
    if premium <= 0 or sell_limit_price <= 0:
        reject_reasons.append("Missing or invalid PE premium")
    if spread_value is not None and spread_value > float(settings["max_bid_ask_spread_percent"]):
        reject_reasons.append("Bid-ask spread exceeds configured maximum")
    if oi < int(settings["min_option_oi"]):
        reject_reasons.append("Option OI is below configured minimum")
    if volume < int(settings["min_option_volume"]):
        reject_reasons.append("Option volume is below configured minimum")
    if event_risk == "RED":
        reject_reasons.append("RED event risk")
    if result.get("fno_ban"):
        reject_reasons.append("Stock is in F&O ban period")
    if premium_yield < float(settings["min_premium_yield_percent"]):
        reject_reasons.append("Premium yield is below configured minimum")
    if strike <= 0 or strike >= cmp_value:
        reject_reasons.append("Selected PE strike is not below CMP")
    if result.get("severe_breakdown"):
        reject_reasons.append("Daily trend is a severe breakdown")
    if result.get("has_active_pe_position"):
        reject_reasons.append("Existing active PE position for this stock")

    core = str(result.get("core") or "").upper() == "Y"
    pe_value = result.get("stock_pe")
    pct_52w = result.get("pct_to_52w_high")
    one_year = result.get("one_year_return")
    month = float(result.get("month_return") or 0)
    week = float(result.get("week_return") or 0)
    today = float(result.get("today_return") or 0)
    business_quality_score = 10 if core else 7
    valuation_score = 5
    if isinstance(pe_value, (int, float)):
        valuation_score = 8 if pe_value <= 30 else 6 if pe_value <= 50 else 3 if pe_value <= 70 else 1
    financial_strength_score = 8 if core else 5
    corrected_but_not_broken_score = (
        6 if isinstance(pct_52w, (int, float)) and -50 < pct_52w <= -10 and month > -12
        else 4 if month > -12 and week > -8
        else 1
    )
    sector_quality_score = 4 if result.get("sector") else 2
    portfolio_fit_score = 4 if int(float(result.get("holding") or 0)) > 0 else 2
    stock_quality_score = min(
        40,
        business_quality_score
        + valuation_score
        + financial_strength_score
        + corrected_but_not_broken_score
        + sector_quality_score
        + portfolio_fit_score,
    )

    otm_buffer_score = 12 if float(settings["min_otm_percent"]) <= otm <= float(settings["max_otm_percent"]) else 8 if otm > float(settings["max_otm_percent"]) else 3
    delta_pop_score = 10 if sell_pop >= float(settings["min_sell_pop_percent"]) and delta <= float(settings["max_delta"]) else 7 if sell_pop >= 80 and delta <= 0.25 else 2
    premium_yield_score = 10 if premium_yield >= 0.60 else 8 if premium_yield >= 0.45 else 6 if premium_yield >= float(settings["min_premium_yield_percent"]) else 0
    liquidity_score = 10
    if oi <= 0 and volume <= 0:
        liquidity_score = 5
    elif spread_value is not None and spread_value > 10:
        liquidity_score = 6
    iv_score = 6 if 15 <= iv <= 40 else 4 if 40 < iv <= 50 else 2
    pcr = result.get("pcr")
    support_score = 6 if isinstance(pcr, (int, float)) and pcr > 0.80 else 4 if isinstance(pcr, (int, float)) and pcr >= 0.60 else 2
    market_sector_trend_score = 4 if month >= -5 and week >= -5 and today >= -4 else 2 if month >= -10 and week >= -8 else 0
    dte_score = 2 if int(settings["preferred_dte_min"]) <= dte <= int(settings["preferred_dte_max"]) else 1
    pe_trade_score = min(
        60,
        otm_buffer_score
        + delta_pop_score
        + premium_yield_score
        + liquidity_score
        + iv_score
        + support_score
        + market_sector_trend_score
        + dte_score,
    )
    result.update(
        {
            "assignment_cash": assignment_cash,
            "max_profit": max_profit,
            "premium_yield_percent": premium_yield,
            "otm_percent": otm,
            "stock_quality_score": stock_quality_score,
            "pe_trade_score": pe_trade_score,
            "final_pe_score": min(100, stock_quality_score + pe_trade_score),
            "reject_reason": "; ".join(dict.fromkeys(reject_reasons)),
            "status": "AVOID_TODAY" if reject_reasons else "WATCH_REVIEW",
            "explanation": (
                f"{otm:.1f}% OTM, {sell_pop:.1f}% SELL POP, "
                f"{premium_yield:.2f}% premium yield, event risk {event_risk}."
            ),
        }
    )
    return result


def rank_pe_sell_candidates(
    candidates: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    limit: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    scored = [score_pe_sell_candidate(candidate, settings) for candidate in candidates]
    valid = [item for item in scored if item["status"] != "AVOID_TODAY"]
    valid.sort(
        key=lambda item: (
            float(item.get("final_pe_score") or 0),
            float(item.get("premium_yield_percent") or 0),
            int(item.get("oi") or 0) + int(item.get("volume") or 0),
            -float(item.get("assignment_cash") or 0),
        ),
        reverse=True,
    )
    top = valid[:limit]
    for item in top:
        item["status"] = "TOP_3"
    watch = valid[limit:]
    avoid = [item for item in scored if item["status"] == "AVOID_TODAY"]
    return top, watch, avoid


def build_live_pe_sell_rankings(
    growth_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    settings = load_pe_sell_settings()
    active_pe_underlyings = active_pe_position_underlyings(False)
    news_cache: dict[str, list[dict[str, str]]] = {}
    candidates: list[dict[str, Any]] = []
    for row in growth_rows:
        symbol = str(row.get("symbol") or "").upper()
        cmp_value = float(row.get("cmp") or 0)
        if not symbol or cmp_value <= 0:
            continue
        try:
            contract = next_monthly_pe_candidate(kite, symbol)
            quote_key = f"NFO:{contract['symbol']}"
            quote = cached_kite_quote(kite, [quote_key]).get(quote_key, {})
            premium = quote_ltp(quote)
            bid, ask, spread = quote_bid_ask(quote)
            analytics = option_analytics_for_symbol(contract["symbol"])
            markup = float(settings["price_markup_percent"])
            sell_limit = ceil_to_tick(premium * (1 + markup / 100), 0.05) if premium > 0 else 0
            event_risk, event_detail = classify_pe_event_risk(contract["symbol"], news_cache)
            month = float(row.get("input_month") or 0)
            week = float(row.get("input_1w") or 0)
            today = float(row.get("input_today") or 0)
            candidates.append(
                {
                    "stock": symbol,
                    "symbol": symbol,
                    "option_symbol": contract["symbol"],
                    "cmp": cmp_value,
                    "target_strike": contract["target_strike"],
                    "strike": contract["strike"],
                    "expiry": contract["expiry"].strftime("%d %b %Y"),
                    "dte": trading_days_remaining(contract["expiry"]),
                    "lot_size": contract["lot_size"],
                    "premium": premium,
                    "sell_limit_price": sell_limit,
                    "delta": abs(float(analytics.get("delta") or 0)),
                    "sell_pop": float(analytics.get("sell_pop") or 0),
                    "iv": float(analytics.get("iv_percent") or 0),
                    "oi": quote_oi(quote),
                    "volume": int(float(quote.get("volume") or 0)),
                    "bid": bid,
                    "ask": ask,
                    "bid_ask_spread_percent": spread,
                    "pcr": analytics.get("pcr"),
                    "event_risk": event_risk,
                    "event_risk_explanation": event_detail,
                    "contract_valid": bool(contract.get("symbol")) and float(contract.get("strike") or 0) <= float(contract.get("target_strike") or 0),
                    "fno_ban": False,
                    "severe_breakdown": month < -12 or week < -8 or today < -6,
                    "has_active_pe_position": symbol in active_pe_underlyings,
                    "core": row.get("core"),
                    "sector": row.get("sector"),
                    "holding": row.get("quantity"),
                    "stock_pe": row.get("input_pe"),
                    "pct_to_52w_high": row.get("input_52w"),
                    "one_year_return": row.get("input_1y"),
                    "month_return": row.get("input_month"),
                    "week_return": row.get("input_1w"),
                    "today_return": row.get("input_today"),
                }
            )
        except Exception as exc:
            candidates.append(
                {
                    "stock": symbol,
                    "symbol": symbol,
                    "cmp": cmp_value,
                    "contract_valid": False,
                    "event_risk": "AMBER",
                    "reject_reasons": [friendly_external_error(exc, f"{symbol} PE candidate")],
                }
            )
    return rank_pe_sell_candidates(candidates, settings)


def income_dashboard_snapshot(force_refresh: bool = False) -> dict[str, Any]:
    profile = selected_kite_profile_name()
    cache_key = f"income-dashboard:{profile}"
    if force_refresh:
        clear_app_cache((cache_key, "kite:positions", "kite:quote:"))

    def load_snapshot() -> dict[str, Any]:
        growth_rows, growth_summary = income_growth_candidates()
        pe_top, pe_watch, pe_avoid = build_live_pe_sell_rankings(growth_rows)
        positions = open_option_positions(use_cache=False)
        if positions and kite_orders is not None:
            positions = refresh_option_positions_with_live_ltp(
                positions,
                kite_orders.kite_client(),
            )
        short_positions = [
            position for position in positions if int(position.get("quantity") or 0) < 0
        ]
        pe_positions = [
            position
            for position in short_positions
            if str(position.get("tradingsymbol") or "").upper().endswith("PE")
        ]
        ce_positions = [
            position
            for position in short_positions
            if str(position.get("tradingsymbol") or "").upper().endswith("CE")
        ]
        current_pnl = sum(float(position.get("pnl") or 0) for position in short_positions)
        return {
            "growth_rows": growth_rows,
            "growth_summary": growth_summary,
            "pe_top": pe_top,
            "pe_watch": pe_watch,
            "pe_avoid": pe_avoid,
            "positions": short_positions,
            "summary": {
                "overall_pnl": current_pnl,
                "active_short_positions": len(short_positions),
                "active_pe_positions": len(pe_positions),
                "active_ce_positions": len(ce_positions),
                "profitable_positions": sum(
                    1 for position in short_positions if float(position.get("pnl") or 0) > 0
                ),
                "review_positions": sum(
                    1 for position in short_positions if float(position.get("pnl") or 0) < 0
                ),
            },
            "calculated_at": datetime.now().strftime("%d %b %Y %H:%M:%S"),
        }

    return cached_value(cache_key, load_snapshot, INCOME_DASHBOARD_CACHE_SECONDS)


def apply_income_dashboard_snapshot(
    state: PageState,
    force_refresh: bool = False,
) -> str:
    snapshot, console_log = call_with_console(income_dashboard_snapshot, force_refresh)
    state.income_growth_rows = snapshot["growth_rows"]
    state.income_growth_summary = snapshot["growth_summary"]
    state.income_pe_top = snapshot["pe_top"]
    state.income_pe_watch = snapshot["pe_watch"]
    state.income_pe_avoid = snapshot["pe_avoid"]
    state.income_positions = snapshot["positions"]
    state.income_summary = snapshot["summary"]
    state.console_log = console_log
    return str(snapshot.get("calculated_at") or "")


DEFAULT_CE_SELL_SETTINGS = {
    "auto_reduce_lots_enabled": True,
    "default_otm_percent": 10.0,
    "core_otm_add_percent": 3.0,
    "min_premium_yield_percent": 0.20,
    "min_sell_pop_percent": 80.0,
    "max_delta": 0.30,
    "min_option_oi": 0,
    "min_option_volume": 0,
    "max_bid_ask_spread_percent": 35.0,
    "price_markup_percent": DEFAULT_OPTION_SELL_MARKUP_PERCENT,
}


def load_ce_sell_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_CE_SELL_SETTINGS)
    if CE_SELL_SETTINGS_PATH.exists():
        try:
            saved = json.loads(CE_SELL_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                settings.update(saved)
        except (OSError, ValueError, TypeError):
            pass
    return apply_option_sell_markup_setting(settings)


def select_valid_ce_contract(
    instruments: list[dict[str, Any]],
    target_strike: float,
) -> dict[str, Any]:
    valid = [
        item
        for item in instruments
        if str(item.get("instrument_type") or "").upper() == "CE"
        and float(item.get("strike") or 0) >= float(target_strike)
    ]
    if not valid:
        raise ValueError("No valid CE strike available above target")
    return min(valid, key=lambda item: float(item.get("strike") or 0))


def score_ce_sell_candidate(
    candidate: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = {**DEFAULT_CE_SELL_SETTINGS, **(settings or {})}
    result = dict(candidate)
    holding_qty = int(float(result.get("holding_qty") or 0))
    lot_size = int(float(result.get("active_lot_size") or 0))
    requested_lots = min(
        MAX_TOP3_CE_SELL_LOTS,
        int(float(result.get("requested_lots") or 0)),
    )
    covered_lots = holding_qty // lot_size if lot_size > 0 else 0
    lots_to_sell = min(
        MAX_TOP3_CE_SELL_LOTS,
        min(requested_lots, covered_lots) if settings["auto_reduce_lots_enabled"] else requested_lots,
    )
    quantity = lots_to_sell * lot_size
    cmp_value = float(result.get("cmp") or 0)
    strike = float(result.get("selected_ce_strike") or 0)
    premium = float(result.get("premium") or 0)
    sell_limit = float(result.get("sell_limit_price") or 0)
    max_profit = sell_limit * quantity
    covered_notional = cmp_value * quantity
    premium_yield = max_profit / covered_notional * 100 if covered_notional > 0 else 0
    otm = (strike - cmp_value) / cmp_value * 100 if cmp_value > 0 else 0
    delta = abs(float(result.get("delta") or 0))
    sell_pop = float(result.get("sell_pop") or 0)
    oi = int(float(result.get("oi") or 0))
    volume = int(float(result.get("volume") or 0))
    spread = result.get("bid_ask_spread_percent")
    spread_value = float(spread) if isinstance(spread, (int, float)) else None
    event_risk = str(result.get("event_risk") or "AMBER").upper()
    breakout_risk = str(result.get("breakout_risk") or "AMBER").upper()
    reject = [str(item) for item in result.get("reject_reasons", []) if str(item)]
    if holding_qty <= 0:
        reject.append("No share holding; naked CE not allowed")
    if lot_size <= 0 or covered_lots <= 0:
        reject.append("Insufficient holding for one covered lot")
    if requested_lots > covered_lots and not settings["auto_reduce_lots_enabled"]:
        reject.append("Requested lots exceed fully covered lots")
    if quantity <= 0 or quantity > holding_qty:
        reject.append("Naked CE risk: quantity is not fully covered")
    if not result.get("contract_valid"):
        reject.append("CE contract not found in active Kite instrument list")
    if strike <= cmp_value:
        reject.append("Selected CE strike must be above CMP")
    if premium <= 0 or sell_limit <= 0:
        reject.append("Missing or invalid CE premium")
    if spread_value is not None and spread_value > float(settings["max_bid_ask_spread_percent"]):
        reject.append("Bid-ask spread exceeds configured maximum")
    if oi < int(settings["min_option_oi"]):
        reject.append("Option OI below configured minimum")
    if volume < int(settings["min_option_volume"]):
        reject.append("Option volume below configured minimum")
    if event_risk == "RED":
        reject.append("RED company event risk")
    if result.get("has_active_position"):
        reject.append("Existing active option position for this stock")
    if premium_yield < float(settings["min_premium_yield_percent"]):
        reject.append("Premium yield below configured minimum")
    if sell_pop < float(settings["min_sell_pop_percent"]):
        reject.append("SELL POP below configured minimum")
    if delta > float(settings["max_delta"]):
        reject.append("CE delta exceeds configured maximum")
    if breakout_risk == "RED" and otm < 12:
        reject.append("RED breakout risk with CE strike too close")

    coverage_score = min(30, (10 if covered_lots >= requested_lots > 0 else 5) + (5 if holding_qty - quantity >= lot_size else 3) + (5 if lots_to_sell <= 2 else 3) + (5 if result.get("core") != "Y" else 3) + 5)
    call_away_score = min(30, (8 if otm >= 10 else 5 if otm >= 7 else 2) + (6 if float(result.get("one_year_return") or 0) <= 10 else 3) + (5 if float(result.get("week_return") or 0) <= 2 else 2) + (5 if breakout_risk == "GREEN" else 3 if breakout_risk == "AMBER" else 0) + (4 if result.get("core") != "Y" else 2) + 2)
    trade_score = min(40, (8 if otm >= 10 else 5 if otm >= 7 else 2) + (7 if sell_pop >= 85 and delta <= 0.25 else 4 if sell_pop >= 75 else 1) + (8 if premium_yield >= 0.5 else 5 if premium_yield >= 0.25 else 1) + (7 if spread_value is None or spread_value <= 15 else 3) + (4 if 15 <= float(result.get("iv") or 0) <= 50 else 2) + (4 if breakout_risk == "GREEN" else 2) + 2)
    if event_risk == "AMBER":
        trade_score = max(0, trade_score - 4)
    if breakout_risk == "AMBER":
        trade_score = max(0, trade_score - 4)
    final_score = min(100, coverage_score + call_away_score + trade_score)
    result.update(
        {
            "covered_lots_available": covered_lots,
            "lots_to_sell": lots_to_sell,
            "quantity": quantity,
            "max_profit": max_profit,
            "notional_covered_value": covered_notional,
            "premium_yield_percent": premium_yield,
            "otm_percent": otm,
            "holding_coverage_score": coverage_score,
            "call_away_comfort_score": call_away_score,
            "ce_trade_score": trade_score,
            "final_ce_score": final_score,
            "status": "AVOID_TODAY" if reject else "WATCH_REVIEW",
            "reject_reason": "; ".join(dict.fromkeys(reject)),
            "explanation": (
                f"{otm:.1f}% OTM, {sell_pop:.1f}% SELL POP, "
                f"{premium_yield:.2f}% covered-value yield, {breakout_risk} breakout risk."
            ),
        }
    )
    return result


def rank_ce_sell_candidates(
    candidates: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    limit: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    scored = [score_ce_sell_candidate(item, settings) for item in candidates]
    valid = [item for item in scored if item["status"] != "AVOID_TODAY"]
    valid.sort(
        key=lambda item: (
            float(item.get("final_ce_score") or 0),
            float(item.get("premium_yield_percent") or 0),
            float(item.get("otm_percent") or 0),
        ),
        reverse=True,
    )
    top = valid[:limit]
    for item in top:
        item["status"] = "TOP_3"
    return top, valid[limit:], [item for item in scored if item["status"] == "AVOID_TODAY"]


def build_live_ce_sell_rankings() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    growth_rows, _ = income_growth_candidates()
    settings = load_ce_sell_settings()
    active_underlyings = active_position_underlyings()
    instruments = cached_kite_instruments(kite, "NFO")
    by_symbol = {str(item.get("tradingsymbol") or "").upper(): item for item in instruments}
    news_cache: dict[str, list[dict[str, str]]] = {}
    candidates: list[dict[str, Any]] = []
    for row in growth_rows:
        symbol = str(row.get("symbol") or "").upper()
        option_symbol = str(row.get("candidate_ce") or "").upper()
        instrument = by_symbol.get(option_symbol)
        holding = int(float(row.get("quantity") or 0))
        cmp_value = float(row.get("cmp") or 0)
        requested_lots = MAX_TOP3_CE_SELL_LOTS
        if not instrument:
            candidates.append({"stock": symbol, "holding_qty": holding, "requested_lots": requested_lots, "cmp": cmp_value, "contract_valid": False})
            continue
        lot_size = int(instrument.get("lot_size") or 0)
        desired_otm = float(settings["default_otm_percent"])
        if str(row.get("core") or "").upper() == "Y":
            desired_otm += float(settings["core_otm_add_percent"])
        target = cmp_value * (1 + desired_otm / 100)
        expiry = instrument.get("expiry")
        same_expiry = [
            item for item in instruments
            if str(item.get("name") or "").upper() == symbol
            and str(item.get("instrument_type") or "").upper() == "CE"
            and item.get("expiry") == expiry
        ]
        try:
            selected = select_valid_ce_contract(same_expiry, target)
            option_symbol = str(selected.get("tradingsymbol") or "").upper()
            lot_size = int(selected.get("lot_size") or 0)
            quote_key = f"NFO:{option_symbol}"
            quote = cached_kite_quote(kite, [quote_key]).get(quote_key, {})
            premium = quote_ltp(quote)
            bid, ask, spread = quote_bid_ask(quote)
            analytics = option_analytics_for_symbol(option_symbol)
            event_risk, event_reason = classify_pe_event_risk(symbol, news_cache)
            week = float(row.get("input_1w") or 0)
            today = float(row.get("input_today") or 0)
            month = float(row.get("input_month") or 0)
            breakout = "RED" if today > 4 or week > 7 else "AMBER" if today > 2 or week > 4 or month > 10 else "GREEN"
            sell_limit = ceil_to_tick(
                premium * (1 + float(settings["price_markup_percent"]) / 100),
                0.05,
            ) if premium > 0 else 0
            candidates.append(
                {
                    "stock": symbol, "holding_qty": holding, "active_lot_size": lot_size,
                    "requested_lots": requested_lots, "cmp": cmp_value,
                    "target_ce_strike_zone": target, "selected_ce_strike": float(selected.get("strike") or 0),
                    "expiry": str(expiry), "option_symbol": option_symbol, "premium": premium,
                    "sell_limit_price": sell_limit, "delta": abs(float(analytics.get("delta") or 0)),
                    "sell_pop": float(analytics.get("sell_pop") or 0), "iv": float(analytics.get("iv_percent") or 0),
                    "oi": quote_oi(quote), "volume": int(float(quote.get("volume") or 0)),
                    "bid": bid, "ask": ask, "bid_ask_spread_percent": spread,
                    "event_risk": event_risk, "event_risk_reason": event_reason,
                    "breakout_risk": breakout, "contract_valid": True,
                    "has_active_position": symbol in active_underlyings, "core": row.get("core"),
                    "one_year_return": row.get("input_1y"), "week_return": week,
                }
            )
        except Exception as exc:
            candidates.append({"stock": symbol, "holding_qty": holding, "active_lot_size": lot_size, "requested_lots": requested_lots, "cmp": cmp_value, "contract_valid": False, "reject_reasons": [str(exc)]})
    return rank_ce_sell_candidates(candidates, settings)


def ce_sell_dashboard(force_refresh: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    cache_key = f"ce-sell-dashboard:{selected_kite_profile_name()}"
    if force_refresh:
        clear_app_cache((cache_key, "kite:positions", "kite:quote:"))
    return cached_value(cache_key, build_live_ce_sell_rankings, CE_SELL_DASHBOARD_CACHE_SECONDS)


def covered_ce_holding_source(kite: Any, underlying: str) -> dict[str, Any]:
    clean_underlying = str(underlying or "").strip().upper()
    kite_qty = 0
    kite_average_price = 0.0
    for holding in kite.holdings():
        if str(holding.get("tradingsymbol") or "").upper() == clean_underlying:
            kite_qty = int(float(holding.get("quantity") or 0))
            kite_average_price = float(holding.get("average_price") or 0)
            break
    income_growth = load_income_growth_holding_map().get(clean_underlying, {})
    income_growth_qty = int(float(income_growth.get("holding") or 0))
    if kite_qty >= income_growth_qty:
        effective_qty = kite_qty
        holding_source = f"Kite profile: {selected_kite_profile_name()}"
        average_price = kite_average_price
    else:
        effective_qty = income_growth_qty
        holding_source = "Income Growth holding record"
        average_price = 0.0
    return {
        "holding_qty": effective_qty,
        "holding_source": holding_source,
        "kite_holding_qty": kite_qty,
        "income_growth_holding_qty": income_growth_qty,
        "average_price": average_price,
    }


def ce_sell_order_snapshot(underlying: str) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    clean_underlying = str(underlying or "").strip().upper()
    if not clean_underlying:
        raise ValueError("Select an approved covered CE candidate first.")

    top, _, _ = ce_sell_dashboard(True)
    candidate = next(
        (item for item in top if str(item.get("stock") or "").upper() == clean_underlying),
        None,
    )
    if not candidate:
        raise PermissionError(
            f"{clean_underlying} is no longer an approved Top 3 covered CE candidate. Recalculate and review."
        )

    kite = kite_orders.kite_client()
    positions = kite.positions().get("net", [])
    active_underlyings = {
        underlying_for_symbol(str(item.get("tradingsymbol") or "").upper())
        for item in positions
        if int(float(item.get("quantity") or 0)) != 0
    }
    if clean_underlying in active_underlyings:
        raise PermissionError(
            f"{clean_underlying} already has an active option position. New covered CE SELL is blocked."
        )

    holding = covered_ce_holding_source(kite, clean_underlying)
    holding_qty = int(holding["holding_qty"])
    average_price = float(holding["average_price"])

    symbol = str(candidate.get("option_symbol") or "").upper()
    lot_size = int(float(candidate.get("active_lot_size") or 0))
    requested_lots = min(
        MAX_TOP3_CE_SELL_LOTS,
        int(float(candidate.get("lots_to_sell") or 0)),
    )
    covered_lots = holding_qty // lot_size if lot_size > 0 else 0
    lots_to_sell = min(MAX_TOP3_CE_SELL_LOTS, requested_lots, covered_lots)
    quantity = lots_to_sell * lot_size
    if lot_size <= 0 or quantity <= 0 or quantity > holding_qty:
        raise PermissionError(
            f"{clean_underlying} is not fully covered now. Effective holding {holding_qty}; "
            f"Kite profile {holding['kite_holding_qty']}; Income Growth {holding['income_growth_holding_qty']}; "
            f"lot size {lot_size}."
        )

    quote_key = f"NFO:{symbol}"
    try:
        quote = kite.quote([quote_key]).get(quote_key, {})
    except Exception as exc:
        raise RuntimeError(friendly_external_error(exc, f"{symbol} CE quote")) from exc
    ltp = quote_ltp(quote)
    if ltp <= 0:
        raise ValueError(f"Could not read fresh CE premium for {symbol}.")
    settings = load_ce_sell_settings()
    limit_price = ceil_to_tick(
        ltp * (1 + float(settings["price_markup_percent"]) / 100),
        0.05,
    )
    cmp_value = float(candidate.get("cmp") or 0)
    strike = float(candidate.get("selected_ce_strike") or 0)
    max_profit = limit_price * quantity
    covered_value = cmp_value * quantity
    return {
        "underlying": clean_underlying,
        "symbol": symbol,
        "holding_qty": holding_qty,
        "holding_source": holding["holding_source"],
        "kite_holding_qty": holding["kite_holding_qty"],
        "income_growth_holding_qty": holding["income_growth_holding_qty"],
        "average_price": average_price,
        "lot_size": lot_size,
        "covered_lots": covered_lots,
        "lots_to_sell": lots_to_sell,
        "quantity": quantity,
        "cmp": cmp_value,
        "strike": strike,
        "expiry": str(candidate.get("expiry") or ""),
        "ltp": ltp,
        "limit_price": limit_price,
        "markup_percent": float(settings["price_markup_percent"]),
        "max_profit": max_profit,
        "covered_value": covered_value,
        "premium_yield_percent": max_profit / covered_value * 100 if covered_value > 0 else 0,
        "otm_percent": float(candidate.get("otm_percent") or 0),
        "score": float(candidate.get("final_ce_score") or 0),
        "event_risk": str(candidate.get("event_risk") or "N/A"),
        "breakout_risk": str(candidate.get("breakout_risk") or "N/A"),
    }


def place_approved_ce_sell_order(underlying: str) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Covered CE order refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    snapshot = ce_sell_order_snapshot(underlying)
    kite = kite_orders.kite_client()
    order = {
        "variety": "regular",
        "exchange": "NFO",
        "tradingsymbol": snapshot["symbol"],
        "transaction_type": "SELL",
        "quantity": snapshot["quantity"],
        "product": "NRML",
        "order_type": "LIMIT",
        "price": snapshot["limit_price"],
        "validity": "DAY",
        "tag": "TOP3_CE",
        "autoslice": True,
    }
    try:
        order_id = place_order_allowing_autoslice(kite, order)
    except Exception as exc:
        detail = friendly_external_error(exc, f"{snapshot['symbol']} CE SELL")
        if int(snapshot.get("kite_holding_qty") or 0) < int(snapshot.get("quantity") or 0):
            detail = (
                f"{detail} Note: selected Kite profile has only "
                f"{snapshot['kite_holding_qty']} shares, while this order uses "
                f"{snapshot['holding_qty']} shares from {snapshot['holding_source']}. "
                "Zerodha may reject or margin this as uncovered in this profile."
            )
        raise RuntimeError(detail) from exc
    invalidate_kite_trade_cache()
    clear_app_cache((f"ce-sell-dashboard:{selected_kite_profile_name()}",))
    return {
        "tradingsymbol": snapshot["symbol"],
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"SELL covered CE {snapshot['quantity']} qty at LIMIT {snapshot['limit_price']:.2f}. "
            f"{float(snapshot.get('markup_percent') or option_sell_markup_percent_setting()):.2f}% above fresh LTP {snapshot['ltp']:.2f}; "
            f"effective holding {snapshot['holding_qty']} shares "
            f"from {snapshot['holding_source']}."
        ),
    }


def income_growth_pe_sell_candidates(rows: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        try:
            symbol = str(row.get("symbol") or "").upper()
            cmp_value = float(row.get("cmp") or 0)
            put_strike = float(row.get("input_put_strike") or 0)
            lot_size = int(float(row.get("lot_size") or row.get("input_lot_size") or 0))
            pe_value = row.get("input_pe")
            pct_52w = row.get("input_52w")
            month = float(row.get("input_month") or 0)
            week_1 = float(row.get("input_1w") or 0)
            today = float(row.get("input_today") or 0)
            if not symbol or cmp_value <= 0 or put_strike <= 0 or lot_size <= 0:
                continue
            put_down_pct = ((cmp_value - put_strike) / cmp_value) * 100
            cash_required = put_strike * lot_size * 0.90
            cash_score = 25 if cash_required <= 500000 else 20 if cash_required <= 800000 else 12 if cash_required <= 1000000 else 0
            buffer_score = 25 if put_down_pct >= 10 else 20 if put_down_pct >= 8 else 12 if put_down_pct >= 5 else 0
            valuation_score = 12
            if isinstance(pe_value, (int, float)):
                valuation_score = 20 if pe_value <= 30 else 15 if pe_value <= 50 else 8 if pe_value <= 70 else 2
            week52_score = 12
            if isinstance(pct_52w, (int, float)):
                week52_score = 20 if pct_52w <= -20 else 15 if pct_52w <= -10 else 8 if pct_52w <= -5 else 2
            trend_score = 15
            if month < -12 or week_1 < -8:
                trend_score = 5
            elif -8 <= month <= 8 and -5 <= week_1 <= 4 and today <= 2:
                trend_score = 20
            elif today > 4 or week_1 > 7:
                trend_score = 8
            score = min(100, cash_score + buffer_score + valuation_score + week52_score + trend_score)
            if score >= 80:
                color, label = "green", "GOOD PE SELL"
            elif score >= 65:
                color, label = "yellow", "OK PE SELL"
            else:
                color, label = "red", "WAIT"
            reasons = [
                f"PUT {put_strike:.0f} is {put_down_pct:.1f}% below CMP",
                f"cash req ~{format_buy_amount(cash_required)}",
                f"PE {fmt_number(pe_value, 1)}",
                f"52W {fmt_number(pct_52w, 1)}%",
                f"1W {week_1:.1f}%, today {today:.1f}%",
            ]
            candidates.append(
                {
                    "symbol": symbol,
                    "put_strike": put_strike,
                    "cash_required": cash_required,
                    "put_down_pct": put_down_pct,
                    "pe": pe_value,
                    "score": score,
                    "label": label,
                    "color": color,
                    "reasons": reasons,
                }
            )
        except Exception:
            continue
    candidates.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return candidates[:limit]


def income_growth_equity_snapshot(symbol: str) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    clean_symbol = normalize_income_growth_symbol(symbol)
    stored = load_income_growth_holding_map()
    if clean_symbol not in stored:
        raise ValueError(f"{clean_symbol} is not an Income Growth stock.")
    kite = kite_orders.kite_client()
    quote_key = f"NSE:{clean_symbol}"
    try:
        quote = kite.quote([quote_key]).get(quote_key, {})
        holdings = kite.holdings()
    except Exception as exc:
        raise RuntimeError(friendly_external_error(exc, f"{clean_symbol} equity quote")) from exc
    ltp = quote_ltp(quote)
    holding = next(
        (
            item
            for item in holdings
            if str(item.get("exchange") or "NSE").upper() == "NSE"
            and str(item.get("tradingsymbol") or "").upper() == clean_symbol
        ),
        {},
    )
    actual_quantity = int(float(holding.get("quantity") or 0))
    average_price = float(holding.get("average_price") or 0)
    if average_price <= 0:
        investing = next(
            (
                item
                for item in INVESTING_HOLDINGS
                if normalize_income_growth_symbol(item.get("code")) == clean_symbol
            ),
            {},
        )
        average_price = float(investing.get("avg_price") or 0)
    if ltp <= 0:
        ltp = float(holding.get("last_price") or stored[clean_symbol].get("cmp") or 0)
    pnl = (ltp - average_price) * actual_quantity if ltp > 0 and average_price > 0 else None
    return {
        "symbol": clean_symbol,
        "quantity": actual_quantity,
        "average_price": average_price,
        "ltp": ltp,
        "pnl": pnl,
        "return_pct": (pnl / (average_price * actual_quantity) * 100)
        if pnl is not None and average_price > 0 and actual_quantity > 0
        else None,
    }


def place_income_growth_equity_order(symbol: str, side: str, quantity: Any) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError(
            'Equity order refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.'
        )
    clean_symbol = normalize_income_growth_symbol(symbol)
    clean_side = str(side or "").strip().upper()
    if clean_side not in {"BUY", "SELL"}:
        raise ValueError("Select BUY or SELL before placing the equity order.")
    try:
        clean_quantity = int(float(quantity))
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a valid whole-number equity quantity.") from exc
    if clean_quantity <= 0:
        raise ValueError("Equity quantity must be greater than zero.")
    snapshot = income_growth_equity_snapshot(clean_symbol)
    if clean_side == "SELL" and clean_quantity > int(snapshot.get("quantity") or 0):
        raise ValueError(
            f"SELL quantity {clean_quantity} exceeds current Kite holding "
            f"{int(snapshot.get('quantity') or 0)} for {clean_symbol}."
        )
    ltp = float(snapshot.get("ltp") or 0)
    if ltp <= 0:
        raise ValueError(f"Could not read current LTP for {clean_symbol}.")
    price = ceil_to_tick(ltp, 0.05) if clean_side == "BUY" else floor_to_tick(ltp, 0.05)
    order = {
        "variety": "regular",
        "exchange": "NSE",
        "tradingsymbol": clean_symbol,
        "transaction_type": clean_side,
        "quantity": clean_quantity,
        "product": "CNC",
        "order_type": "LIMIT",
        "price": price,
        "validity": "DAY",
        "tag": "INC_GROWTH_EQ",
    }
    kite = kite_orders.kite_client()
    order_id = kite_orders.place_order(kite, order)
    invalidate_kite_trade_cache()
    return {
        "tradingsymbol": clean_symbol,
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"{clean_side} {clean_quantity} equity share(s) at LIMIT {price:.2f}; "
            f"fresh LTP {ltp:.2f}. Active Kite profile: {selected_kite_profile_name()}."
        ),
    }


def equity_holdings_snapshot() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    kite = kite_orders.kite_client()
    try:
        holdings = kite.holdings()
        quote_keys = [
            f"{str(item.get('exchange') or 'NSE').upper()}:{str(item.get('tradingsymbol') or '').upper()}"
            for item in holdings
            if str(item.get("tradingsymbol") or "").strip()
        ]
        quotes = kite.quote(quote_keys) if quote_keys else {}
    except Exception as exc:
        raise RuntimeError(friendly_external_error(exc, "Kite equity holdings")) from exc
    rows: list[dict[str, Any]] = []
    for holding in holdings:
        symbol = str(holding.get("tradingsymbol") or "").upper()
        exchange = str(holding.get("exchange") or "NSE").upper()
        if not symbol:
            continue
        quantity = int(float(holding.get("quantity") or 0)) + int(
            float(holding.get("t1_quantity") or 0)
        )
        average_price = float(holding.get("average_price") or 0)
        quote = quotes.get(f"{exchange}:{symbol}", {})
        ltp = quote_ltp(quote) or float(holding.get("last_price") or 0)
        close_price = float(
            (quote.get("ohlc") or {}).get("close")
            or holding.get("close_price")
            or 0
        )
        invested = average_price * quantity
        market_value = ltp * quantity
        pnl = market_value - invested
        net_change_pct = (pnl / invested * 100) if invested else None
        day_change = ltp - close_price if ltp > 0 and close_price > 0 else None
        day_change_pct = (
            (day_change / close_price * 100)
            if day_change is not None and close_price > 0
            else None
        )
        day_pnl = day_change * quantity if day_change is not None else None
        rows.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "quantity": quantity,
                "average_price": average_price,
                "ltp": ltp,
                "invested": invested,
                "market_value": market_value,
                "pnl": pnl,
                "net_change_pct": net_change_pct,
                "day_change": day_change,
                "day_change_pct": day_change_pct,
                "day_pnl": day_pnl,
            }
        )
    rows.sort(key=lambda item: float(item.get("market_value") or 0), reverse=True)
    invested_total = sum(float(row.get("invested") or 0) for row in rows)
    market_total = sum(float(row.get("market_value") or 0) for row in rows)
    pnl_total = sum(float(row.get("pnl") or 0) for row in rows)
    day_pnl_total = sum(float(row.get("day_pnl") or 0) for row in rows)
    summary = {
        "count": len(rows),
        "invested": invested_total,
        "market_value": market_total,
        "pnl": pnl_total,
        "net_change_pct": (pnl_total / invested_total * 100) if invested_total else None,
        "day_pnl": day_pnl_total,
        "day_change_pct": (
            day_pnl_total / (market_total - day_pnl_total) * 100
            if market_total - day_pnl_total
            else None
        ),
        "as_of": datetime.now().strftime("%d %b %Y %H:%M:%S"),
    }
    return rows, summary


def equity_holding_snapshot(symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    clean_symbol = str(symbol or "").strip().upper()
    clean_exchange = str(exchange or "NSE").strip().upper()
    rows, _ = equity_holdings_snapshot()
    row = next(
        (
            item
            for item in rows
            if item["symbol"] == clean_symbol and item["exchange"] == clean_exchange
        ),
        None,
    )
    if row is None:
        raise ValueError(f"{clean_exchange}:{clean_symbol} is not in the selected Kite profile holdings.")
    return row


def place_equity_holding_order(
    symbol: str,
    exchange: str,
    side: str,
    quantity: Any,
    limit_price: Any,
) -> dict[str, Any]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if os.getenv("KITE_CONFIRM_LIVE_ORDER") != "YES":
        raise PermissionError('Equity order refused. Set KITE_CONFIRM_LIVE_ORDER to "YES" first.')
    clean_side = str(side or "").strip().upper()
    if clean_side not in {"BUY", "SELL"}:
        raise ValueError("Select BUY or SELL before placing the equity order.")
    try:
        clean_quantity = int(float(quantity))
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a valid whole-number equity quantity.") from exc
    if clean_quantity <= 0:
        raise ValueError("Equity quantity must be greater than zero.")
    try:
        entered_price = float(limit_price)
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a valid limit price.") from exc
    if entered_price <= 0:
        raise ValueError("Limit price must be greater than zero. Market orders are not allowed.")
    snapshot = equity_holding_snapshot(symbol, exchange)
    if clean_side == "SELL" and clean_quantity > int(snapshot.get("quantity") or 0):
        raise ValueError(
            f"SELL quantity {clean_quantity} exceeds current holding "
            f"{int(snapshot.get('quantity') or 0)} for {snapshot['symbol']}."
        )
    price = max(round(entered_price / 0.05) * 0.05, 0.05)
    order = {
        "variety": "regular",
        "exchange": snapshot["exchange"],
        "tradingsymbol": snapshot["symbol"],
        "transaction_type": clean_side,
        "quantity": clean_quantity,
        "product": "CNC",
        "order_type": "LIMIT",
        "price": round(price, 2),
        "validity": "DAY",
        "tag": "EQUITY_DESK",
    }
    kite = kite_orders.kite_client()
    order_id = kite_orders.place_order(kite, order)
    invalidate_kite_trade_cache()
    ltp = float(snapshot.get("ltp") or 0)
    price_gap = ((price - ltp) / ltp * 100) if ltp else 0
    return {
        "tradingsymbol": snapshot["symbol"],
        "status": "LIVE_SENT",
        "order_id": order_id,
        "detail": (
            f"{clean_side} {clean_quantity} {snapshot['exchange']} equity share(s) at LIMIT "
            f"{price:.2f}; fresh LTP {ltp:.2f}; limit {price_gap:+.2f}% vs LTP. "
            f"Active Kite profile: {selected_kite_profile_name()}."
        ),
    }


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
                for item in cached_kite_instruments(kite, "NSE")
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
    quote = cached_kite_quote(kite, [f"NSE:{clean_symbol}"]).get(f"NSE:{clean_symbol}", {})
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
    invalidate_kite_trade_cache()
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
        for holding in cached_value("kite:holdings", kite.holdings, KITE_READ_CACHE_SECONDS)
    }
    positions_by_symbol: dict[str, dict[str, Any]] = {}
    try:
        for position in cached_kite_positions(kite):
            symbol = str(position.get("tradingsymbol") or "").upper()
            if symbol in all_symbols and str(position.get("exchange") or "").upper() == "NSE":
                positions_by_symbol[symbol] = position
    except Exception:
        positions_by_symbol = {}
    quote_keys = [f"NSE:{symbol}" for symbol in symbols]
    quotes = cached_kite_quote(kite, quote_keys)
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
    quote = cached_kite_quote(kite, [f"NSE:{clean_symbol}"]).get(f"NSE:{clean_symbol}", {})
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
    invalidate_kite_trade_cache()
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
        if not row["quantity"]:
            lots_text = normalized.get("lots", "")
            lot_size_text = normalized.get("lot_size", "")
            if lots_text and lot_size_text:
                try:
                    row["quantity"] = str(int(float(lots_text) * float(lot_size_text)))
                except ValueError:
                    raise ValueError("CSV lots and lot_size must be numeric.") from None
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
    required_headers = {"tradingsymbol", "transaction_type"}
    for index, line in enumerate(lines):
        if "," not in line:
            continue
        header = {canonical_field_name(item) for item in line.split(",")}
        has_quantity = "quantity" in header or {"lots", "lot_size"}.issubset(header)
        if not required_headers.issubset(header) or not has_quantity:
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


def normalize_kite_csv_input(text: str) -> str:
    """Accept a plain CSV or GPT text that contains a Kite CSV block."""
    clean = text.strip()
    if not clean:
        return ""
    try:
        return canonicalize_kite_csv(clean).rstrip() + "\n"
    except Exception:
        return extract_csv_from_text(clean)


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
        payload_preview = json.dumps(payload, indent=2)[:2000]
        raise RuntimeError(
            "OpenAI returned an empty response.\n\n"
            f"Response ID: {payload.get('id') or 'N/A'}\n"
            f"Model: {payload.get('model') or body['model']}\n\n"
            f"OpenAI raw output preview:\n{payload_preview}"
        )
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


def cap_trading_option_rows_by_otm(
    rows: list[dict[str, str]],
    kite: Any,
    max_otm_percent: float = MAX_TRADING_ORDER_OTM_PERCENT,
) -> tuple[list[dict[str, str]], dict[int, dict[str, Any]]]:
    adjusted_rows = [dict(row) for row in rows]
    parsed_rows: list[tuple[int, dict[str, Any]]] = []
    for index, row in enumerate(adjusted_rows):
        exchange = str(row.get("exchange") or "NFO").strip().upper()
        symbol = str(row.get("tradingsymbol") or row.get("symbol") or "").strip().upper()
        parts = option_symbol_parts(symbol)
        if exchange == "NFO" and parts:
            parsed_rows.append((index, parts))
    if not parsed_rows:
        return adjusted_rows, {}

    spot_keys = sorted({f"NSE:{parts['underlying']}" for _, parts in parsed_rows})
    spot_quotes = cached_kite_quote(kite, spot_keys, ttl_seconds=5)
    instruments = cached_kite_instruments(kite, "NFO")
    instruments_by_contract: dict[tuple[str, str, date], list[dict[str, Any]]] = {}
    for instrument in instruments:
        underlying = str(instrument.get("name") or "").strip().upper()
        option_type = str(instrument.get("instrument_type") or "").strip().upper()
        expiry = instrument.get("expiry")
        if underlying and option_type in {"CE", "PE"} and isinstance(expiry, date):
            instruments_by_contract.setdefault((underlying, option_type, expiry), []).append(instrument)

    adjustments: dict[int, dict[str, Any]] = {}
    for index, parts in parsed_rows:
        row = adjusted_rows[index]
        original_symbol = str(row.get("tradingsymbol") or row.get("symbol") or "").strip().upper()
        underlying = str(parts["underlying"]).upper()
        option_type = str(parts["option_type"]).upper()
        strike = float(parts["strike"])
        spot = quote_ltp(spot_quotes.get(f"NSE:{underlying}", {}))
        if spot <= 0:
            raise ValueError(f"Could not read {underlying} spot price to validate the 12.5% OTM cap.")
        otm_percent = (
            ((strike - spot) / spot) * 100
            if option_type == "CE"
            else ((spot - strike) / spot) * 100
        )
        if otm_percent <= max_otm_percent:
            adjustments[index] = {
                "original_symbol": original_symbol,
                "spot": spot,
                "strike": strike,
                "otm_percent": otm_percent,
                "adjusted": False,
            }
            continue

        expiry = expiry_date_for_parts(parts)
        contracts = instruments_by_contract.get((underlying, option_type, expiry), [])
        if option_type == "CE":
            strike_limit = spot * (1 + max_otm_percent / 100)
            valid = [
                item
                for item in contracts
                if spot < float(item.get("strike") or 0) <= strike_limit
            ]
            selected = max(valid, key=lambda item: float(item.get("strike") or 0)) if valid else None
        else:
            strike_limit = spot * (1 - max_otm_percent / 100)
            valid = [
                item
                for item in contracts
                if strike_limit <= float(item.get("strike") or 0) < spot
            ]
            selected = min(valid, key=lambda item: float(item.get("strike") or 0)) if valid else None
        if not selected:
            raise ValueError(
                f"{original_symbol} is {otm_percent:.2f}% OTM, above the {max_otm_percent:.1f}% cap, "
                f"and no active {option_type} contract within the cap was found for the same expiry."
            )

        selected_symbol = str(selected.get("tradingsymbol") or "").strip().upper()
        selected_strike = float(selected.get("strike") or 0)
        selected_otm = (
            ((selected_strike - spot) / spot) * 100
            if option_type == "CE"
            else ((spot - selected_strike) / spot) * 100
        )
        row["tradingsymbol"] = selected_symbol
        if "symbol" in row:
            row["symbol"] = selected_symbol
        adjustments[index] = {
            "original_symbol": original_symbol,
            "spot": spot,
            "strike": selected_strike,
            "otm_percent": selected_otm,
            "adjusted": True,
        }
    return adjusted_rows, adjustments


def build_orders(
    rows: list[dict[str, str]], no_ltp_price: bool, keep_existing_orders: bool
) -> list[dict[str, Any]]:
    has_option_rows = any(
        str(row.get("exchange") or "NFO").strip().upper() == "NFO"
        and option_symbol_parts(str(row.get("tradingsymbol") or row.get("symbol") or "").strip().upper())
        for row in rows
    )
    kite = kite_orders.kite_client() if has_option_rows else None
    working_rows, strike_adjustments = (
        cap_trading_option_rows_by_otm(rows, kite) if kite is not None else ([dict(row) for row in rows], {})
    )
    base_args = default_args(no_ltp_price, keep_existing_orders)
    row_args = [kite_orders.args_for_csv_row(base_args, row) for row in working_rows]
    needs_kite = any(not item.no_ltp_price for item in row_args)
    kite = kite or (kite_orders.kite_client() if needs_kite else None)
    orders: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, item in enumerate(row_args, start=1):
        symbol = str(getattr(item, "symbol", "") or working_rows[index - 1].get("tradingsymbol", "")).upper()
        exchange = str(getattr(item, "exchange", "") or working_rows[index - 1].get("exchange", "NFO")).upper()
        try:
            order = kite_orders.build_order(item, kite)
            adjustment = strike_adjustments.get(index - 1)
            if adjustment:
                order["spot"] = round(float(adjustment["spot"]), 2)
                order["strike"] = round(float(adjustment["strike"]), 2)
                order["otm_percent"] = round(float(adjustment["otm_percent"]), 2)
                if adjustment["adjusted"]:
                    order["adjusted_from_symbol"] = adjustment["original_symbol"]
            orders.append(order)
        except KeyError as exc:
            missing_key = str(exc).strip("'\"") or f"{exchange}:{symbol}"
            errors.append(
                f"Row {index}: Kite did not return LTP for {missing_key}. "
                f"Verify the contract exists and is active, or fix/remove {symbol}. "
                "If you want to use manual CSV prices, turn on 'Use CSV/manual price only' and provide a positive LIMIT price."
            )
        except SystemExit as exc:
            detail = str(exc) or "Order build stopped."
            errors.append(f"Row {index}: {symbol} could not be previewed. {detail}")
        except Exception as exc:
            errors.append(f"Row {index}: {symbol} could not be previewed. {exc}")
    if errors:
        raise ValueError("Order preview could not be completed:\n" + "\n".join(errors))

    option_quote_keys: list[str] = []
    for order in orders:
        symbol = str(order.get("tradingsymbol") or "").strip().upper()
        exchange = str(order.get("exchange") or "NFO").strip().upper()
        if exchange == "NFO" and option_symbol_parts(symbol):
            option_quote_keys.append(f"{exchange}:{symbol}")

    if option_quote_keys:
        try:
            kite = kite or kite_orders.kite_client()
            option_quotes = cached_kite_quote(kite, option_quote_keys, ttl_seconds=5)
        except Exception as exc:
            missing_price_symbols = [
                str(order.get("tradingsymbol") or "")
                for row, order in zip(working_rows, orders)
                if float(row.get("price") or 0) <= 0
            ]
            if missing_price_symbols:
                raise ValueError(
                    "Could not load fresh option LTP for zero-price order(s): "
                    f"{', '.join(missing_price_symbols)}. {exc}"
                ) from exc
            option_quotes = {}

        for row, item, order in zip(working_rows, row_args, orders):
            symbol = str(order.get("tradingsymbol") or "").strip().upper()
            exchange = str(order.get("exchange") or "NFO").strip().upper()
            quote = option_quotes.get(f"{exchange}:{symbol}", {})
            ltp = quote_ltp(quote)
            source_price = float(row.get("price") or 0)
            transaction_type = str(order.get("transaction_type") or "").upper()
            if transaction_type == "SELL":
                if ltp <= 0:
                    raise ValueError(
                        f"Could not read fresh option LTP for {exchange}:{symbol}. "
                        "SELL limit price could not be calculated."
                    )
                tick_size = float(getattr(item, "tick_size", 0.05) or 0.05)
                markup_percent = option_sell_markup_percent_setting()
                order["price"] = ceil_to_tick(ltp * (1 + markup_percent / 100), tick_size)
                order["price_basis"] = "fresh_ltp_plus_markup"
                order["price_markup_percent"] = markup_percent
            elif source_price <= 0:
                if ltp <= 0:
                    raise ValueError(
                        f"Could not read fresh option LTP for {exchange}:{symbol}. "
                        "The zero CSV price was not replaced."
                    )
                tick_size = float(getattr(item, "tick_size", 0.05) or 0.05)
                order["price"] = ceil_to_tick(ltp, tick_size)
                order["price_basis"] = "fresh_ltp"
            if ltp > 0:
                order["ltp"] = round(ltp, 2)
            quantity = abs(int(order.get("quantity") or 0))
            if transaction_type == "SELL":
                order["max_gain"] = round(float(order.get("price") or 0) * quantity, 2)
    return orders


def load_default_trade_preview(state: PageState) -> PageState:
    if not DEFAULT_CSV_PATH.exists():
        state.message = f"Load today's CSV file: {DEFAULT_CSV_PATH.name}"
        return state
    state.csv_path = str(DEFAULT_CSV_PATH)
    state.csv_text = DEFAULT_CSV_PATH.read_text(encoding="utf-8-sig")
    state.rows, state.csv_text = load_rows(state.csv_path, state.csv_text)
    validate_kite_order_rows(state.rows)
    state.orders, state.console_log = call_with_console(
        build_orders,
        state.rows,
        state.no_ltp_price,
        state.keep_existing_orders,
    )
    state.trade_validations = validate_trade_orders(state.orders)
    state.selected_indexes = default_selected_order_indexes(
        state.orders,
        state.trade_validations,
    )
    state.message = f"Loaded and previewed today's CSV with {len(state.orders)} order(s)."
    return state


def load_ce_sell_dashboard(state: PageState, force_refresh: bool = False) -> None:
    (
        state.ce_sell_top,
        state.ce_sell_watch,
        state.ce_sell_avoid,
    ), ce_log = call_with_console(ce_sell_dashboard, force_refresh)
    state.console_log = f"{state.console_log}{ce_log}"


def load_default_csv_research(state: PageState) -> PageState:
    if not DEFAULT_CSV_PATH.exists():
        state.message = f"Load today's CSV file: {DEFAULT_CSV_PATH.name}"
        return state
    state.csv_path = str(DEFAULT_CSV_PATH)
    state.csv_text = DEFAULT_CSV_PATH.read_text(encoding="utf-8-sig")
    state.research_rows, state.console_log = call_with_console(
        research_csv_symbols,
        state.csv_text,
        state.csv_path,
    )
    state.message = (
        f"Loaded today's CSV research for {len(state.research_rows)} symbol(s)."
    )
    return state


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


KITE_PLACE_ORDER_FIELDS = {
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
    "market_protection",
    "trigger_price",
}


def kite_order_payload(order: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in order.items()
        if key in KITE_PLACE_ORDER_FIELDS and value not in {None, ""}
    }


def modify_or_place_order_with_new_fallback(kite: Any, order: dict[str, Any]) -> tuple[str, str]:
    order = kite_order_payload(order)
    similar_orders = kite_orders.find_similar_open_orders(kite, order)
    if not similar_orders:
        order_id = place_order_allowing_autoslice(kite, order)
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
    active_position_keys = active_position_option_block_keys(True, True)
    active_order_keys = active_open_order_option_block_keys(True, True)
    duplicate_messages: list[str] = []
    for order in orders:
        symbol = str(order.get("tradingsymbol") or "").strip().upper()
        side = str(order.get("transaction_type") or "").strip().upper()
        if order_has_active_position(order, active_position_keys):
            duplicate_messages.append(
                f"{symbol} {side}: an active position already exists for this underlying and option side"
            )
        if order_has_open_duplicate(order, active_order_keys):
            duplicate_messages.append(
                f"{symbol} {side}: the same open/pending Kite order already exists"
            )
    if duplicate_messages:
        raise ValueError(
            "Duplicate order protection blocked live execution:\n"
            + "\n".join(dict.fromkeys(duplicate_messages))
        )
    kite_orders.attach_position_info(kite, orders)
    results: list[dict[str, Any]] = []
    for order in orders:
        try:
            payload = kite_order_payload(order)
            if keep_existing_orders:
                order_id = kite_orders.place_order(kite, payload)
                action = "placed_new_requested"
            else:
                order_id, action = modify_or_place_order_with_new_fallback(kite, payload)
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
    if any(item.get("status") == "LIVE_SENT" for item in results):
        invalidate_kite_trade_cache()
    return orders, results


CANCELLABLE_ORDER_STATUSES = {
    "OPEN",
    "TRIGGER PENDING",
    "VALIDATION PENDING",
    "PUT ORDER REQ RECEIVED",
}


def order_completed_quantity(order: dict[str, Any]) -> int:
    for key in ("filled_quantity", "quantity"):
        try:
            quantity = int(float(order.get(key) or 0))
            if quantity > 0:
                return quantity
        except (TypeError, ValueError):
            continue
    return 0


def order_average_fill_price(order: dict[str, Any]) -> float:
    for key in ("average_price", "price"):
        try:
            price = float(order.get(key) or 0)
            if price > 0:
                return price
        except (TypeError, ValueError):
            continue
    return 0.0


def order_sort_value(order: dict[str, Any]) -> str:
    for key in ("order_timestamp", "exchange_timestamp", "exchange_update_timestamp"):
        value = order.get(key)
        if value:
            return str(value)
    return str(order.get("order_id") or "")


def completed_close_pnl_by_order_id(
    orders: list[dict[str, Any]], positions: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Estimate realised P&L when a completed BUY closes an earlier sold option."""
    current_qty_by_symbol: dict[str, int] = {}
    for position in positions:
        symbol = str(position.get("tradingsymbol") or "").upper()
        if not symbol:
            continue
        try:
            current_qty_by_symbol[symbol] = int(float(position.get("quantity") or 0))
        except (TypeError, ValueError):
            current_qty_by_symbol[symbol] = 0

    sell_pool: dict[str, dict[str, float]] = {}
    close_pnl: dict[str, dict[str, Any]] = {}
    completed = [
        order
        for order in orders
        if str(order.get("status") or "").upper() == "COMPLETE"
        and option_symbol_parts(str(order.get("tradingsymbol") or "").upper())
    ]
    for order in sorted(completed, key=order_sort_value):
        symbol = str(order.get("tradingsymbol") or "").upper()
        side = str(order.get("transaction_type") or "").upper()
        quantity = order_completed_quantity(order)
        price = order_average_fill_price(order)
        if quantity <= 0 or price <= 0:
            continue
        pool = sell_pool.setdefault(symbol, {"qty": 0.0, "value": 0.0})
        if side == "SELL":
            pool["qty"] += quantity
            pool["value"] += price * quantity
            continue
        if side != "BUY" or pool["qty"] <= 0:
            continue

        close_qty = min(float(quantity), pool["qty"])
        sell_avg = pool["value"] / pool["qty"] if pool["qty"] else 0.0
        pnl = (sell_avg - price) * close_qty
        pool["qty"] -= close_qty
        pool["value"] = max(0.0, pool["value"] - (sell_avg * close_qty))
        if pool["qty"] <= 0.0001:
            pool["qty"] = 0.0
            pool["value"] = 0.0

        current_qty = current_qty_by_symbol.get(symbol, 0)
        if current_qty < 0:
            portfolio_note = f"Current short remains {current_qty}."
        elif current_qty == 0:
            portfolio_note = "No current open quantity remains."
        else:
            portfolio_note = f"Current net quantity is {current_qty}."
        close_pnl[str(order.get("order_id") or "")] = {
            "pnl": pnl,
            "close_qty": int(close_qty),
            "sell_avg": sell_avg,
            "buy_avg": price,
            "note": portfolio_note,
        }
    return close_pnl


def sync_booked_pnl_from_kite_orders(
    orders: list[dict[str, Any]], positions: list[dict[str, Any]]
) -> int:
    close_pnl_by_order = completed_close_pnl_by_order_id(orders, positions)
    if not close_pnl_by_order:
        return 0
    by_order_id = {str(order.get("order_id") or ""): order for order in orders}
    records: list[dict[str, Any]] = []
    for order_id, detail in close_pnl_by_order.items():
        order = by_order_id.get(order_id) or {}
        symbol = str(order.get("tradingsymbol") or "").upper()
        if not symbol:
            continue
        booked_date = parse_order_date(order)
        records.append(
            {
                "booked_date": booked_date.isoformat(),
                "month_key": booked_date.strftime("%Y-%m"),
                "source": booked_pnl_source(symbol),
                "tradingsymbol": symbol,
                "order_id": order_id,
                "close_qty": detail.get("close_qty") or 0,
                "sell_avg": detail.get("sell_avg") or 0,
                "buy_avg": detail.get("buy_avg") or 0,
                "pnl": detail.get("pnl") or 0,
                "note": detail.get("note") or "",
            }
        )
    return save_booked_pnl_records(records)


def kite_order_book(force_refresh: bool = False) -> list[dict[str, Any]]:
    if kite_orders is None:
        raise RuntimeError(f"Could not import kite_place_order.py: {IMPORT_ERROR}")
    if force_refresh:
        clear_app_cache(("kite:orders", "kite:positions", "kite:quote"))
    kite = kite_orders.kite_client()
    rows: list[dict[str, Any]] = []
    orders = list(reversed(cached_kite_orders(kite)))
    positions = cached_kite_positions(kite)
    position_by_symbol: dict[str, dict[str, Any]] = {}
    for position in positions:
        symbol = str(position.get("tradingsymbol") or "").upper()
        if not symbol:
            continue
        try:
            quantity = int(float(position.get("quantity") or 0))
        except (TypeError, ValueError):
            quantity = 0
        if quantity == 0:
            continue
        position_by_symbol[symbol] = position
    saved_booked_count = sync_booked_pnl_from_kite_orders(orders, positions)
    close_pnl_by_order = completed_close_pnl_by_order_id(orders, positions)
    quote_keys = sorted(
        {
            f"{str(order.get('exchange') or '').upper()}:{str(order.get('tradingsymbol') or '').upper()}"
            for order in orders
            if order.get("exchange") and order.get("tradingsymbol")
        }
    )
    quotes = cached_kite_quote(kite, quote_keys) if quote_keys else {}
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
        position = position_by_symbol.get(symbol.upper()) or {}
        position_avg_price = None
        position_pnl = None
        position_qty = None
        if position:
            position_qty = int(float(position.get("quantity") or 0))
            position_avg_price = float(position.get("average_price") or 0) or None
            position_ltp = float(ltp or position.get("last_price") or position.get("ltp") or 0)
            if position_avg_price and position_ltp and position_qty:
                position_pnl = option_position_pnl(position_qty, position_avg_price, position_ltp)
            elif position.get("pnl") is not None:
                position_pnl = float(position.get("pnl") or 0)
        close_pnl = close_pnl_by_order.get(str(order.get("order_id") or ""))
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
                "position_avg_price": position_avg_price,
                "position_pnl": position_pnl,
                "position_qty": position_qty,
                "close_pnl": close_pnl.get("pnl") if close_pnl else None,
                "close_pnl_detail": close_pnl,
                "booked_pnl_saved": bool(close_pnl) and saved_booked_count >= 0,
                "status": status,
                "status_message": str(order.get("status_message") or ""),
                "is_cancellable": status in CANCELLABLE_ORDER_STATUSES,
            }
        )
    return rows


def order_action_suggestion(order: dict[str, Any]) -> dict[str, Any]:
    status = str(order.get("status") or "").upper()
    side = str(order.get("transaction_type") or "").upper()
    symbol = str(order.get("tradingsymbol") or "").upper()
    option_type = "PUT" if symbol.endswith("PE") else "CALL" if symbol.endswith("CE") else "OPTION"
    ltp = order.get("ltp")
    price = order.get("price")
    try:
        ltp_value = float(ltp or 0)
        price_value = float(price or 0)
    except (TypeError, ValueError):
        ltp_value = 0.0
        price_value = 0.0
    if status not in CANCELLABLE_ORDER_STATUSES:
        return {
            "score": 0,
            "grade": "DONE",
            "class": "validation-neutral",
            "text": "Order is not open; no price action needed.",
        }
    if ltp_value <= 0 or price_value <= 0:
        return {
            "score": 35,
            "grade": "CHECK",
            "class": "validation-yellow",
            "text": "LTP unavailable; refresh orders before modifying price.",
        }
    diff_pct = ((price_value - ltp_value) / ltp_value) * 100
    abs_diff = abs(diff_pct)
    if side == "SELL":
        if diff_pct >= 25:
            score, grade, css = 45, "LOWER", "validation-yellow"
            text = f"SELL {option_type}: ask is {diff_pct:.1f}% above LTP. Lower toward LTP +5-10% if fill is needed."
        elif diff_pct >= 8:
            score, grade, css = 72, "WAIT", "validation-green"
            text = f"SELL {option_type}: premium ask is above market. Wait, or lower 1-2 ticks near close."
        elif diff_pct >= 0:
            score, grade, css = 88, "GOOD", "validation-green"
            text = f"SELL {option_type}: price is near LTP. Good fill balance."
        else:
            score, grade, css = 62, "RAISE", "validation-yellow"
            text = f"SELL {option_type}: price is below LTP. Raise toward LTP to avoid selling cheap."
    elif side == "BUY":
        if diff_pct <= -20:
            score, grade, css = 42, "RAISE", "validation-yellow"
            text = f"BUY {option_type}: bid is far below LTP. Raise price if exit is important."
        elif diff_pct <= -5:
            score, grade, css = 64, "RAISE", "validation-yellow"
            text = f"BUY {option_type}: bargain bid. Raise closer to LTP if risk is increasing."
        elif diff_pct <= 5:
            score, grade, css = 86, "GOOD", "validation-green"
            text = f"BUY {option_type}: near LTP. Good for controlled close."
        else:
            score, grade, css = 58, "LOWER", "validation-red" if abs_diff > 25 else "validation-yellow"
            text = f"BUY {option_type}: price is above LTP. Lower if not urgent; keep only for fast exit."
    else:
        score, grade, css = 40, "CHECK", "validation-yellow"
        text = "Unknown side; review manually before modifying."
    return {"score": score, "grade": grade, "class": css, "text": text}


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
    if any(item.get("status") == "MODIFIED" for item in results):
        invalidate_kite_trade_cache()
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
    if any(item.get("status") == "CANCELLED" for item in results):
        invalidate_kite_trade_cache()
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
    positions = refresh_option_positions_with_live_ltp(positions, kite)
    open_buy_orders = open_option_buy_orders_by_symbol(kite, True)
    orders = [
        order
        for position in positions
        if (order := kite_buy_positions.build_buy_order(position, args, kite)) is not None
        and str(order.get("tradingsymbol") or "").upper() not in open_buy_orders
    ]
    orders = refresh_position_buy_order_prices(orders, kite, args)
    if not orders:
        raise ValueError(
            "No matching positions need a new BUY order after filters. "
            "Options with an existing open BUY close order were skipped."
        )
    if args.max_orders is not None and len(orders) > args.max_orders:
        raise ValueError(
            f"Refusing to create {len(orders)} orders because max-orders is {args.max_orders}."
        )
    return orders


def refresh_position_buy_order_prices(
    orders: list[dict[str, Any]],
    kite: Any,
    args: Any | None = None,
) -> list[dict[str, Any]]:
    keys = [
        f"{order.get('exchange') or 'NFO'}:{order.get('tradingsymbol')}"
        for order in orders
        if order.get("tradingsymbol")
    ]
    live_ltp = fresh_kite_ltp_map(kite, keys)
    refreshed: list[dict[str, Any]] = []
    for order in orders:
        updated = dict(order)
        key = f"{updated.get('exchange') or 'NFO'}:{updated.get('tradingsymbol')}".upper()
        ltp = live_ltp.get(key)
        if ltp is None:
            refreshed.append(updated)
            continue
        quantity = int(updated.get("quantity") or 0)
        average_price = float(updated.get("average_price") or 0)
        position_quantity = -abs(quantity) if str(updated.get("transaction_type") or "").upper() == "BUY" else quantity
        pnl = option_position_pnl(position_quantity, average_price, ltp) if average_price > 0 and quantity else float(updated.get("pnl") or 0)
        discount_percent = float(
            getattr(args, "discount_percent", updated.get("discount_percent", 20.0)) or 20.0
        )
        tick_size = float(getattr(args, "tick_size", 0.05) or 0.05)
        is_profitable = pnl > 0 or (average_price > 0 and ltp > 0 and ltp < average_price)
        price_basis_name = "LTP" if is_profitable else "average_price"
        price_basis = ltp if is_profitable else average_price
        if price_basis > 0:
            updated["price"] = floor_to_tick(price_basis * (1 - discount_percent / 100), tick_size)
        updated["ltp"] = ltp
        updated["pnl"] = pnl
        updated["price_basis"] = price_basis_name
        updated["discount_percent"] = discount_percent
        refreshed.append(updated)
    return refreshed


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


def position_close_schedule_state() -> dict[str, Any]:
    saved = load_app_settings().get("position_close_scheduler")
    state = dict(saved) if isinstance(saved, dict) else {}
    state.setdefault("enabled", True)
    state.setdefault("schedule_time", POSITION_CLOSE_SCHEDULE_TIME)
    state.setdefault("status", "WAITING")
    state.setdefault("message", "Waiting for the next weekday 09:20 IST run.")
    state.setdefault("results", [])
    return state


def save_position_close_schedule_state(**updates: Any) -> dict[str, Any]:
    state = position_close_schedule_state()
    state.update(updates)
    save_app_settings({"position_close_scheduler": state})
    return state


def parse_kite_market_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    parsed = datetime.strptime(text, pattern)
                    break
                except ValueError:
                    parsed = None
            if parsed is None:
                return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=INDIA_TIME_ZONE)
    return parsed.astimezone(INDIA_TIME_ZONE)


def verify_scheduled_position_market_open(kite: Any, now: datetime) -> tuple[bool, str]:
    if now.weekday() >= 5:
        return False, "Weekend: no scheduled close BUY orders placed."
    quotes = kite.quote(["NSE:NIFTY 50"])
    quote = quotes.get("NSE:NIFTY 50", {}) if isinstance(quotes, dict) else {}
    market_stamp = parse_kite_market_timestamp(
        quote.get("timestamp") or quote.get("last_trade_time")
    )
    if market_stamp is None:
        return False, "Could not verify today's NSE market timestamp; orders were not placed."
    if market_stamp.date() != now.date():
        return False, f"NSE appears closed; latest market timestamp is {market_stamp:%d %b %Y %H:%M} IST."
    return True, f"NSE market timestamp verified at {market_stamp:%H:%M:%S} IST."


def run_scheduled_position_close_job(now: datetime | None = None) -> dict[str, Any] | None:
    now = now.astimezone(INDIA_TIME_ZONE) if now and now.tzinfo else (
        now.replace(tzinfo=INDIA_TIME_ZONE) if now else datetime.now(INDIA_TIME_ZONE)
    )
    schedule_state = position_close_schedule_state()
    if (
        not schedule_state.get("enabled", True)
        or scheduled_job_is_paused(schedule_state, now)
        or now.weekday() >= 5
    ):
        return None
    schedule_hour, schedule_minute = (
        int(part) for part in str(schedule_state.get("schedule_time") or POSITION_CLOSE_SCHEDULE_TIME).split(":", 1)
    )
    scheduled_at = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
    window_ends = scheduled_at + timedelta(minutes=POSITION_CLOSE_SCHEDULE_WINDOW_MINUTES)
    if now < scheduled_at or now >= window_ends:
        return None
    today_key = now.strftime("%Y-%m-%d")
    if str(schedule_state.get("last_attempt_date") or "") == today_key:
        return None
    if not POSITION_CLOSE_SCHEDULER_LOCK.acquire(blocking=False):
        return None
    try:
        schedule_state = position_close_schedule_state()
        if str(schedule_state.get("last_attempt_date") or "") == today_key:
            return None
        profile_name = selected_kite_profile_name()
        started_at = now.strftime("%d %b %Y %H:%M:%S IST")
        save_position_close_schedule_state(
            last_attempt_date=today_key,
            last_run_at=started_at,
            profile=profile_name,
            status="RUNNING",
            message="Building default close-position BUY orders.",
            results=[],
        )
        try:
            profile = load_kite_profiles().get(profile_name, blank_kite_profile())
            apply_kite_profile_to_env(profile)
            setup_issue = kite_setup_issue()
            if setup_issue:
                raise RuntimeError(setup_issue)
            kite = kite_buy_positions.kite_client()
            market_open, market_message = verify_scheduled_position_market_open(kite, now)
            if not market_open:
                return save_position_close_schedule_state(
                    status="MARKET_CLOSED",
                    message=market_message,
                    results=[],
                )
            state = PageState(position_dry_run=False)
            orders = build_position_buy_orders(state)
            selected = set(range(len(orders)))
            submitted_orders, results = execute_position_buy_orders(
                orders,
                selected,
                False,
                False,
            )
            live_count = sum(1 for result in results if result.get("status") == "LIVE_SENT")
            error_count = sum(1 for result in results if result.get("status") == "ERROR")
            status = "PLACED" if live_count and not error_count else "PARTIAL" if live_count else "ERROR"
            message = (
                f"{market_message} Default close position orders placed: {live_count}; "
                f"errors: {error_count}."
            )
            return save_position_close_schedule_state(
                status=status,
                message=message,
                order_count=len(submitted_orders),
                results=results,
            )
        except ValueError as exc:
            message = str(exc)
            status = "NO_ORDERS" if "No matching positions need a new BUY order" in message else "ERROR"
            return save_position_close_schedule_state(status=status, message=message, results=[])
        except Exception as exc:
            return save_position_close_schedule_state(
                status="ERROR",
                message=friendly_external_error(exc, "Scheduled close BUY"),
                results=[],
            )
    finally:
        POSITION_CLOSE_SCHEDULER_LOCK.release()


def intraday_position_close_schedule_state() -> dict[str, Any]:
    saved = load_app_settings().get("intraday_position_close_scheduler")
    state = dict(saved) if isinstance(saved, dict) else {}
    state.setdefault("enabled", True)
    state.setdefault("start_time", INTRADAY_POSITION_CLOSE_START_TIME)
    state.setdefault("end_time", INTRADAY_POSITION_CLOSE_END_TIME)
    state.setdefault("interval_minutes", INTRADAY_POSITION_CLOSE_INTERVAL_MINUTES)
    state.setdefault("status", "WAITING")
    state.setdefault(
        "message",
        "Waiting for the next 15-minute trading-hours close-order check.",
    )
    state.setdefault("results", [])
    return state


def save_intraday_position_close_schedule_state(**updates: Any) -> dict[str, Any]:
    state = intraday_position_close_schedule_state()
    state.update(updates)
    save_app_settings({"intraday_position_close_scheduler": state})
    return state


def scheduled_job_definitions() -> dict[str, dict[str, Any]]:
    return {
        "position_close_open": {
            "name": "Default Close Orders",
            "purpose": "Place default close-position BUY orders once at market open.",
            "schedule": "Weekdays at 09:20 IST",
            "load": position_close_schedule_state,
            "save": save_position_close_schedule_state,
        },
        "income_growth_gpt": {
            "name": "Income Growth GPT CSV",
            "purpose": "Validate Income Growth with GPT and save today's trading CSV.",
            "schedule": "Weekdays at 09:30 IST",
            "load": income_growth_gpt_schedule_state,
            "save": save_income_growth_gpt_schedule_state,
        },
        "intraday_position_close": {
            "name": "Intraday Close-Order Guard",
            "purpose": "Find option positions without close BUY orders and place the missing orders.",
            "schedule": "Every 15 min, weekdays 09:30-15:15 IST",
            "load": intraday_position_close_schedule_state,
            "save": save_intraday_position_close_schedule_state,
        },
    }


def scheduled_job_pause_until(state: dict[str, Any]) -> datetime | None:
    return parse_kite_market_timestamp(state.get("paused_until"))


def scheduled_job_is_paused(
    state: dict[str, Any],
    now: datetime | None = None,
) -> bool:
    now = now.astimezone(INDIA_TIME_ZONE) if now and now.tzinfo else (
        now.replace(tzinfo=INDIA_TIME_ZONE) if now else datetime.now(INDIA_TIME_ZONE)
    )
    paused_until = scheduled_job_pause_until(state)
    return bool(paused_until and paused_until > now)


def next_weekday_schedule(base: datetime, hour: int, minute: int) -> datetime:
    candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= base:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def next_scheduled_job_run(
    job_key: str,
    state: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> datetime | None:
    now = now.astimezone(INDIA_TIME_ZONE) if now and now.tzinfo else (
        now.replace(tzinfo=INDIA_TIME_ZONE) if now else datetime.now(INDIA_TIME_ZONE)
    )
    state = state or scheduled_job_definitions()[job_key]["load"]()
    if not state.get("enabled", True):
        return None
    base = max(now, scheduled_job_pause_until(state) or now)
    if job_key == "intraday_position_close":
        start_hour, start_minute = (
            int(part)
            for part in str(
                state.get("start_time") or INTRADAY_POSITION_CLOSE_START_TIME
            ).split(":", 1)
        )
        end_hour, end_minute = (
            int(part)
            for part in str(
                state.get("end_time") or INTRADAY_POSITION_CLOSE_END_TIME
            ).split(":", 1)
        )
        interval = max(
            int(state.get("interval_minutes") or INTRADAY_POSITION_CLOSE_INTERVAL_MINUTES),
            1,
        )
        if base.weekday() < 5:
            start = base.replace(
                hour=start_hour, minute=start_minute, second=0, microsecond=0
            )
            end = base.replace(
                hour=end_hour, minute=end_minute, second=0, microsecond=0
            )
            if base < start:
                return start
            if base < end:
                elapsed = max(int((base - start).total_seconds() // 60), 0)
                next_offset = ((elapsed // interval) + 1) * interval
                candidate = start + timedelta(minutes=next_offset)
                if candidate <= end:
                    return candidate
        return next_weekday_schedule(base, start_hour, start_minute)
    schedule_default = (
        POSITION_CLOSE_SCHEDULE_TIME
        if job_key == "position_close_open"
        else INCOME_GROWTH_GPT_SCHEDULE_TIME
    )
    hour, minute = (
        int(part)
        for part in str(state.get("schedule_time") or schedule_default).split(":", 1)
    )
    return next_weekday_schedule(base, hour, minute)


def update_scheduled_job_control(
    job_key: str,
    action: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    jobs = scheduled_job_definitions()
    if job_key not in jobs:
        raise ValueError("Unknown scheduled job.")
    now = now.astimezone(INDIA_TIME_ZONE) if now and now.tzinfo else (
        now.replace(tzinfo=INDIA_TIME_ZONE) if now else datetime.now(INDIA_TIME_ZONE)
    )
    job = jobs[job_key]
    if action == "stop":
        return job["save"](
            enabled=False,
            paused_until="",
            status="STOPPED",
            message=f"{job['name']} stopped manually.",
        )
    if action == "start":
        return job["save"](
            enabled=True,
            paused_until="",
            status="WAITING",
            message=f"{job['name']} started. Waiting for the next eligible run.",
        )
    if action == "pause-day":
        paused_until = now + timedelta(days=1)
        return job["save"](
            enabled=True,
            paused_until=paused_until.isoformat(),
            status="PAUSED",
            message=f"{job['name']} paused until {paused_until:%d %b %Y %H:%M} IST.",
        )
    raise ValueError("Unknown scheduled job action.")


def intraday_position_close_slot(now: datetime) -> tuple[str, datetime] | None:
    state = intraday_position_close_schedule_state()
    start_hour, start_minute = (
        int(part) for part in str(state.get("start_time") or INTRADAY_POSITION_CLOSE_START_TIME).split(":", 1)
    )
    end_hour, end_minute = (
        int(part) for part in str(state.get("end_time") or INTRADAY_POSITION_CLOSE_END_TIME).split(":", 1)
    )
    interval = max(int(state.get("interval_minutes") or INTRADAY_POSITION_CLOSE_INTERVAL_MINUTES), 1)
    start = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=end_minute, second=59, microsecond=999999)
    if now < start or now > end:
        return None
    elapsed_minutes = int((now - start).total_seconds() // 60)
    slot_offset = (elapsed_minutes // interval) * interval
    slot_at = start + timedelta(minutes=slot_offset)
    if now >= slot_at + timedelta(minutes=interval):
        return None
    return f"{now:%Y-%m-%d}:{slot_at:%H:%M}", slot_at


def run_intraday_position_close_job(now: datetime | None = None) -> dict[str, Any] | None:
    now = now.astimezone(INDIA_TIME_ZONE) if now and now.tzinfo else (
        now.replace(tzinfo=INDIA_TIME_ZONE) if now else datetime.now(INDIA_TIME_ZONE)
    )
    schedule_state = intraday_position_close_schedule_state()
    if (
        not schedule_state.get("enabled", True)
        or scheduled_job_is_paused(schedule_state, now)
        or now.weekday() >= 5
    ):
        return None
    slot = intraday_position_close_slot(now)
    if slot is None:
        return None
    slot_key, slot_at = slot
    if str(schedule_state.get("last_slot_key") or "") == slot_key:
        return None
    if not INTRADAY_POSITION_CLOSE_SCHEDULER_LOCK.acquire(blocking=False):
        return None
    try:
        schedule_state = intraday_position_close_schedule_state()
        if str(schedule_state.get("last_slot_key") or "") == slot_key:
            return None
        profile_name = selected_kite_profile_name()
        today_key = now.strftime("%Y-%m-%d")
        run_count = int(schedule_state.get("run_count_today") or 0)
        if str(schedule_state.get("run_date") or "") != today_key:
            run_count = 0
        started_at = now.strftime("%d %b %Y %H:%M:%S IST")
        save_intraday_position_close_schedule_state(
            last_slot_key=slot_key,
            last_run_at=started_at,
            last_slot=slot_at.strftime("%H:%M"),
            run_date=today_key,
            run_count_today=run_count + 1,
            profile=profile_name,
            status="RUNNING",
            message="Checking open option positions and existing close BUY orders.",
            results=[],
        )
        try:
            profile = load_kite_profiles().get(profile_name, blank_kite_profile())
            apply_kite_profile_to_env(profile)
            setup_issue = kite_setup_issue()
            if setup_issue:
                raise RuntimeError(setup_issue)
            kite = kite_buy_positions.kite_client()
            market_open, market_message = verify_scheduled_position_market_open(kite, now)
            if not market_open:
                return save_intraday_position_close_schedule_state(
                    status="MARKET_CLOSED",
                    message=market_message,
                    results=[],
                )
            state = PageState(
                position_dry_run=False,
                position_discount_percent=20.0,
                position_keep_existing_orders=True,
            )
            orders = build_position_buy_orders(state)
            submitted_orders, results = execute_position_buy_orders(
                orders,
                set(range(len(orders))),
                False,
                True,
            )
            live_count = sum(1 for result in results if result.get("status") == "LIVE_SENT")
            error_count = sum(1 for result in results if result.get("status") == "ERROR")
            status = "PLACED" if live_count and not error_count else "PARTIAL" if live_count else "ERROR"
            pricing_details = "; ".join(
                f"{order.get('tradingsymbol')}: LIMIT {float(order.get('price') or 0):.2f} "
                f"(20% below {order.get('price_basis') or 'price basis'})"
                for order in submitted_orders
            )
            return save_intraday_position_close_schedule_state(
                status=status,
                message=(
                    f"{market_message} Missing close BUY orders placed: {live_count}; "
                    f"errors: {error_count}. {pricing_details}"
                ),
                order_count=len(submitted_orders),
                results=results,
            )
        except ValueError as exc:
            message = str(exc)
            status = "ALL_COVERED" if "No matching positions need a new BUY order" in message else "ERROR"
            return save_intraday_position_close_schedule_state(
                status=status,
                message=(
                    "All open option positions already have close BUY orders."
                    if status == "ALL_COVERED"
                    else message
                ),
                order_count=0,
                results=[],
            )
        except Exception as exc:
            return save_intraday_position_close_schedule_state(
                status="ERROR",
                message=friendly_external_error(exc, "Intraday close BUY check"),
                results=[],
            )
    finally:
        INTRADAY_POSITION_CLOSE_SCHEDULER_LOCK.release()


def position_close_scheduler_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            close_result = run_scheduled_position_close_job()
            if close_result:
                print(
                    "Scheduled close BUY job: "
                    f"{close_result.get('status')} - {close_result.get('message')}"
                )
            gpt_result = run_scheduled_income_growth_gpt_job()
            if gpt_result:
                print(
                    "Scheduled Income Growth GPT job: "
                    f"{gpt_result.get('status')} - {gpt_result.get('message')}"
                )
            intraday_result = run_intraday_position_close_job()
            if intraday_result:
                print(
                    "Intraday close BUY check: "
                    f"{intraday_result.get('status')} - {intraday_result.get('message')}"
                )
        except Exception as exc:
            print(f"Scheduled task error: {friendly_external_error(exc, 'Scheduler')}")
        stop_event.wait(30)


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


def order_has_active_position(order: dict[str, Any], active_option_keys: set[str]) -> bool:
    symbol = str(order.get("tradingsymbol") or "").strip().upper()
    if not symbol:
        return False
    parts = option_symbol_parts(symbol)
    if not parts:
        return symbol in active_option_keys
    option_key = f"{parts['underlying']}:{parts['option_type']}"
    return symbol in active_option_keys or option_key in active_option_keys


def order_has_open_duplicate(order: dict[str, Any], active_order_keys: set[str]) -> bool:
    symbol = str(order.get("tradingsymbol") or "").strip().upper()
    side = str(order.get("transaction_type") or "").strip().upper()
    return bool(symbol and side and f"{symbol}:{side}" in active_order_keys)


def validation_score_percent(validation: dict[str, Any] | None) -> float | None:
    if not validation:
        return None
    try:
        score = float(validation.get("score") or 0)
        max_score = float(validation.get("max_score") or 0)
        if max_score <= 0:
            return 0.0
        return (score / max_score) * 100
    except (TypeError, ValueError):
        return 0.0


def score_status(score_pct: float | None) -> str:
    if score_pct is None:
        return "CHECK"
    if score_pct >= 80:
        return "GOOD"
    if score_pct >= 65:
        return "OK"
    if score_pct >= 50:
        return "RISKY"
    return "AVOID"


def render_score_badge(score_pct: float | None) -> str:
    status = score_status(score_pct)
    text = "N/A" if score_pct is None else f"{score_pct:.0f}"
    return f'<span class="score-badge {status.lower()}">{html.escape(text)}<small>{html.escape(status)}</small></span>'


def render_ce_sell_dashboard(state: PageState) -> str:
    def card(item: dict[str, Any], css_class: str, actionable: bool = False) -> str:
        content = (
            f'<div class="pe-rank-card-head"><strong>{html.escape(str(item.get("stock") or ""))}</strong>'
            f'<span>Score {html.escape(fmt_number(item.get("final_ce_score"), 0))}/100</span></div>'
            f'<div class="pe-score-split"><span>Coverage <strong>{html.escape(fmt_number(item.get("holding_coverage_score"), 0))}/30</strong></span>'
            f'<span>Call-away <strong>{html.escape(fmt_number(item.get("call_away_comfort_score"), 0))}/30</strong></span>'
            f'<span>CE trade <strong>{html.escape(fmt_number(item.get("ce_trade_score"), 0))}/40</strong></span></div>'
            f'<div class="pe-rank-metrics"><span>Selected CE<strong>{html.escape(str(item.get("option_symbol") or "N/A"))}</strong></span>'
            f'<span>Holding / lot<strong>{html.escape(str(item.get("holding_qty") or 0))} / {html.escape(str(item.get("active_lot_size") or 0))}</strong></span>'
            f'<span>Covered / sell lots<strong>{html.escape(str(item.get("covered_lots_available") or 0))} / {html.escape(str(item.get("lots_to_sell") or 0))}</strong></span>'
            f'<span>CMP / strike<strong>{html.escape(fmt_number(item.get("cmp")))} / {html.escape(fmt_number(item.get("selected_ce_strike")))}</strong></span>'
            f'<span>OTM<strong>{html.escape(fmt_number(item.get("otm_percent"), 2))}%</strong></span>'
            f'<span>Sell limit<strong>{html.escape(fmt_number(item.get("sell_limit_price")))}</strong></span>'
            f'<span>Max profit<strong>{html.escape(format_buy_amount(item.get("max_profit")))}</strong></span>'
            f'<span>Yield<strong>{html.escape(fmt_number(item.get("premium_yield_percent"), 2))}%</strong></span>'
            f'<span>Event / breakout<strong>{html.escape(str(item.get("event_risk") or "N/A"))} / {html.escape(str(item.get("breakout_risk") or "N/A"))}</strong></span></div>'
            f'<p>{html.escape(str(item.get("reject_reason") or item.get("explanation") or ""))}</p>'
        )
        if actionable:
            return (
                f'<button type="button" class="pe-rank-card ce-sell-order-button {css_class}" '
                f'data-underlying="{html.escape(str(item.get("stock") or ""), quote=True)}">'
                f'{content}<em>Review fresh quote, news, and covered SELL order</em></button>'
            )
        return f'<article class="pe-rank-card {css_class}">{content}</article>'

    top = "".join(card(item, "validation-green", True) for item in state.ce_sell_top or [])
    watch = "".join(card(item, "validation-yellow") for item in state.ce_sell_watch or [])
    avoid = "".join(card(item, "validation-red") for item in state.ce_sell_avoid or [])
    return (
        '<section class="panel income-growth-pe-panel ce-sell-dashboard">'
        '<div class="panel-title">Top 3 CE Sell Candidates For Today</div>'
        '<div class="status pe-scoring-note">Covered CALL candidates are first filtered for full holding coverage, active F&amp;O contract, existing option positions, event risk, liquidity, premium yield, and breakout risk. Valid candidates are scored using 30 points for holding coverage, 30 points for call-away comfort, and 40 points for CE trade quality. Suggested and submitted Top 3 CE orders are capped at one lot each.</div>'
        '<div class="actions"><button type="submit" formaction="/ce-scan/load">Recalculate Best 3 CE SELL</button></div>'
        f'<div class="pe-candidate-grid">{top or "<div class=\"status\">No covered CE candidate passed every hard filter today.</div>"}</div></section>'
        f'<details class="panel income-growth-pe-panel"><summary>CE Watch / Review <span>{len(state.ce_sell_watch or [])}</span></summary><div class="pe-candidate-grid">{watch or "<div class=\"status\">No additional valid CE candidates.</div>"}</div></details>'
        f'<details class="panel income-growth-pe-panel avoid-today-panel"><summary>CE Avoid Today <span>{len(state.ce_sell_avoid or [])}</span></summary><div class="pe-candidate-grid">{avoid or "<div class=\"status\">No rejected CE candidates.</div>"}</div></details>'
    )


def default_selected_order_indexes(
    orders: list[dict[str, Any]],
    validations: list[dict[str, Any]] | None = None,
) -> set[int]:
    try:
        active_option_keys = active_position_option_block_keys()
    except Exception:
        active_option_keys = set()
    try:
        active_order_keys = active_open_order_option_block_keys()
    except Exception:
        active_order_keys = set()
    selected: set[int] = set()
    for index, order in enumerate(orders):
        if (
            order_has_active_position(order, active_option_keys)
            or order_has_open_duplicate(order, active_order_keys)
        ):
            continue
        validation = validations[index] if validations and index < len(validations) else None
        score_pct = validation_score_percent(validation)
        if score_pct is None or score_pct >= 65:
            selected.add(index)
    return selected


def render_orders_table(
    orders: list[dict[str, Any]] | None,
    selected: set[int] | None = None,
    validations: list[dict[str, Any]] | None = None,
) -> str:
    if not orders:
        return ""
    if selected is None:
        selected = default_selected_order_indexes(orders, validations)
    try:
        active_option_keys = active_position_option_block_keys()
    except Exception:
        active_option_keys = set()
    try:
        active_order_keys = active_open_order_option_block_keys()
    except Exception:
        active_order_keys = set()
    display_fields = [
        "exchange",
        "tradingsymbol",
        "transaction_type",
        "quantity",
        "product",
        "order_type",
        "price",
        "ltp",
        "price_markup_percent",
        "otm_percent",
        "adjusted_from_symbol",
        "max_gain",
        "validity",
        "tag",
    ]
    header_labels = {
        "price": "limit price",
        "ltp": "option LTP",
        "price_markup_percent": "markup %",
        "otm_percent": "OTM %",
        "adjusted_from_symbol": "adjusted from",
        "max_gain": "max gain opportunity",
    }
    header = "".join(
        f"<th>{html.escape(header_labels.get(field, field))}</th>"
        for field in display_fields
    )
    rows = []
    for index, order in enumerate(orders):
        symbol = str(order.get("tradingsymbol") or "").strip().upper()
        parts = option_symbol_parts(symbol) if symbol else None
        underlying = parts["underlying"] if parts else underlying_for_symbol(symbol) if symbol else ""
        option_type = parts["option_type"] if parts else ""
        has_active_position = order_has_active_position(order, active_option_keys)
        has_open_duplicate = order_has_open_duplicate(order, active_order_keys)
        validation = validations[index] if validations and index < len(validations) else None
        score_pct = validation_score_percent(validation)
        disable_checkbox = (
            has_active_position
            or has_open_duplicate
            or (score_pct is not None and score_pct < 50)
        )
        checked_attr = " checked" if index in selected and not disable_checkbox else ""
        disabled_attr = " disabled" if disable_checkbox else ""
        row_class = (
            ' class="order-existing-position active-position-row"'
            if has_active_position or has_open_duplicate
            else ""
        )
        option_label = option_type or "option"
        if has_open_duplicate:
            row_title = (
                f' title="Existing open Kite {html.escape(str(order.get("transaction_type") or ""), quote=True)} '
                f'order found for {html.escape(symbol, quote=True)}"'
            )
        elif has_active_position:
            row_title = (
                f' title="Existing Kite {html.escape(option_label, quote=True)} position found for '
                f'{html.escape(underlying or symbol, quote=True)}"'
            )
        else:
            row_title = ""
        cells = []
        for field in display_fields:
            value = order.get(field, "")
            if field == "max_gain":
                rendered = html.escape(fmt_number(value, 2) if value != "" else "N/A")
            elif field in {"price", "ltp"}:
                rendered = html.escape(fmt_number(value, 2) if value != "" else "N/A")
            elif field == "otm_percent":
                rendered = html.escape(f"{fmt_number(value, 2)}%" if value != "" else "N/A")
            elif field == "price_markup_percent":
                rendered = html.escape(f"{fmt_number(value, 2)}%" if value != "" else "-")
            elif field == "adjusted_from_symbol":
                rendered = html.escape(str(value) if value else "-")
            else:
                rendered = render_symbol_value(field, value)
            cells.append(f"<td>{rendered}</td>")
        rows.append(
            f"<tr{row_class}{row_title}>"
            f'<td><input type="checkbox" name="selected" value="{index}"{checked_attr}{disabled_attr}></td>'
            f"<td>{render_score_badge(score_pct)}</td>"
            f"{''.join(cells)}</tr>"
        )
    return (
        '<section class="panel"><div class="panel-title">Orders</div>'
        '<div class="status order-position-note">Rows in light red already have an active Kite position for the same underlying and option side, or an open/pending Kite order for the exact symbol and transaction side. Duplicate rows cannot be selected.</div>'
        '<div class="table-wrap"><table><thead><tr><th>Select</th><th>Score</th>'
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
        '<div class="actions compact-table-actions">'
        '<button type="button" class="secondary compact-action-button" id="position-select-all">Select All</button>'
        '<button type="button" class="secondary compact-action-button" id="position-unselect-all">Deselect All</button>'
        '</div>'
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
    gpt_preview = ""
    error_text = str(error)
    for marker in ("OpenAI raw output preview:", "Repair raw output preview:"):
        if marker in error_text:
            preview = error_text.split(marker, 1)[1]
            preview = re.split(r"\n\s*(Repair attempt also failed:|Repair raw output preview:|Traceback \(most recent call last\):)", preview, maxsplit=1)[0]
            if preview.strip():
                gpt_preview = preview.strip()
                break
    modal_id = "gpt-error-modal-" + hashlib.sha1(error_text.encode("utf-8", errors="ignore")).hexdigest()[:10]
    gpt_button = (
        f'<button type="button" class="secondary show-gpt-response" data-target="{html.escape(modal_id, quote=True)}">Show GPT response</button>'
        if gpt_preview
        else ""
    )
    gpt_modal = (
        f"""
        <div class="live-modal-backdrop gpt-error-modal" id="{html.escape(modal_id, quote=True)}">
          <div class="live-modal gpt-response-modal">
            <h2>GPT Response Preview</h2>
            <p class="status">This is the raw GPT/OpenAI text captured before CSV validation failed.</p>
            <textarea class="conversation" readonly>{html.escape(gpt_preview)}</textarea>
            <div class="modal-actions">
              <button type="button" class="secondary close-gpt-response" data-target="{html.escape(modal_id, quote=True)}">Close</button>
            </div>
          </div>
        </div>
        """
        if gpt_preview
        else ""
    )
    api_issue = ""
    if "openai" in error_text.lower():
        likely_causes = [
            "The OpenAI API returned no usable text. This can happen when the model produced an empty response, the response shape changed, output was blocked, or the request timed out upstream.",
            "Check OPENAI_API_KEY in Kite Setup, model name, account quota/billing, and whether the prompt is too large.",
            "Try Modify GPT Prompt with a shorter prompt, or click Validate with GPT again after a minute.",
        ]
        api_issue = "\n".join(likely_causes) + "\n\nCaptured error:\n" + error_text
    api_modal_id = "openai-api-modal-" + hashlib.sha1(("api:" + error_text).encode("utf-8", errors="ignore")).hexdigest()[:10]
    api_button = (
        f'<button type="button" class="secondary show-gpt-response" data-target="{html.escape(api_modal_id, quote=True)}">Show API issue</button>'
        if api_issue
        else ""
    )
    api_modal = (
        f"""
        <div class="live-modal-backdrop gpt-error-modal" id="{html.escape(api_modal_id, quote=True)}">
          <div class="live-modal gpt-response-modal">
            <h2>OpenAI API Diagnostics</h2>
            <p class="status">Use this to understand why the GPT validation call failed.</p>
            <textarea class="conversation" readonly>{html.escape(api_issue)}</textarea>
            <div class="modal-actions">
              <button type="button" class="secondary close-gpt-response" data-target="{html.escape(api_modal_id, quote=True)}">Close</button>
            </div>
          </div>
        </div>
        """
        if api_issue
        else ""
    )
    action_buttons = "".join([gpt_button, api_button])
    modals = "".join([gpt_modal, api_modal])
    if not remaining:
        return (
            '<div class="alert error graceful-error">'
            '<button type="button" class="alert-close" aria-label="Close error" onclick="this.parentElement.style.display=\'none\'">x</button>'
            f"<strong>{html.escape(title)}</strong>"
            f"<pre>{html.escape(top_lines)}</pre>"
            f'<div class="error-actions">{action_buttons}</div>'
            f"{modals}"
            "</div>"
        )
    return (
        '<div class="alert error graceful-error">'
        '<button type="button" class="alert-close" aria-label="Close error" onclick="this.parentElement.style.display=\'none\'">x</button>'
        f"<strong>{html.escape(title)}</strong>"
        f"<pre>{html.escape(top_lines)}</pre>"
        f'<div class="error-actions">{action_buttons}</div>'
        "<details>"
        "<summary>Show full details</summary>"
        f'<textarea class="error-details" readonly>{html.escape(str(error))}</textarea>'
        "</details>"
        f"{modals}"
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
            '<div class="price-adjuster">'
            f'<button type="button" class="price-step-button" data-price-step="-3"{disabled_attr}>-3%</button>'
            f'<input class="order-edit-input price-adjust-input" type="number" min="0" step="0.01" '
            f'name="modify_price_{field_key}" value="{price}"{disabled_attr}>'
            f'<button type="button" class="price-step-button" data-price-step="3"{disabled_attr}>+3%</button>'
            "</div>"
        )
        price_diff = order.get("price_diff_pct")
        diff_class = ""
        if price_diff is not None:
            diff_value = float(price_diff)
            diff_class = "pnl-positive" if diff_value >= 0 else "pnl-negative"
        close_pnl = order.get("close_pnl")
        close_pnl_detail = order.get("close_pnl_detail") or {}
        close_pnl_class = ""
        close_pnl_cell = "N/A"
        if close_pnl is not None:
            close_pnl_value = float(close_pnl)
            close_pnl_class = "pnl-positive" if close_pnl_value >= 0 else "pnl-negative"
            close_pnl_cell = (
                f"<strong>{html.escape(display_cell('pnl', close_pnl_value))}</strong>"
                f"<small>Qty {html.escape(str(close_pnl_detail.get('close_qty', '')))} | "
                f"Sell {html.escape(fmt_number(close_pnl_detail.get('sell_avg')))} / "
                f"Buy {html.escape(fmt_number(close_pnl_detail.get('buy_avg')))}</small>"
                f"<small>{html.escape(str(close_pnl_detail.get('note') or ''))}</small>"
            )
        suggestion = order_action_suggestion(order)
        suggestion_score = int(suggestion.get("score") or 0)
        suggestion_cell = (
            f'<div class="order-suggestion {html.escape(str(suggestion.get("class", "")))}">'
            f'<strong>{html.escape(str(suggestion.get("grade", "")))}</strong>'
            f'<span>{html.escape(str(suggestion.get("text", "")))}</span>'
            "</div>"
        )
        position_pnl = order.get("position_pnl")
        position_pnl_class = ""
        position_pnl_cell = "N/A"
        if position_pnl is not None:
            position_pnl_value = float(position_pnl)
            position_pnl_class = "pnl-positive" if position_pnl_value >= 0 else "pnl-negative"
            position_pnl_cell = (
                f"<strong>{html.escape(display_cell('pnl', position_pnl_value))}</strong>"
                f"<small>Qty {html.escape(str(order.get('position_qty') or ''))}</small>"
            )
        rows.append(
            "<tr>"
            f'<td><input type="checkbox" name="order_key" value="{html.escape(key, quote=True)}"{checked_attr}{disabled_attr}></td>'
            f"<td>{html.escape(str(order.get('tradingsymbol', '')))}</td>"
            f"<td>{html.escape(str(order.get('transaction_type', '')))}</td>"
            f"<td>{qty_cell}</td>"
            f"<td>{html.escape(str(order.get('pending_quantity', '')))}</td>"
            f"<td>{price_cell}</td>"
            f"<td>{html.escape(fmt_number(order.get('ltp')))}</td>"
            f"<td>{html.escape(fmt_number(order.get('position_avg_price')))}</td>"
            f'<td class="{position_pnl_class}">{position_pnl_cell}</td>'
            f"<td>{suggestion_cell}</td>"
            f'<td class="{diff_class}">{html.escape(fmt_number(price_diff))}%</td>'
            f'<td><span class="order-score score-{suggestion_score // 20}">{suggestion_score}/100</span></td>'
            f'<td class="{close_pnl_class}">{close_pnl_cell}</td>'
            f"<td>{html.escape(str(order.get('status', '')))}</td>"
            "</tr>"
        )
    body = (
        "".join(rows)
        if rows
        else '<tr><td colspan="14" class="status">No Kite orders found.</td></tr>'
    )
    error_html = render_graceful_error(error, "Kite Orders Error")
    return (
        '<section class="panel order-book-panel"><div class="panel-title">Kite Orders</div>'
        '<p class="status">Select open / pending orders, edit quantity or limit price, then modify or cancel them.</p>'
        f"{error_html}"
        '<div class="actions"><button type="submit" formaction="/orders/modify-selected">Modify Selected Orders</button>'
        '<button type="submit" formaction="/orders/cancel-selected" class="cancel-all-button">Cancel Selected Orders</button>'
        '<button type="submit" formaction="/orders/refresh">Refresh Orders</button>'
        '<button type="button" class="secondary compact-action-button" id="orders-select-all">Select All</button>'
        '<button type="button" class="secondary compact-action-button" id="orders-unselect-all">Unselect All</button></div>'
        '<div class="table-wrap"><table class="order-book-table"><thead><tr>'
        '<th>Select</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Pending</th>'
        '<th>Price</th><th>LTP</th><th>Avg Price</th><th>Current P&L</th><th>Suggestion</th><th>% Diff</th><th>Score</th><th>Close P&L</th><th>Status</th>'
        f"</tr></thead><tbody>{body}</tbody></table></div></section>"
    )


def render_order_management_panel(state: PageState) -> str:
    panel_style = "" if state.active_tab == "order-management" else ' style="display:none"'
    if state.active_tab != "order-management":
        order_book_html = ""
    elif state.order_book is not None or state.order_book_error:
        order_book_html = render_order_book(state)
    else:
        order_book_html = (
            '<section class="panel order-book-panel"><div class="panel-title">Kite Orders</div>'
            '<p class="status">Click Refresh Orders to load open Kite orders. No Kite order API is called until you click.</p>'
            '<div class="actions"><button type="submit" formaction="/orders/refresh">Refresh Orders</button></div>'
            "</section>"
        )
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
      {order_book_html}
      {render_results(state.results)}
      {render_console(state.console_log)}
    </form>
    """


def render_equity_panel(state: PageState) -> str:
    if state.active_tab == "equity" and state.equity_rows is None:
        try:
            state.equity_rows, state.equity_summary = equity_holdings_snapshot()
        except Exception as exc:
            state.error = state.error or f"{exc}\n\n{traceback.format_exc()}"
    rows = state.equity_rows or []
    summary = state.equity_summary or {}

    def metric_class(value: Any) -> str:
        return "pnl-positive" if isinstance(value, (int, float)) and value >= 0 else "pnl-negative" if isinstance(value, (int, float)) else ""

    def pct_text(value: Any) -> str:
        return f"{float(value):+.2f}%" if isinstance(value, (int, float)) else "N/A"

    summary_cards = "".join(
        f'<div class="equity-summary-card"><span>{html.escape(label)}</span><strong class="{metric_class(raw) if colored else ""}">{html.escape(value)}</strong><small>{html.escape(detail)}</small></div>'
        for label, value, detail, raw, colored in [
            ("Holdings", str(summary.get("count") or 0), f"As of {summary.get('as_of') or 'not refreshed'}", None, False),
            ("Total investment", format_buy_amount(summary.get("invested")), "Average cost x quantity", summary.get("invested"), False),
            ("Current value", format_buy_amount(summary.get("market_value")), "Fresh Kite LTP x quantity", summary.get("market_value"), False),
            ("Day P&L", format_buy_amount(summary.get("day_pnl")), pct_text(summary.get("day_change_pct")), summary.get("day_pnl"), True),
            ("Total P&L", format_buy_amount(summary.get("pnl")), pct_text(summary.get("net_change_pct")), summary.get("pnl"), True),
        ]
    )
    table_rows = "".join(
        f'<tr><td><button type="button" class="equity-holding-stock" '
        f'data-symbol="{html.escape(str(row.get("symbol") or ""), quote=True)}" data-exchange="{html.escape(str(row.get("exchange") or "NSE"), quote=True)}" '
        f'data-quantity="{html.escape(str(row.get("quantity") or 0), quote=True)}" data-avg="{html.escape(str(row.get("average_price") or 0), quote=True)}" '
        f'data-ltp="{html.escape(str(row.get("ltp") or 0), quote=True)}" data-pnl="{html.escape(str(row.get("pnl") or 0), quote=True)}">'
        f'<strong>{html.escape(str(row.get("symbol") or ""))}</strong><span>{html.escape(str(row.get("exchange") or "NSE"))}</span></button></td>'
        f'<td>{html.escape(fmt_number(row.get("quantity"), 0))}</td><td>{html.escape(fmt_number(row.get("average_price")))}</td>'
        f'<td><strong>{html.escape(fmt_number(row.get("ltp")))}</strong></td><td>{html.escape(format_buy_amount(row.get("invested")))}</td>'
        f'<td>{html.escape(format_buy_amount(row.get("market_value")))}</td><td class="{metric_class(row.get("pnl"))}"><strong>{html.escape(format_buy_amount(row.get("pnl")))}</strong></td>'
        f'<td class="{metric_class(row.get("net_change_pct"))}">{html.escape(pct_text(row.get("net_change_pct")))}</td>'
        f'<td class="{metric_class(row.get("day_change_pct"))}"><strong>{html.escape(pct_text(row.get("day_change_pct")))}</strong><span>{html.escape(format_buy_amount(row.get("day_pnl")))}</span></td></tr>'
        for row in rows
    ) or '<tr><td colspan="9" class="muted-cell">No equity holdings found for the selected Kite profile.</td></tr>'
    headers = ["Stock", "Qty", "Avg cost", "LTP", "Invested", "Market value", "P&L", "Net change", "Day change"]
    header_html = "".join(
        f'<th><button type="button" class="sort-header" data-sort-col="{index}">{html.escape(label)}</button></th>'
        for index, label in enumerate(headers)
    )
    panel_style = "" if state.active_tab == "equity" else ' style="display:none"'
    return f"""
    <form id="equity-panel" method="post" action="/equity/load"{panel_style}>
      {env_hidden_fields_for_render()}
      <section class="panel equity-hero"><div><div class="panel-title">Equity Holdings</div><p class="status">Live holdings from the selected Kite profile. Click a stock to place a CNC limit BUY or SELL order.</p></div><button type="submit" formaction="/equity/load">Refresh Holdings</button></section>
      {render_graceful_error(state.error, "Equity Holdings Error") if state.error else ""}
      <section class="panel equity-summary-grid">{summary_cards}</section>
      <section class="panel equity-table-panel"><div class="table-wrap"><table id="equity-holdings-table" class="equity-holdings-table"><thead><tr>{header_html}</tr></thead><tbody>{table_rows}</tbody></table></div></section>
      {render_results(state.equity_results)}
      <div class="live-modal-backdrop" id="equity-order-modal"><div class="live-modal equity-order-modal-card">
        <h2 id="equity-order-title">Equity Limit Order</h2><p class="status">Market orders are disabled. Review the latest Kite holding and LTP before continuing.</p>
        <div class="income-equity-metrics"><div><span>Current holding</span><strong id="equity-order-holding">--</strong></div><div><span>Average cost</span><strong id="equity-order-avg">--</strong></div><div><span>Live LTP</span><strong id="equity-order-ltp">--</strong></div><div><span>Current P&amp;L</span><strong id="equity-order-pnl">--</strong></div></div>
        <div class="compact-grid"><label><span>Action</span><select name="equity_side" id="equity-order-side"><option value="BUY">BUY</option><option value="SELL">SELL</option></select></label><label><span>Quantity</span><input name="equity_quantity" id="equity-order-quantity" type="number" min="1" step="1" value="1"></label><label><span>Limit price</span><input name="equity_limit_price" id="equity-order-price" type="number" min="0.05" step="0.05"></label><div class="equity-price-gap"><span>Limit vs CMP</span><strong id="equity-order-gap">--</strong></div></div>
        <input type="hidden" name="equity_symbol" id="equity-order-symbol"><input type="hidden" name="equity_exchange" id="equity-order-exchange"><input type="hidden" name="equity_confirmed" id="equity-order-confirmed" value="0">
        <div class="income-equity-order-summary" id="equity-order-summary">Enter quantity and limit price.</div><div class="breath-circle equity-order-breath" id="equity-order-breath"></div><div class="breath-text" id="equity-order-breath-text">Review order first</div><div class="countdown" id="equity-order-countdown">10</div>
        <div class="modal-actions"><button type="button" class="secondary" id="equity-order-cancel">Cancel</button><button type="button" id="equity-order-review">Submit &amp; Start 10s</button><button type="submit" class="danger" formaction="/equity/order" id="equity-order-go" disabled>GO</button></div>
      </div></div>
      {render_console(state.console_log)}
    </form>"""


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


def render_investing_panel(state: PageState) -> str:
    if state.active_tab != "investing" and state.investing_rows is None:
        return f"""
    <form id="investing-panel" method="post" action="/investing/load" style="display:none">
      {env_hidden_fields_for_render()}
    </form>"""
    rows = state.investing_rows or [
        {
            "symbol": investing_quote_key(str(item["code"])).split(":", 1)[1],
            "finance_url": google_finance_link_for_code(str(item["code"])),
            "screener_url": screener_link_for_code(str(item["code"])),
            "company": item["company"],
            "sector": item["sector"],
            "core": item.get("core") or "",
            "quantity": int(float(item.get("quantity") or 0)),
            "avg_price": float(item.get("avg_price") or 0),
            "cmp": None,
            "daily_change_pct": None,
            "cost_value": int(float(item.get("quantity") or 0)) * float(item.get("avg_price") or 0),
            "market_value": None,
            "pnl": None,
            "pnl_pct": None,
            "pct_to_52_high": None,
            "pct_from_52_low": None,
            "portfolio_pct": None,
            "pe": "N/A",
            "sector_pe": "N/A",
            "opm": "N/A",
            "mcap": "N/A",
            "debt": "N/A",
            "news": None,
            "error": "Click refresh for live CMP",
        }
        for item in INVESTING_HOLDINGS
    ]
    summary = state.investing_summary or {
        "total_cost": sum(float(row.get("cost_value") or 0) for row in rows),
        "total_market": None,
        "total_pnl": None,
        "total_pnl_pct": None,
        "core_value": None,
        "core_pct": None,
    }

    def money_cell(value: Any) -> str:
        return format_buy_amount(value) if value not in {None, ""} else "N/A"

    def crore_cell(value: Any) -> str:
        if value in {None, ""}:
            return "N/A"
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return "N/A"
        return f"{amount / 10_000_000:.2f} Cr"

    def news_cell(row: dict[str, Any]) -> str:
        news = row.get("news") or {}
        if not news:
            return '<td class="investing-news-cell muted-cell">Refresh to load top news</td>'
        title = str(news.get("title") or "No recent news")
        date_text = str(news.get("date") or "")
        sentiment = str(news.get("sentiment") or "neutral")
        link = str(news.get("link") or "")
        content = f'<span class="news-tag news-sentiment-{html.escape(sentiment)}">{html.escape(sentiment.upper())}</span> '
        if date_text:
            content += f'<span class="news-date">{html.escape(date_text)}</span> '
        content += (
            f'<a href="{html.escape(link, quote=True)}" target="_blank" rel="noopener">{html.escape(title)}</a>'
            if link
            else html.escape(title)
        )
        return f'<td class="investing-news-cell">{content}</td>'

    table_rows = ""
    for row in rows:
        pnl = row.get("pnl")
        pnl_class = "signal-neutral"
        if isinstance(pnl, (int, float)):
            pnl_class = "signal-green" if pnl >= 0 else "signal-red"
        pct_to_high = row.get("pct_to_52_high")
        pct_from_low = row.get("pct_from_52_low")
        high_class = ""
        low_class = ""
        if isinstance(pct_to_high, (int, float)) and pct_to_high >= -5:
            high_class = "near-52-high"
        if isinstance(pct_from_low, (int, float)) and pct_from_low <= 10:
            low_class = "near-52-low"
        core = "CORE" if row.get("core") == "Y" else "SAT"
        daily_change_pct = row.get("daily_change_pct")
        daily_class = ""
        if isinstance(daily_change_pct, (int, float)):
            daily_class = "pnl-positive" if daily_change_pct >= 0 else "pnl-negative"
        finance_url = str(row.get("finance_url") or google_finance_link_for_code(f"NSE:{row.get('symbol', '')}"))
        screener_url = str(row.get("screener_url") or screener_link_for_code(f"NSE:{row.get('symbol', '')}"))
        table_rows += (
            "<tr>"
            f'<td class="position-symbol-cell"><a href="{html.escape(finance_url, quote=True)}" target="_blank" rel="noopener">{html.escape(str(row.get("symbol", "")))}</a><span>{html.escape(str(row.get("company", "")))}</span><span><a class="mini-link" href="{html.escape(screener_url, quote=True)}" target="_blank" rel="noopener">Screener</a></span></td>'
            f'<td>{html.escape(str(row.get("sector", "")))}</td>'
            f'<td>{html.escape(str(row.get("quantity", "")))}</td>'
            f'<td>{html.escape(fmt_number(row.get("avg_price")))}</td>'
            f'<td>{html.escape(fmt_number(row.get("cmp")))}</td>'
            f'<td class="{daily_class}">{html.escape(fmt_number(daily_change_pct))}%</td>'
            f'<td>{html.escape(money_cell(row.get("cost_value")))}</td>'
            f'<td>{html.escape(money_cell(row.get("market_value")))}</td>'
            f'<td class="{pnl_class}">{html.escape(money_cell(row.get("pnl")))}<br><small>{html.escape(fmt_number(row.get("pnl_pct")))}%</small></td>'
            f'<td class="{high_class}">{html.escape(fmt_number(pct_to_high))}%</td>'
            f'<td class="{low_class}">{html.escape(fmt_number(pct_from_low))}%</td>'
            f'<td>{html.escape(fmt_number(row.get("portfolio_pct")))}%</td>'
            f"{news_cell(row)}"
            f'<td>{html.escape(str(row.get("pe", "N/A")))}</td>'
            f'<td>{html.escape(str(row.get("sector_pe", "N/A")))}</td>'
            f'<td>{html.escape(str(row.get("opm", "N/A")))}</td>'
            f'<td>{html.escape(str(row.get("mcap", "N/A")))}</td>'
            f'<td>{html.escape(str(row.get("debt", "N/A")))}</td>'
            f'<td class="muted-cell">{html.escape(str(row.get("error", "")))}</td>'
            "</tr>"
        )
    if not table_rows:
        table_rows = (
            '<tr><td colspan="19" class="muted-cell">'
            "Click Refresh Investing Portfolio to load live CMP, P&L, and latest news."
            "</td></tr>"
        )

    summary_cards = "".join(
        [
            f'<div class="investing-summary-card"><span>Cost value</span><strong>{html.escape(crore_cell(summary.get("total_cost")))}</strong><small>Capital invested</small></div>',
            f'<div class="investing-summary-card"><span>Market value</span><strong>{html.escape(crore_cell(summary.get("total_market")))}</strong><small>Live value after refresh</small></div>',
            f'<div class="investing-summary-card highlight"><span>Total P&L</span><strong>{html.escape(crore_cell(summary.get("total_pnl")))}</strong><small>{html.escape(fmt_number(summary.get("total_pnl_pct")))}% return</small></div>',
            f'<div class="investing-summary-card"><span>Core allocation</span><strong>{html.escape(fmt_number(summary.get("core_pct")))}%</strong><small>{html.escape(crore_cell(summary.get("core_value")))} core value</small></div>',
        ]
    )
    return f"""
    <form id="investing-panel" method="post" action="/investing/load"{'' if state.active_tab == 'investing' else ' style="display:none"'}>
      {env_hidden_fields_for_render()}
      <section class="panel investing-hero-panel">
        <div>
          <div class="panel-title">Investing Portfolio</div>
          <p class="status">Long-term share holdings with live CMP, P&L, sector view, recent news, and financial-ratio placeholders.</p>
        </div>
        <div class="actions">
          <button type="submit" formaction="/investing/load">Refresh Investing Portfolio</button>
        </div>
      </section>
      <section class="panel investing-summary-panel">
        <div class="summary-grid">{summary_cards}</div>
      </section>
      <section class="panel investing-table-panel">
        <div class="panel-title">Share Holdings</div>
        <div class="status">Financial ratios show N/A until a fundamentals data source is connected. News is limited to the largest holdings for speed.</div>
        <div class="table-wrap">
          <table class="investing-table" id="investing-holdings-table">
            <thead><tr>
              <th>Share</th><th>Sector</th><th>Qty</th><th>Avg</th><th>CMP</th>
              <th><button type="button" class="sort-header" data-sort-col="5">% Change</button></th>
              <th><button type="button" class="sort-header" data-sort-col="6">Cost</button></th>
              <th><button type="button" class="sort-header" data-sort-col="7">Market Value</button></th>
              <th><button type="button" class="sort-header" data-sort-col="8">P&L</button></th>
              <th><button type="button" class="sort-header" data-sort-col="9">% to 52W High</button></th>
              <th><button type="button" class="sort-header" data-sort-col="10">% from 52W Low</button></th>
              <th><button type="button" class="sort-header" data-sort-col="11">Portfolio %</button></th>
              <th>News / Sector</th>
              <th>PE</th><th>Sector PE</th><th>OPM</th><th>MCAP</th><th>Debt</th><th>Note</th>
            </tr></thead>
            <tbody>{table_rows}</tbody>
          </table>
        </div>
      </section>
      {render_console(state.console_log)}
    </form>"""


def render_income_growth_gpt_schedule_panel() -> str:
    schedule = income_growth_gpt_schedule_state()
    status = str(schedule.get("status") or "WAITING").upper()
    color = "green" if status == "SAVED" else "yellow" if status in {"WAITING", "MARKET_CLOSED"} else "red"
    response_id = str(schedule.get("response_id") or "")
    response_link = (
        f' <a href="https://platform.openai.com/logs" target="_blank" rel="noopener">OpenAI response {html.escape(response_id)}</a>'
        if response_id
        else ""
    )
    preview = str(schedule.get("output_preview") or "")
    preview_html = (
        f'<details><summary>Show scheduled GPT response preview</summary><pre>{html.escape(preview)}</pre></details>'
        if preview
        else ""
    )
    return (
        '<section class="panel income-growth-schedule-panel">'
        '<div class="panel-title">Scheduled Daily GPT Validation</div>'
        '<div class="position-summary-strip">'
        '<div class="position-summary-chip"><span>Schedule</span><strong>09:30 IST</strong></div>'
        f'<div class="position-summary-chip"><span>Profile</span><strong>{html.escape(str(schedule.get("profile") or selected_kite_profile_name()))}</strong></div>'
        f'<div class="position-summary-chip {strength_class(color)}"><span>Last status</span><strong>{html.escape(status)}</strong></div>'
        f'<div class="position-summary-chip"><span>CSV orders</span><strong>{html.escape(str(schedule.get("order_count") or 0))}</strong></div>'
        "</div>"
        f'<p class="status">{html.escape(str(schedule.get("message") or ""))}{response_link}</p>'
        f'<p class="status">Last run: <strong>{html.escape(str(schedule.get("last_run_at") or "Not run yet"))}</strong>'
        f' | Active CSV: <strong>{html.escape(str(schedule.get("csv_path") or "Not generated yet"))}</strong></p>'
        f"{preview_html}</section>"
    )


def render_income_growth_panel(state: PageState) -> str:
    panel_style = "" if state.active_tab == "income-growth" else ' style="display:none"'
    rows = state.income_growth_rows or []
    summary = state.income_growth_summary or {}
    gpt_result = ""
    default_gpt_prompt = income_growth_gpt_user_prompt(rows, summary) if rows else ""
    gpt_prompt_text = state.income_growth_gpt_prompt or default_gpt_prompt
    if state.income_growth_gpt_csv or state.income_growth_gpt_output:
        response_link = (
            f'<a class="inline-link" href="https://platform.openai.com/logs" target="_blank" rel="noopener">Response: {html.escape(state.income_growth_gpt_response_id or "OpenAI logs")}</a>'
            if state.income_growth_gpt_response_id
            else ""
        )
        cache_note = "Cached result reused." if state.income_growth_gpt_cached else "Fresh GPT response."
        gpt_result = f"""
      <section class="panel income-growth-gpt-result">
        <div class="panel-title">GPT Validation Result</div>
        <div class="status">Review this independent GPT validation before placing any covered CALL order. {html.escape(cache_note)} {response_link}</div>
        <label><span>Kite CSV from GPT</span><textarea class="csv-output" readonly>{html.escape(state.income_growth_gpt_csv)}</textarea></label>
        <details><summary>Show full GPT response</summary><textarea class="conversation" readonly>{html.escape(state.income_growth_gpt_output)}</textarea></details>
      </section>"""
    def pct_cell(value: Any) -> str:
        if isinstance(value, (int, float)):
            return f"{value:.2f}%"
        return "N/A" if value is None or value == "" else str(value)

    def income_growth_52w_class(value: Any) -> str:
        if not isinstance(value, (int, float)):
            return ""
        if value >= -10:
            return "strength-lightgreen"
        if value <= -50:
            return "strength-lightcoral"
        return ""

    def income_growth_1y_class(value: Any) -> str:
        if not isinstance(value, (int, float)):
            return ""
        if value > 10:
            return "signal-green"
        if value < -10:
            return "strength-lightcoral"
        return ""

    def income_growth_month_class(value: Any) -> str:
        if not isinstance(value, (int, float)):
            return ""
        if value > 5:
            return "strength-lightgreen"
        if value < -5:
            return "strength-lightcoral"
        return ""

    summary_cards = "".join(
        f'<div class="investing-summary-card"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><small>{html.escape(detail)}</small></div>'
        for label, value, detail in [
            ("Est monthly CC income", fmt_number(summary.get("existing_monthly_income")), "from currently covered lots"),
            ("Best add per 1L", fmt_number(summary.get("best_additional_per_lakh")), "premium unlocked per extra capital"),
            ("Portfolio value", format_buy_amount(summary.get("portfolio_market")), "live market value"),
            ("Updated", str(summary.get("as_of") or "Not refreshed"), "manual refresh only"),
        ]
    )
    def equity_stock_button(row: dict[str, Any]) -> str:
        symbol = str(row.get("symbol") or "").upper()
        company = str(row.get("company") or "")
        return (
            f'<button type="button" class="income-equity-stock" '
            f'data-symbol="{html.escape(symbol, quote=True)}" '
            f'data-company="{html.escape(company, quote=True)}" '
            f'data-holding="{html.escape(str(row.get("quantity") or 0), quote=True)}" '
            f'data-avg="{html.escape(str(row.get("avg_price") or 0), quote=True)}" '
            f'data-ltp="{html.escape(str(row.get("cmp") or 0), quote=True)}" '
            f'data-pnl="{html.escape(str(row.get("pnl") or 0), quote=True)}">'
            f'<strong>{html.escape(symbol)}</strong><span>{html.escape(company)}</span>'
            "</button>"
        )
    table_rows = "".join(
        "<tr>"
        f'<td class="position-symbol-cell">{equity_stock_button(row)}</td>'
        f"<td>{html.escape(str(row.get('quantity', '')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('times_lot'), 2))}</td>"
        f"<td><strong>{html.escape(str(row.get('covered_lots', row.get('lots_can_sell_input', 0))))}</strong></td>"
        f"<td>{html.escape(fmt_number(row.get('cmp')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('input_call_strike')))}</td>"
        f"<td>{html.escape(format_buy_amount(row.get('market_value')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('input_to_sell')))}</td>"
        f"<td>{html.escape(str(row.get('lot_size') or row.get('input_lot_size') or 'N/A'))}</td>"
        f"<td>{html.escape(pct_cell(row.get('input_gap_pct')))}</td>"
        f"<td>{html.escape(pct_cell(row.get('input_put_down_pct')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('input_put_strike')))}</td>"
        f"<td>{html.escape('N/A' if row.get('input_pe') is None else fmt_number(row.get('input_pe'), 2))}</td>"
        f'<td class="{income_growth_52w_class(row.get("input_52w"))}">{html.escape(pct_cell(row.get("input_52w")))}</td>'
        f'<td class="{income_growth_1y_class(row.get("input_1y"))}">{html.escape(pct_cell(row.get("input_1y")))}</td>'
        f'<td class="{income_growth_month_class(row.get("input_month"))}">{html.escape(pct_cell(row.get("input_month")))}</td>'
        f"<td>{html.escape(pct_cell(row.get('input_1w')))}</td>"
        f"<td>{html.escape(pct_cell(row.get('input_today')))}</td>"
        f"<td>{render_symbol_value('tradingsymbol', row.get('candidate_ce', ''))}</td>"
        f"<td>{html.escape(fmt_number(row.get('premium')))}</td>"
        f"<td>{html.escape(fmt_number(row.get('monthly_income')))}</td>"
        f"<td><strong>{html.escape(fmt_number(row.get('cc_capacity_score'), 2))}</strong></td>"
        f'<td class="{strength_class(row.get("decision_color"))}"><strong>{html.escape(str(row.get("decision", "")))}</strong></td>'
        "</tr>"
        for row in rows
    )
    if not table_rows:
        table_rows = '<tr><td colspan="23" class="muted-cell">Click Refresh Income Growth to calculate covered-call capacity from your holdings sheet.</td></tr>'
    try:
        stored_holdings = load_income_growth_holding_map()
    except Exception:
        stored_holdings = {
            normalize_income_growth_symbol(item.get("symbol")): item
            for item in INCOME_GROWTH_SHEET
        }
    symbol_options = "".join(
        f'<option value="{html.escape(symbol)}">'
        for symbol in sorted(stored_holdings)
    )
    latest_update = max(
        (str(item.get("updated_at") or "") for item in stored_holdings.values()),
        default="Seeded from app defaults",
    )
    update_form_html = f"""
      <section class="panel income-growth-update-panel">
        <div class="panel-title">Update Holding Data</div>
        <div class="status">Saved in lightweight SQLite DB: {html.escape(str(APP_DB_PATH.name))}. Update only the holding quantity when your portfolio changes. Last DB update: {html.escape(latest_update or "N/A")}.</div>
        <div class="compact-form-grid income-growth-edit-grid">
          <label><span>Symbol</span><input list="income-growth-symbols" name="income_growth_symbol" placeholder="PFC"></label>
          <datalist id="income-growth-symbols">{symbol_options}</datalist>
          <label><span>Holding shares</span><input name="income_growth_holding" inputmode="decimal" placeholder="3515"></label>
        </div>
        <div class="actions">
          <button type="submit" formaction="/income-growth/save-holding">Save Holding Data</button>
        </div>
      </section>"""
    headers = [
        "Stock",
        "Holding",
        "Times lot",
        "Lots sell",
        "CMP",
        "CALL Strike",
        "Value",
        "To sell",
        "Lot Size",
        "Gap %",
        "PUT down %",
        "PUT Strike",
        "PE",
        "52W",
        "1Y",
        "Month",
        "1W",
        "Today",
        "Kite CE",
        "Premium",
        "Monthly income",
        "Score",
        "Decision",
    ]
    header_html = "".join(
        f'<th><button type="button" class="sort-header" data-sort-col="{index}">{html.escape(label)}</button></th>'
        for index, label in enumerate(headers)
    )
    return f"""
    <form id="income-growth-panel" method="post" action="/income-growth/load"{panel_style}>
      {env_hidden_fields_for_render()}
      <input type="hidden" name="income_growth_gpt_csv" value="{html.escape(state.income_growth_gpt_csv, quote=True)}">
      <input type="hidden" name="income_growth_gpt_output" value="{html.escape(state.income_growth_gpt_output, quote=True)}">
      <input type="hidden" name="income_growth_gpt_response_id" value="{html.escape(state.income_growth_gpt_response_id, quote=True)}">
      <input type="hidden" name="income_growth_gpt_cached" value="{'1' if state.income_growth_gpt_cached else '0'}">
      <section class="panel income-growth-hero">
        <div>
          <div class="panel-title">Income Growth</div>
          <p class="status">Ranks holdings by covered-call capacity, option income efficiency, and capital needed to unlock the next lot.</p>
        </div>
        <div class="actions">
          <button type="submit" formaction="/income-growth/load">Refresh Income Growth</button>
          <button type="submit" formaction="/income-growth/gpt">Validate with GPT</button>
          <button type="button" id="income-growth-edit-gpt">Modify GPT Prompt</button>
        </div>
      </section>
      <section class="panel investing-summary-panel"><div class="summary-grid">{summary_cards}</div></section>
      {render_income_growth_gpt_schedule_panel()}
      {gpt_result}
      <section class="panel income-growth-table-panel">
        <div class="panel-title">Covered Call Capacity Score From Current Holding Sheet</div>
        <div class="status">Click a stock name to BUY or SELL equity through the selected Kite profile. Uses your holding shares, lot multiple, lots can be sold, CMP, call strike, PE, 52W, 1Y, monthly, weekly, and today move.</div>
        <div class="table-wrap"><table id="income-growth-table" class="income-growth-table"><thead><tr>{header_html}</tr></thead><tbody>{table_rows}</tbody></table></div>
      </section>
      {render_results(state.income_growth_equity_results)}
      {update_form_html}
      <div class="live-modal-backdrop" id="income-equity-modal">
        <div class="live-modal income-equity-modal-card">
          <h2 id="income-equity-title">Income Growth Equity Order</h2>
          <p class="status">NSE equity order using CNC, LIMIT, DAY. The price is refreshed from Kite before execution.</p>
          <div class="income-equity-metrics">
            <div><span>Current holding</span><strong id="income-equity-holding">--</strong></div>
            <div><span>Average buy price</span><strong id="income-equity-avg">--</strong></div>
            <div><span>Live LTP</span><strong id="income-equity-ltp">--</strong></div>
            <div><span>Current P&amp;L</span><strong id="income-equity-pnl">--</strong></div>
          </div>
          <div class="compact-grid">
            <label><span>Action</span>
              <select name="income_growth_equity_side" id="income-equity-side">
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </select>
            </label>
            <label><span>Stock quantity</span><input name="income_growth_equity_quantity" id="income-equity-quantity" type="number" min="1" step="1" value="1"></label>
          </div>
          <input type="hidden" name="income_growth_equity_symbol" id="income-equity-symbol">
          <input type="hidden" name="income_growth_equity_confirmed" id="income-equity-confirmed" value="0">
          <div class="income-equity-order-summary" id="income-equity-order-summary">Select BUY or SELL and enter quantity.</div>
          <div class="breath-circle income-equity-breath" id="income-equity-breath"></div>
          <div class="breath-text" id="income-equity-breath-text">Review order first</div>
          <div class="countdown" id="income-equity-countdown">10</div>
          <div class="modal-actions">
            <button type="button" class="secondary" id="income-equity-cancel">Cancel</button>
            <button type="button" id="income-equity-review">Review &amp; Start 10s</button>
            <button type="submit" class="danger" formaction="/income-growth/equity-order" id="income-equity-execute" disabled>Execute Equity Order</button>
          </div>
        </div>
      </div>
      <div class="live-modal-backdrop" id="income-growth-gpt-modal">
        <div class="live-modal income-growth-prompt-modal">
          <h2>Modify Income Growth GPT Prompt</h2>
          <p class="status">Edit the prompt and send a fresh GPT request. Normal Validate with GPT reuses the cache when the prompt is unchanged.</p>
          <label><span>Prompt sent to GPT</span><textarea class="conversation" name="income_growth_gpt_prompt" id="income-growth-gpt-prompt">{html.escape(gpt_prompt_text)}</textarea></label>
          <input type="hidden" name="income_growth_force_gpt" id="income-growth-force-gpt" value="0">
          <div class="modal-actions">
            <button type="button" class="secondary" id="income-growth-gpt-cancel">Cancel</button>
            <button type="submit" formaction="/income-growth/gpt" id="income-growth-gpt-refresh">Refresh GPT Response</button>
          </div>
        </div>
      </div>
      {render_console(state.console_log)}
    </form>"""


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
      {active_section}
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
      <section class="panel">
        <div class="panel-title">CSV Source</div>
        {render_input("csv_path", "CSV path", state.csv_path)}
        <div class="status">CSV path can be a local file or a public Google Sheets link. Google Sheets must be shared as viewable by anyone with the link.</div>
        <label><span>Upload CSV</span><input id="csv-file" type="file" accept=".csv,text/csv"></label>
        <label><span>CSV text</span><textarea id="csv-text" name="csv_text" placeholder="Paste CSV here or choose a file above">{html.escape(state.csv_text)}</textarea></label>
        <div class="actions">
          <button type="submit" formaction="/csv/save-today">Save as Today CSV</button>
          <button type="button" class="secondary" id="clear-csv-text">Clear CSV text</button>
        </div>
        <div class="status">Saves CSV text to {html.escape(str(dated_income_csv_path()))} and updates CSV path.</div>
      </section>
      {render_console(state.console_log)}
    </form>"""


def render_position_close_schedule_panel() -> str:
    schedule = position_close_schedule_state()
    intraday = intraday_position_close_schedule_state()
    results = schedule.get("results") if isinstance(schedule.get("results"), list) else []
    intraday_results = intraday.get("results") if isinstance(intraday.get("results"), list) else []
    status = str(schedule.get("status") or "WAITING").upper()
    intraday_status = str(intraday.get("status") or "WAITING").upper()
    color = "green" if status == "PLACED" else "yellow" if status in {"WAITING", "NO_ORDERS", "MARKET_CLOSED"} else "red"
    intraday_color = (
        "green"
        if intraday_status in {"PLACED", "ALL_COVERED"}
        else "yellow"
        if intraday_status in {"WAITING", "MARKET_CLOSED"}
        else "red"
    )
    result_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(result.get('tradingsymbol') or ''))}</td>"
        f"<td>{html.escape(str(result.get('status') or ''))}</td>"
        f"<td>{html.escape(str(result.get('order_id') or ''))}</td>"
        f"<td>{html.escape(str(result.get('detail') or ''))}</td>"
        "</tr>"
        for result in results
    )
    details = (
        '<details class="scheduled-position-results"><summary>View scheduled order details</summary>'
        '<div class="table-wrap"><table><thead><tr><th>Symbol</th><th>Status</th><th>Order ID</th><th>Detail</th></tr></thead>'
        f"<tbody>{result_rows}</tbody></table></div></details>"
        if result_rows
        else ""
    )
    intraday_result_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(result.get('tradingsymbol') or ''))}</td>"
        f"<td>{html.escape(str(result.get('status') or ''))}</td>"
        f"<td>{html.escape(str(result.get('order_id') or ''))}</td>"
        f"<td>{html.escape(str(result.get('detail') or ''))}</td>"
        "</tr>"
        for result in intraday_results
    )
    intraday_details = (
        '<details class="scheduled-position-results"><summary>View latest intraday order details</summary>'
        '<div class="table-wrap"><table><thead><tr><th>Symbol</th><th>Status</th><th>Order ID</th><th>Detail</th></tr></thead>'
        f"<tbody>{intraday_result_rows}</tbody></table></div></details>"
        if intraday_result_rows
        else ""
    )
    return (
        '<section class="panel scheduled-position-close-panel">'
        '<div class="panel-title">Scheduled Default Close Orders</div>'
        '<div class="position-summary-strip">'
        '<div class="position-summary-chip"><span>Schedule</span><strong>09:20 IST</strong></div>'
        f'<div class="position-summary-chip"><span>Profile</span><strong>{html.escape(str(schedule.get("profile") or selected_kite_profile_name()))}</strong></div>'
        f'<div class="position-summary-chip {strength_class(color)}"><span>Last status</span><strong>{html.escape(status)}</strong></div>'
        f'<div class="position-summary-chip"><span>Last run</span><strong>{html.escape(str(schedule.get("last_run_at") or "Not run yet"))}</strong></div>'
        "</div>"
        f'<p class="status">{html.escape(str(schedule.get("message") or ""))} '
        "Default close-position BUY orders use the current Position BUY pricing logic; existing open BUY close orders are skipped.</p>"
        f"{details}"
        '<hr><div class="panel-title">Intraday Missing Close-Order Guard</div>'
        '<div class="position-summary-strip">'
        '<div class="position-summary-chip"><span>Schedule</span><strong>Every 15 min | 09:30-15:15</strong></div>'
        f'<div class="position-summary-chip"><span>Runs today</span><strong>{html.escape(str(intraday.get("run_count_today") or 0))}</strong></div>'
        f'<div class="position-summary-chip {strength_class(intraday_color)}"><span>Last status</span><strong>{html.escape(intraday_status)}</strong></div>'
        f'<div class="position-summary-chip"><span>Last run</span><strong>{html.escape(str(intraday.get("last_run_at") or "Not run yet"))}</strong></div>'
        "</div>"
        f'<p class="status">{html.escape(str(intraday.get("message") or ""))} '
        "Price rule: when average is above LTP, BUY at 20% below fresh LTP; otherwise BUY at 20% below average price. Existing close BUY orders are skipped.</p>"
        f"{intraday_details}</section>"
    )


def render_scheduler_control_panel() -> str:
    now = datetime.now(INDIA_TIME_ZONE)
    rows: list[str] = []
    for job_key, job in scheduled_job_definitions().items():
        state = job["load"]()
        enabled = bool(state.get("enabled", True))
        paused = scheduled_job_is_paused(state, now)
        status = "STOPPED" if not enabled else "PAUSED" if paused else str(
            state.get("status") or "WAITING"
        ).upper()
        status_badge = (
            "avoid"
            if status in {"STOPPED", "ERROR"}
            else "ok"
            if status in {"PAUSED", "WAITING", "MARKET_CLOSED", "NO_ORDERS"}
            else "good"
        )
        next_run = next_scheduled_job_run(job_key, state, now)
        next_run_text = next_run.strftime("%d %b %Y %H:%M IST") if next_run else "Stopped"
        primary_action = "start" if not enabled else "stop"
        primary_label = "Start job" if not enabled else "Stop job"
        pause_disabled = " disabled" if not enabled else ""
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(job['name'])}</strong><small>{html.escape(job['schedule'])}</small></td>"
            f"<td>{html.escape(job['purpose'])}</td>"
            f"<td>{html.escape(str(state.get('last_run_at') or 'Not run yet'))}</td>"
            f"<td>{html.escape(next_run_text)}</td>"
            f'<td><span class="score-badge {html.escape(status_badge)}">{html.escape(status)}</span></td>'
            '<td><div class="scheduler-job-actions">'
            f'<button type="submit" class="{"secondary" if not enabled else "danger"}" '
            f'formaction="/scheduler/{primary_action}" name="job_name" value="{html.escape(job_key)}">{primary_label}</button>'
            f'<button type="submit" class="secondary" formaction="/scheduler/pause-day" '
            f'name="job_name" value="{html.escape(job_key)}"{pause_disabled}>Pause for 1 day</button>'
            "</div></td>"
            "</tr>"
        )
    return (
        '<section class="panel kite-setup-card scheduler-control-panel">'
        '<div class="setup-card-kicker">07</div>'
        '<div class="panel-title">Scheduled Jobs Control</div>'
        '<p class="status">Monitor and control automated trading jobs. Changes persist in '
        '<code>app_settings.json</code> across restarts. Stopping a job does not cancel orders already placed.</p>'
        '<div class="table-wrap"><table class="scheduler-control-table"><thead><tr>'
        '<th>Name / Schedule</th><th>Purpose</th><th>Last run</th><th>Next schedule</th><th>Status</th><th>Controls</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        "</section>"
    )


def render_positions_panel(
    state: PageState,
    position_orders_payload: str = "",
    position_orders_table: str = "",
    position_execute_button: str = "",
) -> str:
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

    def position_identity(row: dict[str, Any]) -> str:
        existing = row.get("existing_buy_order") or {}
        marker = ""
        if existing:
            marker = (
                '<span class="existing-buy-order">BUY ORDER PLACED</span>'
                f'<span>BUY Qty {html.escape(str(existing.get("quantity", "")))}'
                f' | Limit {html.escape(fmt_number(existing.get("price")))}</span>'
            )
        return (
            f'{render_symbol_value("tradingsymbol", row.get("symbol", ""))}'
            f'<span>{html.escape(str(row.get("product", "")))} | Qty {html.escape(str(row.get("quantity", "")))}</span>'
            f"{marker}"
        )

    def position_action(row: dict[str, Any]) -> str:
        if row.get("existing_buy_order"):
            return '<span class="existing-buy-action">Close BUY pending</span>'
        if int(row.get("quantity") or 0) < 0 and (
            (row.get("captured_pct") is not None and abs(float(row.get("captured_pct") or 0)) >= 50)
            or float(row.get("return_pct") or 0) <= -40
        ):
            return (
                f'<button type="submit" class="book-profit-button compact-action-button" '
                f'formaction="/positions/close-buy" name="close_symbol" '
                f'value="{html.escape(str(row.get("symbol", "")), quote=True)}">BUY -10%</button>'
            )
        return '<span class="commodity-wait">Wait</span>'

    summary_cards = "".join(
        f'<div class="position-summary-chip"><span>{html.escape(label)}</span>'
        f'<strong>{html.escape(value)}</strong></div>'
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
        f'<td class="position-symbol-cell">{position_identity(row)}</td>'
        f"<td><strong>{html.escape(fmt_number(row.get('stock_cmp')))}</strong><span>Stock CMP</span></td>"
        f"<td><strong>{html.escape(fmt_number(row.get('ltp')))}</strong><span>Avg {html.escape(fmt_number(row.get('average_price')))}</span></td>"
        f'<td class="{metric_class(row.get("pnl"))}"><strong>{html.escape(display_cell("pnl", row.get("pnl", "")))}</strong><span>{html.escape(fmt_number(row.get("return_pct")))}% on margin</span></td>'
        f'<td class="{strength_class("green" if (row.get("captured_pct") is not None and float(row.get("captured_pct") or 0) >= 50) else row.get("capture_color"))}"><strong>{html.escape(fmt_number(row.get("captured_pct")))}%</strong><span>Captured</span></td>'
        f"<td><strong>{html.escape(fmt_number(row.get('remaining_premium')))}</strong><span>{html.escape(fmt_number(row.get('remaining_pct')))}% remaining</span></td>"
        f'<td class="{strength_class(row.get("capture_color"))}"><strong>{html.escape(str(row.get("capture_action", "")))}</strong><span>{html.escape(str(row.get("capture_detail", "")))}</span></td>'
        f"<td>{position_action(row)}</td>"
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
        f'<div class="status">Market data as of: <strong>{html.escape(str(summary.get("as_of") or "Not loaded"))}</strong>. Use Load Active Positions for a fresh Kite pull.'
        + (
            f' <span class="pnl-negative">Open BUY order check unavailable: {html.escape(str(summary.get("order_lookup_error")))}</span>'
            if summary.get("order_lookup_error")
            else ""
        )
        + "</div>"
        '<div class="table-wrap positions-table-wrap"><table class="positions-table"><thead><tr>'
        '<th>Position</th><th>Stock CMP</th><th>LTP / Avg</th><th>P&L</th><th>Captured</th><th>Remaining</th><th>Exit</th><th>Action</th><th>Margin</th><th>Buy</th>'
        '<th>POP</th><th>OTM</th><th>Sell</th><th>Strength</th><th>Delta</th>'
        '<th>IV</th><th>PCR</th><th>S / R</th><th>Error</th></tr></thead>'
        f"<tbody>{table_rows}</tbody></table></div></section>"
        if rows
        else ""
    )
    return f"""
    <form id="positions-panel" method="post" action="/positions-research/load"{'' if state.active_tab == 'positions' else ' style="display:none"'}>
      {env_hidden_fields_for_render()}
      <input type="hidden" name="position_live_confirmed" id="position-live-confirmed" value="0">
      <input type="hidden" name="position_orders_payload" value="{html.escape(position_orders_payload, quote=True)}">
      <section class="panel calm-hero-panel">
        <div>
          <p class="calm-quote">"Small drops makes the ocean"</p>
          <p class="status">Analysis of current Positions | P&L, margin, premium capture and roll signals.</p>
        </div>
        <div class="actions">
          <button type="submit" formaction="/positions-research/load">Refresh Active Positions</button>
          <button type="submit" formaction="/positions/load">Get Current Position / Preview BUY</button>
          {position_execute_button}
        </div>
      </section>
      <section class="panel positions-summary-panel"><div class="position-summary-strip">{summary_cards}</div></section>
      {render_position_close_schedule_panel()}
      {table}
      {position_orders_table}
      {render_results(state.position_results)}
      <details class="panel position-buy-settings">
        <summary>
          <span>
            <strong>BUY Preview Settings</strong>
            <small>Optional controls for filtering and pricing position close orders</small>
          </span>
          <span class="position-settings-toggle">Open settings</span>
        </summary>
        <div class="position-buy-settings-body">
          <div class="position-settings-grid position-settings-primary">
            {render_number_input("position_discount_percent", "Discount from price (%)", state.position_discount_percent, "0.05")}
            {render_input("position_exchange", "Exchange", state.position_exchange)}
            {render_input("position_product", "Product filter", state.position_product)}
            {render_input("position_max_orders", "Maximum orders", state.position_max_orders)}
          </div>
          <div class="position-settings-grid position-settings-secondary">
            <div class="position-settings-wide">
              {render_input("position_symbols", "Symbol filter (comma-separated)", state.position_symbols)}
            </div>
            {render_input("position_variety", "Variety", state.position_variety)}
            {render_input("position_validity", "Validity", state.position_validity)}
            {render_input("position_tag", "Order tag", state.position_tag)}
            {render_number_input("position_tick_size", "Tick size", state.position_tick_size, "0.01")}
          </div>
        </div>
      </details>
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
        f"<td>{html.escape(fmt_number(row.get('average_price')))}</td>"
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
        '<tr><td colspan="9" class="status">No commodity ETF holdings found.</td></tr>'
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
        '<th>ETF</th><th>Unit</th><th>Avg Buy Price</th><th>Source</th><th>Investment Amount</th><th>Market Value</th><th>Profit</th><th>% Profit</th><th>Action</th>'
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
          <div class="commodity-dma">50 DMA -- | 200 DMA --</div>
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
        <div class="status">Tracks ETF day change. Buy amount = yearly base x ETF allocation x dip multiplier, capped at {COMMODITY_MAX_MULTIPLIER}x. Current yearly base: {html.escape(format_buy_amount(commodity_yearly_base_amount()))}. <button type="button" class="mini-refresh-button" id="refresh-commodity-quotes">Refresh ETF quotes</button></div>
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
    option_sell_markup = option_sell_markup_percent_setting()
    positions = state.income_positions or []
    pe_top = state.income_pe_top or []
    pe_watch = state.income_pe_watch or []
    pe_avoid = state.income_pe_avoid or []
    blocked_pe_symbols = {
        str(item.get("symbol") or item.get("stock") or "").upper()
        for item in pe_avoid
        if "existing active pe position" in str(item.get("reject_reason") or "").lower()
    }
    panel_style = "" if state.active_tab == "income" else ' style="display:none"'
    overall_pnl = float(summary.get("overall_pnl") or 0)
    pnl_cards = [
        ("Current option P&L", fmt_number(overall_pnl), "pnl-positive" if overall_pnl >= 0 else "pnl-negative"),
        ("Active short positions", str(summary.get("active_short_positions") or 0), ""),
        (
            "PE / CE exposure",
            f"{summary.get('active_pe_positions') or 0} PE / {summary.get('active_ce_positions') or 0} CE",
            "",
        ),
        (
            "Profitable / Review",
            f"{summary.get('profitable_positions') or 0} / {summary.get('review_positions') or 0}",
            "pnl-positive" if int(summary.get("review_positions") or 0) == 0 else "pnl-negative",
        ),
    ]
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
            f'<button type="button" class="book-profit-button income-pe-order-button" data-underlying="{html.escape(str(row.get("symbol", "")), quote=True)}" data-strike="{html.escape(str(row.get("strike") or 0), quote=True)}">SELL PE</button>'
            if not row.get("error") and str(row.get("symbol") or "").upper() not in blocked_pe_symbols
            else '<span class="commodity-wait">Existing PE position - blocked</span>'
            if str(row.get("symbol") or "").upper() in blocked_pe_symbols
            else '<span class="commodity-wait">Review error</span>'
        )
        + f'<small>{html.escape(str(row.get("action", "")))}</small>'
        + f'<small>{html.escape(str(row.get("error", "")))}</small>'
        + "</td>"
        "</tr>"
        for row in rows
    )
    position_rows = "".join(
        "<tr>"
        f"<td>{render_symbol_value('tradingsymbol', position.get('tradingsymbol', ''))}</td>"
        f"<td>{html.escape(str(position.get('quantity') or 0))}</td>"
        f"<td>{html.escape(fmt_number(position.get('average_price')))}</td>"
        f"<td>{html.escape(fmt_number(position.get('ltp')))}</td>"
        f'<td class="{"pnl-positive" if float(position.get("pnl") or 0) >= 0 else "pnl-negative"}"><strong>{html.escape(fmt_number(position.get("pnl")))}</strong></td>'
        "</tr>"
        for position in positions
    )
    position_rows_html = position_rows or '<tr><td colspan="5">No active short option positions.</td></tr>'
    positions_table = (
        '<section class="panel income-current-positions"><div class="panel-title">Current Income Positions &amp; P&amp;L</div>'
        '<div class="status">Live short-option exposure used by this decision dashboard.</div>'
        '<div class="table-wrap"><table><thead><tr><th>Position</th><th>Qty</th><th>Avg</th><th>LTP</th><th>P&amp;L</th>'
        f'</tr></thead><tbody>{position_rows_html}</tbody></table></div></section>'
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
    def pe_candidate_card(item: dict[str, Any], actionable: bool) -> str:
        symbol = str(item.get("symbol") or item.get("stock") or "")
        status = str(item.get("status") or "")
        event_risk = str(item.get("event_risk") or "AMBER")
        card_class = (
            "validation-green"
            if status == "TOP_3"
            else "validation-red"
            if status == "AVOID_TODAY"
            else "validation-yellow"
        )
        content = (
            f'<div class="pe-rank-card-head"><strong>{html.escape(symbol)}</strong>'
            f'<span>Score {html.escape(fmt_number(item.get("final_pe_score"), 0))}/100</span></div>'
            f'<div class="pe-score-split"><span>Stock quality <strong>{html.escape(fmt_number(item.get("stock_quality_score"), 0))}/40</strong></span>'
            f'<span>PE trade <strong>{html.escape(fmt_number(item.get("pe_trade_score"), 0))}/60</strong></span></div>'
            f'<div class="pe-rank-metrics"><span>Selected PE<strong>{html.escape(str(item.get("option_symbol") or "N/A"))}</strong></span>'
            f'<span>Target zone<strong>{html.escape(fmt_number(item.get("target_strike")))}</strong></span>'
            f'<span>Tradable strike<strong>{html.escape(fmt_number(item.get("strike")))}</strong></span>'
            f'<span>CMP<strong>{html.escape(fmt_number(item.get("cmp")))}</strong></span>'
            f'<span>OTM<strong>{html.escape(fmt_number(item.get("otm_percent"), 2))}%</strong></span>'
            f'<span>Sell limit<strong>{html.escape(fmt_number(item.get("sell_limit_price")))}</strong></span>'
            f'<span>Max profit<strong>{html.escape(format_buy_amount(item.get("max_profit")))}</strong></span>'
            f'<span>Assignment cash<strong>{html.escape(format_buy_amount(item.get("assignment_cash")))}</strong></span>'
            f'<span>Yield<strong>{html.escape(fmt_number(item.get("premium_yield_percent"), 2))}%</strong></span>'
            f'<span>Event risk<strong>{html.escape(event_risk)}</strong></span></div>'
            f'<p>{html.escape(str(item.get("reject_reason") or item.get("explanation") or ""))}</p>'
        )
        if actionable:
            return (
                f'<button type="button" class="pe-rank-card income-pe-order-button {card_class}" '
                f'data-underlying="{html.escape(symbol, quote=True)}" '
                f'data-strike="{html.escape(str(item.get("strike") or 0), quote=True)}">{content}'
                '<em>Open reviewed SELL order</em></button>'
            )
        return f'<article class="pe-rank-card {card_class}">{content}</article>'

    top_cards = "".join(pe_candidate_card(item, True) for item in pe_top)
    watch_cards = "".join(pe_candidate_card(item, False) for item in pe_watch)
    avoid_cards = "".join(pe_candidate_card(item, False) for item in pe_avoid)
    growth_pe_section = (
        '<section class="panel income-growth-pe-panel"><div class="panel-title">Top 3 PE Sell Candidates For Today</div>'
        '<div class="status pe-scoring-note">Candidates are first filtered for assignment size, existing PE positions, event risk, contract validity, liquidity, premium yield, and trend breakdown. Valid candidates are then scored using 40 points for assignment quality and 60 points for PE trade quality. Click an approved card to review a live SELL order.</div>'
        f'<div class="pe-candidate-grid">{top_cards or "<div class=\"status\">No candidate passed every hard filter today.</div>"}</div></section>'
        f'<details class="panel income-growth-pe-panel"><summary>Watch / Review <span>{len(pe_watch)}</span></summary>'
        f'<div class="pe-candidate-grid">{watch_cards or "<div class=\"status\">No additional valid candidates.</div>"}</div></details>'
        f'<details class="panel income-growth-pe-panel avoid-today-panel"><summary>Avoid Today <span>{len(pe_avoid)}</span></summary>'
        f'<div class="pe-candidate-grid">{avoid_cards or "<div class=\"status\">No hard-rejected candidates.</div>"}</div></details>'
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
          <p class="status">Cached decision dashboard for current option exposure and the strongest cash-secured PE opportunities. Recalculate only when you need a fresh market scan.</p>
        </div>
        <div class="actions">
          <button type="submit" formaction="/income/load">Recalculate Best 3 PE SELL</button>
        </div>
      </section>
      <section class="panel income-pnl-panel"><div class="panel-title">Income Decision Summary</div><div class="income-pnl-grid">{pnl_summary_html}</div></section>
      {positions_table}
      {growth_pe_section}
      {render_results(state.income_results)}
      <div class="live-modal-backdrop" id="income-pe-order-modal">
        <div class="live-modal income-pe-order-modal-card">
          <h2 id="income-pe-order-title">Cash-Secured PE SELL</h2>
          <p class="status">Fresh Kite premium is loaded when the candidate opens. The limit order is set {option_sell_markup:.2f}% above LTP.</p>
          <div class="quote-loading-state active" id="income-pe-loading" role="status" aria-live="polite">
            <span class="backend-spinner" aria-hidden="true"></span>
            <strong>Recalculating PE contract, premium, cash requirement, and risk...</strong>
          </div>
          <div class="income-equity-metrics">
            <div><span>Option</span><strong id="income-pe-option">--</strong></div>
            <div><span>Fresh LTP</span><strong id="income-pe-ltp">--</strong></div>
            <div><span>SELL limit +{option_sell_markup:.2f}%</span><strong id="income-pe-limit">--</strong></div>
            <div><span>Quantity</span><strong id="income-pe-quantity">--</strong></div>
            <div><span>Expiry</span><strong id="income-pe-expiry">--</strong></div>
            <div><span>Assignment cash</span><strong id="income-pe-assignment">--</strong></div>
            <div><span>Maximum profit</span><strong id="income-pe-max-profit">--</strong></div>
            <div><span>Premium yield</span><strong id="income-pe-yield">--</strong></div>
          </div>
          <div class="income-equity-order-summary" id="income-pe-summary">Loading fresh PE contract and premium...</div>
          <input type="hidden" name="income_underlying" id="income-pe-underlying">
          <input type="hidden" name="income_target_strike" id="income-pe-target-strike">
          <input type="hidden" name="income_pe_confirmed" id="income-pe-confirmed" value="0">
          <div class="breath-circle income-pe-breath" id="income-pe-breath"></div>
          <div class="breath-text" id="income-pe-breath-text">Review order first</div>
          <div class="countdown" id="income-pe-countdown">10</div>
          <div class="modal-actions">
            <button type="button" class="secondary" id="income-pe-cancel">Cancel</button>
            <button type="button" id="income-pe-review" disabled>Submit &amp; Start 10s</button>
            <button type="submit" class="danger" formaction="/income/sell-pe" id="income-pe-go" disabled>GO</button>
          </div>
        </div>
      </div>
      <details class="panel income-playbook">
        <summary>Strategy Rules &amp; Entry / Exit Playbook</summary>
        <div class="income-rule-grid">{rule_cards}</div>
        <div class="income-filter-grid">{filter_html}</div>
      </details>
      {('<section class="panel">' + render_graceful_error(state.income_error, "INCOME Error") + '</section>') if state.income_error else ''}
      {render_collapsed_console(state.console_log)}
    </form>"""


def env_hidden_fields_for_render() -> str:
    return (
        f'<input type="hidden" name="kite_profile" value="{html.escape(selected_kite_profile_name(), quote=True)}">'
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


def render_collapsed_console(console_log: str) -> str:
    if not console_log.strip():
        return ""
    return (
        '<details class="panel console-details"><summary>View Kite Console</summary>'
        f'<pre class="console">{html.escape(console_log)}</pre></details>'
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
    underlyings = home_tickers_setting()
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
    global_quote_cards = "".join(
        '<div class="global-card" data-global-symbol="'
        f'{html.escape(str(item["symbol"]), quote=True)}">'
        f'<span class="global-label">{html.escape(str(item["label"]))}</span>'
        '<span class="global-ltp">...</span>'
        '<span class="global-change">--</span>'
        "</div>"
        for item in GLOBAL_MARKET_WATCHLIST
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
    pnl_summary = monthly_booked_pnl_summary()
    pnl_class = "pnl-positive" if float(pnl_summary["overall_pnl"]) >= 0 else "pnl-negative"
    today_class = "pnl-positive" if float(pnl_summary["today_pnl"]) >= 0 else "pnl-negative"
    pnl_cards = (
        f'<div class="home-pnl-card featured"><span>{html.escape(pnl_summary["month_label"])} - Monthly P&L</span>'
        f'<strong class="{pnl_class}">{html.escape(display_cell("pnl", pnl_summary["overall_pnl"]))}</strong>'
        f'<small>{int(pnl_summary["trade_count"])} booked close trade(s)</small></div>'
        f'<div class="home-pnl-card"><span>Trading booked</span><strong>{html.escape(display_cell("pnl", pnl_summary["trading_pnl"]))}</strong></div>'
        f'<div class="home-pnl-card"><span>Income booked</span><strong>{html.escape(display_cell("pnl", pnl_summary["income_pnl"]))}</strong></div>'
        f'<div class="home-pnl-card"><span>Today booked</span><strong class="{today_class}">{html.escape(display_cell("pnl", pnl_summary["today_pnl"]))}</strong>'
        f'<small>{int(pnl_summary["today_count"])} close(s)</small></div>'
    )
    return f"""
    <section class="market-shell top-command-center">
      <div class="home-hero">
        <div>
          <div class="home-kicker">Today decision cockpit</div>
          <h2>Should I sell premium today, close risk, or wait?</h2>
          <p>Use this screen first. It combines MMI, Indian indices, global cues, expiry distance, and your watchlist movement into one calm pre-trade view.</p>
        </div>
        <div class="home-hero-date">{quote_date}</div>
      </div>
      <div class="home-pnl-strip">{pnl_cards}</div>
      <div class="home-decision-grid">
        <div class="decision-tile decision-primary" id="home-bias-card">
          <span>Market bias</span>
          <strong id="home-bias">Checking...</strong>
          <small id="home-bias-detail">Waiting for MMI and global cues.</small>
        </div>
        <div class="decision-tile" id="home-new-position-card">
          <span>New position gate</span>
          <strong id="home-new-position">Wait for data</strong>
          <small id="home-new-position-detail">Avoid entries near expiry or when global risk is red.</small>
        </div>
        <div class="decision-tile" id="home-close-card">
          <span>Close / roll focus</span>
          <strong id="home-close-focus">Review positions</strong>
          <small>Book sold options at 50-70% capture. Roll before gamma risk rises.</small>
        </div>
        <div class="decision-tile mmi-card">
          <span>Market Mood Index</span>
          <strong id="mmi-value">Loading...</strong>
          <small><span id="mmi-zone">Tickertape MMI</span><span id="mmi-action"> | Signal: <strong>Checking...</strong></span></small>
          <a href="{MMI_URL}" target="_blank" rel="noopener">Open MMI</a>
        </div>
      </div>
      <div class="rule-strip compact-rules">
        <div class="rule-card sell-stock">
          <div class="rule-kicker">Rule 1</div>
          <div class="rule-title">SELL CALL only when you hold the stock with lot size</div>
        </div>
        <div class="rule-card sell-put">
          <div class="rule-kicker">Rule 2</div>
          <div class="rule-title">SELL PUT only when you have cash to buy all lots</div>
        </div>
      </div>
      <div class="global-market-strip">
        <div class="global-market-title">Market cues <button type="button" class="mini-refresh-button" id="refresh-global-quotes">Refresh</button></div>
        <div class="global-error" id="global-error"></div>
        <div class="global-grid" id="global-grid">{global_quote_cards}</div>
      </div>
      <details class="ticker-disclosure" id="kite-ltp-disclosure">
        <summary>
          <span>Kite LTP and Day Change | {quote_date}</span>
          <strong>Open details</strong>
        </summary>
        <div class="ticker-panel">
          <div class="ticker-title live-title">Selected Kite watchlist <button type="button" class="mini-refresh-button" id="refresh-market-quotes">Refresh now</button></div>
          <div class="quote-error" id="quote-error"></div>
          <div class="quote-grid" id="quote-grid">{quote_cards}</div>
        </div>
      </details>
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

    orders_table = render_orders_table(state.orders, state.selected_indexes, state.trade_validations)
    trade_validation_table = render_trade_validation_table(state.trade_validations)
    position_orders_table = render_position_orders_table(
        state.position_orders, state.position_selected_indexes
    )
    execute_button = (
        '<button type="submit" formaction="/execute" class="danger" id="execute-selected-button">Execute Selected</button>'
        if state.rows
        else ""
    )
    execution_checks = (
        '<div class="execution-checks">'
        f'{render_checkbox("dry_run", "Dry run", state.dry_run, "Build orders and show what would happen without sending anything to Kite.")}'
        f'{render_checkbox("no_ltp_price", "Use CSV/manual price only", state.no_ltp_price, "Leave this on when the CSV already has prices or lot_size. Turn off to fetch LTP/lot size from Kite.")}'
        f'{render_checkbox("keep_existing_orders", "Always place new order", state.keep_existing_orders, "Turn off to modify a similar open order when found; if no modifiable order exists, the app places a new order.")}'
        "</div>"
    )
    execute_after_orders = (
        f'<div class="actions order-execute-actions">{execute_button}</div>{execution_checks}'
        if execute_button
        else ""
    )
    position_execute_button = (
        '<button type="submit" formaction="/positions/execute" class="danger" id="position-execute-selected-button">Execute Selected BUY</button>'
        if state.position_orders
        else ""
    )
    home_tab_class = "active" if state.active_tab == "home" else ""
    place_tab_class = "active" if state.active_tab == "place" else ""
    positions_tab_class = "active" if state.active_tab in {"positions", "positions-research"} else ""
    gpt_tab_class = "active" if state.active_tab == "gpt" else ""
    kite_setup_tab_class = "active" if state.active_tab == "kite-setup" else ""
    analytics_tab_class = "active" if state.active_tab == "analytics" else ""
    research_tab_class = "active" if state.active_tab == "research" else ""
    commodity_tab_class = "active" if state.active_tab == "commodity" else ""
    income_tab_class = "active" if state.active_tab == "income" else ""
    order_management_tab_class = "active" if state.active_tab == "order-management" else ""
    investing_tab_class = "active" if state.active_tab == "investing" else ""
    income_growth_tab_class = "active" if state.active_tab == "income-growth" else ""
    equity_tab_class = "active" if state.active_tab == "equity" else ""
    place_panel_style = "" if state.active_tab == "place" else ' style="display:none"'
    gpt_panel_style = "" if state.active_tab == "gpt" else ' style="display:none"'
    kite_setup_panel_style = "" if state.active_tab == "kite-setup" else ' style="display:none"'
    home_market_html = render_market_topper(state) if state.active_tab == "home" else ""
    kite_profiles = load_kite_profiles()
    active_kite_profile = selected_kite_profile_name(state.kite_profile)
    active_kite_values = kite_profiles.get(active_kite_profile, blank_kite_profile())
    active_profile_ready = all(
        str(active_kite_values.get(key) or "").strip()
        for key in ("KITE_API_KEY", "KITE_API_SECRET", "KITE_ACCESS_TOKEN")
    )
    active_profile_class = "ready" if active_profile_ready else "needs-setup"
    active_profile_hint = "Ready" if active_profile_ready else "Setup needed"
    if state.active_tab == "kite-setup":
        active_kite_values = {
            "KITE_API_KEY": state.api_key
            if state.api_key != ""
            else active_kite_values.get("KITE_API_KEY", ""),
            "KITE_API_SECRET": state.api_secret
            if state.api_secret != ""
            else active_kite_values.get("KITE_API_SECRET", ""),
            "KITE_ACCESS_TOKEN": state.access_token
            if state.access_token != ""
            else active_kite_values.get("KITE_ACCESS_TOKEN", ""),
            "KITE_CONFIRM_LIVE_ORDER": state.confirm_live_order
            if state.confirm_live_order != ""
            else active_kite_values.get("KITE_CONFIRM_LIVE_ORDER", "YES"),
        }
        kite_profiles[active_kite_profile] = active_kite_values
    kite_profiles_json = html.escape(json.dumps(kite_profiles), quote=True)
    profile_options = "".join(
        f'<option value="{html.escape(name, quote=True)}"{" selected" if name == active_kite_profile else ""}>{html.escape(name)}</option>'
        for name in KITE_PROFILE_NAMES
    )
    active_login_url = (
        "https://kite.zerodha.com/connect/login?"
        f"api_key={quote_plus(active_kite_values.get('KITE_API_KEY') or '')}&v=3"
    )
    def kite_env_input(name: str, label: str, env_key: str, input_type: str = "text") -> str:
        safe_value = html.escape(active_kite_values.get(env_key, ""), quote=True)
        secret_class = " secret-field" if input_type == "password" else ""
        input_id = f"kite-{name.replace('_', '-')}"
        return (
            f'<label><span>{html.escape(label)}</span>'
            f'<input id="{input_id}" class="{secret_class}" name="{name}" type="{input_type}" '
            f'value="{safe_value}" autocomplete="off"></label>'
        )
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
            <div class="profile-selector-row">
              <label><span>Kite Profile</span>
                <select id="kite-profile-select" name="kite_profile" data-profiles="{kite_profiles_json}" autocomplete="off">
                  {profile_options}
                </select>
              </label>
              <div class="profile-note">
                <strong id="kite-profile-note-name">{html.escape(active_kite_profile)}</strong>
                <span id="kite-profile-note-status">credentials are used for login, token generation, quotes, and order actions.</span>
              </div>
            </div>
            <div class="compact-grid">
              {kite_env_input("api_key", "KITE_API_KEY", "KITE_API_KEY")}
              {kite_env_input("confirm_live_order", "KITE_CONFIRM_LIVE_ORDER", "KITE_CONFIRM_LIVE_ORDER")}
              {kite_env_input("api_secret", "KITE_API_SECRET", "KITE_API_SECRET", "password")}
              {kite_env_input("access_token", "KITE_ACCESS_TOKEN", "KITE_ACCESS_TOKEN", "password")}
            </div>
            <div class="actions compact-actions">
              <button type="submit" formaction="/kite-token/save">Save Access Token</button>
            </div>
            {render_checkbox("show_credentials", "Show credential values", False, "Reveals KITE_API_SECRET, KITE_ACCESS_TOKEN, and OPENAI_API_KEY in this local browser page.")}
          </section>
          <section class="panel kite-setup-card token-card">
            <div class="setup-card-kicker">02</div>
            <div class="panel-title">Access Token</div>
            <p class="status">Open Kite login, paste the full redirected URL or only <code>request_token</code>, then generate and save today's token.</p>
            <div class="actions">
              <a id="kite-login-link" class="button-link" href="{html.escape(active_login_url, quote=True)}" target="_blank" rel="noopener">Open Kite Login</a>
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
            {render_number_input("option_sell_markup_percent", "Option SELL limit markup %", state.option_sell_markup_percent, "0.05")}
            <p class="status">Used by Trading Top 3 CE SELL and INCOME PE SELL cards. Default is 20% above fresh option LTP.</p>
            <div class="kite-action-preview">{html.escape(etf_buy_action)}</div>
            <p class="status">Saved in <code>{html.escape(str(SETTINGS_PATH.name))}</code>.</p>
          </section>
          <section class="panel kite-setup-card watchlist-card">
            <div class="setup-card-kicker">04</div>
            <div class="panel-title">Home Watchlist</div>
            <p class="status">One ticker per line or comma-separated. These decide which Kite LTP cards appear on Home.</p>
            <label><span>Home tickers</span><textarea class="watchlist-box" name="home_tickers">{html.escape(state.home_tickers)}</textarea></label>
          </section>
          <section class="panel kite-setup-card ip-card">
            <div class="setup-card-kicker">05</div>
            <div class="panel-title">OpenAI Setup</div>
            <p class="status">Used by the GPT tab to generate Kite-ready CSV from your strategy prompt.</p>
            {render_input("openai_api_key", "OPENAI_API_KEY", state.openai_api_key or env_value("OPENAI_API_KEY"), "password")}
            {render_checkbox("show_credentials", "Show OPENAI_API_KEY", False, "Temporarily reveals the OpenAI key in this browser.")}
            <p class="status">Saved to <code>.env</code> when you click Save Kite Setup.</p>
          </section>
          <section class="panel kite-setup-card ip-card">
            <div class="setup-card-kicker">06</div>
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
    .profile-header-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 6px;
      padding: 5px 9px;
      border-radius: 999px;
      border: 1px solid rgba(153, 246, 228, 0.32);
      background: rgba(236, 254, 255, 0.12);
      color: #e0f2fe;
      font-size: 11px;
      font-weight: 900;
      line-height: 1;
    }}
    .profile-header-pill.ready strong {{ color: #bbf7d0; }}
    .profile-header-pill.needs-setup strong {{ color: #fecaca; }}
    .profile-header-pill span {{
      color: #cbd5e1;
      font-weight: 800;
    }}
    main {{
      width: min(1480px, calc(100vw - 28px));
      margin: 22px auto 40px;
    }}
    .market-shell {{
      margin-bottom: 18px;
      padding: 16px;
      border: 1px solid #bde8e3;
      border-radius: 22px;
      background:
        radial-gradient(circle at top left, rgba(56, 189, 248, 0.18), transparent 28%),
        radial-gradient(circle at bottom right, rgba(34, 197, 94, 0.14), transparent 30%),
        linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(236, 254, 255, 0.84)),
        #ffffff;
      box-shadow: 0 22px 54px rgba(15, 23, 42, 0.10);
    }}
    .home-hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: center;
      margin-bottom: 12px;
      padding: 14px 16px;
      border-radius: 18px;
      background: linear-gradient(135deg, #0f172a 0%, #134e4a 58%, #0f766e 100%);
      color: #ffffff;
      box-shadow: 0 18px 38px rgba(15, 23, 42, 0.16);
    }}
    .home-kicker {{
      color: #99f6e4;
      font-size: 10px;
      font-weight: 950;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }}
    .home-hero h2 {{
      margin: 0;
      font-size: 24px;
      line-height: 1.08;
      letter-spacing: 0;
    }}
    .home-hero p {{
      margin: 6px 0 0;
      color: #d1fae5;
      font-size: 12.5px;
      max-width: 760px;
      line-height: 1.35;
    }}
    .home-hero-date {{
      padding: 8px 10px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
      color: #ecfeff;
      font-weight: 900;
      white-space: nowrap;
    }}
    .home-pnl-strip {{
      display: grid;
      grid-template-columns: minmax(260px, 1.35fr) repeat(3, minmax(160px, 1fr));
      gap: 10px;
      margin-bottom: 10px;
    }}
    .home-pnl-card {{
      padding: 12px 14px;
      border: 1px solid #bfdbfe;
      border-radius: 16px;
      background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
      box-shadow: 0 10px 22px rgba(15, 23, 42, 0.06);
    }}
    .home-pnl-card.featured {{
      border-color: #86efac;
      background: linear-gradient(135deg, #ecfdf5 0%, #f0fdfa 100%);
    }}
    .home-pnl-card span,
    .home-pnl-card small {{
      display: block;
      color: #64748b;
      font-size: 10.5px;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }}
    .home-pnl-card strong {{
      display: block;
      margin: 4px 0;
      color: #07152b;
      font-size: 20px;
      font-weight: 950;
    }}
    .home-decision-grid {{
      display: grid;
      grid-template-columns: minmax(260px, 1.25fr) minmax(240px, 1fr) minmax(240px, 1fr) minmax(220px, 0.9fr);
      gap: 10px;
      margin-bottom: 10px;
    }}
    .decision-tile {{
      min-height: 116px;
      padding: 14px;
      border: 1px solid #cde9e5;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.92);
      box-shadow: 0 12px 28px rgba(15, 23, 42, 0.07);
    }}
    .decision-tile span {{
      display: block;
      color: #64748b;
      font-size: 10px;
      font-weight: 950;
      text-transform: uppercase;
      margin-bottom: 7px;
    }}
    .decision-tile strong {{
      display: block;
      color: #07152b;
      font-size: 20px;
      line-height: 1.05;
      margin-bottom: 8px;
    }}
    .decision-tile small {{
      display: block;
      color: #475569;
      font-size: 12px;
      line-height: 1.3;
    }}
    .decision-tile.mmi-card span,
    .decision-tile.mmi-card strong,
    .decision-tile.mmi-card small {{
      color: #4c1d95;
    }}
    .decision-tile.mmi-card a {{
      display: inline-block;
      margin-top: 6px;
      color: #5b21b6;
      font-size: 11px;
      font-weight: 900;
    }}
    .decision-primary {{
      background: linear-gradient(135deg, #ecfeff 0%, #dcfce7 100%);
      border-color: #99f6e4;
    }}
    .decision-green {{
      background: #ecfdf5;
      border-color: #86efac;
    }}
    .decision-yellow {{
      background: #fffbeb;
      border-color: #fde68a;
    }}
    .decision-red {{
      background: #fff1f2;
      border-color: #fda4af;
    }}
    .home-action-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 10px;
    }}
    .home-action-card {{
      display: block;
      text-decoration: none;
      padding: 12px;
      border-radius: 14px;
      border: 1px solid #bae6fd;
      background: linear-gradient(135deg, #ffffff 0%, #f0f9ff 100%);
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
    }}
    .home-action-card strong {{
      display: block;
      color: #075985;
      margin-bottom: 5px;
      font-size: 13px;
    }}
    .home-action-card span {{
      display: block;
      color: #475569;
      font-size: 12px;
      line-height: 1.35;
    }}
    .rule-strip {{
      display: grid;
      grid-template-columns: 1.1fr 1.1fr 0.9fr;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .compact-rules {{
      grid-template-columns: 1fr 1fr;
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
      display: grid;
      grid-template-columns: minmax(62px, 1fr) auto minmax(48px, auto);
      align-items: center;
      gap: 7px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 8px;
      background: #f8fafc;
      min-height: 28px;
      overflow: hidden;
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
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .quote-ltp {{
      font-size: 12px;
      font-weight: 900;
      white-space: nowrap;
    }}
    .quote-change {{ 
      justify-self: end;
      border-radius: 999px;
      padding: 2px 5px;
      background: #eef2f7;
      font-size: 10.5px;
      font-weight: 950;
      color: var(--muted);
      white-space: nowrap;
    }}
    .quote-change.up {{ color: #047857; background: #dcfce7; }}
    .quote-change.down {{ color: #b42318; background: #fee2e2; }}
    .global-market-strip {{
      margin: 0 0 8px;
      padding: 10px 12px;
      border: 1px solid rgba(15, 118, 110, 0.16);
      border-radius: 15px;
      background: linear-gradient(135deg, rgba(240, 253, 250, 0.92), rgba(239, 246, 255, 0.92));
      display: grid;
      grid-template-columns: 110px 1fr;
      gap: 10px;
      align-items: start;
    }}
    .global-market-title {{
      color: #0f766e;
      font-size: 10px;
      font-weight: 900;
      text-transform: uppercase;
      white-space: nowrap;
      padding-top: 6px;
    }}
    .global-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
      gap: 6px;
      align-items: center;
    }}
    .global-card {{
      display: grid;
      grid-template-columns: 1fr auto;
      align-items: center;
      gap: 4px 8px;
      min-height: 42px;
      padding: 6px 9px;
      border-radius: 12px;
      border: 1px solid #c7d2fe;
      background: #f8fafc;
    }}
    .global-card.up {{
      border-color: #86efac;
      background: #ecfdf5;
    }}
    .global-card.down {{
      border-color: #fca5a5;
      background: #fff1f2;
    }}
    .global-label {{
      color: #334155;
      font-size: 9.5px;
      font-weight: 900;
      text-transform: uppercase;
    }}
    .global-ltp {{
      font-size: 13px;
      font-weight: 950;
      color: #07152b;
    }}
    .global-change {{
      grid-column: 1 / -1;
      font-size: 10px;
      font-weight: 900;
      color: #64748b;
    }}
    .global-change.up {{ color: #047857; }}
    .global-change.down {{ color: #b42318; }}
    .global-error {{
      display: none;
      grid-column: 1 / -1;
      color: #991b1b;
      font-size: 11px;
      font-weight: 800;
    }}
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
      padding: 14px;
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
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(178px, 1fr));
      gap: 6px;
      padding: 8px 10px 10px;
    }}
    .top-command-center .quote-card {{
      grid-template-columns: minmax(78px, 1fr) auto minmax(52px, auto);
      min-height: 36px;
      gap: 7px;
      padding: 6px 8px;
      border-radius: 11px;
      min-width: 0;
    }}
    .top-command-center .quote-symbol {{
      font-size: 9px;
    }}
    .top-command-center .quote-ltp {{
      font-size: 13px;
    }}
    .top-command-center .quote-change {{
      font-size: 10.5px;
      padding: 2px 6px;
    }}
    .ticker-disclosure {{
      margin-top: 10px;
      border: 1px solid #bae6fd;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.72);
      overflow: hidden;
    }}
    .ticker-disclosure summary {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 11px 14px;
      color: #075985;
      cursor: pointer;
      font-size: 13px;
      font-weight: 900;
      list-style: none;
    }}
    .ticker-disclosure summary::-webkit-details-marker {{ display: none; }}
    .ticker-disclosure summary strong {{
      padding: 4px 9px;
      border-radius: 999px;
      color: #0f766e;
      background: #ccfbf1;
      font-size: 10px;
      text-transform: uppercase;
    }}
    .ticker-disclosure[open] summary {{
      border-bottom: 1px solid #dbeafe;
      background: #f0fdfa;
    }}
    .ticker-disclosure .ticker-panel {{ margin: 0; border: 0; border-radius: 0; box-shadow: none; }}
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
      background: linear-gradient(135deg, #ecfdf5 0%, #dcfce7 100%);
      border-color: #22c55e;
      box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.20), 0 16px 36px rgba(21, 128, 61, 0.16);
    }}
    .commodity-card.below-200-dma {{
      background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
      border-color: #4ade80;
      box-shadow: 0 0 0 2px rgba(74, 222, 128, 0.16), 0 14px 30px rgba(21, 128, 61, 0.12);
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
    .commodity-dma {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
      color: #0f3b65;
      font-size: 11px;
      font-weight: 900;
    }}
    .commodity-dma span {{
      border: 1px solid #cfe4f3;
      border-radius: 999px;
      padding: 4px 7px;
      background: #f0f9ff;
      white-space: nowrap;
    }}
    .commodity-card.below-200-dma .commodity-dma .dma-200 {{
      border-color: #22c55e;
      background: #bbf7d0;
      color: #166534;
    }}
    .commodity-card.below-200-dma:not(.buy-now) .commodity-action {{
      background: #dcfce7;
      color: #166534;
      border: 1px solid #86efac;
    }}
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
      background: #15803d;
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
      background: linear-gradient(135deg, #16a34a, #0f766e);
      box-shadow: 0 8px 22px rgba(21, 128, 61, 0.22);
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
    .income-current-positions {{
      border-color: #99f6e4;
      background: linear-gradient(135deg, #ffffff 0%, #f0fdfa 100%);
    }}
    .income-current-positions table {{
      min-width: 620px;
    }}
    .income-current-positions th {{
      background: linear-gradient(135deg, #0f4c5c, #0f766e);
      color: #ffffff;
    }}
    .income-growth-pe-panel > summary,
    .income-playbook > summary,
    .console-details > summary {{
      cursor: pointer;
      color: #0f4c5c;
      font-size: 15px;
      font-weight: 900;
      list-style-position: inside;
    }}
    .income-growth-pe-panel > summary span {{
      display: inline-block;
      min-width: 24px;
      margin-left: 6px;
      padding: 2px 7px;
      border-radius: 999px;
      background: #ccfbf1;
      color: #0f766e;
      font-size: 11px;
      text-align: center;
    }}
    .income-growth-pe-panel[open] > summary,
    .income-playbook[open] > summary,
    .console-details[open] > summary {{
      margin-bottom: 12px;
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
    .investing-hero-panel {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
      padding: 12px 16px;
      border-color: #86efac;
      background:
        radial-gradient(circle at 12% 0%, rgba(34, 197, 94, 0.14), transparent 32%),
        linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 48%, #f8fffb 100%);
      box-shadow: 0 18px 38px rgba(22, 101, 52, 0.08);
    }}
    .investing-hero-panel .panel-title {{
      font-size: 16px;
    }}
    .investing-hero-panel .status {{
      margin-top: 4px;
      font-size: 12px;
    }}
    .investing-summary-panel {{
      border-color: #bbf7d0;
      background:
        radial-gradient(circle at top right, rgba(187, 247, 208, 0.44), transparent 34%),
        linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
      padding: 10px 12px;
    }}
    .investing-summary-panel .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(160px, 1fr));
      gap: 10px;
    }}
    .investing-summary-card {{
      min-height: 76px;
      padding: 10px 12px;
      border: 1px solid #bbf7d0;
      border-radius: 12px;
      background: linear-gradient(135deg, #ffffff 0%, #ecfdf5 100%);
      box-shadow: 0 12px 28px rgba(22, 101, 52, 0.08);
    }}
    .investing-summary-card.highlight {{
      border-color: #86efac;
      background: linear-gradient(135deg, #dcfce7 0%, #f0fdf4 100%);
    }}
    .investing-summary-card span,
    .investing-summary-card small {{
      display: block;
      color: #64748b;
      font-size: 9.5px;
      font-weight: 900;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }}
    .investing-summary-card strong {{
      display: block;
      margin: 5px 0 3px;
      color: #065f46;
      font-size: 19px;
      font-weight: 950;
      line-height: 1.05;
      overflow-wrap: anywhere;
    }}
    .investing-table-panel {{
      border-color: #a7f3d0;
      background: linear-gradient(135deg, #ffffff 0%, #f8fffd 100%);
    }}
    .investing-table {{
      min-width: 1780px;
    }}
    .investing-table th {{
      background: linear-gradient(135deg, #0f4c5c, #0f766e);
      color: #ffffff;
      font-size: 11px;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .investing-table .sort-header,
    .income-growth-table .sort-header {{
      width: 100%;
      padding: 0;
      border: 0;
      background: transparent;
      color: #ffffff;
      cursor: pointer;
      font: inherit;
      font-weight: 950;
      letter-spacing: inherit;
      text-align: left;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .investing-table .sort-header::after,
    .income-growth-table .sort-header::after {{
      content: "  ↕";
      color: #bbf7d0;
      font-size: 10px;
    }}
    .investing-table .sort-header[data-sort-dir="asc"]::after,
    .income-growth-table .sort-header[data-sort-dir="asc"]::after {{
      content: "  ↑";
    }}
    .investing-table .sort-header[data-sort-dir="desc"]::after,
    .income-growth-table .sort-header[data-sort-dir="desc"]::after {{
      content: "  ↓";
    }}
    .income-growth-hero {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      border-color: #86efac;
      background:
        radial-gradient(circle at 12% 0%, rgba(45, 212, 191, 0.16), transparent 32%),
        linear-gradient(135deg, #ecfeff 0%, #f0fdf4 52%, #ffffff 100%);
    }}
    .income-growth-table-panel {{
      border-color: #99f6e4;
      background: linear-gradient(135deg, #ffffff 0%, #f0fdfa 100%);
    }}
    .income-growth-gpt-result {{
      border-color: #7dd3fc;
      background:
        radial-gradient(circle at top right, rgba(125, 211, 252, 0.24), transparent 34%),
        linear-gradient(135deg, #f0fdfa 0%, #eff6ff 100%);
    }}
    .income-growth-gpt-result textarea {{
      min-height: 118px;
      font-family: Consolas, "Courier New", monospace;
    }}
    .income-growth-pe-panel {{
      border-color: #a7f3d0;
      background:
        radial-gradient(circle at top left, rgba(16, 185, 129, 0.16), transparent 30%),
        linear-gradient(135deg, #ffffff 0%, #ecfdf5 100%);
    }}
    .income-growth-update-panel {{
      border-color: #bae6fd;
      background:
        radial-gradient(circle at 100% 0%, rgba(56, 189, 248, 0.14), transparent 30%),
        linear-gradient(135deg, #ffffff 0%, #f0fdfa 100%);
    }}
    .compact-form-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(120px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }}
    .compact-form-grid label span {{
      display: block;
      margin-bottom: 4px;
      color: #475569;
      font-size: 10px;
      font-weight: 900;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .compact-form-grid input {{
      min-height: 34px;
      padding: 7px 9px;
      border: 1px solid #cbd5e1;
      border-radius: 9px;
      background: rgba(255, 255, 255, 0.9);
      font: inherit;
      font-size: 12px;
      font-weight: 750;
      width: 100%;
      box-sizing: border-box;
    }}
    .pe-candidate-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(220px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }}
    .pe-candidate-card {{
      border: 1px solid rgba(15, 118, 110, 0.18);
      border-radius: 12px;
      padding: 11px 12px;
      box-shadow: 0 12px 28px rgba(15, 118, 110, 0.08);
      color: inherit;
      font: inherit;
      text-align: left;
      cursor: pointer;
      width: 100%;
    }}
    .pe-candidate-card:hover {{ transform: translateY(-1px); box-shadow: 0 15px 32px rgba(15, 118, 110, 0.14); }}
    .pe-candidate-card div {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
    }}
    .pe-candidate-card strong {{
      display: block;
      font-size: 15px;
      font-weight: 950;
    }}
    .pe-candidate-card span {{
      display: block;
      color: #475569;
      font-size: 10px;
      font-weight: 950;
      text-transform: uppercase;
    }}
    .pe-candidate-card p {{
      margin: 8px 0 5px;
      font-size: 12px;
      font-weight: 850;
    }}
    .pe-candidate-card small,
    .pe-candidate-card em {{
      display: block;
      color: #334155;
      font-size: 10.5px;
      line-height: 1.35;
    }}
    .pe-candidate-card em {{
      margin-top: 6px;
      color: #047857;
      font-style: normal;
      font-weight: 850;
    }}
    .pe-scoring-note {{
      margin: 8px 0 12px;
      padding: 10px 12px;
      border: 1px solid #99f6e4;
      border-radius: 8px;
      background: #f0fdfa;
      color: #134e4a;
    }}
    .pe-rank-card {{
      appearance: none;
      width: 100%;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      padding: 12px;
      text-align: left;
      color: #0f172a;
      background: #fff;
    }}
    button.pe-rank-card {{ cursor: pointer; }}
    button.pe-rank-card:hover {{ border-color: #0f766e; box-shadow: 0 8px 20px rgba(15, 118, 110, .12); }}
    .pe-rank-card.validation-green {{ background: #ecfdf5; border-color: #86efac; }}
    .pe-rank-card.validation-yellow {{ background: #fffbeb; border-color: #fde68a; }}
    .pe-rank-card.validation-red {{ background: #fff1f2; border-color: #fecaca; }}
    .pe-rank-card-head, .pe-score-split {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
    }}
    .pe-rank-card-head strong {{ color: #006b5f; font-size: 17px; }}
    .pe-rank-card-head span {{ font-weight: 800; }}
    .pe-score-split {{ margin: 8px 0; font-size: 12px; color: #475569; }}
    .pe-rank-metrics {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 5px 10px;
    }}
    .pe-rank-metrics span {{ color: #64748b; font-size: 11px; }}
    .pe-rank-metrics strong {{ display: block; color: #0f172a; font-size: 13px; overflow-wrap: anywhere; }}
    .pe-rank-card p {{ margin: 9px 0 0; font-size: 12px; color: #475569; }}
    .pe-rank-card em {{ display: block; margin-top: 8px; font-style: normal; font-weight: 800; color: #047857; }}
    .income-growth-prompt-modal {{
      width: min(980px, calc(100vw - 32px));
    }}
    .income-growth-prompt-modal textarea {{
      min-height: 360px;
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
      line-height: 1.35;
    }}
    .income-growth-table {{
      min-width: 2140px;
    }}
    .income-growth-table th {{
      background: linear-gradient(135deg, #0f766e, #166534);
      color: #ffffff;
      font-size: 11px;
      text-transform: uppercase;
      border: 1px solid rgba(6, 95, 70, 0.34);
    }}
    .income-growth-table td {{
      vertical-align: top;
      border: 1px solid rgba(15, 118, 110, 0.18);
    }}
    .income-equity-stock {{
      width: 100%;
      border: 0;
      padding: 0;
      text-align: left;
      color: #00786f;
      background: transparent;
      box-shadow: none;
      cursor: pointer;
    }}
    .income-equity-stock:hover strong {{ text-decoration: underline; }}
    .income-equity-stock strong,
    .income-equity-stock span {{ display: block; }}
    .income-equity-stock strong {{ font-size: 13px; }}
    .income-equity-stock span {{
      margin-top: 2px;
      color: #49627d;
      font-size: 9px;
      font-weight: 700;
    }}
    .income-equity-modal-card {{ width: min(680px, calc(100vw - 24px)); }}
    .equity-hero {{
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      border-left: 5px solid #0284c7; background: linear-gradient(120deg, #eff6ff, #ecfdf5);
    }}
    .equity-summary-grid {{ display: grid; grid-template-columns: repeat(5, minmax(150px, 1fr)); gap: 10px; }}
    .equity-summary-card {{ padding: 10px 12px; border: 1px solid #bae6fd; border-radius: 8px; background: #f8fafc; }}
    .equity-summary-card span, .equity-summary-card strong, .equity-summary-card small {{ display: block; }}
    .equity-summary-card span {{ color: var(--muted); font-size: 11px; font-weight: 800; text-transform: uppercase; }}
    .equity-summary-card strong {{ margin: 4px 0; font-size: 19px; color: #0f172a; }}
    .equity-summary-card small {{ color: var(--muted); font-size: 11px; }}
    .equity-holdings-table {{ min-width: 1040px; }}
    .equity-holdings-table th, .equity-holdings-table td {{ padding: 9px 10px; border-right: 1px solid #dbe7ea; }}
    .equity-holdings-table td span {{ display: block; font-size: 10px; color: var(--muted); }}
    .equity-holdings-table .sort-header {{ border: 0; padding: 0; background: transparent; color: inherit; box-shadow: none; font: inherit; font-weight: 800; text-align: left; }}
    .equity-holdings-table .sort-header::after {{ content: " ↕"; opacity: 0.65; }}
    .equity-holding-stock {{ border: 0; padding: 0; background: transparent; box-shadow: none; color: #047857; text-align: left; cursor: pointer; }}
    .equity-holding-stock:hover strong {{ text-decoration: underline; }}
    .equity-holding-stock strong, .equity-holding-stock span {{ display: block; }}
    .equity-order-modal-card {{ width: min(700px, calc(100vw - 24px)); }}
    .equity-order-breath {{ display: none; }}
    .equity-order-breath.active {{ display: block; }}
    .equity-price-gap {{ padding: 8px 10px; border: 1px solid var(--line); border-radius: 6px; background: #f8fafc; }}
    .equity-price-gap span, .equity-price-gap strong {{ display: block; }}
    .equity-price-gap span {{ color: var(--muted); font-size: 11px; }}
    .equity-price-gap strong {{ margin-top: 5px; font-size: 17px; }}
    .income-equity-metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(110px, 1fr));
      gap: 8px;
      margin: 12px 0;
    }}
    .income-equity-metrics div {{
      padding: 10px;
      border: 1px solid #bde8e3;
      border-radius: 9px;
      background: #f8fafc;
    }}
    .income-equity-metrics span,
    .income-equity-metrics strong {{ display: block; }}
    .income-equity-metrics span {{
      color: #64748b;
      font-size: 10px;
      font-weight: 850;
      text-transform: uppercase;
    }}
    .income-equity-metrics strong {{
      margin-top: 5px;
      color: #083344;
      font-size: 18px;
    }}
    .income-equity-order-summary {{
      margin: 12px 0;
      padding: 10px;
      border: 1px solid #99f6e4;
      border-radius: 9px;
      color: #0f766e;
      background: #ecfdf5;
      font-weight: 850;
    }}
    .income-equity-breath {{ display: none; }}
    .income-equity-breath.active {{ display: block; }}
    .income-pe-order-modal-card {{ width: min(680px, calc(100vw - 24px)); }}
    .income-pe-breath {{ display: none; }}
    .income-pe-breath.active {{ display: block; }}
    .quote-loading-state {{
      display: none;
      align-items: center;
      justify-content: center;
      gap: 12px;
      margin: 12px 0;
      padding: 12px 14px;
      border: 1px solid #7dd3fc;
      border-radius: 8px;
      background: #f0f9ff;
      color: #075985;
      text-align: left;
    }}
    .quote-loading-state.active {{ display: flex; }}
    .backend-spinner {{
      width: 24px;
      height: 24px;
      flex: 0 0 24px;
      border: 3px solid #bae6fd;
      border-top-color: #0284c7;
      border-radius: 50%;
      animation: backendSpin 0.8s linear infinite;
    }}
    @keyframes backendSpin {{
      to {{ transform: rotate(360deg); }}
    }}
    .investing-core-pill {{
      display: inline-flex;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 10px;
      font-weight: 950;
      background: #f1f5f9;
      color: #475569;
    }}
    .investing-core-pill.core {{
      background: #dcfce7;
      color: #166534;
    }}
    .investing-core-pill.sat {{
      background: #eef2ff;
      color: #3730a3;
    }}
    .investing-news-cell {{
      min-width: 340px;
      white-space: normal;
      line-height: 1.35;
    }}
    .investing-table td.near-52-high {{
      background: #fee2e2;
      color: #991b1b;
      font-weight: 950;
    }}
    .investing-table td.near-52-low {{
      background: #dcfce7;
      color: #166534;
      font-weight: 950;
    }}
    .muted-cell {{
      color: #64748b;
      font-size: 12px;
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
    .tab-button[data-tab="home"] {{
      --tab-a: #ccfbf1;
      --tab-b: #ecfeff;
      --tab-ink: #0f766e;
      --tab-shadow: rgba(20, 184, 166, 0.14);
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
    .tab-button[data-tab="income-growth"] {{
      --tab-a: #ccfbf1;
      --tab-b: #dcfce7;
      --tab-ink: #0f766e;
      --tab-shadow: rgba(20, 184, 166, 0.16);
    }}
    .tab-button[data-tab="equity"] {{
      --tab-a: #dbeafe;
      --tab-b: #dcfce7;
      --tab-ink: #075985;
      --tab-shadow: rgba(14, 116, 144, 0.16);
    }}
    .tab-button[data-tab="investing"] {{
      --tab-a: #dbeafe;
      --tab-b: #ecfdf5;
      --tab-ink: #0f766e;
      --tab-shadow: rgba(14, 165, 233, 0.14);
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
      grid-template-columns: repeat(10, minmax(0, 1fr));
      gap: 6px;
      padding: 7px;
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
      min-height: 38px;
      padding: 7px 5px;
      color: var(--tab-ink);
      font-size: 12px;
      font-weight: 800;
      text-align: center;
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    .tab-button.primary-action {{
      font-size: 12px;
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
    .score-badge {{
      display: inline-flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-width: 48px;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 950;
      line-height: 1.05;
      text-align: center;
      white-space: nowrap;
    }}
    .score-badge small {{
      display: block;
      margin-top: 2px;
      font-size: 8px;
      font-weight: 950;
      letter-spacing: 0.03em;
    }}
    .score-badge.good {{
      background: #dcfce7;
      color: #166534;
    }}
    .score-badge.ok {{
      background: #fef9c3;
      color: #854d0e;
    }}
    .score-badge.risky {{
      background: #ffedd5;
      color: #9a3412;
    }}
    .score-badge.avoid {{
      background: #fee2e2;
      color: #991b1b;
    }}
    .score-badge.check {{
      background: #e0f2fe;
      color: #075985;
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
      grid-template-columns: repeat(2, minmax(320px, 1fr));
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
      padding: 16px;
    }}
    .kite-setup-card::after {{
      content: "";
      position: absolute;
      width: 84px;
      height: 84px;
      right: -34px;
      top: -34px;
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
    .token-card {{ border-color: #bfdbfe; }}
    .etf-card {{ border-color: #bbf7d0; }}
    .ip-card {{ border-color: #fde68a; }}
    .profile-selector-row {{
      display: grid;
      grid-template-columns: minmax(220px, 0.45fr) 1fr;
      gap: 10px;
      align-items: end;
      margin: 6px 0 12px;
    }}
    .profile-selector-row select {{
      width: 100%;
      min-height: 36px;
      border: 1px solid #bde8e3;
      border-radius: 9px;
      padding: 8px 10px;
      background: #f8fafc;
      color: #083344;
      font-weight: 900;
    }}
    .profile-note {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
      padding: 9px 10px;
      border: 1px solid #99f6e4;
      border-radius: 10px;
      background: linear-gradient(135deg, #ecfeff, #f0fdf4);
      color: #475569;
      font-size: 12px;
    }}
    .profile-note strong {{
      color: #0f766e;
      font-size: 14px;
    }}
    .kite-action-preview {{
      margin-top: 8px;
      padding: 10px;
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
    .graceful-error .error-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 6px 0 2px;
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
    .gpt-response-modal {{
      width: min(860px, calc(100vw - 32px));
    }}
    .gpt-response-modal textarea {{
      min-height: 320px;
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
      line-height: 1.35;
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
    .global-work-overlay {{
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
      background: rgba(15, 23, 42, 0.72);
      backdrop-filter: blur(3px);
      z-index: 200;
      cursor: wait;
    }}
    .global-work-overlay.active {{ display: flex; }}
    .global-work-card {{
      width: min(440px, calc(100vw - 32px));
      display: grid;
      justify-items: center;
      gap: 10px;
      padding: 24px;
      border: 1px solid #7dd3fc;
      border-radius: 8px;
      background: #f8fafc;
      box-shadow: 0 24px 80px rgba(15, 23, 42, 0.42);
      color: #0f4c5c;
      text-align: center;
    }}
    .global-work-card strong {{ font-size: 19px; }}
    .global-work-card span:last-child {{ color: #52627a; font-size: 13px; }}
    .global-work-spinner {{
      width: 42px;
      height: 42px;
      border: 5px solid #bae6fd;
      border-top-color: #0f766e;
      border-radius: 50%;
      animation: backendSpin 0.8s linear infinite;
    }}
    body.global-work-active {{
      overflow: hidden;
      cursor: wait;
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
    .compact-actions {{
      margin-top: 8px;
      margin-bottom: 2px;
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
    .positions-summary-panel {{
      padding: 10px 14px;
      margin-top: 10px;
      margin-bottom: 10px;
    }}
    .position-summary-strip {{
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 8px;
    }}
    .position-summary-chip {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      min-height: 34px;
      padding: 7px 10px;
      border: 1px solid #cfe4df;
      border-radius: 10px;
      background: linear-gradient(135deg, #f8fffd 0%, #ffffff 100%);
    }}
    .position-summary-chip span {{
      color: #64748b;
      font-size: 10.5px;
      font-weight: 900;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .position-summary-chip strong {{
      color: #0f172a;
      font-size: 15px;
      font-weight: 950;
      line-height: 1;
      white-space: nowrap;
    }}
    #positions-panel .calm-hero-panel {{
      padding: 10px 14px;
      margin-bottom: 10px;
    }}
    #positions-panel .calm-hero-panel .calm-quote {{
      margin: 0 0 2px;
      font-size: 15px;
      line-height: 1.15;
    }}
    #positions-panel .calm-hero-panel .status {{
      margin: 0;
      font-size: 11px;
    }}
    #positions-panel .calm-hero-panel .actions {{
      gap: 8px;
    }}
    #positions-panel .calm-hero-panel button {{
      padding: 8px 12px;
      min-height: 34px;
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
    .position-symbol-cell .mini-link {{
      display: inline-block;
      margin-top: 3px;
      color: #1769aa;
      font-size: 10px;
      font-weight: 900;
      text-decoration: underline;
    }}
    .position-symbol-cell .existing-buy-order {{
      display: inline-block;
      width: fit-content;
      margin-top: 5px;
      padding: 3px 6px;
      border: 1px solid #86efac;
      border-radius: 5px;
      background: #dcfce7;
      color: #166534;
      font-size: 9px;
      font-weight: 950;
    }}
    .existing-buy-action {{
      display: inline-block;
      padding: 4px 7px;
      border-radius: 999px;
      background: #dcfce7;
      color: #166534;
      font-size: 9px;
      font-weight: 900;
      white-space: nowrap;
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
      min-width: 1540px;
      table-layout: fixed;
    }}
    .order-book-table td,
    .order-book-table th {{
      white-space: normal;
      overflow-wrap: anywhere;
      vertical-align: top;
    }}
    .order-book-table th:nth-child(1),
    .order-book-table td:nth-child(1) {{ width: 44px; text-align: center; }}
    .order-book-table th:nth-child(2),
    .order-book-table td:nth-child(2) {{ width: 218px; }}
    .order-book-table th:nth-child(3),
    .order-book-table td:nth-child(3) {{ width: 58px; white-space: nowrap; overflow-wrap: normal; word-break: normal; }}
    .order-book-table th:nth-child(4),
    .order-book-table td:nth-child(4) {{ width: 106px; }}
    .order-book-table th:nth-child(5),
    .order-book-table td:nth-child(5) {{ width: 82px; white-space: nowrap; overflow-wrap: normal; word-break: normal; text-align: right; }}
    .order-book-table th:nth-child(6),
    .order-book-table td:nth-child(6) {{ width: 190px; }}
    .order-book-table th:nth-child(7),
    .order-book-table td:nth-child(7) {{ width: 74px; white-space: nowrap; overflow-wrap: normal; word-break: normal; }}
    .order-book-table th:nth-child(8),
    .order-book-table td:nth-child(8) {{ width: 90px; white-space: nowrap; overflow-wrap: normal; word-break: normal; }}
    .order-book-table th:nth-child(9),
    .order-book-table td:nth-child(9) {{ width: 112px; }}
    .order-book-table th:nth-child(10),
    .order-book-table td:nth-child(10) {{ width: 280px; }}
    .order-book-table th:nth-child(11),
    .order-book-table td:nth-child(11) {{ width: 92px; white-space: nowrap; overflow-wrap: normal; word-break: normal; }}
    .order-book-table th:nth-child(12),
    .order-book-table td:nth-child(12) {{ width: 86px; white-space: nowrap; overflow-wrap: normal; word-break: normal; }}
    .order-book-table th:nth-child(13),
    .order-book-table td:nth-child(13) {{ width: 118px; }}
    .order-book-table th:nth-child(14),
    .order-book-table td:nth-child(14) {{ width: 92px; white-space: nowrap; overflow-wrap: normal; word-break: normal; }}
    .order-book-table small {{
      display: block;
      margin-top: 2px;
      color: #475569;
      font-size: 10px;
      font-weight: 750;
      line-height: 1.2;
    }}
    .order-book-table .pnl-positive {{
      background: #ecfdf5;
      color: #047857;
      font-weight: 900;
    }}
    .scheduler-control-panel {{
      grid-column: 1 / -1;
      border-color: #a7f3d0;
    }}
    .scheduler-control-table td {{
      vertical-align: top;
      min-width: 130px;
    }}
    .scheduler-control-table td:first-child {{
      min-width: 190px;
      color: #064e3b;
    }}
    .scheduler-control-table td:first-child small {{
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-weight: 650;
    }}
    .scheduler-job-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      min-width: 210px;
    }}
    .scheduler-job-actions button {{
      padding: 7px 10px;
      font-size: 12px;
    }}
    .order-book-table .pnl-negative {{
      background: #fef2f2;
      color: #b91c1c;
      font-weight: 900;
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
    .price-adjuster {{
      display: grid;
      grid-template-columns: auto minmax(76px, 96px) auto;
      gap: 4px;
      align-items: center;
      min-width: 178px;
    }}
    .price-adjuster .order-edit-input {{
      width: 100%;
      text-align: center;
    }}
    .price-step-button {{
      border: 0;
      border-radius: 6px;
      padding: 6px 7px;
      background: #e0f2fe;
      color: #075985;
      font-size: 11px;
      font-weight: 950;
      cursor: pointer;
      white-space: nowrap;
    }}
    .price-step-button[data-price-step="-3"] {{
      background: #fee2e2;
      color: #991b1b;
    }}
    .price-step-button[data-price-step="3"] {{
      background: #dcfce7;
      color: #047857;
    }}
    .price-step-button:disabled {{
      cursor: not-allowed;
      opacity: 0.5;
    }}
    .mini-refresh-button {{
      margin-left: 8px;
      border: 1px solid rgba(15, 118, 110, 0.24);
      border-radius: 999px;
      padding: 4px 9px;
      background: #ecfeff;
      color: #0f766e;
      font-size: 10px;
      font-weight: 950;
      cursor: pointer;
      vertical-align: middle;
    }}
    .mini-refresh-button:hover {{
      background: #ccfbf1;
    }}
    .order-score {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 64px;
      border-radius: 999px;
      padding: 5px 8px;
      background: #f1f5f9;
      color: #475569;
      font-size: 12px;
      font-weight: 950;
      white-space: nowrap;
    }}
    .order-score.score-4,
    .order-score.score-5 {{
      background: #dcfce7;
      color: #047857;
    }}
    .order-score.score-2,
    .order-score.score-3 {{
      background: #fef9c3;
      color: #a16207;
    }}
    .order-score.score-0,
    .order-score.score-1 {{
      background: #fee2e2;
      color: #b91c1c;
    }}
    .order-suggestion {{
      max-width: 260px;
      border: 1px solid rgba(100, 116, 139, 0.22);
      border-radius: 9px;
      padding: 7px 8px;
      line-height: 1.25;
    }}
    .order-suggestion strong {{
      display: inline-block;
      margin-bottom: 3px;
      font-size: 12px;
      letter-spacing: 0.03em;
    }}
    .order-suggestion span {{
      display: block;
      color: #1f2937;
      font-size: 11px;
      font-weight: 750;
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
    .position-buy-settings {{
      padding: 0;
      overflow: hidden;
      border-color: #b7e4da;
      background: linear-gradient(135deg, #ffffff 0%, #f0fdfa 100%);
    }}
    .position-buy-settings summary {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 16px;
      cursor: pointer;
      list-style: none;
      color: #0f3d56;
      background: linear-gradient(90deg, #ecfeff 0%, #f0fdf4 100%);
    }}
    .position-buy-settings summary::-webkit-details-marker {{
      display: none;
    }}
    .position-buy-settings summary span:first-child {{
      display: grid;
      gap: 2px;
    }}
    .position-buy-settings summary strong {{
      font-size: 14px;
      font-weight: 950;
    }}
    .position-buy-settings summary small {{
      color: #64748b;
      font-size: 11px;
      font-weight: 600;
    }}
    .position-settings-toggle {{
      padding: 6px 10px;
      border: 1px solid #99f6e4;
      border-radius: 999px;
      color: #0f766e;
      background: #ffffff;
      font-size: 11px;
      font-weight: 900;
      white-space: nowrap;
    }}
    .position-buy-settings[open] .position-settings-toggle {{
      color: #475569;
      border-color: #cbd5e1;
    }}
    .position-buy-settings[open] .position-settings-toggle::before {{
      content: "Close ";
    }}
    .position-buy-settings[open] .position-settings-toggle {{
      font-size: 0;
    }}
    .position-buy-settings[open] .position-settings-toggle::before {{
      font-size: 11px;
    }}
    .position-buy-settings-body {{
      display: grid;
      gap: 10px;
      padding: 12px 16px 16px;
      border-top: 1px solid #ccfbf1;
    }}
    .position-settings-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(130px, 1fr));
      gap: 10px;
    }}
    .position-settings-secondary {{
      grid-template-columns: minmax(260px, 2fr) repeat(4, minmax(110px, 1fr));
    }}
    .position-settings-grid label {{
      display: grid;
      align-content: start;
      gap: 4px;
      margin: 0;
      color: #475569;
      font-size: 11px;
      font-weight: 800;
    }}
    .position-settings-grid input {{
      width: 100%;
      min-width: 0;
      min-height: 34px;
      padding: 7px 9px;
      border-color: #cfe4df;
      background: #ffffff;
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
    .watchlist-box {{
      min-height: 118px;
      font-family: Consolas, monospace;
      text-transform: uppercase;
    }}
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
      .home-hero {{ grid-template-columns: 1fr; }}
      .income-equity-metrics {{ grid-template-columns: repeat(2, minmax(110px, 1fr)); }}
      .home-hero h2 {{ font-size: 20px; }}
      .home-pnl-strip {{ grid-template-columns: 1fr; }}
      .home-decision-grid {{ grid-template-columns: 1fr; }}
      .home-action-grid {{ grid-template-columns: 1fr; }}
      .investing-hero-panel {{ align-items: flex-start; flex-direction: column; }}
      .investing-summary-panel .summary-grid {{ grid-template-columns: 1fr; }}
      .equity-hero {{ align-items: flex-start; flex-direction: column; }}
      .equity-summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .position-summary-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .position-summary-chip {{ align-items: flex-start; flex-direction: column; gap: 4px; }}
      .position-settings-grid,
      .position-settings-secondary {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .position-settings-wide {{ grid-column: 1 / -1; }}
      .compact-rules {{ grid-template-columns: 1fr; }}
      .decision-tile {{ min-height: auto; }}
      .tab-button[data-tab="home"] {{ display: inline-flex; }}
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
<body class="tab-{html.escape(state.active_tab, quote=True)}">
  <header>
    <div class="header-inner">
    <div class="brand-block">
      <div class="brand-mark">विकल्प</div>
      <div>
        <h1>Income Desk</h1>
        <p>Wheel income, positions, ETF actions, and calm execution.</p>
        <div class="profile-header-pill {active_profile_class}">
          Kite profile: <strong>{html.escape(active_kite_profile)}</strong>
          <span>{html.escape(active_profile_hint)}</span>
        </div>
      </div>
    </div>
    <div class="blessing">&#2384; | Jai Sri Ram | Jai Laxmi Mata</div>
    <p class="naval-quote">"Trade money for time, not time for money. You're going to run out of time first." <strong>- Naval</strong></p>
    </div>
  </header>
  <main>
    {alert}
    <div class="tabs">
      <button class="tab-button utility-action home-tab {home_tab_class}" type="button" data-tab="home">Home</button>
      <button class="tab-button primary-action {positions_tab_class}" type="button" data-tab="positions">Position</button>
      <button class="tab-button utility-action {research_tab_class}" type="button" data-tab="research">Research</button>
      <button class="tab-button primary-action {place_tab_class}" type="button" data-tab="place">Trading</button>
      <button class="tab-button utility-action {order_management_tab_class}" type="button" data-tab="order-management">Modify / Cancel</button>
      <button class="tab-button utility-action {investing_tab_class}" type="button" data-tab="investing">Investing</button>
      <button class="tab-button utility-action {equity_tab_class}" type="button" data-tab="equity">Equity</button>
      <button class="tab-button utility-action {income_growth_tab_class}" type="button" data-tab="income-growth">Income Growth</button>
      <button class="tab-button utility-action {income_tab_class}" type="button" data-tab="income">INCOME</button>
      <button class="tab-button utility-action {commodity_tab_class}" type="button" data-tab="commodity">Commodity</button>
      <button class="tab-button utility-action {analytics_tab_class}" type="button" data-tab="analytics">Analytics</button>
      <button class="tab-button utility-action {gpt_tab_class}" type="button" data-tab="gpt">GPT</button>
      <button class="tab-button utility-action {kite_setup_tab_class}" type="button" data-tab="kite-setup">Kite Setup</button>
    </div>
    {home_market_html}
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
        {render_ce_sell_dashboard(state)}
        <div class="live-modal-backdrop" id="ce-sell-order-modal">
          <div class="live-modal income-pe-order-modal-card">
            <h2 id="ce-sell-order-title">Covered CE SELL Review</h2>
            <p class="status">Fresh Kite coverage and premium are revalidated before order placement. Review recent stock news, then complete the 10-second pause.</p>
            <div class="quote-loading-state active" id="ce-sell-loading" role="status" aria-live="polite">
              <span class="backend-spinner" aria-hidden="true"></span>
              <strong>Revalidating coverage, position risk, quote, analytics, and news...</strong>
            </div>
            <div class="income-equity-metrics">
              <div><span>Option</span><strong id="ce-sell-option">--</strong></div>
              <div><span>Fresh LTP</span><strong id="ce-sell-ltp">--</strong></div>
              <div><span>SELL limit</span><strong id="ce-sell-limit">--</strong></div>
              <div><span>Holding / quantity</span><strong id="ce-sell-coverage">--</strong><small id="ce-sell-holding-source">--</small></div>
              <div><span>CMP / strike</span><strong id="ce-sell-strike">--</strong></div>
              <div><span>Maximum profit</span><strong id="ce-sell-max-profit">--</strong></div>
              <div><span>OTM / yield</span><strong id="ce-sell-yield">--</strong></div>
              <div><span>Score / risk</span><strong id="ce-sell-risk">--</strong></div>
            </div>
            <div class="income-equity-order-summary" id="ce-sell-summary">Loading fresh covered CE order...</div>
            <div class="trade-news-panel"><strong>Recent stock news</strong><div id="ce-sell-news">Loading news...</div></div>
            <input type="hidden" name="ce_sell_underlying" id="ce-sell-underlying">
            <input type="hidden" name="ce_sell_confirmed" id="ce-sell-confirmed" value="0">
            <div class="breath-circle income-pe-breath" id="ce-sell-breath"></div>
            <div class="breath-text" id="ce-sell-breath-text">Review order first</div>
            <div class="countdown" id="ce-sell-countdown">10</div>
            <div class="modal-actions">
              <button type="button" class="secondary" id="ce-sell-cancel">Cancel</button>
              <button type="button" id="ce-sell-review" disabled>Review &amp; Start 10s</button>
              <button type="submit" class="danger" formaction="/ce-scan/sell" id="ce-sell-go" disabled>GO</button>
            </div>
          </div>
        </div>
        {render_results(state.results)}
      </section>
      {render_console(state.console_log)}
    </form>
    {render_order_management_panel(state)}
    {render_positions_panel(state, position_orders_payload, position_orders_table, position_execute_button)}
    <form id="kite-setup-panel" method="post" action="/kite-setup"{kite_setup_panel_style}>
      {env_panel}
      {render_scheduler_control_panel()}
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
    {render_investing_panel(state)}
    {render_equity_panel(state)}
    {render_income_growth_panel(state)}
    {render_commodity_panel(state)}
  </main>
  <div class="global-work-overlay" id="global-work-overlay" role="status" aria-live="assertive" aria-hidden="true">
    <div class="global-work-card">
      <span class="global-work-spinner" aria-hidden="true"></span>
      <strong id="global-work-title">Working securely...</strong>
      <span id="global-work-detail">Refreshing Kite data and validating the action. Please wait.</span>
    </div>
  </div>
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
  <div class="live-modal-backdrop" id="position-confirm-modal">
    <div class="live-modal">
      <h2>Pause Before Position BUY</h2>
      <p>Selected BUY orders are about to run. Breathe in, breathe out, and review current stock movement.</p>
      <div class="breath-circle"></div>
      <div class="breath-text" id="position-breath-text">Breathe in</div>
      <div class="countdown" id="position-countdown">10</div>
      <div class="news-box guardrail-box">
        <h3>CMP and Current Movement</h3>
        <div id="position-quote-check">Loading current prices...</div>
      </div>
      <div class="modal-actions">
        <button type="button" class="secondary" id="position-cancel">Cancel</button>
        <button type="button" class="danger" id="position-good" disabled>Good to go</button>
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
    const clearCsvButton = document.getElementById('clear-csv-text');
    const showCredentials = Array.from(document.querySelectorAll('input[name="show_credentials"]'));
    const secretFields = Array.from(document.querySelectorAll('.secret-field'));
    fileInput && fileInput.addEventListener('change', async () => {{
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      textArea.value = await file.text();
    }});
    clearCsvButton && clearCsvButton.addEventListener('click', () => {{
      if (textArea) {{
        textArea.value = '';
        textArea.focus();
      }}
      if (fileInput) {{
        fileInput.value = '';
      }}
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
    const kiteProfileSelect = document.getElementById('kite-profile-select');
    const kiteLoginLink = document.getElementById('kite-login-link');
    const kiteProfileNoteName = document.getElementById('kite-profile-note-name');
    const kiteProfileNoteStatus = document.getElementById('kite-profile-note-status');
    function setInputValue(id, value) {{
      const input = document.getElementById(id);
      if (input) input.value = value || '';
    }}
    function updateKiteLoginLink(apiKey) {{
      if (!kiteLoginLink) return;
      const cleanKey = String(apiKey || '').trim();
      kiteLoginLink.href = 'https://kite.zerodha.com/connect/login?api_key='
        + encodeURIComponent(cleanKey)
        + '&v=3';
    }}
    function applySelectedKiteProfile() {{
      if (!kiteProfileSelect) return;
      let profiles = {{}};
      try {{
        profiles = JSON.parse(kiteProfileSelect.dataset.profiles || '{{}}');
      }} catch (error) {{
        profiles = {{}};
      }}
      const profile = profiles[kiteProfileSelect.value] || {{}};
      setInputValue('kite-api-key', profile.KITE_API_KEY);
      setInputValue('kite-api-secret', profile.KITE_API_SECRET);
      setInputValue('kite-access-token', profile.KITE_ACCESS_TOKEN);
      setInputValue('kite-confirm-live-order', profile.KITE_CONFIRM_LIVE_ORDER || 'YES');
      updateKiteLoginLink(profile.KITE_API_KEY);
      const ready = Boolean(
        String(profile.KITE_API_KEY || '').trim()
        && String(profile.KITE_API_SECRET || '').trim()
        && String(profile.KITE_ACCESS_TOKEN || '').trim()
      );
      if (kiteProfileNoteName) kiteProfileNoteName.textContent = kiteProfileSelect.value;
      if (kiteProfileNoteStatus) {{
        kiteProfileNoteStatus.textContent = ready
          ? 'profile ready for login, quotes, and order actions.'
          : 'profile needs API key, secret, and today\\'s access token.';
      }}
    }}
    kiteProfileSelect && kiteProfileSelect.addEventListener('change', applySelectedKiteProfile);
    applySelectedKiteProfile();
    const investingTable = document.getElementById('investing-holdings-table');
    function numericTableValue(cell) {{
      const text = (cell && cell.textContent ? cell.textContent : '').replace(/,/g, '');
      const match = text.match(/-?[0-9]+(?:[.][0-9]+)?/);
      return match ? Number(match[0]) : Number.NEGATIVE_INFINITY;
    }}
    function sortableTableValue(cell) {{
      const raw = (cell && cell.textContent ? cell.textContent : '').trim();
      const cleaned = raw.replace(/,/g, '');
      const match = cleaned.match(/-?[0-9]+(?:[.][0-9]+)?/);
      if (match) {{
        return {{ kind: 'number', value: Number(match[0]) }};
      }}
      return {{ kind: 'text', value: raw.toLowerCase() }};
    }}
    function compareSortableCells(leftCell, rightCell, dir) {{
      const left = sortableTableValue(leftCell);
      const right = sortableTableValue(rightCell);
      let result = 0;
      if (left.kind === 'number' && right.kind === 'number') {{
        result = left.value - right.value;
      }} else {{
        result = String(left.value).localeCompare(String(right.value), undefined, {{ numeric: true, sensitivity: 'base' }});
      }}
      return dir === 'asc' ? result : -result;
    }}
    function enableTableSorting(table) {{
      if (!table) return;
      for (const header of table.querySelectorAll('.sort-header')) {{
        header.addEventListener('click', () => {{
          const column = Number(header.dataset.sortCol);
          const currentDir = header.dataset.sortDir === 'desc' ? 'asc' : 'desc';
          for (const other of table.querySelectorAll('.sort-header')) {{
            other.dataset.sortDir = '';
          }}
          header.dataset.sortDir = currentDir;
          const tbody = table.tBodies[0];
          const rows = Array.from(tbody.querySelectorAll('tr'));
          rows.sort((left, right) => {{
            return compareSortableCells(left.cells[column], right.cells[column], currentDir);
          }});
          for (const row of rows) {{
            tbody.appendChild(row);
          }}
        }});
      }}
    }}
    enableTableSorting(investingTable);
    enableTableSorting(document.getElementById('income-growth-table'));
    enableTableSorting(document.getElementById('equity-holdings-table'));
    const ordersSelectAll = document.getElementById('orders-select-all');
    const ordersUnselectAll = document.getElementById('orders-unselect-all');
    function setOrderCheckboxes(checked) {{
      for (const checkbox of document.querySelectorAll('#order-management-panel input[name="order_key"]:not(:disabled)')) {{
        checkbox.checked = checked;
      }}
    }}
    ordersSelectAll && ordersSelectAll.addEventListener('click', () => setOrderCheckboxes(true));
    ordersUnselectAll && ordersUnselectAll.addEventListener('click', () => setOrderCheckboxes(false));
    const positionSelectAll = document.getElementById('position-select-all');
    const positionUnselectAll = document.getElementById('position-unselect-all');
    function setPositionCheckboxes(checked) {{
      for (const checkbox of document.querySelectorAll('#positions-panel input[name="position_selected"]:not(:disabled)')) {{
        checkbox.checked = checked;
      }}
    }}
    positionSelectAll && positionSelectAll.addEventListener('click', () => setPositionCheckboxes(true));
    positionUnselectAll && positionUnselectAll.addEventListener('click', () => setPositionCheckboxes(false));
    for (const button of document.querySelectorAll('.price-step-button')) {{
      button.addEventListener('click', () => {{
        const wrapper = button.closest('.price-adjuster');
        const input = wrapper ? wrapper.querySelector('.price-adjust-input') : null;
        if (!input || input.disabled) return;
        const stepPct = Number(button.dataset.priceStep || 0);
        const current = Number(input.value || 0);
        if (!Number.isFinite(current) || current <= 0 || !Number.isFinite(stepPct)) return;
        const tickSize = 0.05;
        const rawMove = current * Math.abs(stepPct) / 100;
        const move = Math.max(rawMove, tickSize);
        const direction = stepPct >= 0 ? 1 : -1;
        const rawNext = Math.max(current + (direction * move), tickSize);
        const roundedTicks = direction >= 0
          ? Math.ceil(rawNext / tickSize)
          : Math.floor(rawNext / tickSize);
        const next = Math.max(roundedTicks * tickSize, tickSize);
        input.value = next.toFixed(2);
        const row = button.closest('tr');
        const checkbox = row ? row.querySelector('input[name="order_key"]:not(:disabled)') : null;
        if (checkbox) checkbox.checked = true;
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
      }});
    }}
    for (const button of document.querySelectorAll('.tab-button')) {{
      button.addEventListener('click', () => {{
        const active = button.dataset.tab;
        const routes = {{
          home: '/home',
          place: '/',
          positions: '/positions',
          analytics: '/analytics',
          research: '/research',
          income: '/income',
          investing: '/investing',
          equity: '/equity',
          'income-growth': '/income-growth',
          commodity: '/commodity',
          'order-management': '/orders',
          gpt: '/gpt',
          'kite-setup': '/kite-setup'
        }};
        const route = routes[active] || '/';
        if (window.location.pathname !== route) {{
          window.location.href = route;
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
        document.getElementById('investing-panel').style.display = active === 'investing' ? '' : 'none';
        document.getElementById('equity-panel').style.display = active === 'equity' ? '' : 'none';
        document.getElementById('income-growth-panel').style.display = active === 'income-growth' ? '' : 'none';
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
    function compactClientError(message, fallback) {{
      const text = String(message || '').trim();
      if (!text) return fallback || 'Data unavailable.';
      openKiteSetupForError(text);
      const lower = text.toLowerCase();
      if (lower.includes('getaddrinfo') || lower.includes('failed to resolve') || lower.includes('name resolution')) {{
        return 'Network/DNS error: this machine cannot resolve Kite or market-data hosts. Check internet/DNS, then refresh.';
      }}
      if (lower.includes('api_key') || lower.includes('access_token') || lower.includes('invalid session')) {{
        return 'Kite authentication error: confirm the active Kite profile and regenerate today\\'s access token.';
      }}
      if (lower.includes('timed out') || lower.includes('timeout')) {{
        return 'Network timeout: retry after a few seconds.';
      }}
      return text.length > 240 ? text.slice(0, 240) + '...' : text;
    }}
    const globalWorkOverlay = document.getElementById('global-work-overlay');
    const globalWorkTitle = document.getElementById('global-work-title');
    const globalWorkDetail = document.getElementById('global-work-detail');
    let globalWorkDepth = 0;
    function beginGlobalWork(title, detail) {{
      globalWorkDepth += 1;
      if (globalWorkTitle) globalWorkTitle.textContent = title || 'Working securely...';
      if (globalWorkDetail) globalWorkDetail.textContent = detail || 'Refreshing Kite data and validating the action. Please wait.';
      if (globalWorkOverlay) {{
        globalWorkOverlay.classList.add('active');
        globalWorkOverlay.setAttribute('aria-hidden', 'false');
      }}
      document.body.classList.add('global-work-active');
    }}
    function endGlobalWork() {{
      globalWorkDepth = Math.max(0, globalWorkDepth - 1);
      if (globalWorkDepth > 0) return;
      if (globalWorkOverlay) {{
        globalWorkOverlay.classList.remove('active');
        globalWorkOverlay.setAttribute('aria-hidden', 'true');
      }}
      document.body.classList.remove('global-work-active');
    }}
    const heavyActionLabels = {{
      '/load': 'Loading and validating today\\'s CSV...',
      '/research/load': 'Researching CSV option symbols...',
      '/positions/load': 'Loading fresh active positions...',
      '/positions-research/load': 'Calculating position analytics...',
      '/orders/refresh': 'Loading current Kite orders...',
      '/analytics/load': 'Calculating option analytics...',
      '/income/load': 'Calculating income candidates...',
      '/income-growth/load': 'Refreshing income-growth analysis...',
      '/investing/load': 'Refreshing investing portfolio...',
      '/equity/load': 'Loading equity holdings...',
      '/commodity/refresh': 'Refreshing ETF quotes and averages...',
      '/ce-scan/load': 'Recalculating covered CALL candidates...',
      '/gpt/generate': 'Waiting for OpenAI analysis...',
      '/income-growth/gpt': 'Waiting for OpenAI validation...',
      '/execute': 'Submitting selected trading orders...',
      '/positions/execute': 'Submitting selected position BUY orders...',
      '/orders/modify-selected': 'Modifying selected Kite orders...',
      '/orders/cancel-selected': 'Cancelling selected Kite orders...',
      '/orders/cancel-all': 'Cancelling all open Kite orders...'
    }};
    document.addEventListener('submit', (event) => {{
      window.setTimeout(() => {{
        if (event.defaultPrevented) return;
        const submitter = event.submitter;
        const actionUrl = submitter && submitter.formAction
          ? new URL(submitter.formAction, window.location.href)
          : new URL(event.target.action || window.location.href, window.location.href);
        const label = heavyActionLabels[actionUrl.pathname];
        if (label) beginGlobalWork(label, 'The page is locked until the backend action completes.');
      }}, 0);
    }});
    const isHomePage = window.location.pathname === '/home';
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
    const positionForm = document.getElementById('positions-panel');
    const positionExecuteButton = document.getElementById('position-execute-selected-button');
    const positionModal = document.getElementById('position-confirm-modal');
    const positionCancel = document.getElementById('position-cancel');
    const positionGood = document.getElementById('position-good');
    const positionCountdown = document.getElementById('position-countdown');
    const positionBreathText = document.getElementById('position-breath-text');
    const positionLiveConfirmed = document.getElementById('position-live-confirmed');
    const positionQuoteCheck = document.getElementById('position-quote-check');
    const incomeGrowthGptModal = document.getElementById('income-growth-gpt-modal');
    const incomeGrowthEditGpt = document.getElementById('income-growth-edit-gpt');
    const incomeGrowthGptCancel = document.getElementById('income-growth-gpt-cancel');
    const incomeGrowthGptRefresh = document.getElementById('income-growth-gpt-refresh');
    const incomeGrowthForceGpt = document.getElementById('income-growth-force-gpt');
    const incomePeModal = document.getElementById('income-pe-order-modal');
    const incomePeTitle = document.getElementById('income-pe-order-title');
    const incomePeOption = document.getElementById('income-pe-option');
    const incomePeLtp = document.getElementById('income-pe-ltp');
    const incomePeLimit = document.getElementById('income-pe-limit');
    const incomePeQuantity = document.getElementById('income-pe-quantity');
    const incomePeExpiry = document.getElementById('income-pe-expiry');
    const incomePeAssignment = document.getElementById('income-pe-assignment');
    const incomePeMaxProfit = document.getElementById('income-pe-max-profit');
    const incomePeYield = document.getElementById('income-pe-yield');
    const incomePeSummary = document.getElementById('income-pe-summary');
    const incomePeUnderlying = document.getElementById('income-pe-underlying');
    const incomePeTargetStrike = document.getElementById('income-pe-target-strike');
    const incomePeConfirmed = document.getElementById('income-pe-confirmed');
    const incomePeReview = document.getElementById('income-pe-review');
    const incomePeGo = document.getElementById('income-pe-go');
    const incomePeCancel = document.getElementById('income-pe-cancel');
    const incomePeCountdown = document.getElementById('income-pe-countdown');
    const incomePeBreathText = document.getElementById('income-pe-breath-text');
    const incomePeBreath = document.getElementById('income-pe-breath');
    const incomePeLoading = document.getElementById('income-pe-loading');
    const ceSellModal = document.getElementById('ce-sell-order-modal');
    const ceSellTitle = document.getElementById('ce-sell-order-title');
    const ceSellOption = document.getElementById('ce-sell-option');
    const ceSellLtp = document.getElementById('ce-sell-ltp');
    const ceSellLimit = document.getElementById('ce-sell-limit');
    const ceSellCoverage = document.getElementById('ce-sell-coverage');
    const ceSellHoldingSource = document.getElementById('ce-sell-holding-source');
    const ceSellStrike = document.getElementById('ce-sell-strike');
    const ceSellMaxProfit = document.getElementById('ce-sell-max-profit');
    const ceSellYield = document.getElementById('ce-sell-yield');
    const ceSellRisk = document.getElementById('ce-sell-risk');
    const ceSellSummary = document.getElementById('ce-sell-summary');
    const ceSellNews = document.getElementById('ce-sell-news');
    const ceSellUnderlying = document.getElementById('ce-sell-underlying');
    const ceSellConfirmed = document.getElementById('ce-sell-confirmed');
    const ceSellReview = document.getElementById('ce-sell-review');
    const ceSellGo = document.getElementById('ce-sell-go');
    const ceSellCancel = document.getElementById('ce-sell-cancel');
    const ceSellCountdown = document.getElementById('ce-sell-countdown');
    const ceSellBreathText = document.getElementById('ce-sell-breath-text');
    const ceSellBreath = document.getElementById('ce-sell-breath');
    const ceSellLoading = document.getElementById('ce-sell-loading');
    const equityOrderModal = document.getElementById('equity-order-modal');
    const equityOrderTitle = document.getElementById('equity-order-title');
    const equityOrderSymbol = document.getElementById('equity-order-symbol');
    const equityOrderExchange = document.getElementById('equity-order-exchange');
    const equityOrderSide = document.getElementById('equity-order-side');
    const equityOrderQuantity = document.getElementById('equity-order-quantity');
    const equityOrderPrice = document.getElementById('equity-order-price');
    const equityOrderConfirmed = document.getElementById('equity-order-confirmed');
    const equityOrderHolding = document.getElementById('equity-order-holding');
    const equityOrderAvg = document.getElementById('equity-order-avg');
    const equityOrderLtp = document.getElementById('equity-order-ltp');
    const equityOrderPnl = document.getElementById('equity-order-pnl');
    const equityOrderGap = document.getElementById('equity-order-gap');
    const equityOrderSummary = document.getElementById('equity-order-summary');
    const equityOrderReview = document.getElementById('equity-order-review');
    const equityOrderGo = document.getElementById('equity-order-go');
    const equityOrderCancel = document.getElementById('equity-order-cancel');
    const equityOrderCountdown = document.getElementById('equity-order-countdown');
    const equityOrderBreathText = document.getElementById('equity-order-breath-text');
    const equityOrderBreath = document.getElementById('equity-order-breath');
    const incomeEquityModal = document.getElementById('income-equity-modal');
    const incomeEquityTitle = document.getElementById('income-equity-title');
    const incomeEquitySymbol = document.getElementById('income-equity-symbol');
    const incomeEquitySide = document.getElementById('income-equity-side');
    const incomeEquityQuantity = document.getElementById('income-equity-quantity');
    const incomeEquityConfirmed = document.getElementById('income-equity-confirmed');
    const incomeEquityHolding = document.getElementById('income-equity-holding');
    const incomeEquityAvg = document.getElementById('income-equity-avg');
    const incomeEquityLtp = document.getElementById('income-equity-ltp');
    const incomeEquityPnl = document.getElementById('income-equity-pnl');
    const incomeEquitySummary = document.getElementById('income-equity-order-summary');
    const incomeEquityReview = document.getElementById('income-equity-review');
    const incomeEquityExecute = document.getElementById('income-equity-execute');
    const incomeEquityCancel = document.getElementById('income-equity-cancel');
    const incomeEquityCountdown = document.getElementById('income-equity-countdown');
    const incomeEquityBreathText = document.getElementById('income-equity-breath-text');
    const incomeEquityBreath = document.getElementById('income-equity-breath');
    let pendingLiveSubmit = false;
    let countdownTimer = null;
    let pendingCommodityForm = null;
    let commodityCountdownTimer = null;
    let pendingPositionSubmit = false;
    let positionCountdownTimer = null;
    let incomePeCountdownTimer = null;
    let ceSellCountdownTimer = null;
    let equityOrderCountdownTimer = null;
    let equityOrderSnapshot = null;
    let incomeEquityCountdownTimer = null;
    let incomeEquitySnapshot = null;
    function setQuoteLoading(modal, loadingElement, active, title) {{
      if (loadingElement) loadingElement.classList.toggle('active', active);
      if (modal) modal.setAttribute('aria-busy', active ? 'true' : 'false');
      if (active) beginGlobalWork(title || 'Revalidating fresh market data...', 'Quotes, positions, risk, and order details are being checked.');
      else endGlobalWork();
    }}
    function resetIncomePeConfirmation() {{
      if (incomePeCountdownTimer) clearInterval(incomePeCountdownTimer);
      incomePeCountdownTimer = null;
      if (incomePeConfirmed) incomePeConfirmed.value = '0';
      if (incomePeGo) incomePeGo.disabled = true;
      if (incomePeReview) incomePeReview.disabled = true;
      if (incomePeCountdown) incomePeCountdown.textContent = '10';
      if (incomePeBreathText) incomePeBreathText.textContent = 'Review order first';
      if (incomePeBreath) incomePeBreath.classList.remove('active');
    }}
    async function openIncomePeModal(button) {{
      if (!incomePeModal) return;
      resetIncomePeConfirmation();
      const underlying = button.dataset.underlying || '';
      const strike = button.dataset.strike || '';
      incomePeModal.style.display = 'flex';
      if (incomePeTitle) incomePeTitle.textContent = `${{underlying}} Cash-Secured PE SELL`;
      if (incomePeUnderlying) incomePeUnderlying.value = underlying;
      if (incomePeTargetStrike) incomePeTargetStrike.value = strike;
      if (incomePeSummary) incomePeSummary.textContent = 'Loading fresh monthly PE contract and premium from Kite...';
      setQuoteLoading(incomePeModal, incomePeLoading, true, 'Recalculating PE SELL candidate...');
      try {{
        const response = await fetch(`/income/pe-quote?underlying=${{encodeURIComponent(underlying)}}&strike=${{encodeURIComponent(strike)}}`, {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Could not load PE quote');
        if (incomePeOption) incomePeOption.textContent = data.symbol || '--';
        if (incomePeLtp) incomePeLtp.textContent = Number(data.ltp || 0).toFixed(2);
        if (incomePeLimit) incomePeLimit.textContent = Number(data.limit_price || 0).toFixed(2);
        if (incomePeQuantity) incomePeQuantity.textContent = String(data.quantity || 0);
        if (incomePeExpiry) incomePeExpiry.textContent = data.expiry || '--';
        if (incomePeAssignment) incomePeAssignment.textContent = Number(data.assignment_value || 0).toFixed(0);
        if (incomePeMaxProfit) incomePeMaxProfit.textContent = Number(data.max_profit || 0).toFixed(0);
        if (incomePeYield) incomePeYield.textContent = `${{Number(data.premium_yield_percent || 0).toFixed(2)}}%`;
        if (incomePeSummary) incomePeSummary.textContent = `SELL ${{data.quantity}} ${{data.symbol}} at LIMIT ${{Number(data.limit_price || 0).toFixed(2)}} | ${{Number(data.markup_percent || 0).toFixed(2)}}% above fresh LTP ${{Number(data.ltp || 0).toFixed(2)}} | Assignment value ${{Number(data.assignment_value || 0).toFixed(0)}} | Maximum profit ${{Number(data.max_profit || 0).toFixed(0)}}`;
        if (incomePeReview) incomePeReview.disabled = false;
      }} catch (error) {{
        if (incomePeSummary) incomePeSummary.textContent = compactClientError(error.message, 'Could not load PE quote');
      }} finally {{
        setQuoteLoading(incomePeModal, incomePeLoading, false);
      }}
    }}
    for (const button of document.querySelectorAll('.income-pe-order-button')) {{
      button.addEventListener('click', () => openIncomePeModal(button));
    }}
    incomePeCancel && incomePeCancel.addEventListener('click', () => {{
      resetIncomePeConfirmation();
      if (incomePeModal) incomePeModal.style.display = 'none';
    }});
    incomePeReview && incomePeReview.addEventListener('click', () => {{
      resetIncomePeConfirmation();
      let remaining = 10;
      if (incomePeReview) incomePeReview.disabled = true;
      if (incomePeBreath) incomePeBreath.classList.add('active');
      if (incomePeBreathText) incomePeBreathText.textContent = 'Breathe in';
      incomePeCountdownTimer = setInterval(() => {{
        remaining -= 1;
        if (incomePeCountdown) incomePeCountdown.textContent = String(Math.max(remaining, 0));
        if (incomePeBreathText) incomePeBreathText.textContent = remaining % 2 === 0 ? 'Breathe in' : 'Breathe out';
        if (remaining <= 0) {{
          clearInterval(incomePeCountdownTimer);
          incomePeCountdownTimer = null;
          if (incomePeBreathText) incomePeBreathText.textContent = 'Ready. Cancel or GO.';
          if (incomePeConfirmed) incomePeConfirmed.value = '1';
          if (incomePeGo) incomePeGo.disabled = false;
        }}
      }}, 1000);
    }});
    function closeOrderModalForSubmit(modal, reviewButton, goButton) {{
      if (modal) {{
        modal.setAttribute('aria-busy', 'true');
        for (const button of modal.querySelectorAll('button')) button.disabled = true;
        modal.style.display = 'none';
      }}
      if (reviewButton) reviewButton.disabled = true;
      if (goButton) {{
        goButton.disabled = true;
        goButton.textContent = 'Submitting...';
      }}
      document.body.classList.add('order-submit-in-progress');
      window.setTimeout(() => {{
        for (const button of document.querySelectorAll('button, input[type="submit"]')) {{
          button.disabled = true;
        }}
      }}, 0);
    }}
    function submitOrderModal(event, modal, reviewButton, goButton) {{
      event.preventDefault();
      if (!goButton || !goButton.form) return;
      const form = goButton.form;
      const submitAction = goButton.formAction;
      const submitMethod = goButton.formMethod || form.method || 'post';
      closeOrderModalForSubmit(modal, reviewButton, goButton);
      beginGlobalWork('Submitting order to Kite...', 'Please wait for Zerodha to accept or reject the order.');
      form.action = submitAction;
      form.method = submitMethod;
      HTMLFormElement.prototype.submit.call(form);
    }}
    incomePeGo && incomePeGo.addEventListener('click', (event) => {{
      submitOrderModal(event, incomePeModal, incomePeReview, incomePeGo);
    }});
    function resetCeSellConfirmation() {{
      if (ceSellCountdownTimer) clearInterval(ceSellCountdownTimer);
      ceSellCountdownTimer = null;
      if (ceSellConfirmed) ceSellConfirmed.value = '0';
      if (ceSellGo) ceSellGo.disabled = true;
      if (ceSellReview) ceSellReview.disabled = true;
      if (ceSellCountdown) ceSellCountdown.textContent = '10';
      if (ceSellBreathText) ceSellBreathText.textContent = 'Review order first';
      if (ceSellBreath) ceSellBreath.classList.remove('active');
    }}
    async function loadCeSellNews(underlying) {{
      if (!ceSellNews) return;
      ceSellNews.textContent = 'Loading recent stock news...';
      try {{
        const response = await fetch(`/trade-news?stocks=${{encodeURIComponent(underlying)}}`, {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Could not load news');
        const news = (data.news || []).slice(0, 3);
        ceSellNews.innerHTML = news.length ? '<ol>' + news.map((item) => {{
          const sentiment = ['positive', 'negative', 'neutral'].includes(item.sentiment) ? item.sentiment : 'neutral';
          const title = escapeHtml(item.title || 'News item');
          const date = item.published_date ? `<span class="news-date">${{escapeHtml(item.published_date)}}</span>` : '';
          const content = item.link ? `<a href="${{escapeHtml(item.link)}}" target="_blank" rel="noopener">${{title}}</a>` : title;
          return `<li class="news-sentiment-${{sentiment}}">${{content}}<span class="news-tag">${{sentiment}}</span>${{date}}</li>`;
        }}).join('') + '</ol>' : 'No recent news found.';
      }} catch (error) {{
        ceSellNews.textContent = compactClientError(error.message, 'Could not load stock news');
      }}
    }}
    async function openCeSellModal(button) {{
      if (!ceSellModal) return;
      resetCeSellConfirmation();
      const underlying = button.dataset.underlying || '';
      ceSellModal.style.display = 'flex';
      if (ceSellTitle) ceSellTitle.textContent = `${{underlying}} Covered CE SELL Review`;
      if (ceSellUnderlying) ceSellUnderlying.value = underlying;
      if (ceSellSummary) ceSellSummary.textContent = 'Revalidating Top 3 status, coverage, positions, and fresh CE premium...';
      setQuoteLoading(ceSellModal, ceSellLoading, true, 'Revalidating covered CE SELL candidate...');
      const newsPromise = loadCeSellNews(underlying);
      try {{
        const response = await fetch(`/ce-scan/quote?underlying=${{encodeURIComponent(underlying)}}`, {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Could not load covered CE quote');
        if (ceSellOption) ceSellOption.textContent = data.symbol || '--';
        if (ceSellLtp) ceSellLtp.textContent = Number(data.ltp || 0).toFixed(2);
        if (ceSellLimit) ceSellLimit.textContent = Number(data.limit_price || 0).toFixed(2);
        if (ceSellCoverage) ceSellCoverage.textContent = `${{data.holding_qty || 0}} / ${{data.quantity || 0}}`;
        if (ceSellHoldingSource) ceSellHoldingSource.textContent = `${{data.holding_source || 'Unknown source'}} | Kite ${{data.kite_holding_qty || 0}} | Income Growth ${{data.income_growth_holding_qty || 0}}`;
        if (ceSellStrike) ceSellStrike.textContent = `${{Number(data.cmp || 0).toFixed(2)}} / ${{Number(data.strike || 0).toFixed(2)}}`;
        if (ceSellMaxProfit) ceSellMaxProfit.textContent = Number(data.max_profit || 0).toFixed(0);
        if (ceSellYield) ceSellYield.textContent = `${{Number(data.otm_percent || 0).toFixed(2)}}% / ${{Number(data.premium_yield_percent || 0).toFixed(2)}}%`;
        if (ceSellRisk) ceSellRisk.textContent = `${{Number(data.score || 0).toFixed(0)}} / ${{data.event_risk || 'N/A'}} event / ${{data.breakout_risk || 'N/A'}} breakout`;
        if (ceSellSummary) ceSellSummary.textContent = `SELL ${{data.quantity}} ${{data.symbol}} at LIMIT ${{Number(data.limit_price || 0).toFixed(2)}} | ${{Number(data.markup_percent || 0).toFixed(2)}}% above fresh LTP ${{Number(data.ltp || 0).toFixed(2)}} | Effective holding ${{data.holding_qty}} from ${{data.holding_source || 'holding record'}}`;
        await newsPromise;
        if (ceSellReview) ceSellReview.disabled = false;
      }} catch (error) {{
        if (ceSellSummary) ceSellSummary.textContent = compactClientError(error.message, 'Could not load covered CE order');
      }} finally {{
        setQuoteLoading(ceSellModal, ceSellLoading, false);
      }}
    }}
    for (const button of document.querySelectorAll('.ce-sell-order-button')) {{
      button.addEventListener('click', () => openCeSellModal(button));
    }}
    ceSellCancel && ceSellCancel.addEventListener('click', () => {{
      resetCeSellConfirmation();
      if (ceSellModal) ceSellModal.style.display = 'none';
    }});
    ceSellReview && ceSellReview.addEventListener('click', () => {{
      resetCeSellConfirmation();
      let remaining = 10;
      if (ceSellReview) ceSellReview.disabled = true;
      if (ceSellBreath) ceSellBreath.classList.add('active');
      if (ceSellBreathText) ceSellBreathText.textContent = 'Breathe in';
      ceSellCountdownTimer = setInterval(() => {{
        remaining -= 1;
        if (ceSellCountdown) ceSellCountdown.textContent = String(Math.max(remaining, 0));
        if (ceSellBreathText) ceSellBreathText.textContent = remaining % 2 === 0 ? 'Breathe in' : 'Breathe out';
        if (remaining <= 0) {{
          clearInterval(ceSellCountdownTimer);
          ceSellCountdownTimer = null;
          if (ceSellBreathText) ceSellBreathText.textContent = 'Ready. Cancel or GO.';
          if (ceSellConfirmed) ceSellConfirmed.value = '1';
          if (ceSellGo) ceSellGo.disabled = false;
        }}
      }}, 1000);
    }});
    ceSellGo && ceSellGo.addEventListener('click', (event) => {{
      submitOrderModal(event, ceSellModal, ceSellReview, ceSellGo);
    }});
    function stopEquityOrderCountdown() {{
      if (equityOrderCountdownTimer) {{
        clearInterval(equityOrderCountdownTimer);
        equityOrderCountdownTimer = null;
      }}
    }}
    function resetEquityOrderConfirmation() {{
      stopEquityOrderCountdown();
      if (equityOrderConfirmed) equityOrderConfirmed.value = '0';
      if (equityOrderGo) equityOrderGo.disabled = true;
      if (equityOrderCountdown) equityOrderCountdown.textContent = '10';
      if (equityOrderBreathText) equityOrderBreathText.textContent = 'Review order first';
      if (equityOrderBreath) equityOrderBreath.classList.remove('active');
    }}
    function updateEquityOrderSummary() {{
      if (!equityOrderSummary) return;
      const side = equityOrderSide ? equityOrderSide.value : 'BUY';
      const quantity = Number(equityOrderQuantity ? equityOrderQuantity.value : 0);
      const limit = Number(equityOrderPrice ? equityOrderPrice.value : 0);
      const ltp = Number(equityOrderSnapshot && equityOrderSnapshot.ltp || 0);
      const holding = Number(equityOrderSnapshot && equityOrderSnapshot.quantity || 0);
      const gap = ltp > 0 && limit > 0 ? ((limit - ltp) / ltp) * 100 : 0;
      if (equityOrderGap) {{
        equityOrderGap.textContent = ltp > 0 && limit > 0 ? `${{gap >= 0 ? '+' : ''}}${{gap.toFixed(2)}}%` : '--';
        equityOrderGap.className = gap >= 0 ? 'pnl-positive' : 'pnl-negative';
      }}
      equityOrderSummary.textContent = `${{side}} ${{quantity || 0}} ${{equityOrderSymbol ? equityOrderSymbol.value : ''}} at LIMIT ${{limit.toFixed(2)}} | LTP ${{ltp.toFixed(2)}} | Holding ${{holding}}`;
      equityOrderSummary.classList.toggle('signal-red', side === 'SELL' && quantity > holding);
    }}
    async function openEquityOrderModal(button) {{
      if (!equityOrderModal) return;
      resetEquityOrderConfirmation();
      const symbol = button.dataset.symbol || '';
      const exchange = button.dataset.exchange || 'NSE';
      equityOrderSnapshot = {{ symbol, exchange, quantity: Number(button.dataset.quantity || 0), average_price: Number(button.dataset.avg || 0), ltp: Number(button.dataset.ltp || 0), pnl: Number(button.dataset.pnl || 0) }};
      equityOrderModal.style.display = 'flex';
      if (equityOrderTitle) equityOrderTitle.textContent = `${{symbol}} Equity Limit Order`;
      if (equityOrderSymbol) equityOrderSymbol.value = symbol;
      if (equityOrderExchange) equityOrderExchange.value = exchange;
      if (equityOrderSide) equityOrderSide.value = 'BUY';
      if (equityOrderQuantity) equityOrderQuantity.value = '1';
      if (equityOrderPrice) equityOrderPrice.value = (Math.round(Number(equityOrderSnapshot.ltp || 0) / 0.05) * 0.05).toFixed(2);
      if (equityOrderHolding) equityOrderHolding.textContent = String(equityOrderSnapshot.quantity);
      if (equityOrderAvg) equityOrderAvg.textContent = Number(equityOrderSnapshot.average_price || 0).toFixed(2);
      if (equityOrderLtp) equityOrderLtp.textContent = Number(equityOrderSnapshot.ltp || 0).toFixed(2);
      if (equityOrderPnl) equityOrderPnl.textContent = Number(equityOrderSnapshot.pnl || 0).toFixed(2);
      updateEquityOrderSummary();
      try {{
        const response = await fetch(`/equity/quote?symbol=${{encodeURIComponent(symbol)}}&exchange=${{encodeURIComponent(exchange)}}`, {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Could not refresh equity holding');
        equityOrderSnapshot = data;
        if (equityOrderHolding) equityOrderHolding.textContent = String(data.quantity || 0);
        if (equityOrderAvg) equityOrderAvg.textContent = Number(data.average_price || 0).toFixed(2);
        if (equityOrderLtp) equityOrderLtp.textContent = Number(data.ltp || 0).toFixed(2);
        if (equityOrderPnl) {{
          equityOrderPnl.textContent = Number(data.pnl || 0).toFixed(2);
          equityOrderPnl.className = Number(data.pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative';
        }}
        if (equityOrderPrice) equityOrderPrice.value = (Math.round(Number(data.ltp || 0) / 0.05) * 0.05).toFixed(2);
        updateEquityOrderSummary();
      }} catch (error) {{
        if (equityOrderSummary) equityOrderSummary.textContent = compactClientError(error.message, 'Could not refresh equity holding');
      }}
    }}
    for (const button of document.querySelectorAll('.equity-holding-stock')) {{
      button.addEventListener('click', () => openEquityOrderModal(button));
    }}
    for (const input of [equityOrderSide, equityOrderQuantity, equityOrderPrice]) {{
      input && input.addEventListener(input === equityOrderPrice || input === equityOrderQuantity ? 'input' : 'change', () => {{
        resetEquityOrderConfirmation();
        updateEquityOrderSummary();
      }});
    }}
    equityOrderCancel && equityOrderCancel.addEventListener('click', () => {{
      resetEquityOrderConfirmation();
      if (equityOrderModal) equityOrderModal.style.display = 'none';
    }});
    equityOrderReview && equityOrderReview.addEventListener('click', () => {{
      const quantity = Number(equityOrderQuantity ? equityOrderQuantity.value : 0);
      const limit = Number(equityOrderPrice ? equityOrderPrice.value : 0);
      const holding = Number(equityOrderSnapshot && equityOrderSnapshot.quantity || 0);
      const side = equityOrderSide ? equityOrderSide.value : '';
      if (!Number.isInteger(quantity) || quantity <= 0 || !Number.isFinite(limit) || limit <= 0) {{
        if (equityOrderSummary) equityOrderSummary.textContent = 'Enter a valid whole-number quantity and a positive limit price.';
        return;
      }}
      if (side === 'SELL' && quantity > holding) {{
        if (equityOrderSummary) equityOrderSummary.textContent = `SELL blocked: quantity ${{quantity}} exceeds current holding ${{holding}}.`;
        return;
      }}
      resetEquityOrderConfirmation();
      let remaining = 10;
      if (equityOrderBreath) equityOrderBreath.classList.add('active');
      if (equityOrderBreathText) equityOrderBreathText.textContent = 'Breathe in';
      equityOrderCountdownTimer = setInterval(() => {{
        remaining -= 1;
        if (equityOrderCountdown) equityOrderCountdown.textContent = String(Math.max(remaining, 0));
        if (equityOrderBreathText) equityOrderBreathText.textContent = remaining % 2 === 0 ? 'Breathe in' : 'Breathe out';
        if (remaining <= 0) {{
          stopEquityOrderCountdown();
          if (equityOrderBreathText) equityOrderBreathText.textContent = 'Ready. Cancel or GO.';
          if (equityOrderConfirmed) equityOrderConfirmed.value = '1';
          if (equityOrderGo) equityOrderGo.disabled = false;
        }}
      }}, 1000);
    }});
    function stopIncomeEquityCountdown() {{
      if (incomeEquityCountdownTimer) {{
        clearInterval(incomeEquityCountdownTimer);
        incomeEquityCountdownTimer = null;
      }}
    }}
    function resetIncomeEquityConfirmation() {{
      stopIncomeEquityCountdown();
      if (incomeEquityConfirmed) incomeEquityConfirmed.value = '0';
      if (incomeEquityExecute) incomeEquityExecute.disabled = true;
      if (incomeEquityCountdown) incomeEquityCountdown.textContent = '10';
      if (incomeEquityBreathText) incomeEquityBreathText.textContent = 'Review order first';
      if (incomeEquityBreath) incomeEquityBreath.classList.remove('active');
    }}
    function updateIncomeEquitySummary() {{
      if (!incomeEquitySummary) return;
      const side = incomeEquitySide ? incomeEquitySide.value : 'BUY';
      const quantity = Number(incomeEquityQuantity ? incomeEquityQuantity.value : 0);
      const symbol = incomeEquitySymbol ? incomeEquitySymbol.value : '';
      const ltp = Number(incomeEquitySnapshot && incomeEquitySnapshot.ltp || 0);
      const holding = Number(incomeEquitySnapshot && incomeEquitySnapshot.quantity || 0);
      const value = quantity > 0 && ltp > 0 ? quantity * ltp : 0;
      incomeEquitySummary.textContent = `${{side}} ${{quantity || 0}} ${{symbol}} share(s) near LTP ${{ltp.toFixed(2)}} | Approx value ${{value.toFixed(2)}} | Holding ${{holding}}`;
      incomeEquitySummary.classList.toggle('signal-red', side === 'SELL' && quantity > holding);
    }}
    async function openIncomeEquityModal(button) {{
      if (!incomeEquityModal) return;
      resetIncomeEquityConfirmation();
      const symbol = button.dataset.symbol || '';
      const company = button.dataset.company || '';
      incomeEquitySnapshot = {{
        symbol,
        quantity: Number(button.dataset.holding || 0),
        average_price: Number(button.dataset.avg || 0),
        ltp: Number(button.dataset.ltp || 0),
        pnl: Number(button.dataset.pnl || 0),
      }};
      incomeEquityModal.style.display = 'flex';
      if (incomeEquityTitle) incomeEquityTitle.textContent = `${{symbol}} Equity Order`;
      if (incomeEquitySymbol) incomeEquitySymbol.value = symbol;
      if (incomeEquityQuantity) incomeEquityQuantity.value = '1';
      if (incomeEquitySide) incomeEquitySide.value = 'BUY';
      if (incomeEquityHolding) incomeEquityHolding.textContent = String(incomeEquitySnapshot.quantity);
      if (incomeEquityAvg) incomeEquityAvg.textContent = Number(incomeEquitySnapshot.average_price || 0).toFixed(2);
      if (incomeEquityLtp) incomeEquityLtp.textContent = Number(incomeEquitySnapshot.ltp || 0).toFixed(2);
      if (incomeEquityPnl) incomeEquityPnl.textContent = Number(incomeEquitySnapshot.pnl || 0).toFixed(2);
      updateIncomeEquitySummary();
      try {{
        const response = await fetch(`/income-growth/equity-quote?symbol=${{encodeURIComponent(symbol)}}`, {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Could not refresh equity data');
        incomeEquitySnapshot = data;
        if (incomeEquityHolding) incomeEquityHolding.textContent = String(data.quantity || 0);
        if (incomeEquityAvg) incomeEquityAvg.textContent = Number(data.average_price || 0).toFixed(2);
        if (incomeEquityLtp) incomeEquityLtp.textContent = Number(data.ltp || 0).toFixed(2);
        if (incomeEquityPnl) {{
          incomeEquityPnl.textContent = Number(data.pnl || 0).toFixed(2);
          incomeEquityPnl.className = Number(data.pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative';
        }}
        updateIncomeEquitySummary();
      }} catch (error) {{
        if (incomeEquitySummary) incomeEquitySummary.textContent = compactClientError(error.message, 'Could not refresh equity data');
      }}
    }}
    for (const button of document.querySelectorAll('.income-equity-stock')) {{
      button.addEventListener('click', () => openIncomeEquityModal(button));
    }}
    incomeEquitySide && incomeEquitySide.addEventListener('change', () => {{
      resetIncomeEquityConfirmation();
      updateIncomeEquitySummary();
    }});
    incomeEquityQuantity && incomeEquityQuantity.addEventListener('input', () => {{
      resetIncomeEquityConfirmation();
      updateIncomeEquitySummary();
    }});
    incomeEquityCancel && incomeEquityCancel.addEventListener('click', () => {{
      resetIncomeEquityConfirmation();
      if (incomeEquityModal) incomeEquityModal.style.display = 'none';
    }});
    incomeEquityReview && incomeEquityReview.addEventListener('click', () => {{
      const quantity = Number(incomeEquityQuantity ? incomeEquityQuantity.value : 0);
      const holding = Number(incomeEquitySnapshot && incomeEquitySnapshot.quantity || 0);
      const side = incomeEquitySide ? incomeEquitySide.value : '';
      if (!Number.isInteger(quantity) || quantity <= 0) {{
        if (incomeEquitySummary) incomeEquitySummary.textContent = 'Enter a valid whole-number quantity greater than zero.';
        return;
      }}
      if (side === 'SELL' && quantity > holding) {{
        if (incomeEquitySummary) incomeEquitySummary.textContent = `SELL blocked: quantity ${{quantity}} exceeds current holding ${{holding}}.`;
        return;
      }}
      resetIncomeEquityConfirmation();
      let remaining = 10;
      if (incomeEquityBreath) incomeEquityBreath.classList.add('active');
      if (incomeEquityBreathText) incomeEquityBreathText.textContent = 'Breathe in';
      incomeEquityCountdownTimer = setInterval(() => {{
        remaining -= 1;
        if (incomeEquityCountdown) incomeEquityCountdown.textContent = String(Math.max(remaining, 0));
        if (incomeEquityBreathText) incomeEquityBreathText.textContent = remaining % 2 === 0 ? 'Breathe in' : 'Breathe out';
        if (remaining <= 0) {{
          stopIncomeEquityCountdown();
          if (incomeEquityBreathText) incomeEquityBreathText.textContent = 'Ready to execute';
          if (incomeEquityConfirmed) incomeEquityConfirmed.value = '1';
          if (incomeEquityExecute) incomeEquityExecute.disabled = false;
        }}
      }}, 1000);
    }});
    incomeGrowthEditGpt && incomeGrowthEditGpt.addEventListener('click', () => {{
      if (incomeGrowthGptModal) incomeGrowthGptModal.style.display = 'flex';
    }});
    incomeGrowthGptCancel && incomeGrowthGptCancel.addEventListener('click', () => {{
      if (incomeGrowthGptModal) incomeGrowthGptModal.style.display = 'none';
      if (incomeGrowthForceGpt) incomeGrowthForceGpt.value = '0';
    }});
    incomeGrowthGptRefresh && incomeGrowthGptRefresh.addEventListener('click', () => {{
      if (incomeGrowthForceGpt) incomeGrowthForceGpt.value = '1';
    }});
    for (const button of document.querySelectorAll('.show-gpt-response')) {{
      button.addEventListener('click', () => {{
        const modal = document.getElementById(button.dataset.target || '');
        if (modal) modal.style.display = 'flex';
      }});
    }}
    for (const button of document.querySelectorAll('.close-gpt-response')) {{
      button.addEventListener('click', () => {{
        const modal = document.getElementById(button.dataset.target || '');
        if (modal) modal.style.display = 'none';
      }});
    }}
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
    function selectedPositionStocks() {{
      const stocks = [];
      const seen = new Set();
      if (!positionForm) return stocks;
      const rows = positionForm.querySelectorAll('table tbody tr');
      for (const row of rows) {{
        const checkbox = row.querySelector('input[name="position_selected"]');
        if (!checkbox || !checkbox.checked || row.cells.length < 3) continue;
        const symbol = row.cells[2].innerText.trim();
        const stock = optionUnderlying(symbol);
        if (stock && !seen.has(stock)) {{
          stocks.push(stock);
          seen.add(stock);
        }}
      }}
      return stocks;
    }}
    async function loadPositionQuoteCheck(stocks) {{
      if (!positionQuoteCheck) return;
      if (!stocks.length) {{
        positionQuoteCheck.textContent = 'No selected position BUY orders found.';
        return;
      }}
      positionQuoteCheck.textContent = `Loading CMP for ${{stocks.join(', ')}}...`;
      try {{
        const response = await fetch('/market-quotes', {{ cache: 'no-store' }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Could not load market quotes');
        const bySymbol = new Map((data.quotes || []).map((quote) => [String(quote.symbol || '').toUpperCase(), quote]));
        positionQuoteCheck.innerHTML = '<div class="guardrail-grid">' + stocks.map((stock) => {{
          const quote = bySymbol.get(stock.toUpperCase());
          if (!quote || quote.ltp === null || quote.ltp === undefined) {{
            return `<div><span>${{escapeHtml(stock)}}</span><strong>N/A</strong><small>Quote unavailable</small></div>`;
          }}
          const pct = quote.change_percent === null || quote.change_percent === undefined ? null : Number(quote.change_percent);
          const sign = pct !== null && pct > 0 ? '+' : '';
          const move = pct === null ? '--' : `${{sign}}${{pct.toFixed(2)}}%`;
          const cls = pct !== null && pct >= 0 ? 'news-sentiment-positive' : 'news-sentiment-negative';
          return `<div class="${{cls}}"><span>${{escapeHtml(stock)}}</span><strong>${{Number(quote.ltp).toFixed(2)}}</strong><small>${{move}} today</small></div>`;
        }}).join('') + '</div>';
      }} catch (error) {{
        positionQuoteCheck.textContent = `Quote check error: ${{error.message}}`;
      }}
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
    function stopPositionCountdown() {{
      if (positionCountdownTimer) {{
        clearInterval(positionCountdownTimer);
        positionCountdownTimer = null;
      }}
    }}
    function openPositionModal() {{
      const stocks = selectedPositionStocks();
      let remaining = Math.max(5, stocks.length * 5);
      pendingPositionSubmit = true;
      positionGood.disabled = true;
      positionCountdown.textContent = String(remaining);
      positionBreathText.textContent = 'Breathe in';
      positionModal.style.display = 'flex';
      loadPositionQuoteCheck(stocks);
      stopPositionCountdown();
      positionCountdownTimer = setInterval(() => {{
        remaining -= 1;
        positionCountdown.textContent = String(Math.max(remaining, 0));
        positionBreathText.textContent = remaining % 2 === 0 ? 'Breathe in' : 'Breathe out';
        if (remaining <= 0) {{
          stopPositionCountdown();
          positionBreathText.textContent = 'Ready';
          positionGood.disabled = false;
        }}
      }}, 1000);
    }}
    function closePositionModal() {{
      pendingPositionSubmit = false;
      if (positionLiveConfirmed) positionLiveConfirmed.value = '0';
      positionModal.style.display = 'none';
      stopPositionCountdown();
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
    positionForm && positionForm.addEventListener('submit', (event) => {{
      const submitter = event.submitter;
      if (!submitter || submitter.id !== 'position-execute-selected-button') {{
        return;
      }}
      const dryRun = positionForm.querySelector('input[name="position_dry_run"]');
      if (dryRun && dryRun.checked) {{
        return;
      }}
      if (positionLiveConfirmed && positionLiveConfirmed.value === '1') {{
        return;
      }}
      event.preventDefault();
      openPositionModal();
    }});
    positionCancel && positionCancel.addEventListener('click', closePositionModal);
    positionGood && positionGood.addEventListener('click', () => {{
      if (positionGood.disabled || !pendingPositionSubmit) return;
      pendingPositionSubmit = false;
      stopPositionCountdown();
      positionModal.style.display = 'none';
      if (positionLiveConfirmed) positionLiveConfirmed.value = '1';
      positionExecuteButton.setAttribute('formaction', '/positions/execute');
      positionForm.requestSubmit(positionExecuteButton);
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
    let homeMmiValue = null;
    let homeGlobalRedCount = 0;
    function setDecisionClass(element, className) {{
      if (!element) return;
      element.classList.remove('decision-green', 'decision-yellow', 'decision-red');
      if (className) element.classList.add(className);
    }}
    function updateHomeDecision() {{
      const biasCard = document.getElementById('home-bias-card');
      const bias = document.getElementById('home-bias');
      const biasDetail = document.getElementById('home-bias-detail');
      const gateCard = document.getElementById('home-new-position-card');
      const gate = document.getElementById('home-new-position');
      const gateDetail = document.getElementById('home-new-position-detail');
      const closeCard = document.getElementById('home-close-card');
      if (!bias || !gate) return;
      const mmi = Number(homeMmiValue || 0);
      const globalRisk = homeGlobalRedCount >= 3;
      if (globalRisk) {{
        bias.textContent = 'Risk-off / protect';
        biasDetail.textContent = 'Several global cues are red. Prefer smaller size, covered calls, or wait.';
        gate.textContent = 'Avoid fresh aggressive trades';
        gateDetail.textContent = 'Only high-score covered CALL/CSP setups after checking news and liquidity.';
        setDecisionClass(biasCard, 'decision-red');
        setDecisionClass(gateCard, 'decision-red');
      }} else if (mmi > 60) {{
        bias.textContent = 'SELL CALL bias';
        biasDetail.textContent = 'Greed zone. Prefer covered CALLs, avoid naked CE, be careful with fresh PUT selling.';
        gate.textContent = 'Only covered CALL / high-score CSP';
        gateDetail.textContent = 'Enter only if score, POP, OTM and capital guardrails are green/yellow.';
        setDecisionClass(biasCard, 'decision-yellow');
        setDecisionClass(gateCard, 'decision-yellow');
      }} else if (mmi && mmi < 40) {{
        bias.textContent = 'SELL PUT watchlist';
        biasDetail.textContent = 'Fear zone. Consider cash-secured PUT only near support and with full assignment cash.';
        gate.textContent = 'CSP only after support holds';
        gateDetail.textContent = 'Wait for stabilization; do not catch falling knives.';
        setDecisionClass(biasCard, 'decision-yellow');
        setDecisionClass(gateCard, 'decision-yellow');
      }} else {{
        bias.textContent = 'Neutral / wait for edge';
        biasDetail.textContent = 'No strong mood signal. Let Research and Positions decide.';
        gate.textContent = 'Trade only best scores';
        gateDetail.textContent = 'Prefer 3+ green indicators and no event risk.';
        setDecisionClass(biasCard, 'decision-green');
        setDecisionClass(gateCard, 'decision-green');
      }}
      setDecisionClass(closeCard, 'decision-green');
    }}
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
          homeMmiValue = mmi;
          if (mmi > 60) {{
            action.innerHTML = '| Signal: <strong>SELL CALL</strong>';
          }} else if (mmi < 40) {{
            action.innerHTML = '| Signal: <strong>SELL PUT</strong>';
          }} else {{
            action.innerHTML = '| Signal: <strong>WAIT / NEUTRAL</strong>';
          }}
          updateHomeDecision();
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
    if (isHomePage) {{
      refreshMmi();
      setInterval(refreshMmi, {TOP_QUOTE_REFRESH_MS});
    }}
    async function refreshGlobalQuotes() {{
      const cards = Array.from(document.querySelectorAll('.global-card[data-global-symbol]'));
      if (!cards.length) return;
      const errorBox = document.getElementById('global-error');
      const inverseRiskSymbols = new Set(['KITE:INDIA_VIX', '^INDIAVIX', 'CL=F', 'INR=X']);
      const isRiskRed = (symbol, pct) => inverseRiskSymbols.has(symbol) ? pct > 0.5 : pct < -0.5;
      const isRiskGreen = (symbol, pct) => inverseRiskSymbols.has(symbol) ? pct <= 0 : pct >= 0;
      try {{
        const response = await fetch('/global-quotes', {{ cache: 'no-store' }});
        const data = await response.json();
        const bySymbol = new Map((data.quotes || []).map((quote) => [quote.symbol, quote]));
        if (errorBox) {{
          errorBox.style.display = data.ok ? 'none' : 'block';
          errorBox.textContent = data.ok ? '' : compactClientError(data.error, 'Some global quotes unavailable');
        }}
        let redCount = 0;
        for (const card of cards) {{
          const symbol = card.dataset.globalSymbol;
          const quote = bySymbol.get(symbol);
          const ltp = card.querySelector('.global-ltp');
          const change = card.querySelector('.global-change');
          if (!quote || quote.ltp === null || quote.ltp === undefined) {{
            ltp.textContent = 'N/A';
            change.textContent = '--';
            change.className = 'global-change';
            card.classList.remove('up', 'down');
            continue;
          }}
          ltp.textContent = Number(quote.ltp).toFixed(2);
          if (quote.change_percent === null || quote.change_percent === undefined) {{
            change.textContent = '--';
            change.className = 'global-change';
            card.classList.remove('up', 'down');
          }} else {{
            const pct = Number(quote.change_percent);
            const sign = pct > 0 ? '+' : '';
            change.textContent = `${{sign}}${{pct.toFixed(2)}}%`;
            change.className = `global-change ${{pct >= 0 ? 'up' : 'down'}}`;
            card.classList.toggle('up', isRiskGreen(symbol, pct));
            card.classList.toggle('down', isRiskRed(symbol, pct));
            if (isRiskRed(symbol, pct)) redCount += 1;
          }}
        }}
        homeGlobalRedCount = redCount;
        updateHomeDecision();
      }} catch (error) {{
        if (errorBox) {{
          errorBox.style.display = 'block';
          errorBox.textContent = compactClientError(error.message, 'Global quote error');
        }}
      }}
    }}
    const refreshGlobalButton = document.getElementById('refresh-global-quotes');
    refreshGlobalButton && refreshGlobalButton.addEventListener('click', refreshGlobalQuotes);
    if (isHomePage) {{
      refreshGlobalQuotes();
      setInterval(refreshGlobalQuotes, {TOP_QUOTE_REFRESH_MS});
    }}
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
          quoteError.textContent = compactClientError(error.message, 'Kite quote error');
        }}
        for (const card of cards) {{
          card.querySelector('.quote-ltp').textContent = 'N/A';
          card.querySelector('.quote-change').textContent = error.message.includes('api_key') || error.message.includes('access_token')
            ? 'Auth error'
            : 'Kite quote error';
        }}
      }}
    }}
    const refreshMarketButton = document.getElementById('refresh-market-quotes');
    refreshMarketButton && refreshMarketButton.addEventListener('click', refreshQuotes);
    const kiteLtpDisclosure = document.getElementById('kite-ltp-disclosure');
    let kiteLtpLoaded = false;
    kiteLtpDisclosure && kiteLtpDisclosure.addEventListener('toggle', () => {{
      if (kiteLtpDisclosure.open && !kiteLtpLoaded) {{
        kiteLtpLoaded = true;
        refreshQuotes();
      }}
    }});
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
          const dma = card.querySelector('.commodity-dma');
          const action = card.querySelector('.commodity-action');
          const buyButton = card.querySelector('.commodity-buy-button');
          if (!quote || !quote.ltp) {{
            price.textContent = 'N/A';
            change.textContent = 'Quote unavailable';
            change.className = 'commodity-change';
            if (dma) dma.textContent = '50 DMA -- | 200 DMA --';
            action.textContent = 'Wait';
            if (buyButton) buyButton.textContent = `Add more ${{assetName}}`;
            card.classList.remove('buy-now');
            card.classList.remove('below-200-dma');
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
          if (dma) {{
            const dma50 = quote.dma_50 === null || quote.dma_50 === undefined ? '--' : Number(quote.dma_50).toFixed(2);
            const dma200 = quote.dma_200 === null || quote.dma_200 === undefined ? '--' : Number(quote.dma_200).toFixed(2);
            dma.innerHTML = `<span>50 DMA ${{dma50}}</span><span class="dma-200">200 DMA ${{dma200}}</span>`;
          }}
          const below200Dma = Boolean(quote.below_200_dma);
          card.classList.toggle('below-200-dma', below200Dma);
          card.classList.toggle('buy-now', Boolean(quote.buy_signal));
          action.innerHTML = quote.buy_signal
            ? `<strong>BUY NOW</strong> | ${{escapeHtml(quote.action || 'buy the ETF today')}} (${{quote.multiplier}}x)`
            : below200Dma
            ? `<strong>BELOW 200 DMA</strong> | Review accumulation`
            : `Wait | fall ${{Number(quote.daily_fall_pct || 0).toFixed(2)}}%`;
          if (buyButton) {{
            buyButton.textContent = `Add more ${{assetName}}`;
          }}
        }}
      }} catch (error) {{
        openKiteSetupForError(error.message);
        if (errorBox) {{
          errorBox.style.display = 'block';
          errorBox.textContent = compactClientError(error.message, 'ETF quote error');
        }}
      }}
    }}
    const refreshCommodityButton = document.getElementById('refresh-commodity-quotes');
    refreshCommodityButton && refreshCommodityButton.addEventListener('click', refreshCommodityQuotes);
  </script>
</body>
</html>"""
    return html_doc.encode("utf-8")


def render_fallback_error_page(error: str) -> bytes:
    body = render_graceful_error(error, "Page render error")
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vikalp Income Desk - Error</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #eef7f5; color: #07152b; }}
    main {{ max-width: 980px; margin: 40px auto; padding: 0 18px; }}
    .alert {{ border: 1px solid #fecaca; background: #fee2e2; color: #7f1d1d; border-radius: 12px; padding: 16px; }}
    .alert-close {{ float: right; }}
    pre {{ white-space: pre-wrap; font-family: Consolas, monospace; }}
    textarea {{ width: 100%; min-height: 220px; }}
    a {{ color: #006b5f; font-weight: 700; }}
  </style>
</head>
<body>
  <main>
    <h1>Vikalp Income Desk</h1>
    {body}
    <p><a href="/">Back to app</a></p>
  </main>
</body>
</html>"""
    return html_doc.encode("utf-8")


class KiteWebHandler(BaseHTTPRequestHandler):
    server_version = "KiteCSVTrader/1.0"

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except Exception as exc:
            try:
                content = render_fallback_error_page(f"{exc}\n\n{traceback.format_exc()}")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception:
                raise

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
            state = PageState(active_tab="positions")
            try:
                (
                    state.positions_rows,
                    state.positions_summary,
                ), state.console_log = call_with_console(positions_research, True)
                state.message = (
                    f"Loaded fresh Kite analytics for {len(state.positions_rows)} active option position(s)."
                )
            except Exception as exc:
                state.error = f"{friendly_external_error(exc, 'Kite positions')}\n\n{traceback.format_exc()}"
            self.send_page(state)
            return
        if parsed_url.path == "/home":
            self.send_page(PageState(active_tab="home"))
            return
        if parsed_url.path == "/orders":
            state = PageState(active_tab="order-management")
            try:
                state.order_book, state.console_log = call_with_console(
                    kite_order_book,
                    True,
                )
                state.message = f"Loaded {len(state.order_book)} current Kite order(s)."
            except Exception as exc:
                state.order_book_error = friendly_external_error(exc, "Kite orders")
                state.error = f"{state.order_book_error}\n\n{traceback.format_exc()}"
            self.send_page(state)
            return
        if parsed_url.path == "/income":
            state = PageState(active_tab="income")
            try:
                calculated_at = apply_income_dashboard_snapshot(state)
                state.message = (
                    f"Loaded cached INCOME decision dashboard calculated at {calculated_at}. "
                    "Use Recalculate Best 3 PE SELL for a fresh scan."
                )
            except Exception as exc:
                state.income_error = f"{friendly_external_error(exc, 'INCOME PE ranking')}\n\n{traceback.format_exc()}"
            self.send_page(state)
            return
        if parsed_url.path == "/income/pe-quote":
            query = parse_qs(parsed_url.query, keep_blank_values=True)
            try:
                snapshot = income_pe_order_snapshot(
                    first(query, "underlying"),
                    first(query, "strike"),
                )
                self.send_json({"ok": True, **snapshot})
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": friendly_external_error(exc, "Income PE quote"),
                    }
                )
            return
        if parsed_url.path == "/ce-scan/quote":
            query = parse_qs(parsed_url.query, keep_blank_values=True)
            try:
                snapshot = ce_sell_order_snapshot(first(query, "underlying"))
                self.send_json({"ok": True, **snapshot})
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": friendly_external_error(exc, "Covered CE quote"),
                    }
                )
            return
        if parsed_url.path == "/investing":
            self.send_page(PageState(active_tab="investing"))
            return
        if parsed_url.path == "/equity":
            self.send_page(PageState(active_tab="equity"))
            return
        if parsed_url.path == "/equity/quote":
            query = parse_qs(parsed_url.query, keep_blank_values=True)
            try:
                snapshot = equity_holding_snapshot(
                    first(query, "symbol"),
                    first(query, "exchange", "NSE"),
                )
                self.send_json({"ok": True, **snapshot})
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": friendly_external_error(exc, "Kite equity holding"),
                    }
                )
            return
        if parsed_url.path == "/income-growth":
            self.send_page(PageState(active_tab="income-growth"))
            return
        if parsed_url.path == "/income-growth/equity-quote":
            query = parse_qs(parsed_url.query, keep_blank_values=True)
            try:
                snapshot = income_growth_equity_snapshot(first(query, "symbol"))
                self.send_json({"ok": True, **snapshot})
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": friendly_external_error(exc, "Income Growth equity quote"),
                    }
                )
            return
        if parsed_url.path == "/research":
            state = PageState(active_tab="research")
            try:
                load_default_csv_research(state)
            except Exception as exc:
                state.error = (
                    f"{friendly_external_error(exc, 'CSV research')}\n\n"
                    f"{traceback.format_exc()}"
                )
                state.message = f"Load today's CSV file: {DEFAULT_CSV_PATH.name}"
            self.send_page(state)
            return
        if parsed_url.path == "/execute":
            state = PageState(active_tab="place")
            try:
                load_default_trade_preview(state)
            except Exception as exc:
                state.error = (
                    f"{friendly_external_error(exc, 'CSV trade preview')}\n\n"
                    f"{traceback.format_exc()}"
                )
                state.message = f"Load today's CSV file: {DEFAULT_CSV_PATH.name}"
            try:
                load_ce_sell_dashboard(state)
            except Exception as exc:
                state.console_log = f"{state.console_log}\nCE scan unavailable: {friendly_external_error(exc, 'CE scan')}"
            self.send_page(state)
            return
        if parsed_url.path.startswith("/gpt"):
            self.send_page(PageState(active_tab="gpt"))
            return
        if parsed_url.path == "/kite-setup":
            self.send_page(PageState(active_tab="kite-setup"))
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
                        "error": friendly_external_error(exc, "MMI"),
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
                        "error": friendly_external_error(exc, "Kite quote"),
                        "quotes": [],
                    }
                )
            return
        if self.path == "/global-quotes":
            try:
                self.send_json(fetch_global_market_quotes())
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": friendly_external_error(exc, "Global market quote"),
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
                        "error": friendly_external_error(exc, "Commodity ETF quote"),
                        "quotes": [],
                    }
                )
            return
        setup_issue = kite_setup_issue()
        state = PageState(
            active_tab=default_active_tab(),
            error=setup_issue,
        )
        if parsed_url.path == "/" and not setup_issue:
            try:
                load_default_trade_preview(state)
            except Exception as exc:
                state.error = (
                    f"{friendly_external_error(exc, 'CSV trade preview')}\n\n"
                    f"{traceback.format_exc()}"
                )
                state.message = f"Load today's CSV file: {DEFAULT_CSV_PATH.name}"
            try:
                load_ce_sell_dashboard(state)
            except Exception as exc:
                state.console_log = f"{state.console_log}\nCE scan unavailable: {friendly_external_error(exc, 'CE scan')}"
        self.send_page(state)

    def do_POST(self) -> None:
        request_path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(body, keep_blank_values=True)
        if request_path == "/login":
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
                "place"
                if request_path in {"/load", "/execute"}
                else "positions"
                if request_path.startswith("/positions")
                else "research"
                if request_path.startswith("/csv")
                else "commodity"
                if request_path.startswith("/commodity")
                else "income-growth"
                if request_path.startswith("/income-growth")
                else "income"
                if request_path.startswith("/income")
                else "investing"
                if request_path.startswith("/investing")
                else "equity"
                if request_path.startswith("/equity")
                else "gpt"
                if request_path.startswith("/gpt")
                else "kite-setup"
                if request_path.startswith("/kite-setup") or request_path.startswith("/kite-token") or request_path.startswith("/kite-ip") or request_path.startswith("/scheduler")
                else "order-management"
                if request_path.startswith("/orders")
                else "analytics"
                if request_path.startswith("/analytics")
                else "research"
                if request_path.startswith("/research")
                else "place"
                if request_path.startswith("/ce-scan")
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
            kite_profile=selected_kite_profile_name(first(form, "kite_profile")),
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
            position_live_confirmed=first(form, "position_live_confirmed") == "1",
            gpt_url=first(form, "gpt_url", DEFAULT_GPT_SHARE_URL),
            gpt_conversation=first(form, "gpt_conversation"),
            gpt_csv_text=first(form, "gpt_csv_text"),
            gpt_api_output=first(form, "gpt_api_output"),
            gpt_api_response_id=first(form, "gpt_api_response_id"),
            openai_api_key=first(form, "openai_api_key"),
            openai_model=first(form, "openai_model", DEFAULT_OPENAI_MODEL),
            openai_system_prompt=first(form, "openai_system_prompt", read_openai_csv_system_prompt()),
            openai_prompt=first(form, "openai_prompt", DEFAULT_OPENAI_PROMPT),
            income_growth_gpt_csv=first(form, "income_growth_gpt_csv"),
            income_growth_gpt_output=first(form, "income_growth_gpt_output"),
            income_growth_gpt_response_id=first(form, "income_growth_gpt_response_id"),
            income_growth_gpt_prompt=first(form, "income_growth_gpt_prompt"),
            income_growth_gpt_cached=first(form, "income_growth_gpt_cached") == "1",
            analytics_symbol=first(form, "analytics_symbol"),
            kite_request_token=first(form, "kite_request_token"),
            etf_buy_amount=float(first(form, "etf_buy_amount", str(etf_buy_amount_setting())) or etf_buy_amount_setting()),
            option_sell_markup_percent=float(
                first(
                    form,
                    "option_sell_markup_percent",
                    str(option_sell_markup_percent_setting()),
                )
                or option_sell_markup_percent_setting()
            ),
            home_tickers=first(form, "home_tickers", home_tickers_text()),
        )

        try:
            if request_path == "/load":
                persist_message = persist_default_csv_text(state.csv_text)
                state.rows, state.csv_text = load_rows(state.csv_path, state.csv_text)
                validate_kite_order_rows(state.rows)
                state.orders, state.console_log = call_with_console(
                    build_orders,
                    state.rows,
                    state.no_ltp_price,
                    state.keep_existing_orders,
                )
                state.trade_validations = validate_trade_orders(state.orders)
                state.selected_indexes = default_selected_order_indexes(
                    state.orders,
                    state.trade_validations,
                )
                state.message = f"{persist_message} Loaded {len(state.orders)} order(s).".strip()
                try:
                    load_ce_sell_dashboard(state)
                except Exception as exc:
                    state.console_log = f"{state.console_log}\nCE scan unavailable: {friendly_external_error(exc, 'CE scan')}"
            elif request_path == "/ce-scan/load":
                load_ce_sell_dashboard(state, True)
                state.message = (
                    f"Fresh CE scan completed. Top {len(state.ce_sell_top or [])}; "
                    f"Watch {len(state.ce_sell_watch or [])}; Avoid {len(state.ce_sell_avoid or [])}."
                )
            elif request_path == "/ce-scan/sell":
                if first(form, "ce_sell_confirmed") != "1":
                    raise PermissionError("Covered CE SELL order needs 10-second breathe confirmation.")
                underlying = first(form, "ce_sell_underlying")
                result, order_log = call_with_console(
                    place_approved_ce_sell_order,
                    underlying,
                )
                state.results = [result]
                state.console_log = f"{order_log}{state.console_log}"
                load_ce_sell_dashboard(state, True)
                state.message = f"Submitted approved covered CE order for {underlying.upper()}."
            elif request_path == "/csv/save-today":
                state.csv_path, state.message = save_today_csv_text(state.csv_text)
                state.csv_text = Path(state.csv_path).read_text(encoding="utf-8-sig")
                state.research_rows, research_log = call_with_console(
                    research_csv_symbols,
                    state.csv_text,
                    state.csv_path,
                )
                state.console_log = f"{state.console_log}{research_log}"
                state.message = (
                    f"{state.message} Loaded CSV Symbol Research Comparison for "
                    f"{len(state.research_rows)} symbol(s)."
                )
            elif request_path == "/execute":
                rows_payload = first(form, "rows_payload")
                state.rows = decode_rows(rows_payload) if rows_payload else None
                if not state.rows:
                    persist_message = persist_default_csv_text(state.csv_text)
                    state.rows, state.csv_text = load_rows(state.csv_path, state.csv_text)
                else:
                    persist_message = ""
                validate_kite_order_rows(state.rows)
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
                state.selected_indexes = selected
                if state.dry_run:
                    state.message = (
                        f"{persist_message} Dry run completed for "
                        f"{len(state.orders)} selected order(s)."
                    ).strip()
                else:
                    state.message = (
                        f"{persist_message} Submitted {len(state.orders)} selected order(s) to Kite."
                    ).strip()
            elif request_path == "/orders/cancel-all":
                state.results, state.console_log = call_with_console(cancel_all_open_orders)
                try:
                    state.order_book = kite_order_book(True)
                except Exception as exc:
                    state.order_book_error = str(exc)
                cancelled = sum(1 for item in state.results if item.get("status") == "CANCELLED")
                errors = sum(1 for item in state.results if item.get("status") == "ERROR")
                state.message = f"Cancel all completed. Cancelled {cancelled} order(s); errors {errors}."
            elif request_path == "/orders/cancel-selected":
                selected_order_keys = form.get("order_key", [])
                state.results, state.console_log = call_with_console(
                    cancel_selected_orders,
                    selected_order_keys,
                )
                try:
                    state.order_book = kite_order_book(True)
                except Exception as exc:
                    state.order_book_error = str(exc)
                cancelled = sum(1 for item in state.results if item.get("status") == "CANCELLED")
                errors = sum(1 for item in state.results if item.get("status") == "ERROR")
                skipped = sum(1 for item in state.results if item.get("status") == "SKIPPED")
                state.message = (
                    f"Cancel selected completed. Cancelled {cancelled}; skipped {skipped}; errors {errors}."
                )
            elif request_path == "/orders/modify-selected":
                selected_order_keys = form.get("order_key", [])
                state.results, state.console_log = call_with_console(
                    modify_selected_orders,
                    selected_order_keys,
                    form,
                )
                try:
                    state.order_book = kite_order_book(True)
                except Exception as exc:
                    state.order_book_error = str(exc)
                modified = sum(1 for item in state.results if item.get("status") == "MODIFIED")
                errors = sum(1 for item in state.results if item.get("status") == "ERROR")
                skipped = sum(1 for item in state.results if item.get("status") == "SKIPPED")
                state.message = (
                    f"Modify selected completed. Modified {modified}; skipped {skipped}; errors {errors}."
                )
            elif request_path == "/orders/refresh":
                state.order_book, state.console_log = call_with_console(kite_order_book, True)
                state.message = f"Loaded {len(state.order_book)} Kite order(s)."
            elif request_path == "/positions/load":
                clear_app_cache(("kite:positions", "kite:quote", "positions-research"))
                state.position_orders, state.console_log = call_with_console(
                    build_position_buy_orders,
                    state,
                )
                state.position_selected_indexes = set(range(len(state.position_orders)))
                state.message = f"Loaded {len(state.position_orders)} BUY order(s) from current positions."
            elif request_path == "/positions/execute":
                orders_payload = first(form, "position_orders_payload")
                state.position_orders = decode_orders(orders_payload) if orders_payload else None
                if not state.position_orders:
                    state.position_orders, state.console_log = call_with_console(
                        build_position_buy_orders,
                        state,
                    )
                else:
                    fresh_kite = kite_buy_positions.kite_client()
                    state.position_orders = refresh_position_buy_order_prices(
                        state.position_orders,
                        fresh_kite,
                        position_args_from_state(state),
                    )
                selected = {int(value) for value in form.get("position_selected", [])}
                if selected and not state.position_dry_run and not state.position_live_confirmed:
                    raise PermissionError(
                        "Position BUY live order needs breathe confirmation before order placement."
                    )
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
            elif request_path == "/positions/close-buy":
                close_symbol = first(form, "close_symbol")
                result, state.console_log = call_with_console(
                    place_position_close_buy_order,
                    close_symbol,
                )
                state.position_results = [result]
                (
                    state.positions_rows,
                    state.positions_summary,
                ), refresh_log = call_with_console(positions_research, True)
                state.console_log = f"{state.console_log}{refresh_log}"
                state.message = f"Submitted BUY close order for {close_symbol.upper()}."
            elif request_path == "/gpt/load":
                state.gpt_conversation, state.console_log = call_with_console(
                    fetch_gpt_conversation,
                    state.gpt_url,
                )
                state.message = "Fetched GPT share conversation. Review it, then extract CSV."
            elif request_path == "/gpt/extract":
                state.gpt_csv_text = extract_csv_from_text(state.gpt_conversation)
                state.message = "Extracted CSV from GPT conversation."
            elif request_path == "/gpt/generate":
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
            elif request_path in {"/gpt/save", "/gpt/save-preview", "/gpt/save_preview"}:
                if not state.gpt_csv_text.strip():
                    state.gpt_csv_text = extract_csv_from_text(state.gpt_conversation)
                state.gpt_csv_text = normalize_kite_csv_input(state.gpt_csv_text)
                persist_message = persist_default_csv_text(state.gpt_csv_text)
                state.csv_text = state.gpt_csv_text
                if request_path in {"/gpt/save-preview", "/gpt/save_preview"}:
                    state.rows = parse_csv_text(state.gpt_csv_text)
                    state.orders, state.console_log = call_with_console(
                        build_orders,
                        state.rows,
                        True,
                        state.keep_existing_orders,
                    )
                    state.trade_validations = validate_trade_orders(state.orders)
                    state.selected_indexes = default_selected_order_indexes(
                        state.orders,
                        state.trade_validations,
                    )
                    state.message = (
                        f"{persist_message} Previewed {len(state.orders)} order(s)."
                    ).strip()
                else:
                    state.message = persist_message
            elif request_path == "/kite-setup":
                profile_name = selected_kite_profile_name(state.kite_profile)
                profile_values = kite_profile_values_from_state(state)
                saved_profile_values = save_kite_profile(profile_name, profile_values)
                apply_kite_profile_to_env(saved_profile_values)
                save_env_values(
                    {
                        "KITE_CONFIRM_LIVE_ORDER": saved_profile_values.get("KITE_CONFIRM_LIVE_ORDER", "YES"),
                        "KITE_API_KEY": saved_profile_values.get("KITE_API_KEY", ""),
                        "KITE_API_SECRET": saved_profile_values.get("KITE_API_SECRET", ""),
                        "KITE_ACCESS_TOKEN": saved_profile_values.get("KITE_ACCESS_TOKEN", ""),
                        "OPENAI_API_KEY": state.openai_api_key or env_value("OPENAI_API_KEY"),
                    }
                )
                normalized_home_tickers = normalize_home_tickers(state.home_tickers)
                save_app_settings(
                    {
                        "etf_buy_amount": state.etf_buy_amount,
                        "option_sell_markup_percent": state.option_sell_markup_percent,
                        "home_tickers": normalized_home_tickers,
                        "selected_kite_profile": profile_name,
                    }
                )
                state.home_tickers = "\n".join(normalized_home_tickers)
                clear_app_cache(("market-quotes", "kite:quote", "income-dashboard", "ce-sell-dashboard"))
                state.message = (
                    f"Kite setup saved for {profile_name}. ETF buy amount {format_buy_amount(state.etf_buy_amount)}. "
                    f"Option SELL markup {state.option_sell_markup_percent:.2f}%. "
                    f"Home watchlist has {len(normalized_home_tickers)} ticker(s)."
                )
            elif request_path == "/kite-token/generate":
                access_token, state.console_log = call_with_console(
                    generate_kite_access_token,
                    state.kite_request_token,
                )
                state.access_token = access_token
                profile_name = selected_kite_profile_name(state.kite_profile)
                saved_profile_values = save_kite_profile(
                    profile_name,
                    kite_profile_values_from_state(state, access_token),
                )
                apply_kite_profile_to_env(saved_profile_values)
                state.message = (
                    f"Generated today's KITE_ACCESS_TOKEN for {profile_name}, saved it to .env, "
                    "and applied it to this running app."
                )
            elif request_path == "/kite-token/save":
                access_token, state.console_log = call_with_console(
                    save_kite_access_token,
                    state.access_token or env_value("KITE_ACCESS_TOKEN"),
                )
                state.access_token = access_token
                profile_name = selected_kite_profile_name(state.kite_profile)
                saved_profile_values = save_kite_profile(
                    profile_name,
                    kite_profile_values_from_state(state, access_token),
                )
                apply_kite_profile_to_env(saved_profile_values)
                state.message = (
                    f"Saved KITE_ACCESS_TOKEN for {profile_name} to .env and applied it to this running app."
                )
            elif request_path == "/kite-ip/check":
                state.kite_ip_data, state.console_log = call_with_console(fetch_public_ip_data)
                ips = [item["ip"] for item in state.kite_ip_data if item.get("ip")]
                state.message = (
                    "Fetched current public IP. Add the matching IP to Kite developer console."
                    if ips
                    else "Could not fetch public IP. Check network and try again."
                )
            elif request_path in {
                "/scheduler/start",
                "/scheduler/stop",
                "/scheduler/pause-day",
            }:
                job_key = first(form, "job_name")
                action = request_path.rsplit("/", 1)[-1]
                updated = update_scheduled_job_control(job_key, action)
                job_name = scheduled_job_definitions()[job_key]["name"]
                state.message = f"{job_name}: {updated.get('message', 'Schedule updated.')}"
            elif request_path == "/analytics/load":
                state.analytics_data, state.console_log = call_with_console(
                    option_analytics_for_symbol,
                    state.analytics_symbol,
                )
                state.message = f"Loaded analytics for {state.analytics_symbol.upper()}."
            elif request_path == "/research/load":
                state.research_rows, state.console_log = call_with_console(
                    research_csv_symbols,
                    state.csv_text,
                    state.csv_path,
                )
                state.message = f"Research completed for {len(state.research_rows)} CSV symbol(s)."
            elif request_path == "/income/load":
                calculated_at = apply_income_dashboard_snapshot(state, True)
                state.message = (
                    f"Fresh INCOME scan completed at {calculated_at}. "
                    f"Ranked {len(state.income_pe_top or [])} Top PE candidate(s); "
                    f"{len(state.income_pe_avoid or [])} blocked today."
                )
            elif request_path == "/investing/load":
                (
                    state.investing_rows,
                    state.investing_summary,
                ), state.console_log = call_with_console(investing_holdings_rows)
                state.message = f"Investing portfolio refreshed for {len(state.investing_rows)} holding(s)."
            elif request_path == "/equity/load":
                (
                    state.equity_rows,
                    state.equity_summary,
                ), state.console_log = call_with_console(equity_holdings_snapshot)
                state.message = f"Loaded {len(state.equity_rows)} live Kite equity holding(s)."
            elif request_path == "/equity/order":
                if first(form, "equity_confirmed") != "1":
                    raise PermissionError("Equity order needs 10-second breathe confirmation.")
                result, order_log = call_with_console(
                    place_equity_holding_order,
                    first(form, "equity_symbol"),
                    first(form, "equity_exchange", "NSE"),
                    first(form, "equity_side"),
                    first(form, "equity_quantity"),
                    first(form, "equity_limit_price"),
                )
                state.equity_results = [result]
                (
                    state.equity_rows,
                    state.equity_summary,
                ), refresh_log = call_with_console(equity_holdings_snapshot)
                state.console_log = f"{order_log}{refresh_log}"
                state.message = (
                    f"Submitted {first(form, 'equity_side').upper()} equity limit order "
                    f"for {first(form, 'equity_symbol').upper()}."
                )
            elif request_path == "/income-growth/load":
                (
                    state.income_growth_rows,
                    state.income_growth_summary,
                ), state.console_log = call_with_console(income_growth_candidates)
                state.message = f"Income growth capacity refreshed for {len(state.income_growth_rows)} holding(s)."
            elif request_path == "/income-growth/save-holding":
                (updated_symbol, _), save_log = call_with_console(
                    save_income_growth_holding_from_form,
                    form,
                )
                (
                    state.income_growth_rows,
                    state.income_growth_summary,
                ), refresh_log = call_with_console(income_growth_candidates)
                state.console_log = f"{save_log}{refresh_log}"
                state.message = (
                    f"Saved Income Growth holding data for {updated_symbol}. "
                    f"Refreshed {len(state.income_growth_rows)} option-income candidate(s)."
                )
            elif request_path == "/income-growth/equity-order":
                if first(form, "income_growth_equity_confirmed") != "1":
                    raise PermissionError(
                        "Income Growth equity order needs 10-second breathe confirmation."
                    )
                result, state.console_log = call_with_console(
                    place_income_growth_equity_order,
                    first(form, "income_growth_equity_symbol"),
                    first(form, "income_growth_equity_side"),
                    first(form, "income_growth_equity_quantity"),
                )
                state.income_growth_equity_results = [result]
                (
                    state.income_growth_rows,
                    state.income_growth_summary,
                ), refresh_log = call_with_console(income_growth_candidates)
                state.console_log = f"{state.console_log}{refresh_log}"
                state.message = (
                    f"Submitted {first(form, 'income_growth_equity_side').upper()} equity order "
                    f"for {first(form, 'income_growth_equity_symbol').upper()}."
                )
            elif request_path == "/income-growth/gpt":
                (
                    state.income_growth_rows,
                    state.income_growth_summary,
                ), growth_log = call_with_console(income_growth_candidates)
                (
                    state.income_growth_gpt_csv,
                    state.income_growth_gpt_output,
                    state.income_growth_gpt_response_id,
                    state.income_growth_gpt_cached,
                ), gpt_log = call_with_console(
                    validate_income_growth_with_openai,
                    state.income_growth_rows,
                    state.income_growth_summary,
                    state.openai_model,
                    state.openai_system_prompt,
                    state.income_growth_gpt_prompt,
                    first(form, "income_growth_force_gpt") == "1",
                )
                state.console_log = f"{growth_log}{gpt_log}"
                state.message = (
                    "GPT validation reused cached CSV. Review before trading."
                    if state.income_growth_gpt_cached
                    else "GPT validated Income Growth candidates and returned fresh Kite CSV. Review before trading."
                )
            elif request_path == "/income/sell-ce":
                underlying = first(form, "income_underlying")
                result, order_log = call_with_console(
                    place_income_covered_call_order,
                    underlying,
                )
                state.income_results = [result]
                invalidate_kite_trade_cache()
                refresh_at = apply_income_dashboard_snapshot(state, True)
                state.console_log = f"{order_log}{state.console_log}\nDashboard refreshed at {refresh_at}."
                state.message = f"Submitted covered CE order for {underlying.upper()}."
            elif request_path == "/income/sell-pe":
                if first(form, "income_pe_confirmed") != "1":
                    raise PermissionError("Income PE SELL order needs 10-second breathe confirmation.")
                underlying = first(form, "income_underlying")
                result, order_log = call_with_console(
                    place_income_cash_secured_put_order,
                    underlying,
                    first(form, "income_target_strike"),
                )
                state.income_results = [result]
                invalidate_kite_trade_cache()
                refresh_at = apply_income_dashboard_snapshot(state, True)
                state.console_log = f"{order_log}{state.console_log}\nDashboard refreshed at {refresh_at}."
                state.message = f"Submitted cash-secured PE order for {underlying.upper()}."
            elif request_path == "/positions-research/load":
                (
                    state.positions_rows,
                    state.positions_summary,
                ), state.console_log = call_with_console(positions_research, True)
                state.message = (
                    f"Loaded fresh Kite analytics for {len(state.positions_rows)} active option position(s)."
                )
            elif request_path == "/commodity/refresh":
                state.commodity_holdings, state.console_log = call_with_console(
                    commodity_etf_holdings
                )
                non_zero = sum(1 for item in state.commodity_holdings if item.get("quantity"))
                state.message = f"Refreshed commodity ETF holdings. Found {non_zero} holding(s)."
            elif request_path == "/commodity/buy":
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
            elif request_path == "/commodity/sell":
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
                state.error = f"Unknown path: {request_path}"
        except Exception as exc:
            if request_path == "/csv/save-today":
                state.csv_path, state.csv_text = restore_csv_text_after_save_error(state.csv_path)
            state.error = f"{friendly_external_error(exc, 'Kite/App action')}\n\n{traceback.format_exc()}"

        self.send_page(state)

    def send_page(self, state: PageState) -> None:
        try:
            redirect_state_to_kite_setup_on_error(state)
            content = render_page(state)
        except Exception as exc:
            content = render_fallback_error_page(f"{exc}\n\n{traceback.format_exc()}")
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
    scheduler_stop = threading.Event()
    scheduler_thread = threading.Thread(
        target=position_close_scheduler_loop,
        args=(scheduler_stop,),
        name="position-close-scheduler",
        daemon=True,
    )
    scheduler_thread.start()
    print(f"Kite CSV Trader running at http://{host}:{port}")
    print("Default close-position BUY scheduler enabled for weekdays at 09:20 IST.")
    print("Intraday missing close-order guard enabled every 15 minutes from 09:30 to 15:15 IST.")
    print("Income Growth GPT CSV scheduler enabled for weekdays at 09:30 IST.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Kite CSV Trader.")
    finally:
        scheduler_stop.set()
        scheduler_thread.join(timeout=2)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
