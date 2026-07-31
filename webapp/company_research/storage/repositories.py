from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import connect
from .migrations import migrate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def snapshot_hash(payload: dict[str, Any]) -> str:
    material = {key: value for key, value in payload.items() if key not in {"captured_at", "fetched_at", "updated_at"}}
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class CompanyResearchRepository:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        migrate(self.path)

    def upsert_identity(self, company_key: str, identity: dict[str, Any], row_payload: dict[str, Any]) -> None:
        now = _now()
        with connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO company_identity(
                    company_key, canonical_name, legal_name, exchange, segment,
                    nse_symbol, bse_security_code, isin, kite_key, instrument_token,
                    row_payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_key) DO UPDATE SET
                    canonical_name=excluded.canonical_name,
                    legal_name=excluded.legal_name,
                    exchange=excluded.exchange,
                    segment=excluded.segment,
                    nse_symbol=excluded.nse_symbol,
                    bse_security_code=excluded.bse_security_code,
                    isin=excluded.isin,
                    kite_key=excluded.kite_key,
                    instrument_token=excluded.instrument_token,
                    row_payload_json=excluded.row_payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    company_key,
                    identity.get("canonical_name") or "",
                    identity.get("legal_name") or "",
                    identity.get("exchange") or "",
                    identity.get("segment") or "",
                    identity.get("nse_symbol") or "",
                    identity.get("bse_security_code") or "",
                    identity.get("isin") or "",
                    identity.get("kite_key") or "",
                    identity.get("instrument_token"),
                    json.dumps(row_payload, sort_keys=True, default=str),
                    now,
                    now,
                ),
            )

    def save_source_mapping(self, company_key: str, source: dict[str, Any]) -> None:
        now = _now()
        with connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO company_source_mapping(
                    company_key, source_name, source_identifier, source_url,
                    mapping_status, identity_match_score, verified_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_key, source_name, source_identifier) DO UPDATE SET
                    source_url=excluded.source_url,
                    mapping_status=excluded.mapping_status,
                    identity_match_score=excluded.identity_match_score,
                    verified_at=excluded.verified_at,
                    updated_at=excluded.updated_at
                """,
                (
                    company_key,
                    source.get("source_name") or "",
                    source.get("source_identifier") or "",
                    source.get("source_url") or "",
                    source.get("mapping_status") or "CANDIDATE",
                    source.get("identity_match_score"),
                    source.get("verified_at"),
                    now,
                ),
            )

    def save_market_snapshot(self, company_key: str, payload: dict[str, Any]) -> bool:
        captured_at = payload.get("captured_at") or _now()
        digest = snapshot_hash(payload)
        with connect(self.path) as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO market_snapshot(
                    company_key, captured_at, ltp, previous_close, open, high, low,
                    volume, average_price, best_bid, best_ask, one_week_return,
                    one_month_return, three_month_return, six_month_return, one_year_return,
                    high_52w, low_52w, drawdown_52w, average_traded_value_20d,
                    liquidity_status, source, snapshot_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_key,
                    captured_at,
                    payload.get("ltp"),
                    payload.get("previous_close"),
                    payload.get("open"),
                    payload.get("high"),
                    payload.get("low"),
                    payload.get("volume"),
                    payload.get("average_price"),
                    payload.get("best_bid"),
                    payload.get("best_ask"),
                    payload.get("one_week_return"),
                    payload.get("one_month_return"),
                    payload.get("three_month_return"),
                    payload.get("six_month_return"),
                    payload.get("one_year_return"),
                    payload.get("high_52w"),
                    payload.get("low_52w"),
                    payload.get("drawdown_52w"),
                    payload.get("average_traded_value_20d"),
                    payload.get("liquidity_status"),
                    payload.get("source") or "cached_row",
                    digest,
                ),
            )
            return cursor.rowcount > 0

    def save_financial_snapshot(self, company_key: str, payload: dict[str, Any]) -> bool:
        captured_at = payload.get("captured_at") or _now()
        digest = snapshot_hash(payload)
        with connect(self.path) as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO financial_snapshot(
                    company_key, captured_at, financial_period, statement_type,
                    market_cap, enterprise_value, pe, pb, ps, ev_ebitda, sales_yoy,
                    pat_yoy, opm, roce, roe, debt_equity, interest_coverage,
                    cfo_pat, debtor_days, inventory_days, promoter_holding,
                    promoter_pledge, source, source_url, data_quality_score,
                    raw_values_json, snapshot_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_key,
                    captured_at,
                    payload.get("financial_period"),
                    payload.get("statement_type") or "UNKNOWN",
                    payload.get("market_cap"),
                    payload.get("enterprise_value"),
                    None if payload.get("pe") is None else str(payload.get("pe")),
                    payload.get("pb"),
                    payload.get("ps"),
                    payload.get("ev_ebitda"),
                    payload.get("sales_yoy"),
                    payload.get("pat_yoy"),
                    payload.get("opm"),
                    payload.get("roce"),
                    payload.get("roe"),
                    payload.get("debt_equity"),
                    payload.get("interest_coverage"),
                    payload.get("cfo_pat"),
                    payload.get("debtor_days"),
                    payload.get("inventory_days"),
                    payload.get("promoter_holding"),
                    payload.get("promoter_pledge"),
                    payload.get("source") or "cached_row",
                    payload.get("source_url") or "",
                    payload.get("data_quality_score"),
                    json.dumps(payload.get("raw_values") or [], sort_keys=True, default=str),
                    digest,
                ),
            )
            return cursor.rowcount > 0

    def save_research_snapshot(self, company_key: str, payload: dict[str, Any]) -> bool:
        digest = snapshot_hash(payload)
        with connect(self.path) as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO research_snapshot(company_key, created_at, payload_json, snapshot_hash) VALUES (?, ?, ?, ?)",
                (company_key, _now(), json.dumps(payload, sort_keys=True, default=str), digest),
            )
            return cursor.rowcount > 0

    def log_fetch(self, company_key: str, provider: str, fetch_type: str, status: str, error_code: str = "", error_message: str = "", records_saved: int = 0) -> None:
        now = _now()
        with connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO fetch_log(company_key, provider, fetch_type, started_at, completed_at, status, error_code, error_message, records_saved)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (company_key, provider, fetch_type, now, now, status, error_code, error_message, int(records_saved)),
            )

    def get_company_detail(self, company_key: str) -> dict[str, Any]:
        with connect(self.path) as conn:
            identity = conn.execute("SELECT * FROM company_identity WHERE company_key = ?", (company_key,)).fetchone()
            market = conn.execute("SELECT * FROM market_snapshot WHERE company_key = ? ORDER BY captured_at DESC, id DESC LIMIT 1", (company_key,)).fetchone()
            financial = conn.execute("SELECT * FROM financial_snapshot WHERE company_key = ? ORDER BY captured_at DESC, id DESC LIMIT 1", (company_key,)).fetchone()
            sources = conn.execute("SELECT * FROM company_source_mapping WHERE company_key = ? ORDER BY source_name", (company_key,)).fetchall()
            history = conn.execute(
                """
                SELECT captured_at, ltp, NULL AS pe, NULL AS sales_yoy, NULL AS pat_yoy, NULL AS opm, NULL AS roce, liquidity_status AS decision, source
                FROM market_snapshot WHERE company_key = ?
                UNION ALL
                SELECT captured_at, NULL AS ltp, pe, sales_yoy, pat_yoy, opm, roce, NULL AS decision, source
                FROM financial_snapshot WHERE company_key = ?
                ORDER BY captured_at DESC LIMIT 50
                """,
                (company_key, company_key),
            ).fetchall()
            fetch_logs = conn.execute("SELECT * FROM fetch_log WHERE company_key = ? ORDER BY completed_at DESC LIMIT 20", (company_key,)).fetchall()
        row_payload = {}
        if identity and identity["row_payload_json"]:
            try:
                row_payload = json.loads(identity["row_payload_json"])
            except json.JSONDecodeError:
                row_payload = {}
        return {
            "identity": dict(identity) if identity else {},
            "row": row_payload,
            "market": dict(market) if market else {},
            "financial": dict(financial) if financial else {},
            "sources": [dict(row) for row in sources],
            "history": [dict(row) for row in history],
            "fetch_logs": [dict(row) for row in fetch_logs],
        }

