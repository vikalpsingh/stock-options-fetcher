from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .financial_calculator import calculated_pe, number
from .financial_normalizer import normalize_flat_financial_row
from .source_link_builder import build_external_links, build_yahoo_symbol
from ..providers.screener_csv_provider import ScreenerCsvProvider
from ..storage.repositories import CompanyResearchRepository


def _text(value: Any) -> str:
    return str(value or "").strip()


def company_key_from_row(row: dict[str, Any]) -> str:
    symbol = _text(row.get("symbol") or row.get("nse_symbol")).upper()
    exchange = _text(row.get("exchange") or row.get("primary_exchange")).upper()
    company = _text(row.get("company_name") or row.get("canonical_name")).upper()
    return "|".join(part for part in [exchange, symbol, company] if part)[:180]


def identity_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_name": _text(row.get("company_name") or row.get("canonical_name")),
        "legal_name": _text(row.get("legal_name")),
        "exchange": _text(row.get("exchange")),
        "segment": _text(row.get("segment") or row.get("ipo_type")),
        "nse_symbol": _text(row.get("nse_symbol") or row.get("symbol")),
        "bse_security_code": _text(row.get("bse_security_code") or row.get("bse_code")),
        "isin": _text(row.get("isin")),
        "kite_key": _text(row.get("kite_key")),
        "instrument_token": int(number(row.get("instrument_token")) or 0) or None,
    }


def market_snapshot_from_row(row: dict[str, Any], source: str = "cached_ipo_row") -> dict[str, Any]:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ltp": number(row.get("kite_ltp") or row.get("ltp") or row.get("current_price")),
        "previous_close": number(row.get("previous_close") or row.get("kite_previous_close")),
        "open": number(row.get("open")),
        "high": number(row.get("day_high") or row.get("high")),
        "low": number(row.get("day_low") or row.get("low")),
        "volume": number(row.get("volume")),
        "average_price": number(row.get("average_price") or row.get("average_traded_price")),
        "best_bid": number(row.get("best_bid")),
        "best_ask": number(row.get("best_ask")),
        "one_week_return": number(row.get("one_week_return_pct") or row.get("weekly_gain_pct")),
        "one_month_return": number(row.get("one_month_return_pct")),
        "three_month_return": number(row.get("three_month_return_pct")),
        "six_month_return": number(row.get("six_month_return_pct")),
        "one_year_return": number(row.get("one_year_return_pct")),
        "high_52w": number(row.get("high_52w")),
        "low_52w": number(row.get("low_52w")),
        "drawdown_52w": number(row.get("drawdown_from_52w_high_pct")),
        "average_traded_value_20d": number(row.get("average_traded_value_20d")),
        "liquidity_status": _text(row.get("liquidity_status") or row.get("status_badge")),
        "source": source,
    }


def financial_snapshot_from_row(row: dict[str, Any], source: str = "cached_ipo_row", source_url: str = "") -> dict[str, Any]:
    pe_value = row.get("pe_ratio") or row.get("pe")
    pe = "NM" if str(pe_value).upper() == "NM" else number(pe_value)
    if pe is None:
        calculated, _warnings = calculated_pe(number(row.get("market_cap") or row.get("current_market_cap")), number(row.get("ttm_pat")), int(number(row.get("quarter_count")) or 0))
        pe = calculated
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "financial_period": _text(row.get("financial_period") or row.get("quarter") or row.get("ipo_year")),
        "statement_type": _text(row.get("statement_type") or "UNKNOWN"),
        "market_cap": number(row.get("market_cap") or row.get("current_market_cap")),
        "enterprise_value": number(row.get("enterprise_value")),
        "pe": pe,
        "pb": number(row.get("pb_ratio") or row.get("pb")),
        "ps": number(row.get("ps_ratio") or row.get("ps")),
        "ev_ebitda": number(row.get("ev_ebitda")),
        "sales_yoy": number(row.get("sales_yoy_pct") or row.get("latest_revenue_growth_yoy") or row.get("revenue_growth_yoy")),
        "pat_yoy": number(row.get("pat_yoy_pct") or row.get("latest_pat_growth_yoy") or row.get("pat_growth_yoy")),
        "opm": number(row.get("opm_pct") or row.get("opm_trend_pct")),
        "roce": number(row.get("roce")),
        "roe": number(row.get("roe")),
        "debt_equity": number(row.get("debt_to_equity")),
        "interest_coverage": number(row.get("interest_coverage")),
        "cfo_pat": number(row.get("cfo_pat")),
        "debtor_days": number(row.get("debtor_days")),
        "inventory_days": number(row.get("inventory_days")),
        "promoter_holding": number(row.get("promoter_holding")),
        "promoter_pledge": number(row.get("pledge_pct") or row.get("promoter_pledge")),
        "source": source,
        "source_url": source_url or _text(row.get("source_url") or row.get("screener_url")),
        "data_quality_score": number(row.get("lt_data_quality_score") or row.get("data_quality_score")),
        "raw_values": [],
    }


