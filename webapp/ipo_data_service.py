"""IPO dashboard data service.

This module keeps IPO data, scoring, cache, and snapshot persistence separate
from the trading app. Production mode never uses local demo rows for ranking or
buy-zone decisions; seed data is available only when IPO_DATA_MODE=demo.
"""

from __future__ import annotations

import csv
import html as html_lib
import io
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ipo_cache import ensure_ipo_cache_schema, load_or_generate, make_ipo_cache_key
from ipo_scoring_engine import filter_multibaggers_or_all, rank_ipo_candidates
from ipo_screener_config import (
    IPO_EXPORT_FIELD_SETS,
    IPO_MARKET_TYPE_OPTIONS as CONFIG_IPO_MARKET_TYPE_OPTIONS,
    IPO_RANKING_VIEWS as CONFIG_IPO_RANKING_VIEWS,
    IPO_THEME_OPTIONS as CONFIG_IPO_THEME_OPTIONS,
)
from ipo_screener_engine import (
    build_ipo_screener_payload,
    infer_market_type,
    infer_theme,
    normalize_ipo_record,
)


QUARTER_OPTIONS = ["Latest Available", "Q1", "Q2", "Q3", "Q4"]

IPO_HTTP_TIMEOUT_SECONDS = 7
IPO_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
CHITTORGARH_MAINBOARD_YEAR_URL = "https://www.chittorgarh.com/ipo/ipo_perf_tracker.asp?year={year}"
CHITTORGARH_MAINBOARD_FALLBACK_URL = "https://www.chittorgarh.com/ipo/ipo_perf_tracker.asp"
CHITTORGARH_SME_YEAR_URL = "https://www.chittorgarh.com/ipo/ipo_perf_tracker.asp?exchange=sme&year={year}"
CHITTORGARH_SME_FALLBACK_URL = "https://www.chittorgarh.com/ipo/ipo_perf_tracker.asp?exchange=sme"
IPOMARKET_YEAR_URL = "https://www.ipomarket.in/performance/{year}"
IPOGURU_MAINBOARD_URL = "https://www.ipoguru.in/ipo-performance"
IPOGURU_SME_URL = "https://www.ipoguru.in/sme-ipo-performance"
IPO_DATA_SOURCE_PRIORITY = [
    "ipomarket",
    "ipoguru",
    "economic_times",
    "hdfcsec",
    "mint",
    "nse_verification",
    "chittorgarh",
]
IPO_SOURCE_URLS = {
    "ipomarket": {
        "all_by_year": IPOMARKET_YEAR_URL,
    },
    "ipoguru": {
        "mainboard": IPOGURU_MAINBOARD_URL,
        "sme": IPOGURU_SME_URL,
    },
    "economic_times": {
        "all": "https://economictimes.indiatimes.com/markets/ipo/recently-listed",
        "mainboard": "https://economictimes.indiatimes.com/markets/ipo/recently-listed/mainboard",
        "sme": "https://economictimes.indiatimes.com/markets/ipo/recently-listed/sme",
    },
    "mint": {
        "performance": "https://www.livemint.com/market/ipo/performance-tracker",
    },
    "hdfcsec": {
        "past_ipo": "https://www.hdfcsec.com/offering/past-ipo",
    },
    "nse": {
        "ipo_tracker": "https://www.nseindia.com/ipo-tracker",
        "ipo_tracker_sme": "https://www.nseindia.com/ipo-tracker?type=nse_sme_segment",
        "securities_master": "https://www.nseindia.com/static/market-data/securities-available-for-trading",
    },
    "chittorgarh_optional": {
        "mainboard_by_year": CHITTORGARH_MAINBOARD_YEAR_URL,
        "sme_by_year": CHITTORGARH_SME_YEAR_URL,
    },
}
DEFAULT_CHITTORGARH_LISTED_URL = CHITTORGARH_MAINBOARD_FALLBACK_URL
DEFAULT_IPOWATCH_GMP_URL = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"
DEFAULT_NSE_UPCOMING_URL = "https://www.nseindia.com/api/ipo-current-issue"
IPO_NO_VERIFIED_DATA_MESSAGE = "No verified IPO companies available. Please load NSE/BSE IPO master data."
IPO_DEMO_MODE_VALUES = {"demo", "sample", "mock", "development"}
IPO_VERIFIED_EXCHANGES = {"NSE", "BSE", "NSE SME", "BSE SME", "SME"}
IPO_DEMO_SYMBOLS = {"DIGIX", "GGPOWER", "GGPWER", "BDS"}
IPO_DEMO_COMPANY_NAMES = {
    "digital india exchange services",
    "greengrid power infra",
    "bharat defence systems",
}
IPO_DEMO_SOURCE_MARKERS = ("demo", "mock", "sample", "fallback", "seed")
IPO_REAL_SOURCE_MARKERS = ("ipomarket", "ipoguru", "chittorgarh", "nse", "bse", "screener")
IPO_SCREENER_SYMBOL_ALIASES = {
    # Public IPO trackers sometimes show "Symbol pending" even after listing.
    # Keep only hand-verified aliases here; unknown rows fall back to Screener search.
    "RUBICON RESEARCH": "RUBICON",
    "XTRANET TECHNOLOGIES": "XTRANET",
}
IPO_FINANCIAL_REQUIRED_FIELDS = (
    "latest_revenue_growth_yoy",
    "revenue_growth_yoy",
    "latest_pat_growth_yoy",
    "pat_growth_yoy",
    "profit_growth_yoy",
)
IPO_FINANCIAL_SUPPORT_FIELDS = (
    "cfo_pat",
    "roce",
    "roe",
    "operating_margin",
    "opm_trend_pct",
    "pe_ratio",
    "peer_median_pe",
    "industry_pe",
)
IPO_SHAREHOLDING_FIELDS = (
    "promoter_holding",
    "promoter_holding_change",
    "pledge_pct",
    "pledge_change",
    "fii_dii_holding",
    "fii_dii_change",
)

try:  # Optional. The regex parser below keeps the app working without bs4.
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - depends on deployment image
    BeautifulSoup = None  # type: ignore[assignment]

IPO_MARKET_TYPE_OPTIONS = CONFIG_IPO_MARKET_TYPE_OPTIONS
IPO_THEME_FILTER_OPTIONS = CONFIG_IPO_THEME_OPTIONS
IPO_RANKING_VIEW_OPTIONS = CONFIG_IPO_RANKING_VIEWS
IPO_WATCHLIST_FIELDS = IPO_EXPORT_FIELD_SETS["watchlist"]
IPO_BUY_ZONE_FIELDS = IPO_EXPORT_FIELD_SETS["buy_zone"]
IPO_RISK_ALERT_FIELDS = IPO_EXPORT_FIELD_SETS["risk_alerts"]
IPO_QUARTERLY_FIELDS = IPO_EXPORT_FIELD_SETS["quarterly"]

IPO_MASTER_FIELDS = [
    "company_name",
    "symbol",
    "isin",
    "exchange",
    "ipo_year",
    "listing_date",
    "ipo_price",
    "ipo_market_cap",
    "listing_price",
    "current_price",
    "current_market_cap",
    "gain_from_ipo_pct",
    "drawdown_from_52w_high_pct",
    "sector",
    "theme",
    "market_type",
    "lt_score",
    "is_listed_verified",
    "eligible_for_scoring",
    "flag",
    "action",
    "exclusion_reason",
    "missing_fields",
    "final_recommendation",
    "data_source",
    "last_updated_at",
]

IPO_EXPORT_FIELDS = [
    "company_name",
    "symbol",
    "isin",
    "exchange",
    "ipo_year",
    "listing_date",
    "ipo_price",
    "ipo_market_cap",
    "listing_price",
    "current_price",
    "current_market_cap",
    "gain_from_ipo_pct",
    "drawdown_from_52w_high_pct",
    "sector",
    "theme",
    "market_type",
    "lt_score",
    "sector_quality_score",
    "is_listed_verified",
    "eligible_for_scoring",
    "flag",
    "action",
    "exclusion_reason",
    "missing_fields",
    "rating",
    "risk_flags",
    "data_source",
    "last_updated_at",
]

IPO_SIMPLE_EXPORT_FIELDS = [
    "rank",
    "company_name",
    "symbol",
    "ipo_type",
    "listing_date",
    "ipo_price",
    "listing_price",
    "current_price",
    "listing_gain_pct",
    "current_gain_pct",
    "gain_from_ipo_rs",
    "issue_size",
    "ipo_market_cap",
    "status_badge",
    "screener_url",
    "source_url",
]

IPO_TOP10_FIELDS = [
    "rank",
    "company_name",
    "symbol",
    "sector",
    "theme",
    "market_type",
    "gain_from_ipo_pct",
    "drawdown_from_52w_high_pct",
    "lt_score",
    "sector_quality_score",
    "total_score",
    "quality_score",
    "growth_score",
    "valuation_score",
    "cash_flow_quality_score",
    "flag",
    "action",
    "rating",
    "final_recommendation",
    "ai_commentary",
]

IPO_SNAPSHOT_FIELDS = [
    "created_at",
    "ipo_year",
    "financial_year",
    "quarter",
    "rank",
    "symbol",
    "company_name",
    "total_score",
    "quality_score",
    "growth_score",
    "profitability_score",
    "valuation_score",
    "balance_sheet_score",
    "management_score",
    "sector_score",
    "market_performance_score",
    "risk_score",
    "ai_commentary",
]

IPO_LEGACY_MASTER_FIELDS = [
    "company_name",
    "symbol",
    "ipo_year",
    "listing_date",
    "issue_price",
    "listing_price",
    "current_price",
    "return_from_issue_pct",
    "return_from_listing_pct",
    "sector",
    "market_cap",
    "data_source",
    "last_updated_at",
]


def ipo_year_options(today: date | None = None) -> list[int]:
    current_year = (today or date.today()).year
    years = {2024, 2025, 2026, current_year}
    if current_year > 2026:
        years.update(range(2026, current_year + 2))
    return sorted(years, reverse=True)