class CompanyDetailService:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.repository = CompanyResearchRepository(db_path)

    def ensure_company(self, row: dict[str, Any]) -> str:
        company_key = _text(row.get("company_key")) or company_key_from_row(row)
        identity = identity_from_row(row)
        mapping = {**row, **identity, "yahoo_symbol": row.get("yahoo_symbol"), "yahoo_symbol_status": row.get("yahoo_symbol_status")}
        self.repository.upsert_identity(company_key, identity, row)
        links = build_external_links(mapping)
        yahoo_symbol = build_yahoo_symbol(mapping)
        if yahoo_symbol:
            self.repository.save_source_mapping(
                company_key,
                {
                    "source_name": "YAHOO",
                    "source_identifier": yahoo_symbol,
                    "source_url": links["yahoo"]["url"],
                    "mapping_status": _text(row.get("yahoo_symbol_status") or "CANDIDATE"),
                },
            )
        for source_name, source in links.items():
            if source["url"]:
                self.repository.save_source_mapping(
                    company_key,
                    {
                        "source_name": source_name.upper(),
                        "source_identifier": source["url"],
                        "source_url": source["url"],
                        "mapping_status": source["status"],
                    },
                )
        return company_key

    def save_snapshot_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        company_key = self.ensure_company(row)
        market_saved = self.repository.save_market_snapshot(company_key, market_snapshot_from_row(row))
        financial_saved = self.repository.save_financial_snapshot(company_key, financial_snapshot_from_row(row))
        evidence = self.local_gpt_evidence(company_key)
        research_saved = self.repository.save_research_snapshot(company_key, evidence)
        self.repository.log_fetch(company_key, "LOCAL", "save_snapshot", "FRESH", records_saved=int(market_saved) + int(financial_saved) + int(research_saved))
        return {"company_key": company_key, "market_saved": market_saved, "financial_saved": financial_saved, "research_saved": research_saved}

    def refresh_market_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        company_key = self.ensure_company(row)
        saved = self.repository.save_market_snapshot(company_key, market_snapshot_from_row(row, "cached_kite_or_source"))
        self.repository.log_fetch(company_key, "KITE", "market", "CACHED", records_saved=int(saved))
        return {"company_key": company_key, "saved": saved, "status": "CACHED"}

    def refresh_financials_from_providers(self, row: dict[str, Any]) -> dict[str, Any]:
        company_key = self.ensure_company(row)
        mapping = {**row, **identity_from_row(row)}
        provider = ScreenerCsvProvider()
        csv_row = provider.find_row(mapping)
        if csv_row:
            normalized = normalize_flat_financial_row(csv_row, source_name="screener_csv", source_url=_text(row.get("screener_url")))
            payload = financial_snapshot_from_row({**row, **normalized["metrics"]}, "screener_csv", _text(row.get("screener_url")))
            payload["financial_period"] = normalized["period"]
            payload["raw_values"] = normalized["raw_values"]
            saved = self.repository.save_financial_snapshot(company_key, payload)
            self.repository.log_fetch(company_key, "SCREENER_CSV", "financials", "FRESH", records_saved=int(saved))
            return {"company_key": company_key, "saved": saved, "status": "FRESH", "provider": "screener_csv"}
        saved = self.repository.save_financial_snapshot(company_key, financial_snapshot_from_row(row, "cached_ipo_row"))
        self.repository.log_fetch(company_key, "CACHED_ROW", "financials", "CACHED", error_code="SCREENER_CSV_NOT_FOUND", records_saved=int(saved))
        return {"company_key": company_key, "saved": saved, "status": "CACHED", "provider": "cached_ipo_row"}

    def detail(self, company_key: str) -> dict[str, Any]:
        return self.repository.get_company_detail(company_key)

    def local_gpt_evidence(self, company_key: str) -> dict[str, Any]:
        detail = self.detail(company_key)
        financial = detail.get("financial") or {}
        market = detail.get("market") or {}
        identity = detail.get("identity") or {}
        missing = []
        for field in ("ltp", "one_month_return", "drawdown_52w"):
            if market.get(field) in {None, ""}:
                missing.append(f"market.{field}")
        for field in ("market_cap", "pe", "sales_yoy", "pat_yoy", "opm", "roce"):
            if financial.get(field) in {None, ""}:
                missing.append(f"financial.{field}")
        return {
            "identity": identity,
            "market_snapshot": market,
            "financial_snapshot": financial,
            "quarterly_financials": [],
            "annual_financials": [],
            "cash_flow": {},
            "shareholding": {
                "promoter_holding": financial.get("promoter_holding"),
                "promoter_pledge": financial.get("promoter_pledge"),
            },
            "valuation": {
                "market_cap": financial.get("market_cap"),
                "pe": financial.get("pe"),
                "pb": financial.get("pb"),
                "ev_ebitda": financial.get("ev_ebitda"),
            },
            "data_quality": {"score": financial.get("data_quality_score")},
            "missing_fields": missing,
            "sources": detail.get("sources") or [],
            "python_decision": {
                "decision": (detail.get("row") or {}).get("lt_final_decision"),
                "maximum_allowed_decision": (detail.get("row") or {}).get("lt_python_decision"),
            },
        }