def ensure_ipo_tables(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_ipo_cache_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipo_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                ipo_year INTEGER NOT NULL,
                listing_date TEXT,
                issue_price REAL,
                listing_price REAL,
                sector TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(symbol, ipo_year)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipo_quarterly_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                financial_year TEXT,
                quarter TEXT,
                revenue_growth_yoy REAL,
                profit_growth_yoy REAL,
                eps_growth_yoy REAL,
                roe REAL,
                roce REAL,
                debt_to_equity REAL,
                current_ratio REAL,
                operating_margin REAL,
                net_profit_margin REAL,
                pe_ratio REAL,
                industry_pe REAL,
                promoter_holding REAL,
                fii_dii_holding REAL,
                pledge_pct REAL,
                result_date TEXT,
                source TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipo_rank_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ipo_year INTEGER NOT NULL,
                financial_year TEXT,
                quarter TEXT,
                rank INTEGER,
                symbol TEXT,
                company_name TEXT,
                total_score REAL,
                quality_score REAL,
                growth_score REAL,
                profitability_score REAL,
                valuation_score REAL,
                balance_sheet_score REAL,
                management_score REAL,
                sector_score REAL,
                market_performance_score REAL,
                risk_score REAL,
                ai_commentary TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        def ensure_columns(table_name: str, columns: dict[str, str]) -> None:
            existing = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    conn.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    )

        ensure_columns(
            "ipo_master",
            {
                "ipo_price": "REAL",
                "ipo_market_cap": "REAL",
                "current_price": "REAL",
                "current_market_cap": "REAL",
                "gain_from_ipo_pct": "REAL",
                "drawdown_from_52w_high_pct": "REAL",
                "theme": "TEXT",
                "market_type": "TEXT",
                "data_source": "TEXT",
                "last_updated_at": "TEXT",
            },
        )
        ensure_columns(
            "ipo_quarterly_metrics",
            {
                "ebitda_growth_yoy": "REAL",
                "pat_growth_yoy": "REAL",
                "opm_trend": "TEXT",
                "opm_trend_pct": "REAL",
                "debtor_days": "REAL",
                "debtor_days_change_pct": "REAL",
                "inventory_days": "REAL",
                "inventory_days_change_pct": "REAL",
                "cash_conversion_cycle": "REAL",
                "cfo_pat": "REAL",
                "cfo_pat_change": "REAL",
                "fcf": "REAL",
                "promoter_holding_change": "REAL",
                "pledge_change": "REAL",
                "fii_dii_change": "REAL",
            },
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipo_price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price_date TEXT NOT NULL,
                close_price REAL,
                high_52w REAL,
                low_52w REAL,
                market_cap REAL,
                source TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(symbol, price_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipo_valuation_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                valuation_date TEXT NOT NULL,
                pe_ratio REAL,
                peer_median_pe REAL,
                ev_ebitda REAL,
                price_to_sales REAL,
                market_cap REAL,
                source TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(symbol, valuation_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipo_shareholding_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                financial_year TEXT,
                quarter TEXT,
                promoter_holding REAL,
                promoter_holding_change REAL,
                pledge_pct REAL,
                pledge_change REAL,
                fii_dii_holding REAL,
                fii_dii_change REAL,
                source TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(symbol, financial_year, quarter)
            )
            """
        )
        existing_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(ipo_rank_snapshots)").fetchall()
        }
        for column_name in ("profitability_score", "market_performance_score"):
            if column_name not in existing_columns:
                conn.execute(
                    f"ALTER TABLE ipo_rank_snapshots ADD COLUMN {column_name} REAL"
                )
        conn.commit()


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _pct(current: float | None, base: float | None) -> float | None:
    if current is None or base in {None, 0}:
        return None
    return round((float(current) - float(base)) / float(base) * 100, 2)


def _clean_text(value: Any) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _clean_text(value).lower()).strip("_")


def _number(value: Any) -> float | None:
    text = _clean_text(value)
    if not text or text.upper() in {"N/A", "NA", "-", "--"}:
        return None
    match = re.search(r"-?\d+(?:,\d{2,3})*(?:\.\d+)?|-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _ipo_price_reference(value: Any) -> float | None:
    """Return the highest price from an IPO price band for GMP percentage math."""
    text = _clean_text(value)
    if not text or text.upper() in {"N/A", "NA", "-", "--"}:
        return None
    normalized = re.sub(r"(?<=\d)\s*-\s*(?=\d)", " ", text)
    matches = re.findall(r"\d+(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?", normalized)
    prices: list[float] = []
    for match in matches:
        try:
            prices.append(float(match.replace(",", "")))
        except ValueError:
            continue
    return max(prices) if prices else None


def _gmp_percent(gmp: Any, ipo_price_or_band: Any) -> float | None:
    """Calculate GMP as a percent of IPO price; existing percent text is preserved."""
    gmp_text = _clean_text(gmp)
    if not gmp_text or gmp_text.upper() in {"N/A", "NA", "-", "--"}:
        return None
    gmp_value = _number(gmp_text)
    if gmp_value is None:
        return None
    if "%" in gmp_text:
        return round(gmp_value, 2)
    price = _ipo_price_reference(ipo_price_or_band)
    if price in {None, 0}:
        return None
    return round(float(gmp_value) / float(price) * 100, 2)


def ipo_data_mode() -> str:
    return str(os.getenv("IPO_DATA_MODE", "production") or "production").strip().lower()


def ipo_demo_mode_enabled() -> bool:
    return ipo_data_mode() in IPO_DEMO_MODE_VALUES


def _ipo_screener_url(symbol: Any, exchange: Any = "NSE") -> str:
    clean_symbol = re.sub(r"[^A-Z0-9-]", "", str(symbol or "").upper())
    return (
        f"https://www.screener.in/company/{clean_symbol}/"
        if clean_symbol
        else "https://www.screener.in/"
    )


def _has_any_number(row: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return any(_number(row.get(field)) is not None for field in fields)


def _is_demo_ipo_record(row: dict[str, Any]) -> bool:
    symbol = str(row.get("symbol") or "").strip().upper()
    company = str(row.get("company_name") or "").strip().lower()
    source = str(row.get("data_source") or row.get("source") or "").strip().lower()
    if bool(row.get("is_demo") or row.get("is_mock") or row.get("is_sample")):
        return True
    if symbol in IPO_DEMO_SYMBOLS or company in IPO_DEMO_COMPANY_NAMES:
        return True
    return any(marker in source for marker in IPO_DEMO_SOURCE_MARKERS)


def _is_real_ipo_source(row: dict[str, Any], is_demo: bool | None = None) -> bool:
    if is_demo is None:
        is_demo = _is_demo_ipo_record(row)
    source = str(row.get("data_source") or row.get("source") or "").strip().lower()
    return (not is_demo) and any(marker in source for marker in IPO_REAL_SOURCE_MARKERS)


def _exchange_value(row: dict[str, Any]) -> str:
    exchange = (
        row.get("exchange")
        or row.get("listing_exchange")
        or row.get("primary_exchange")
        or row.get("market")
        or ""
    )
    return str(exchange or "").strip().upper()


def _missing_ipo_fields(
    row: dict[str, Any],
    is_demo: bool,
    is_real_source: bool | None = None,
) -> list[str]:
    missing: list[str] = []
    exchange = _exchange_value(row)
    if is_real_source is None:
        is_real_source = _is_real_ipo_source(row, is_demo)
    if is_demo:
        missing.append("non_demo_verified_source")
    if not is_real_source:
        missing.append("real_ipo_source")
    if not str(row.get("symbol") or "").strip():
        missing.append("symbol")
    if not str(row.get("isin") or row.get("ISIN") or "").strip():
        missing.append("isin")
    if not str(row.get("listing_date") or "").strip():
        missing.append("listing_date")
    if exchange not in IPO_VERIFIED_EXCHANGES:
        missing.append("exchange")
    if _number(row.get("ipo_price") or row.get("issue_price")) is None:
        missing.append("ipo_price")
    if _number(row.get("current_price")) is None:
        missing.append("current_price")
    if _number(row.get("current_market_cap") or row.get("market_cap")) is None:
        missing.append("market_cap")
    if not str(row.get("screener_url") or row.get("screener_link") or "").strip() and not str(row.get("symbol") or "").strip():
        missing.append("screener_link")
    has_growth = any(_number(row.get(field)) is not None for field in IPO_FINANCIAL_REQUIRED_FIELDS)
    has_financial_support = _has_any_number(row, IPO_FINANCIAL_SUPPORT_FIELDS)
    if not (has_growth and has_financial_support):
        missing.append("latest_financial_data")
    if not _has_any_number(row, IPO_SHAREHOLDING_FIELDS):
        missing.append("shareholding_data")
    return missing


def _verify_ipo_record(record: dict[str, Any]) -> dict[str, Any]:
    row = normalize_ipo_record(record)
    is_demo = _is_demo_ipo_record(row)
    is_real_source = _is_real_ipo_source(row, is_demo)
    exchange = _exchange_value(row)
    row["exchange"] = exchange
    row["isin"] = row.get("isin") or row.get("ISIN") or ""
    row["screener_url"] = row.get("screener_url") or row.get("screener_link") or _ipo_screener_url(row.get("symbol"), exchange)
    missing = _missing_ipo_fields(row, is_demo, is_real_source)
    listed_required = {
        "symbol",
        "isin",
        "listing_date",
        "exchange",
        "non_demo_verified_source",
        "real_ipo_source",
    }
    is_listed_verified = not any(field in listed_required for field in missing)
    has_price_data = "current_price" not in missing and "ipo_price" not in missing
    has_financial_data = "latest_financial_data" not in missing
    has_shareholding_data = "shareholding_data" not in missing
    eligible = (
        is_listed_verified
        and has_price_data
        and "market_cap" not in missing
        and has_financial_data
        and has_shareholding_data
        and not is_demo
    )
    row["is_demo"] = is_demo
    row["is_real_ipo_source"] = is_real_source
    row["is_listed_verified"] = bool(is_listed_verified)
    row["has_price_data"] = bool(has_price_data)
    row["has_financial_data"] = bool(has_financial_data)
    row["has_shareholding_data"] = bool(has_shareholding_data)
    row["eligible_for_scoring"] = bool(eligible)
    row["missing_fields"] = ", ".join(missing)
    row["exclusion_reason"] = "Missing/invalid: " + ", ".join(missing) if missing else ""
    if not eligible:
        row["lt_score"] = None
        row["total_score"] = None
        row["sector_quality_score"] = None
        row["quality_score"] = None
        row["growth_score"] = None
        row["risk_score"] = None
        row["buy_zone"] = None
        row["is_buy_zone"] = False
        row["flag"] = "RED" if not is_listed_verified or is_demo else "YELLOW"
        row["action"] = "UNVERIFIED - EXCLUDED" if not is_listed_verified or is_demo else "WATCH / DATA PENDING"
        row["rating"] = row["action"]
        row["risk_flags"] = missing
        row["final_recommendation"] = (
            "Excluded from IPO ranking until NSE/BSE listing, price, market-cap, financial, and shareholding data are verified."
            if row["action"] == "UNVERIFIED - EXCLUDED"
            else "Verified listing, but latest price/fundamental data is incomplete. Keep in data-pending watch, not buy zone."
        )
    return row


def _apply_ipo_verification(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_verify_ipo_record(record) for record in records]


def _ipo_validation_report(rows: list[dict[str, Any]]) -> dict[str, int]:
    def has_missing(row: dict[str, Any], field: str) -> bool:
        return field in {item.strip() for item in str(row.get("missing_fields") or "").split(",") if item.strip()}

    return {
        "total_rows_loaded": len(rows),
        "real_ipo_source_rows": sum(1 for row in rows if row.get("is_real_ipo_source")),
        "verified_listed_companies": sum(1 for row in rows if row.get("is_listed_verified")),
        "eligible_for_scoring": sum(1 for row in rows if row.get("eligible_for_scoring")),
        "excluded_unverified_rows": sum(1 for row in rows if not row.get("eligible_for_scoring")),
        "data_pending_rows": sum(
            1
            for row in rows
            if row.get("is_listed_verified") and not row.get("eligible_for_scoring")
        ),
        "rows_missing_price": sum(1 for row in rows if has_missing(row, "current_price")),
        "rows_missing_financials": sum(1 for row in rows if has_missing(row, "latest_financial_data")),
        "rows_missing_shareholding": sum(1 for row in rows if has_missing(row, "shareholding_data")),
        "mainboard_rows": sum(1 for row in rows if "main" in str(row.get("market_type") or "").lower()),
        "sme_rows": sum(1 for row in rows if "sme" in str(row.get("market_type") or "").lower()),
    }


def _parse_year(value: Any) -> int | None:
    match = re.search(r"\b(20\d{2})\b", _clean_text(value))
    return int(match.group(1)) if match else None


def _first_present(row: dict[str, str], aliases: list[str]) -> str:
    for key, value in row.items():
        normalized = _normalize_key(key)
        for alias in aliases:
            if alias in normalized and value:
                return value
    return ""


def _clean_chittorgarh_company_name(value: Any) -> str:
    text = _clean_text(value)
    text = re.sub(r"\s*\bIPO\s+Detail\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s*\bStock\s+Quotes\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s*\bSymbol\s+pending\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s*\bListed\s*:\s*\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2}\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s*\bListed\s*:.*$", "", text, flags=re.I)
    text = re.sub(r"\s*\bListed\s+On\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -|")


def _ipo_company_lookup_key(value: Any) -> str:
    text = _clean_chittorgarh_company_name(value).upper()
    text = re.sub(r"\b(LIMITED|LTD|LTD\.|PRIVATE|PVT|PVT\.|INDIA|THE)\b", " ", text)
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def _infer_ipo_screener_symbol(row: dict[str, Any]) -> str:
    raw_symbol_text = str(row.get("symbol") or "").strip()
    symbol_placeholder = raw_symbol_text.upper() in {
        "",
        "-",
        "--",
        "NA",
        "N/A",
        "NONE",
        "PENDING",
        "SYMBOL PENDING",
        "SYMBOLPENDING",
        "TO BE UPDATED",
    }
    symbol = re.sub(r"[^A-Z0-9-]", "", raw_symbol_text.upper())
    if symbol and not symbol_placeholder:
        return symbol
    company_key = _ipo_company_lookup_key(
        row.get("company_name") or row.get("company") or row.get("ipo_name") or ""
    )
    for alias_key, alias_symbol in IPO_SCREENER_SYMBOL_ALIASES.items():
        if alias_key in company_key or company_key in alias_key:
            return alias_symbol
    return ""


def _http_get_text(url: str, headers: dict[str, str] | None = None) -> str:
    request_headers = dict(IPO_HTTP_HEADERS)
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=IPO_HTTP_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _html_table_rows(markup: str) -> list[list[str]]:
    if BeautifulSoup is not None:  # pragma: no cover - parser presence varies
        soup = BeautifulSoup(markup, "html.parser")
        rows: list[list[str]] = []
        for tr in soup.find_all("tr"):
            cells = [
                _clean_text(cell.get_text(" "))
                for cell in tr.find_all(["th", "td"])
            ]
            if any(cells):
                rows.append(cells)
        return rows

    rows = []
    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", markup, flags=re.I | re.S):
        cells = [
            _clean_text(cell)
            for cell in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row_html, flags=re.I | re.S)
        ]
        if any(cells):
            rows.append(cells)
    return rows


def _records_from_html_tables(markup: str) -> list[dict[str, str]]:
    rows = _html_table_rows(markup)
    records: list[dict[str, str]] = []
    header: list[str] | None = None
    header_markers = (
        "company",
        "company_name",
        "symbol",
        "isin",
        "listing",
        "listed_on",
        "issue_price",
        "current_price",
        "profit_loss",
        "gain",
        "market_cap",
        "ipo_price",
    )
    for cells in rows:
        normalized = [_normalize_key(cell) for cell in cells]
        marker_hits = sum(
            1
            for item in normalized
            if any(marker in item for marker in header_markers)
        )
        looks_like_header = marker_hits >= 2 or (header is None and marker_hits >= 1)
        if header is None or looks_like_header:
            header = cells
            continue
        if not header or len(cells) < 2:
            continue
        if len(cells) > len(header):
            cells = cells[: len(header)]
        padded = cells + [""] * (len(header) - len(cells))
        records.append(dict(zip(header, padded)))
    return records


def _screener_url(symbol: str) -> str:
    clean = re.sub(r"[^A-Z0-9-]", "", str(symbol or "").upper())
    return f"https://www.screener.in/company/{clean}/" if clean else "https://www.screener.in/"


def fetch_screener_fundamentals(symbol: str) -> dict[str, Any]:
    """Best-effort Screener scrape for post-listing fundamentals.

    Screener can throttle or require login for some pages. Missing fields are
    therefore non-fatal; the scoring engine already handles partial data.
    """
    if not symbol:
        return {}
    text = _http_get_text(_screener_url(symbol))
    metrics: dict[str, Any] = {"fundamental_source": "screener"}
    pairs = {
        "market_cap": [r"Market Cap\s*₹?\s*([0-9,.]+)\s*Cr"],
        "pe_ratio": [r"Stock P/E\s*([0-9,.]+)", r"P/E\s*([0-9,.]+)"],
        "roe": [r"ROE\s*([0-9,.]+)\s*%"],
        "roce": [r"ROCE\s*([0-9,.]+)\s*%"],
        "debt_to_equity": [r"Debt to equity\s*([0-9,.]+)", r"Debt/equity\s*([0-9,.]+)"],
        "operating_margin": [r"OPM\s*([0-9,.]+)\s*%"],
    }
    plain = _clean_text(text)
    for field, patterns in pairs.items():
        for pattern in patterns:
            match = re.search(pattern, plain, flags=re.I)
            if match:
                metrics[field] = _number(match.group(1))
                break
    return {key: value for key, value in metrics.items() if value not in {None, ""}}


def enrich_listed_ipos_with_screener(
    records: list[dict[str, Any]],
    max_records: int = 6,
) -> tuple[list[dict[str, Any]], list[str]]:
    enriched: list[dict[str, Any]] = []
    notes: list[str] = []
    fetch_count = 0
    for record in records:
        updated = dict(record)
        symbol = str(updated.get("symbol") or "").strip().upper()
        needs_fundamentals = any(
            updated.get(field) in {None, "", "N/A"}
            for field in ("pe_ratio", "roe", "roce", "market_cap")
        )
        if symbol and needs_fundamentals and fetch_count < max_records:
            fetch_count += 1
            try:
                metrics = fetch_screener_fundamentals(symbol)
            except Exception as exc:  # pragma: no cover - network dependent
                notes.append(f"Screener unavailable for {symbol}: {_clean_text(exc)}")
                metrics = {}
            if metrics:
                updated.update({k: v for k, v in metrics.items() if v not in {None, ""}})
                old_source = str(updated.get("data_source") or "")
                updated["data_source"] = (
                    f"{old_source}; Screener fundamentals"
                    if old_source
                    else "Screener fundamentals"
                )
        enriched.append(updated)
    return enriched, notes


def _listed_record(
    company_name: str,
    symbol: str,
    ipo_year: int,
    listing_date: str,
    issue_price: float,
    listing_price: float,
    current_price: float,
    sector: str,
    market_cap: float,
    **metrics: Any,
) -> dict[str, Any]:
    now = _now_text()
    high_52w = metrics.get("high_52w")
    low_52w = metrics.get("low_52w")
    if high_52w is None:
        high_52w = round(max(issue_price, listing_price, current_price) * 1.18, 2)
    if low_52w is None:
        low_52w = round(min(issue_price, listing_price, current_price) * 0.75, 2)
    base_metrics = {
        "ebitda_growth_yoy": metrics.get("ebitda_growth_yoy", metrics.get("profit_growth_yoy")),
        "pat_growth_yoy": metrics.get("pat_growth_yoy", metrics.get("profit_growth_yoy")),
        "latest_revenue_growth_yoy": metrics.get("latest_revenue_growth_yoy", metrics.get("revenue_growth_yoy")),
        "latest_pat_growth_yoy": metrics.get("latest_pat_growth_yoy", metrics.get("profit_growth_yoy")),
        "opm_trend": metrics.get("opm_trend", "stable"),
        "opm_trend_pct": metrics.get("opm_trend_pct", 0.0),
        "debtor_days": metrics.get("debtor_days", None),
        "debtor_days_change_pct": metrics.get("debtor_days_change_pct", 0.0),
        "inventory_days": metrics.get("inventory_days", None),
        "inventory_days_change_pct": metrics.get("inventory_days_change_pct", 0.0),
        "cash_conversion_cycle": metrics.get("cash_conversion_cycle", None),
        "cfo_pat": metrics.get("cfo_pat", 0.8),
        "cfo_pat_change": metrics.get("cfo_pat_change", 0.0),
        "fcf": metrics.get("fcf", 0.0),
        "promoter_holding_change": metrics.get("promoter_holding_change", 0.0),
        "pledge_change": metrics.get("pledge_change", 0.0),
        "fii_dii_change": metrics.get("fii_dii_change", 0.0),
        "peer_median_pe": metrics.get("peer_median_pe", metrics.get("industry_pe")),
        "high_52w": high_52w,
        "low_52w": low_52w,
        "drawdown_from_52w_high_pct": _pct(current_price, high_52w),
        "theme": metrics.get("theme") or infer_theme({"company_name": company_name, "sector": sector}),
        "market_type": metrics.get("market_type") or infer_market_type(metrics),
    }
    return {
        "company_name": company_name,
        "symbol": symbol,
        "ipo_year": ipo_year,
        "listing_date": listing_date,
        "ipo_price": issue_price,
        "issue_price": issue_price,
        "listing_price": listing_price,
        "current_price": current_price,
        "ipo_market_cap": round(market_cap * issue_price / current_price, 2) if current_price else None,
        "current_market_cap": market_cap,
        "gain_from_ipo_pct": _pct(current_price, issue_price),
        "return_from_issue_pct": _pct(current_price, issue_price),
        "return_from_listing_pct": _pct(current_price, listing_price),
        "sector": sector,
        "market_cap": market_cap,
        "data_source": "local fallback seed - verify with NSE/BSE/provider",
        "last_updated_at": now,
        **base_metrics,
        **metrics,
    }


def _seed_listed_ipos(year: int) -> list[dict[str, Any]]:
    samples: dict[int, list[dict[str, Any]]] = {
        2024: [
            _listed_record("Bajaj Housing Finance", "BAJAJHFL", 2024, "2024-09-16", 70, 150, 128, "Housing Finance", 91000, revenue_growth_yoy=24, profit_growth_yoy=22, eps_growth_yoy=18, roe=15.5, roce=13, debt_to_equity=3.8, current_ratio=1.1, operating_margin=55, net_profit_margin=18, pe_ratio=48, industry_pe=38, promoter_holding=88, fii_dii_holding=7, pledge_pct=0),
            _listed_record("Premier Energies", "PREMIERENE", 2024, "2024-09-03", 450, 991, 1130, "Solar manufacturing", 51000, revenue_growth_yoy=42, profit_growth_yoy=58, eps_growth_yoy=40, roe=22, roce=24, debt_to_equity=0.3, current_ratio=1.4, operating_margin=21, net_profit_margin=12, pe_ratio=58, industry_pe=64, promoter_holding=64, fii_dii_holding=12, pledge_pct=0),
            _listed_record("Waaree Energies", "WAAREEENER", 2024, "2024-10-28", 1503, 2500, 3129, "Energy transition", 89000, revenue_growth_yoy=31, profit_growth_yoy=36, eps_growth_yoy=30, roe=25, roce=28, debt_to_equity=0.2, current_ratio=1.8, operating_margin=17, net_profit_margin=10, pe_ratio=49, industry_pe=56, promoter_holding=64, fii_dii_holding=14, pledge_pct=0),
            _listed_record("Ola Electric", "OLAELEC", 2024, "2024-08-09", 76, 76, 52, "EV", 23000, revenue_growth_yoy=18, profit_growth_yoy=-15, eps_growth_yoy=-20, roe=-12, roce=-9, debt_to_equity=0.8, current_ratio=0.9, operating_margin=-8, net_profit_margin=-16, pe_ratio=None, industry_pe=45, promoter_holding=36, fii_dii_holding=6, pledge_pct=0),
            _listed_record("Swiggy", "SWIGGY", 2024, "2024-11-13", 390, 420, 360, "Consumer internet", 81000, revenue_growth_yoy=30, profit_growth_yoy=-8, eps_growth_yoy=-6, roe=-5, roce=-4, debt_to_equity=0.1, current_ratio=1.5, operating_margin=-2, net_profit_margin=-8, pe_ratio=None, industry_pe=70, promoter_holding=0, fii_dii_holding=20, pledge_pct=0),
        ],
        2025: [
            _listed_record("Hexaware Technologies", "HEXT", 2025, "2025-02-19", 708, 745, 825, "IT services", 50000, revenue_growth_yoy=16, profit_growth_yoy=18, eps_growth_yoy=14, roe=22, roce=26, debt_to_equity=0.1, current_ratio=1.6, operating_margin=16, net_profit_margin=12, pe_ratio=34, industry_pe=32, promoter_holding=74, fii_dii_holding=15, pledge_pct=0),
            _listed_record("Quality Power Electrical", "QPOWER", 2025, "2025-02-24", 425, 430, 610, "Electrical infrastructure", 4700, revenue_growth_yoy=26, profit_growth_yoy=24, eps_growth_yoy=21, roe=18, roce=20, debt_to_equity=0.2, current_ratio=1.3, operating_margin=19, net_profit_margin=11, pe_ratio=36, industry_pe=40, promoter_holding=68, fii_dii_holding=5, pledge_pct=0),
            _listed_record("Ajax Engineering", "AJAXENGG", 2025, "2025-02-17", 629, 576, 690, "Capital goods", 7900, revenue_growth_yoy=19, profit_growth_yoy=17, eps_growth_yoy=16, roe=17, roce=19, debt_to_equity=0.0, current_ratio=2.1, operating_margin=14, net_profit_margin=10, pe_ratio=31, industry_pe=35, promoter_holding=82, fii_dii_holding=4, pledge_pct=0),
        ],
        2026: [
            _listed_record("Digital India Exchange Services", "DIGIX", 2026, "2026-02-06", 180, 228, 420, "Financial infrastructure", 12500, revenue_growth_yoy=34, profit_growth_yoy=39, eps_growth_yoy=32, roe=24, roce=28, debt_to_equity=0.0, current_ratio=2.4, operating_margin=29, net_profit_margin=19, pe_ratio=42, industry_pe=48, promoter_holding=51, fii_dii_holding=18, pledge_pct=0),
            _listed_record("GreenGrid Power Infra", "GGPOWER", 2026, "2026-03-18", 320, 345, 515, "Power / energy transition", 18800, revenue_growth_yoy=28, profit_growth_yoy=24, eps_growth_yoy=22, roe=18, roce=21, debt_to_equity=0.4, current_ratio=1.2, operating_margin=23, net_profit_margin=13, pe_ratio=38, industry_pe=42, promoter_holding=59, fii_dii_holding=11, pledge_pct=0),
            _listed_record("Bharat Defence Systems", "BDS", 2026, "2026-04-08", 540, 615, 1010, "Defence manufacturing", 26500, revenue_growth_yoy=38, profit_growth_yoy=42, eps_growth_yoy=35, roe=26, roce=29, debt_to_equity=0.1, current_ratio=1.7, operating_margin=24, net_profit_margin=15, pe_ratio=46, industry_pe=52, promoter_holding=62, fii_dii_holding=16, pledge_pct=0),
        ],
    }
    return [
        {
            **dict(record),
            "is_demo": True,
            "data_source": "DEMO local seed - excluded from production scoring",
        }
        for record in samples.get(int(year), [])
    ]


def _seed_upcoming_ipos(today: date | None = None) -> list[dict[str, Any]]:
    base = today or date.today()
    now = _now_text()
    return [
        {
            "company_name": "NSDL",
            "symbol": "NSDL",
            "ipo_date": (base + timedelta(days=9)).isoformat(),
            "sector": "Capital markets infrastructure",
            "issue_size": "To be announced",
            "price_band": "To be announced",
            "gmp": "N/A",
            "source": "DEMO local upcoming watchlist - verify before decision",
            "is_demo": True,
            "last_updated_at": now,
        },
        {
            "company_name": "Tata Capital",
            "symbol": "TATACAP",
            "ipo_date": (base + timedelta(days=18)).isoformat(),
            "sector": "NBFC",
            "issue_size": "To be announced",
            "price_band": "To be announced",
            "gmp": "N/A",
            "source": "DEMO local upcoming watchlist - verify before decision",
            "is_demo": True,
            "last_updated_at": now,
        },
        {
            "company_name": "Hero FinCorp",
            "symbol": "HEROFIN",
            "ipo_date": (base + timedelta(days=27)).isoformat(),
            "sector": "NBFC",
            "issue_size": "To be announced",
            "price_band": "To be announced",
            "gmp": "N/A",
            "source": "DEMO local upcoming watchlist - verify before decision",
            "is_demo": True,
            "last_updated_at": now,
        },
    ]


def _merge_by_symbol(
    fallback_records: list[dict[str, Any]],
    live_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in fallback_records:
        key = str(record.get("symbol") or record.get("company_name") or "").upper()
        if key:
            merged[key] = dict(record)
    for record in live_records:
        key = str(record.get("symbol") or record.get("company_name") or "").upper()
        if not key:
            continue
        base = dict(merged.get(key) or {})
        base.update({k: v for k, v in record.items() if v not in {None, ""}})
        merged[key] = base
    return list(merged.values())


def _ipo_year_from_row(raw: dict[str, str], listing_date: str) -> int | None:
    return _parse_year(listing_date) or _parse_year(" ".join(str(value) for value in raw.values()))


def _chittorgarh_url_plan(year: int, ipo_type: str) -> list[tuple[str, str]]:
    normalized_type = str(ipo_type or "mainboard").strip().lower()
    if normalized_type == "sme":
        return [
            ("year", CHITTORGARH_SME_YEAR_URL.format(year=int(year))),
            ("fallback", CHITTORGARH_SME_FALLBACK_URL),
        ]

    override = os.getenv("IPO_CHITTORGARH_LISTED_URL")
    if override:
        return [("override", override)]
    return [
        ("year", CHITTORGARH_MAINBOARD_YEAR_URL.format(year=int(year))),
        ("fallback", CHITTORGARH_MAINBOARD_FALLBACK_URL),
    ]


def _chittorgarh_source_name(ipo_type: str) -> str:
    return (
        "Chittorgarh SME IPO performance tracker"
        if str(ipo_type or "").strip().lower() == "sme"
        else "Chittorgarh Mainboard IPO performance tracker"
    )


def _ipo_market_type_from_text(value: Any, default: str = "Mainboard") -> str:
    text = _clean_text(value).lower()
    if "sme" in text:
        return "SME"
    if "mainboard" in text or "main board" in text or text == "main":
        return "Mainboard"
    return default


def _normalize_ipo_performance_record(
    raw: dict[str, str],
    year: int,
    ipo_type: str,
    source_url: str,
    source_label: str,
    default_market_type: str | None = None,
    require_year: bool = True,
) -> dict[str, Any] | None:
    company = _clean_chittorgarh_company_name(
        _first_present(raw, ["company_name", "company", "ipo_name", "issuer", "name"])
    )
    if not company or _normalize_key(company) in {"company", "company_name", "name"}:
        return None

    listing_date = _first_present(
        raw,
        ["listed_on", "listing_date", "list_date", "date_of_listing", "listing"],
    )
    row_year = _ipo_year_from_row(raw, listing_date)
    if require_year:
        if row_year and row_year != int(year):
            return None
        if row_year is None and str(int(year)) not in " ".join(str(value) for value in raw.values()):
            return None

    normalized_type = "SME" if str(ipo_type or "").strip().lower() == "sme" else "Mainboard"
    market_type_text = _first_present(raw, ["market_type", "ipo_type", "segment", "category", "exchange"])
    market_type = _ipo_market_type_from_text(
        market_type_text,
        default_market_type or normalized_type,
    )
    if normalized_type == "SME" and market_type != "SME":
        if market_type_text:
            return None
        market_type = "SME"
    if normalized_type == "Mainboard" and market_type == "SME":
        return None

    raw_symbol = _first_present(raw, ["symbol", "nse_symbol", "bse_symbol", "scrip", "code"])
    symbol = _infer_ipo_screener_symbol({"symbol": raw_symbol, "company_name": company})
    ipo_price = _number(_first_present(raw, ["issue_price", "ipo_price", "offer_price", "issue_pr", "price_band"]))
    listing_price = _number(
        _first_present(raw, ["listing_day_close", "listing_price", "list_price", "listing_close"])
    )
    current_price = _number(
        _first_present(raw, ["current_price", "cmp", "ltp", "last_traded_price", "last_price"])
    )
    listing_gain = _number(
        _first_present(raw, ["listing_day_gain", "listing_gain", "listing_return", "return_from_listing"])
    )
    current_gain = _number(
        _first_present(
            raw,
            [
                "profit_loss",
                "current_gain",
                "current_return",
                "gain_from_ipo",
                "return_from_issue",
                "return_since_ipo",
            ],
        )
    )
    if current_gain is None:
        current_gain = _pct(current_price, ipo_price)

    gain_rs = None
    if current_price is not None and ipo_price is not None:
        gain_rs = round(float(current_price) - float(ipo_price), 2)

    sector = _first_present(raw, ["sector", "industry"]) or "N/A"
    issue_size = _first_present(raw, ["issue_size", "ipo_size", "issue_amount", "issue"])
    market_cap = _number(_first_present(raw, ["current_market_cap", "market_cap", "mcap"]))
    ipo_market_cap = _number(_first_present(raw, ["ipo_market_cap", "issue_market_cap"]))
    high_52w = _number(_first_present(raw, ["high_52w", "52w_high", "52_week_high", "year_high"]))
    drawdown = _number(_first_present(raw, ["drawdown_from_52w_high", "52w_drawdown", "drawdown"]))
    exchange = _first_present(raw, ["exchange", "listed_on", "listing_exchange"])
    if not exchange:
        exchange = "SME" if market_type == "SME" else "NSE"

    record: dict[str, Any] = {
        "company_name": company,
        "symbol": symbol,
        "isin": _first_present(raw, ["isin"]),
        "exchange": str(exchange or "").strip().upper(),
        "ipo_year": int(year),
        "listing_date": listing_date,
        "ipo_price": ipo_price,
        "issue_price": ipo_price,
        "listing_price": listing_price,
        "current_price": current_price,
        "current_market_cap": market_cap,
        "market_cap": market_cap,
        "ipo_market_cap": ipo_market_cap,
        "gain_from_ipo_pct": current_gain,
        "return_from_issue_pct": current_gain,
        "return_from_listing_pct": listing_gain,
        "drawdown_from_52w_high_pct": drawdown,
        "high_52w": high_52w,
        "sector": sector,
        "issue_size": issue_size or "N/A",
        "theme": infer_theme({"company_name": company, "sector": sector}),
        "market_type": market_type,
        "data_source": source_label,
        "source_url": source_url,
        "screener_url": _simple_ipo_screener_url(
            {"company_name": company, "symbol": symbol, "exchange": exchange}
        ),
        "last_updated_at": _now_text(),
    }
    if record["ipo_market_cap"] is None and market_cap is not None and ipo_price and current_price:
        record["ipo_market_cap"] = round(float(market_cap) * float(ipo_price) / float(current_price), 2)
    if record["drawdown_from_52w_high_pct"] is None and current_price is not None and high_52w:
        record["drawdown_from_52w_high_pct"] = _pct(current_price, high_52w)
    return record


def _normalize_chittorgarh_record(
    raw: dict[str, str],
    year: int,
    ipo_type: str,
    source_url: str,
) -> dict[str, Any] | None:
    company = _clean_chittorgarh_company_name(_first_present(raw, ["company", "ipo_name", "issuer", "name"]))
    if not company or "company" == _normalize_key(company):
        return None
    listing_date = _first_present(raw, ["listing_date", "list_date", "listing", "listed_on"])
    row_year = _ipo_year_from_row(raw, listing_date)
    if row_year and row_year != int(year):
        return None
    if row_year is None and str(int(year)) not in " ".join(str(value) for value in raw.values()):
        return None

    raw_symbol = _first_present(raw, ["symbol", "code", "scrip"])
    symbol = _infer_ipo_screener_symbol({"symbol": raw_symbol, "company_name": company})
    issue_price = _number(
        _first_present(raw, ["issue_price", "offer_price", "ipo_price", "price_band", "price"])
    )
    listing_price = _number(
        _first_present(
            raw,
            ["listing_price", "list_price", "list_price_rs", "listing_day_close", "listing_close"],
        )
    )
    current_price = _number(_first_present(raw, ["current_price", "cmp", "ltp", "current", "last_price"]))
    gain_from_ipo = _number(
        _first_present(
            raw,
            [
                "change_percent_from_ipo",
                "gain_from_ipo",
                "current_gain",
                "return_from_issue",
                "profit_loss",
            ],
        )
    )
    sector = _first_present(raw, ["sector", "industry"]) or "N/A"
    issue_size = _first_present(raw, ["issue_size", "issue_size_rs", "issue_size_cr", "issue", "size"])
    market_cap = _number(_first_present(raw, ["current_market_cap", "market_cap", "mcap"]))
    ipo_market_cap = _number(_first_present(raw, ["ipo_market_cap", "issue_market_cap"]))
    exchange = _first_present(raw, ["exchange", "listed_on", "listing_exchange"])
    if not exchange:
        exchange = "SME" if str(ipo_type or "").strip().lower() == "sme" else "NSE"
    market_type = "SME" if str(ipo_type or "").strip().lower() == "sme" else "Mainboard"
    high_52w = _number(_first_present(raw, ["high_52w", "52w_high", "52_week_high", "year_high"]))
    drawdown = _number(_first_present(raw, ["drawdown_from_52w_high", "52w_drawdown", "drawdown"]))

    record: dict[str, Any] = {
        "company_name": company,
        "symbol": symbol,
        "isin": _first_present(raw, ["isin"]),
        "exchange": str(exchange or "").strip().upper(),
        "ipo_year": int(year),
        "listing_date": listing_date,
        "ipo_price": issue_price,
        "issue_price": issue_price,
        "listing_price": listing_price,
        "current_price": current_price,
        "current_market_cap": market_cap,
        "market_cap": market_cap,
        "ipo_market_cap": ipo_market_cap,
        "gain_from_ipo_pct": gain_from_ipo,
        "return_from_issue_pct": gain_from_ipo,
        "return_from_listing_pct": _number(
            _first_present(raw, ["return_from_listing", "listing_gain", "listing_day_gain"])
        ),
        "drawdown_from_52w_high_pct": drawdown,
        "high_52w": high_52w,
        "sector": sector,
        "issue_size": issue_size or "N/A",
        "theme": infer_theme({"company_name": company, "sector": sector}),
        "market_type": market_type,
        "data_source": _chittorgarh_source_name(ipo_type),
        "source_url": source_url,
        "screener_url": _simple_ipo_screener_url(
            {"company_name": company, "symbol": symbol, "exchange": exchange}
        ),
        "last_updated_at": _now_text(),
    }
    if record["gain_from_ipo_pct"] is None:
        record["gain_from_ipo_pct"] = _pct(current_price, issue_price)
        record["return_from_issue_pct"] = record["gain_from_ipo_pct"]
    if record["ipo_market_cap"] is None and market_cap is not None and issue_price and current_price:
        record["ipo_market_cap"] = round(float(market_cap) * float(issue_price) / float(current_price), 2)
    if record["drawdown_from_52w_high_pct"] is None and current_price is not None and high_52w:
        record["drawdown_from_52w_high_pct"] = _pct(current_price, high_52w)
    return record


def fetch_chittorgarh_ipos(year: int, ipo_type: str = "mainboard") -> dict[str, Any]:
    """Fetch listed IPO rows from Chittorgarh, trying year URL then fallback.

    The adapter intentionally does not invent exchange symbols. If the public
    table lacks symbol/ISIN/financials, the row is shown as data-pending and is
    excluded from scoring until a verified source enriches it.
    """
    errors: list[str] = []
    tried_sources: list[str] = []
    for source_kind, url in _chittorgarh_url_plan(year, ipo_type):
        tried_sources.append(url)
        try:
            html_text = _http_get_text(url)
        except Exception as exc:
            errors.append(f"{url}: {_clean_text(exc)}")
            continue

        records = [
            record
            for raw in _records_from_html_tables(html_text)
            if (record := _normalize_chittorgarh_record(raw, year, ipo_type, url)) is not None
        ]
        if records:
            return {
                "records": records,
                "source": url,
                "source_kind": source_kind,
                "tried_sources": tried_sources,
                "error": "; ".join(errors),
            }
        if source_kind != "fallback":
            errors.append(f"{url}: no usable {int(year)} rows")

    return {
        "records": [],
        "source": tried_sources[-1] if tried_sources else "",
        "source_kind": "none",
        "tried_sources": tried_sources,
        "error": "; ".join(errors),
    }


def fetch_chittorgarh_listed_ipos(year: int) -> dict[str, Any]:
    """Fetch mainboard and SME IPO tracker rows from Chittorgarh."""
    all_records: list[dict[str, Any]] = []
    sources: list[str] = []
    errors: list[str] = []
    for ipo_type in ("mainboard", "sme"):
        result = fetch_chittorgarh_ipos(year, ipo_type)
        all_records.extend(list(result.get("records") or []))
        if result.get("source"):
            sources.append(str(result.get("source")))
        if result.get("error"):
            errors.append(str(result.get("error")))
    return {"records": all_records, "source": ", ".join(sources), "error": "; ".join(errors)}


def _filter_source_records_for_ipo_type(
    records: list[dict[str, Any]],
    ipo_type: str,
) -> list[dict[str, Any]]:
    target = "sme" if str(ipo_type or "").strip().lower() == "sme" else "mainboard"
    filtered: list[dict[str, Any]] = []
    for row in records:
        market_type = str(row.get("market_type") or row.get("ipo_type") or "").strip().lower()
        if target == "sme":
            if "sme" in market_type:
                filtered.append(row)
        else:
            if "sme" not in market_type:
                filtered.append(row)
    return filtered


def _usable_simple_performance_source_row(row: dict[str, Any]) -> bool:
    return (
        bool(_clean_text(row.get("company_name")))
        and _number(row.get("ipo_price") or row.get("issue_price")) is not None
        and (
            _number(row.get("current_price")) is not None
            or _number(row.get("current_gain_pct") or row.get("gain_from_ipo_pct") or row.get("return_from_issue_pct")) is not None
        )
    )


def fetch_ipomarket_ipos(year: int, ipo_type: str = "mainboard") -> dict[str, Any]:
    """Fetch year-wise IPO performance rows from IPO Market.

    IPO Market is preferred for the simple research tab because its public
    performance view is year-oriented and usually includes issue/current prices.
    """
    url = IPOMARKET_YEAR_URL.format(year=int(year))
    try:
        html_text = _http_get_text(url)
    except Exception as exc:
        return {"records": [], "source": url, "source_kind": "ipomarket", "error": f"{url}: {_clean_text(exc)}"}

    normalized: list[dict[str, Any]] = []
    for raw in _records_from_html_tables(html_text):
        record = _normalize_ipo_performance_record(
            raw,
            year,
            ipo_type,
            url,
            "IPO Market IPO performance tracker",
            require_year=True,
        )
        if record and _usable_simple_performance_source_row(record):
            normalized.append(record)
    records = _filter_source_records_for_ipo_type(normalized, ipo_type)
    return {
        "records": records,
        "source": url,
        "source_kind": "ipomarket",
        "tried_sources": [url],
        "error": "" if records else f"{url}: no usable {int(year)} {ipo_type} rows",
    }


def _fetch_generic_ipo_performance_url(
    source_key: str,
    url: str,
    year: int,
    ipo_type: str,
    default_market_type: str,
    require_year: bool,
) -> dict[str, Any]:
    try:
        html_text = _http_get_text(url)
    except Exception as exc:
        return {"records": [], "source": url, "source_kind": source_key, "error": f"{url}: {_clean_text(exc)}"}

    records: list[dict[str, Any]] = []
    for raw in _records_from_html_tables(html_text):
        record = _normalize_ipo_performance_record(
            raw,
            year,
            ipo_type,
            url,
            f"{source_key.replace('_', ' ').title()} IPO performance tracker",
            default_market_type=default_market_type,
            require_year=require_year,
        )
        if record and _usable_simple_performance_source_row(record):
            records.append(record)
    records = _filter_source_records_for_ipo_type(records, ipo_type)
    return {
        "records": records,
        "source": url,
        "source_kind": source_key,
        "tried_sources": [url],
        "error": "" if records else f"{url}: no usable {int(year)} {ipo_type} rows",
    }


def fetch_ipoguru_ipos(year: int, ipo_type: str = "mainboard") -> dict[str, Any]:
    source_type = "sme" if str(ipo_type or "").strip().lower() == "sme" else "mainboard"
    url = IPOGURU_SME_URL if source_type == "sme" else IPOGURU_MAINBOARD_URL
    default_market_type = "SME" if source_type == "sme" else "Mainboard"
    return _fetch_generic_ipo_performance_url(
        "ipoguru",
        url,
        year,
        ipo_type,
        default_market_type,
        require_year=True,
    )


def fetch_secondary_ipo_source(source_key: str, year: int, ipo_type: str = "mainboard") -> dict[str, Any]:
    """Best-effort parser for simple public performance sources.

    These sites may change markup frequently. They are intentionally treated as
    fallback sources and never produce demo rows.
    """
    source_type = "sme" if str(ipo_type or "").strip().lower() == "sme" else "mainboard"
    source_map = {
        "economic_times": IPO_SOURCE_URLS["economic_times"].get(source_type) or IPO_SOURCE_URLS["economic_times"]["all"],
        "hdfcsec": IPO_SOURCE_URLS["hdfcsec"]["past_ipo"],
        "mint": IPO_SOURCE_URLS["mint"]["performance"],
    }
    url = source_map.get(source_key)
    if not url:
        return {"records": [], "source": "", "source_kind": source_key, "error": f"{source_key}: no configured URL"}
    return _fetch_generic_ipo_performance_url(
        source_key,
        url,
        year,
        ipo_type,
        "SME" if source_type == "sme" else "Mainboard",
        require_year=True,
    )


def _fetch_simple_ipo_performance_by_priority(year: int, ipo_type: str) -> dict[str, Any]:
    errors: list[str] = []
    tried_sources: list[str] = []
    for source_key in IPO_DATA_SOURCE_PRIORITY:
        if source_key == "ipomarket":
            result = fetch_ipomarket_ipos(year, ipo_type)
        elif source_key == "ipoguru":
            result = fetch_ipoguru_ipos(year, ipo_type)
        elif source_key in {"economic_times", "hdfcsec", "mint"}:
            result = fetch_secondary_ipo_source(source_key, year, ipo_type)
        elif source_key == "chittorgarh":
            result = fetch_chittorgarh_ipos(year, ipo_type)
        else:
            errors.append(f"{source_key}: used only for listing verification, not year-wise performance parsing")
            continue

        tried_sources.extend(str(item) for item in (result.get("tried_sources") or [result.get("source")]) if item)
        if result.get("records"):
            return {
                **result,
                "tried_sources": tried_sources,
                "source_mode": "live",
                "source_priority": source_key,
                "error": "; ".join([*errors, str(result.get("error") or "")]).strip("; "),
            }
        if result.get("error"):
            errors.append(str(result.get("error")))

    return {
        "records": [],
        "source": tried_sources[-1] if tried_sources else "",
        "source_kind": "none",
        "tried_sources": tried_sources,
        "source_priority": "",
        "error": "; ".join(errors),
    }


def _simple_ipo_cache_dir() -> Path:
    return Path(__file__).resolve().parent / "data" / "ipo"


def _simple_ipo_cache_path(year: int, ipo_type: str) -> Path:
    clean_type = "sme" if str(ipo_type or "").strip().lower() == "sme" else "mainboard"
    return _simple_ipo_cache_dir() / f"ipo_performance_{clean_type}_{int(year)}.csv"


def _simple_ipo_screener_url(row: dict[str, Any]) -> str:
    symbol = _infer_ipo_screener_symbol(row)
    if symbol:
        return f"https://www.screener.in/company/{symbol}/"
    company = _clean_chittorgarh_company_name(row.get("company_name") or "")
    return f"https://www.screener.in/search/?q={quote_plus(company)}" if company else "https://www.screener.in/"


def _simple_ipo_status(current_gain_pct: float | None) -> tuple[str, str]:
    if current_gain_pct is None:
        return "Data Pending", "neutral"
    if current_gain_pct >= 100:
        return "Strong Gainer", "strong"
    if current_gain_pct >= 50:
        return "Good Gainer", "good"
    if current_gain_pct >= 20:
        return "Moderate Gainer", "watch"
    if current_gain_pct >= 0:
        return "Flat / Low Return", "flat"
    return "Below IPO Price", "bad"


def _simple_ipo_performance_row(row: dict[str, Any], ipo_type: str) -> dict[str, Any]:
    company = _clean_chittorgarh_company_name(row.get("company_name") or "")
    symbol = _infer_ipo_screener_symbol({**row, "company_name": company})
    ipo_price = _number(row.get("ipo_price") or row.get("issue_price"))
    listing_price = _number(row.get("listing_price"))
    current_price = _number(row.get("current_price"))
    current_gain = _number(row.get("current_gain_pct") or row.get("gain_from_ipo_pct") or row.get("return_from_issue_pct"))
    if current_gain is None:
        current_gain = _pct(current_price, ipo_price)
    listing_gain = _number(row.get("listing_gain_pct") or row.get("return_from_listing_pct"))
    if listing_gain is None:
        listing_gain = _pct(listing_price, ipo_price)
    gain_rs = None
    if current_price is not None and ipo_price is not None:
        gain_rs = round(float(current_price) - float(ipo_price), 2)
    status, status_class = _simple_ipo_status(current_gain)
    normalized_type = "SME" if str(ipo_type or "").strip().lower() == "sme" else "Mainboard"
    simplified = {
        "rank": "",
        "company_name": company,
        "symbol": symbol,
        "ipo_type": normalized_type,
        "listing_date": _clean_text(row.get("listing_date") or ""),
        "ipo_price": ipo_price,
        "listing_price": listing_price,
        "current_price": current_price,
        "listing_gain_pct": listing_gain,
        "current_gain_pct": current_gain,
        "gain_from_ipo_rs": gain_rs,
        "issue_size": _clean_text(row.get("issue_size") or "N/A"),
        "ipo_market_cap": _number(row.get("ipo_market_cap")),
        "status_badge": status,
        "status_class": status_class,
        "screener_url": _simple_ipo_screener_url({**row, "company_name": company, "symbol": symbol}),
        "source_url": _clean_text(row.get("source_url") or row.get("source") or ""),
    }
    return simplified


def _simple_ipo_sort_key(row: dict[str, Any]) -> tuple[int, float]:
    gain = _number(row.get("current_gain_pct"))
    return (1 if gain is not None else 0, float(gain or -10_000))


def _rank_simple_ipo_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=_simple_ipo_sort_key, reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return ranked


def _write_simple_ipo_csv_cache(year: int, ipo_type: str, rows: list[dict[str, Any]], fetched_at: str) -> None:
    path = _simple_ipo_cache_path(year, ipo_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [*IPO_SIMPLE_EXPORT_FIELDS, "status_class", "_cache_fetched_at"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "_cache_fetched_at": fetched_at})


def _read_simple_ipo_csv_cache(year: int, ipo_type: str) -> tuple[list[dict[str, Any]], str]:
    path = _simple_ipo_cache_path(year, ipo_type)
    if not path.exists():
        return [], ""
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    timestamp = ""
    for row in rows:
        timestamp = str(row.pop("_cache_fetched_at", "") or timestamp)
        for field in (
            "rank",
            "ipo_price",
            "listing_price",
            "current_price",
            "listing_gain_pct",
            "current_gain_pct",
            "gain_from_ipo_rs",
            "ipo_market_cap",
        ):
            if field == "rank":
                try:
                    row[field] = int(float(row.get(field) or 0))
                except (TypeError, ValueError):
                    row[field] = ""
            else:
                row[field] = _number(row.get(field))
        clean_company = _clean_chittorgarh_company_name(row.get("company_name") or "")
        row["company_name"] = clean_company
        symbol = _infer_ipo_screener_symbol(row)
        row["symbol"] = symbol
        row["screener_url"] = _simple_ipo_screener_url({**row, "symbol": symbol, "company_name": clean_company})
    if not timestamp:
        timestamp = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    return rows, timestamp


def _load_simple_chittorgarh_performance(
    year: int,
    ipo_type: str,
    force_refresh: bool = False,
) -> dict[str, Any]:
    if not force_refresh:
        cached_rows, cached_at = _read_simple_ipo_csv_cache(year, ipo_type)
        if cached_rows:
            return {
                "rows": _rank_simple_ipo_rows(cached_rows),
                "source": str(_simple_ipo_cache_path(year, ipo_type)),
                "source_mode": "cache",
                "last_refreshed": cached_at,
                "messages": [],
            }

    fetched_at = _now_text()
    result = _fetch_simple_ipo_performance_by_priority(year, ipo_type)
    raw_rows = list(result.get("records") or [])
    rows = _rank_simple_ipo_rows([
        _simple_ipo_performance_row(row, ipo_type)
        for row in raw_rows
        if not _is_demo_ipo_record(row)
    ])
    messages: list[str] = []
    if result.get("error"):
        messages.append(str(result.get("error")))
    if rows:
        _write_simple_ipo_csv_cache(year, ipo_type, rows, fetched_at)
        return {
            "rows": rows,
            "source": str(result.get("source") or ""),
            "source_mode": "live",
            "last_refreshed": fetched_at,
            "messages": [
                f"Loaded {len(rows)} {ipo_type} IPO row(s) from {result.get('source_priority') or result.get('source_kind') or 'live source'}.",
                *messages,
            ],
        }

    cached_rows, cached_at = _read_simple_ipo_csv_cache(year, ipo_type)
    if cached_rows:
        messages.append(
            f"Live {ipo_type} IPO source-priority fetch returned no usable rows; showing cached data from {cached_at}."
        )
        return {
            "rows": _rank_simple_ipo_rows(cached_rows),
            "source": str(_simple_ipo_cache_path(year, ipo_type)),
            "source_mode": "cache_fallback",
            "last_refreshed": cached_at,
            "messages": messages,
        }
    messages.append(
        f"No verified {ipo_type} IPO performance data available for {int(year)}. Use Refresh IPO Data after checking network access."
    )
    return {
        "rows": [],
        "source": str(result.get("source") or ""),
        "source_mode": "empty",
        "last_refreshed": "",
        "messages": messages,
    }


def _parse_ipo_date_text(value: Any, default_year: int | None = None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _clean_text(value)
    if not text:
        return None
    first_part = re.split(r"\s+(?:to|-)\s+", text, maxsplit=1, flags=re.I)[0].strip()
    candidates = [first_part, text]
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate[:10]).date()
        except ValueError:
            pass
        for fmt in ("%d %b %Y", "%d %B %Y", "%d-%m-%Y", "%d/%m/%Y", "%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(candidate.replace(",", ""), fmt).date()
            except ValueError:
                continue
    month_match = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})(?:\s+(20\d{2}))?", text)
    if month_match:
        day, month, year_text = month_match.groups()
        year = int(year_text or default_year or date.today().year)
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(f"{day} {month} {year}", fmt).date()
            except ValueError:
                continue
    month_first = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})(?:,?\s+(20\d{2}))?", text)
    if month_first:
        month, day, year_text = month_first.groups()
        year = int(year_text or default_year or date.today().year)
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(f"{month} {day} {year}", fmt).date()
            except ValueError:
                continue
    return None


def _upcoming_ipos_next_7_days(today: date | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    anchor = today or date.today()
    rows, notes = _load_research_ready_upcoming_ipos(anchor)
    next_week = anchor + timedelta(days=7)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        ipo_date = _parse_ipo_date_text(row.get("ipo_date"), anchor.year)
        if ipo_date is None or not (anchor <= ipo_date <= next_week):
            continue
        gmp_pct = row.get("gmp_pct")
        if gmp_pct in {None, ""}:
            gmp_pct = _gmp_percent(row.get("gmp"), row.get("price_band"))
        filtered.append(
            {
                **row,
                "ipo_date": ipo_date.isoformat(),
                "gmp_pct": gmp_pct,
                "screener_url": _simple_ipo_screener_url(row),
            }
        )
    filtered.sort(key=lambda item: str(item.get("ipo_date") or ""))
    return filtered, notes


def build_simple_ipo_performance_dashboard(
    year: int,
    force_refresh: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    """Build a fast IPO performance tracker with no demo/mock rows."""
    selected_year = int(year)
    mainboard = _load_simple_chittorgarh_performance(selected_year, "mainboard", force_refresh)
    sme = _load_simple_chittorgarh_performance(selected_year, "sme", force_refresh)
    main_rows = list(mainboard.get("rows") or [])
    sme_rows = list(sme.get("rows") or [])
    positive_main_rows = [
        row for row in main_rows if (_number(row.get("current_gain_pct")) or -10_000) >= 0
    ]
    positive_sme_rows = [
        row for row in sme_rows if (_number(row.get("current_gain_pct")) or -10_000) >= 0
    ]
    main_top20 = _rank_simple_ipo_rows([dict(row) for row in positive_main_rows[:20]])
    sme_top20 = _rank_simple_ipo_rows([dict(row) for row in positive_sme_rows[:20]])
    combined_top40 = _rank_simple_ipo_rows([dict(row) for row in [*main_top20, *sme_top20]])[:40]
    upcoming, upcoming_notes = _upcoming_ipos_next_7_days(today)

    def count_gain(rows: list[dict[str, Any]], threshold: float) -> int:
        return sum(1 for row in rows if (_number(row.get("current_gain_pct")) or -10_000) >= threshold)

    def best_name(rows: list[dict[str, Any]]) -> str:
        return str(rows[0].get("company_name") or "N/A") if rows else "N/A"

    timestamps = [
        value
        for value in (mainboard.get("last_refreshed"), sme.get("last_refreshed"))
        if value
    ]
    last_refreshed = max(timestamps) if timestamps else _now_text()
    messages = [
        *list(mainboard.get("messages") or []),
        *list(sme.get("messages") or []),
        *upcoming_notes,
    ]
    if not main_rows and not sme_rows:
        messages.append(IPO_NO_VERIFIED_DATA_MESSAGE)
    return {
        "mode": "simple_performance",
        "year": selected_year,
        "generated_at": _now_text(),
        "last_refreshed": last_refreshed,
        "mainboard_all_count": len(main_rows),
        "sme_all_count": len(sme_rows),
        "mainboard_top20": main_top20,
        "sme_top20": sme_top20,
        "combined_top40": combined_top40,
        "upcoming_next7": upcoming,
        "messages": messages,
        "sources": {
            "mainboard": mainboard.get("source"),
            "sme": sme.get("source"),
            "mainboard_mode": mainboard.get("source_mode"),
            "sme_mode": sme.get("source_mode"),
        },
        "summary": {
            "total_mainboard_loaded": len(main_rows),
            "total_sme_loaded": len(sme_rows),
            "mainboard_positive_return": len(positive_main_rows),
            "sme_positive_return": len(positive_sme_rows),
            "mainboard_gt50_gain": count_gain(main_rows, 50),
            "sme_gt50_gain": count_gain(sme_rows, 50),
            "best_mainboard": best_name(main_rows),
            "best_sme": best_name(sme_rows),
            "last_refreshed": last_refreshed,
            "upcoming_next7_count": len(upcoming),
        },
    }


IPO_VALUE_INVESTOR_SYSTEM_PROMPT = """
You are a senior Indian value investor and growth-in-India analyst.

Analyze recently listed Indian IPO companies for long-term investment potential.
Do not invent financials. If quarterly numbers, cash flow, valuation, promoter
data, or balance-sheet data are missing, explicitly mark "Data needed".

Use a value-investor lens:
- sector tailwind and Indian economy growth runway
- business quality and competitive position
- growth quality and execution consistency
- capital efficiency and cash conversion
- valuation comfort after listing
- governance, promoter, pledge, and dilution risk
- when to wait for quarterly result confirmation or valuation correction

Return a concise investment note with:
1. Top 5 long-term candidates
2. Watchlist / wait-for-correction names
3. Avoid / data-risk names
4. Data still required before buying
5. Final action summary
"""


IPO_VALUE_INVESTOR_PROMPT_FIELDS = [
    "rank",
    "company_name",
    "symbol",
    "ipo_type",
    "listing_date",
    "ipo_price",
    "listing_price",
    "current_price",
    "listing_gain_pct",
    "current_gain_pct",
    "gain_from_ipo_rs",
    "issue_size",
    "ipo_market_cap",
    "status_badge",
    "screener_url",
    "source_url",
]


def selected_ipo_rows_for_value_analysis(
    dashboard: dict[str, Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return the currently ranked IPO rows suitable for GPT value analysis."""
    ranked_rows = list(dashboard.get("combined_top40") or [])
    if not ranked_rows:
        ranked_rows = [
            *list(dashboard.get("mainboard_top20") or []),
            *list(dashboard.get("sme_top20") or []),
        ]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in ranked_rows:
        if _is_demo_ipo_record(row):
            continue
        key = str(row.get("symbol") or row.get("company_name") or "").strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append(dict(row))
        if len(selected) >= max(1, int(limit)):
            break
    return selected


def build_ipo_value_investor_prompt(rows: list[dict[str, Any]], year: int) -> str:
    """Build a compact CSV-backed prompt for IPO long-term research."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IPO_VALUE_INVESTOR_PROMPT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                field: row.get(field, "")
                for field in IPO_VALUE_INVESTOR_PROMPT_FIELDS
            }
        )
    csv_payload = output.getvalue().strip()
    return f"""
Analyze these {int(year)} Indian IPO performance candidates from my IPO Screener page.

Context:
- I am a long-term investor looking for Indian economy growth compounders.
- Listing gains alone are not enough; prefer result confirmation, cash-flow quality,
  valuation comfort, governance comfort, and sector tailwind.
- Screener links are included for manual follow-up research.
- If a row has missing symbol, financials, market cap, or quarterly data, downgrade
  confidence and clearly say what data is needed.

Please rank the best companies to study for long-term investment and explain the
buy/watch/avoid decision in practical language.

IPO rows:
{csv_payload}
""".strip()


def fetch_nse_upcoming_ipos(today: date | None = None) -> dict[str, Any]:
    """Best-effort NSE upcoming IPO fetch.

    NSE often requires cookies and may block server-side requests. The caller
    treats any failure as a source note and keeps the local/IPOWatch fallback.
    """
    url = os.getenv("IPO_NSE_UPCOMING_URL", DEFAULT_NSE_UPCOMING_URL)
    text = _http_get_text(
        url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo",
        },
    )
    data = json.loads(text)
    rows = data.get("data") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        rows = []
    now = _now_text()
    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        company = (
            row.get("companyName")
            or row.get("company")
            or row.get("issuerName")
            or row.get("issuer")
        )
        if not company:
            continue
        records.append(
            {
                "company_name": _clean_text(company),
                "symbol": _clean_text(row.get("symbol") or row.get("series") or company).upper()[:20],
                "ipo_date": _clean_text(
                    row.get("issueStartDate")
                    or row.get("openDate")
                    or row.get("biddingStartDate")
                    or row.get("date")
                ),
                "sector": _clean_text(row.get("sector") or row.get("industry") or "N/A"),
                "issue_size": _clean_text(row.get("issueSize") or row.get("issueSizeInCr") or "N/A"),
                "price_band": _clean_text(row.get("priceBand") or row.get("priceRange") or "N/A"),
                "gmp": "N/A",
                "gmp_pct": None,
                "source": "NSE upcoming IPO API",
                "last_updated_at": now,
            }
        )
    return {"records": records, "source": url, "error": ""}


def fetch_ipowatch_upcoming_ipos(today: date | None = None) -> dict[str, Any]:
    """Fetch upcoming/GMP watch rows from IPOWatch when reachable."""
    url = os.getenv("IPO_IPOWATCH_GMP_URL", DEFAULT_IPOWATCH_GMP_URL)
    html_text = _http_get_text(url)
    now = _now_text()
    records: list[dict[str, Any]] = []
    for raw in _records_from_html_tables(html_text):
        company = _first_present(raw, ["company", "ipo_name", "ipo", "name"])
        if not company or "company" in company.lower():
            continue
        symbol = _first_present(raw, ["symbol", "code"]) or re.sub(
            r"[^A-Z0-9]",
            "",
            company.upper().split()[0],
        )[:14]
        price_band = _first_present(raw, ["price_band", "price"]) or "N/A"
        gmp = _first_present(raw, ["gmp", "premium"]) or "N/A"
        records.append(
            {
                "company_name": company,
                "symbol": symbol,
                "ipo_date": _first_present(raw, ["ipo_date", "open", "date"]) or "N/A",
                "sector": _first_present(raw, ["sector", "industry"]) or "N/A",
                "issue_size": _first_present(raw, ["issue_size", "size"]) or "N/A",
                "price_band": price_band,
                "gmp": gmp,
                "gmp_pct": _gmp_percent(gmp, price_band),
                "source": "IPOWatch GMP/upcoming table",
                "last_updated_at": now,
            }
        )
    return {"records": records[:25], "source": url, "error": ""}


def _load_research_ready_listed_ipos(year: int) -> tuple[list[dict[str, Any]], list[str]]:
    demo_mode = ipo_demo_mode_enabled()
    fallback = _seed_listed_ipos(year) if demo_mode else []
    notes: list[str] = []
    live_records: list[dict[str, Any]] = []
    try:
        chittorgarh = fetch_chittorgarh_listed_ipos(year)
        live_records = list(chittorgarh.get("records") or [])
        if live_records:
            notes.append(f"Loaded {len(live_records)} listed IPO row(s) from Chittorgarh.")
        else:
            notes.append(
                "Chittorgarh listed IPO source returned no usable rows."
                + (" Demo seed rows are visible as data issues only." if demo_mode else "")
            )
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        notes.append(
            f"Chittorgarh listed IPO source unavailable: {_clean_text(exc)}."
            + (" Demo seed rows are visible as data issues only." if demo_mode else "")
        )
    combined = _merge_by_symbol(fallback, live_records)
    combined, screener_notes = enrich_listed_ipos_with_screener(combined)
    notes.extend(screener_notes[:5])
    verified = _apply_ipo_verification(combined)
    return verified, notes


def _load_research_ready_upcoming_ipos(today: date | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    demo_mode = ipo_demo_mode_enabled()
    fallback = _seed_upcoming_ipos(today) if demo_mode else []
    notes: list[str] = []
    live_records: list[dict[str, Any]] = []
    for label, fetcher in (
        ("NSE upcoming IPO API", fetch_nse_upcoming_ipos),
        ("IPOWatch GMP/upcoming table", fetch_ipowatch_upcoming_ipos),
    ):
        try:
            result = fetcher(today)
            rows = list(result.get("records") or [])
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            notes.append(f"{label} unavailable: {_clean_text(exc)}.")
            continue
        if rows:
            live_records.extend(rows)
    if not live_records:
        notes.append(
            "Upcoming IPO live sources returned no usable rows."
            + (" Demo upcoming watchlist is shown only because IPO_DATA_MODE=demo." if demo_mode else "")
        )
    return _merge_by_symbol(fallback, live_records), notes


def _ipo_research_decision(
    ranked: list[dict[str, Any]],
    upcoming: list[dict[str, Any]],
    source_notes: list[str],
    validation_report: dict[str, int] | None = None,
) -> dict[str, Any]:
    validation_report = validation_report or {}
    eligible_count = int(validation_report.get("eligible_for_scoring") or len(ranked))
    verified_count = int(validation_report.get("verified_listed_companies") or eligible_count)
    excluded_count = int(validation_report.get("excluded_unverified_rows") or 0)
    enriched_count = sum(
        1
        for row in ranked
        if "screener" in str(row.get("data_source") or "").lower()
        or "chittorgarh" in str(row.get("data_source") or "").lower()
    )
    best = ranked[0] if ranked else {}
    score = best.get("total_score")
    rating = best.get("rating") or "N/A"
    symbol = best.get("symbol") or ""
    if not best:
        outcome = IPO_NO_VERIFIED_DATA_MESSAGE
    elif (float(score or 0) >= 80) and enriched_count:
        outcome = f"Research {symbol} first for long-term allocation; score is strong and at least one live/enriched source was used."
    elif float(score or 0) >= 80:
        outcome = f"Research {symbol} first, but verify the latest NSE/BSE filings before acting."
    else:
        outcome = "No clean long-term buy candidate yet. Keep watchlist and wait for stronger quarterly proof."
    return {
        "best": best,
        "outcome": outcome,
        "rating": rating,
        "source_quality": (
            f"{eligible_count} eligible ranked row(s), {verified_count} verified listed row(s), "
            f"{excluded_count} excluded data issue row(s), {len(upcoming)} upcoming watch row(s)."
        ),
        "research_steps": [
            "Open Screener and verify sales/profit growth, ROE/ROCE, debt, pledge, and valuation.",
            "Use GMP only as sentiment; never as long-term score input.",
            "Prefer score >=80 with sector tailwind and 2-3 quarterly results after listing.",
        ],
        "source_notes": source_notes[:8],
    }


def _ipo_return_pct(row: dict[str, Any]) -> float | None:
    value = _number(row.get("gain_from_ipo_pct"))
    if value is None:
        value = _number(row.get("return_from_issue_pct"))
    return value


def _filter_listed_tracker_rows(
    rows: list[dict[str, Any]],
    market_type: str = "All",
    theme: str = "All",
    only_positive: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """Rows shown immediately after Load Screener.

    This is deliberately separate from the ranking engine. It may show
    real-source rows that are still data-pending, but mock/demo rows never
    appear here and only eligible rows can be scored or marked buy-zone.
    """
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if row.get("is_demo") or not row.get("is_real_ipo_source"):
            continue
        if market_type != "All" and str(row.get("market_type") or "").lower() != market_type.lower():
            continue
        if theme != "All" and str(row.get("theme") or "").lower() != theme.lower():
            continue
        return_pct = _ipo_return_pct(row)
        if only_positive and (return_pct is None or return_pct <= 0):
            continue
        filtered.append(dict(row))

    filtered.sort(
        key=lambda item: (
            1 if item.get("eligible_for_scoring") else 0,
            float(item.get("lt_score") or item.get("total_score") or -1),
            _ipo_return_pct(item) if _ipo_return_pct(item) is not None else -9999,
            str(item.get("listing_date") or ""),
        ),
        reverse=True,
    )
    if only_positive:
        return filtered, f"Showing {len(filtered)} real-source IPO row(s) with positive return from issue price."
    return filtered, f"Showing {len(filtered)} real-source IPO row(s) after {market_type} / {theme} filters."


def _upsert_ipo_master(db_path: Path, records: list[dict[str, Any]]) -> None:
    ensure_ipo_tables(db_path)
    now = _now_text()
    with sqlite3.connect(db_path) as conn:
        for record in records:
            row = normalize_ipo_record(record)
            symbol = str(row.get("symbol") or "").upper()
            ipo_year = int(row.get("ipo_year") or 0)
            conn.execute(
                """
                INSERT INTO ipo_master(
                    company_name, symbol, ipo_year, listing_date, issue_price,
                    listing_price, sector, created_at, updated_at, ipo_price,
                    ipo_market_cap, current_price, current_market_cap,
                    gain_from_ipo_pct, drawdown_from_52w_high_pct, theme,
                    market_type, data_source, last_updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, ipo_year) DO UPDATE SET
                    company_name = excluded.company_name,
                    listing_date = excluded.listing_date,
                    issue_price = excluded.issue_price,
                    listing_price = excluded.listing_price,
                    sector = excluded.sector,
                    ipo_price = excluded.ipo_price,
                    ipo_market_cap = excluded.ipo_market_cap,
                    current_price = excluded.current_price,
                    current_market_cap = excluded.current_market_cap,
                    gain_from_ipo_pct = excluded.gain_from_ipo_pct,
                    drawdown_from_52w_high_pct = excluded.drawdown_from_52w_high_pct,
                    theme = excluded.theme,
                    market_type = excluded.market_type,
                    data_source = excluded.data_source,
                    last_updated_at = excluded.last_updated_at,
                    updated_at = excluded.updated_at
                """,
                (
                    row.get("company_name"),
                    symbol,
                    ipo_year,
                    row.get("listing_date"),
                    row.get("issue_price"),
                    row.get("listing_price"),
                    row.get("sector"),
                    now,
                    now,
                    row.get("ipo_price"),
                    row.get("ipo_market_cap"),
                    row.get("current_price"),
                    row.get("current_market_cap"),
                    row.get("gain_from_ipo_pct"),
                    row.get("drawdown_from_52w_high_pct"),
                    row.get("theme"),
                    row.get("market_type"),
                    row.get("data_source"),
                    row.get("last_updated_at") or now,
                ),
            )
            if symbol:
                conn.execute(
                    """
                    INSERT INTO ipo_price_history(
                        symbol, price_date, close_price, high_52w, low_52w,
                        market_cap, source, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, price_date) DO UPDATE SET
                        close_price = excluded.close_price,
                        high_52w = excluded.high_52w,
                        low_52w = excluded.low_52w,
                        market_cap = excluded.market_cap,
                        source = excluded.source
                    """,
                    (
                        symbol,
                        date.today().isoformat(),
                        row.get("current_price"),
                        row.get("high_52w"),
                        row.get("low_52w"),
                        row.get("current_market_cap"),
                        row.get("data_source"),
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO ipo_valuation_data(
                        symbol, valuation_date, pe_ratio, peer_median_pe,
                        market_cap, source, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, valuation_date) DO UPDATE SET
                        pe_ratio = excluded.pe_ratio,
                        peer_median_pe = excluded.peer_median_pe,
                        market_cap = excluded.market_cap,
                        source = excluded.source
                    """,
                    (
                        symbol,
                        date.today().isoformat(),
                        row.get("pe_ratio"),
                        row.get("peer_median_pe"),
                        row.get("current_market_cap"),
                        row.get("data_source"),
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO ipo_shareholding_data(
                        symbol, financial_year, quarter, promoter_holding,
                        promoter_holding_change, pledge_pct, pledge_change,
                        fii_dii_holding, fii_dii_change, source, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, financial_year, quarter) DO UPDATE SET
                        promoter_holding = excluded.promoter_holding,
                        promoter_holding_change = excluded.promoter_holding_change,
                        pledge_pct = excluded.pledge_pct,
                        pledge_change = excluded.pledge_change,
                        fii_dii_holding = excluded.fii_dii_holding,
                        fii_dii_change = excluded.fii_dii_change,
                        source = excluded.source
                    """,
                    (
                        symbol,
                        f"FY{ipo_year}",
                        row.get("quarter") or "Latest Available",
                        row.get("promoter_holding"),
                        row.get("promoter_holding_change"),
                        row.get("pledge_pct"),
                        row.get("pledge_change"),
                        row.get("fii_dii_holding"),
                        row.get("fii_dii_change"),
                        row.get("data_source"),
                        now,
                    ),
                )
        conn.commit()


def _build_dashboard_payload(
    year: int,
    quarter: str,
    only_multibagger: bool,
    today: date | None = None,
    market_type: str = "All",
    theme: str = "All",
    ranking_view: str = "Best IPOs by long-term score",
) -> dict[str, Any]:
    listed_all, listed_notes = _load_research_ready_listed_ipos(year)
    validation_report = _ipo_validation_report(listed_all)
    eligible_listed = [dict(row) for row in listed_all if row.get("eligible_for_scoring")]
    data_issues = [dict(row) for row in listed_all if not row.get("eligible_for_scoring")]
    listed_tracker, tracker_message = _filter_listed_tracker_rows(
        listed_all,
        market_type=market_type,
        theme=theme,
        only_positive=only_multibagger,
    )
    upcoming, upcoming_notes = _load_research_ready_upcoming_ipos(today)
    source_notes = [*listed_notes, *upcoming_notes]
    screener = build_ipo_screener_payload(
        eligible_listed,
        upcoming,
        year,
        market_type=market_type,
        theme=theme,
        ranking_view=ranking_view,
    )
    if only_multibagger:
        legacy_filtered, filter_message = filter_multibaggers_or_all(screener["master"])
        screener["master"] = rank_ipo_candidates(legacy_filtered)
    else:
        filter_message = (
            f"Showing {screener['summary']['listed_filtered']} IPO(s) after "
            f"{market_type} / {theme} filters."
        )
    ranked_all = rank_ipo_candidates(eligible_listed)
    ranked_visible = list(screener.get("master") or [])
    if listed_tracker:
        filter_message = tracker_message
    elif not eligible_listed:
        filter_message = IPO_NO_VERIFIED_DATA_MESSAGE
    if data_issues:
        source_notes.append(
            f"Excluded {len(data_issues)} unverified or data-incomplete IPO row(s). See Data Issues."
        )
    research_decision = _ipo_research_decision(ranked_all, upcoming, source_notes, validation_report)
    return {
        "year": int(year),
        "quarter": quarter or "Latest Available",
        "only_multibagger": bool(only_multibagger),
        "market_type": market_type,
        "theme": theme,
        "ranking_view": ranking_view,
        "upcoming": upcoming,
        "listed_all_count": len(listed_all),
        "listed_verified_count": validation_report.get("verified_listed_companies", 0),
        "listed_eligible_count": len(eligible_listed),
        "validation_report": validation_report,
        "data_issues": data_issues,
        "listed": ranked_visible,
        "listed_tracker": listed_tracker,
        "listed_tracker_count": len(listed_tracker),
        "quality": ranked_visible,
        "top10": ranked_all[:10],
        "screener": screener,
        "quarterly_monitor": screener.get("quarterly_monitor") or [],
        "alerts": screener.get("alerts") or [],
        "rankings": screener.get("rankings") or {},
        "detail": screener.get("detail") or {},
        "summary": screener.get("summary") or {},
        "messages": [filter_message, *source_notes[:4]],
        "source_notes": source_notes,
        "research_decision": research_decision,
        "generated_at": _now_text(),
        "data_source": research_decision.get("source_quality") or "IPO source adapters - daily cached",
    }


def build_ipo_dashboard(
    year: int,
    quarter: str,
    db_path: Path,
    only_multibagger: bool = False,
    force_refresh: bool = False,
    today: date | None = None,
    market_type: str = "All",
    theme: str = "All",
    ranking_view: str = "Best IPOs by long-term score",
) -> dict[str, Any]:
    ensure_ipo_tables(db_path)
    safe_market = _normalize_key(market_type or "all")
    safe_theme = _normalize_key(theme or "all")
    safe_view = _normalize_key(ranking_view or "score")
    mode = _normalize_key(ipo_data_mode())
    key_suffix = f"{mode}:multibagger" if only_multibagger else f"{mode}:{safe_market}:{safe_theme}:{safe_view}"
    cache_key = make_ipo_cache_key(year, quarter, f"dashboard_v4:{key_suffix}")
    payload = load_or_generate(
        db_path,
        cache_key,
        lambda: _build_dashboard_payload(
            year,
            quarter,
            only_multibagger,
            today,
            market_type=market_type,
            theme=theme,
            ranking_view=ranking_view,
        ),
        source="ipo_data_service",
        force_refresh=force_refresh,
        today=today,
    )
    _upsert_ipo_master(db_path, list(payload.get("listed_tracker") or payload.get("listed") or []))
    payload["snapshots"] = load_ipo_snapshots(db_path, year)
    return payload


def save_ipo_top10_snapshot(
    db_path: Path,
    year: int,
    quarter: str,
    top10: list[dict[str, Any]],
) -> int:
    ensure_ipo_tables(db_path)
    now = _now_text()
    financial_year = f"FY{int(year)}"
    with sqlite3.connect(db_path) as conn:
        for item in top10[:10]:
            conn.execute(
                """
                INSERT INTO ipo_rank_snapshots(
                    ipo_year, financial_year, quarter, rank, symbol, company_name,
                    total_score, quality_score, growth_score, profitability_score,
                    valuation_score, balance_sheet_score, management_score, sector_score,
                    market_performance_score, risk_score,
                    ai_commentary, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(year),
                    financial_year,
                    quarter,
                    int(item.get("rank") or 0),
                    item.get("symbol"),
                    item.get("company_name"),
                    item.get("total_score"),
                    item.get("quality_score"),
                    item.get("growth_score"),
                    item.get("profitability_score"),
                    item.get("valuation_score"),
                    item.get("balance_sheet_score"),
                    item.get("management_score"),
                    item.get("sector_score"),
                    item.get("market_performance_score"),
                    item.get("risk_score"),
                    item.get("ai_commentary"),
                    now,
                ),
            )
        conn.commit()
    return len(top10[:10])


def load_ipo_snapshots(
    db_path: Path,
    year: int | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    ensure_ipo_tables(db_path)
    query = """
        SELECT ipo_year, financial_year, quarter, rank, symbol, company_name,
               total_score, quality_score, growth_score, profitability_score,
               valuation_score, balance_sheet_score, management_score, sector_score,
               market_performance_score, risk_score,
               ai_commentary, created_at
        FROM ipo_rank_snapshots
    """
    params: tuple[Any, ...] = ()
    if year is not None:
        query += " WHERE ipo_year = ?"
        params = (int(year),)
    query += " ORDER BY created_at DESC, rank ASC LIMIT ?"
    params = (*params, int(limit))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    return [row for row in rows if not _is_demo_ipo_record(row)]


def export_ipo_records_csv(records: list[dict[str, Any]], fields: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(record)
    return buffer.getvalue()


def ipo_export_filename(kind: str, year: int, quarter: str) -> str:
    safe_quarter = str(quarter or "latest").lower().replace(" ", "_")
    return f"ipo_{kind}_{int(year)}_{safe_quarter}.csv"
