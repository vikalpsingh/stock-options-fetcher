from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ParsedValueStock


def default_db_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "value_stock" / "value_stock.db"


class ValueStockRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS value_stock_company (
                    company_key TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    sector TEXT,
                    industry TEXT,
                    exchange TEXT,
                    screener_url TEXT,
                    business_description TEXT,
                    latest_source_document_id INTEGER,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS value_stock_document (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    checksum TEXT NOT NULL UNIQUE,
                    company_key TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_date TEXT,
                    uploaded_at TEXT NOT NULL,
                    extraction_status TEXT NOT NULL,
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    raw_text TEXT
                );

                CREATE TABLE IF NOT EXISTS value_stock_snapshot (
                    company_key TEXT PRIMARY KEY,
                    metrics_json TEXT NOT NULL,
                    annual_json TEXT NOT NULL,
                    half_yearly_json TEXT NOT NULL,
                    balance_sheet_json TEXT NOT NULL,
                    cash_flow_json TEXT NOT NULL,
                    ratios_json TEXT NOT NULL,
                    shareholding_json TEXT NOT NULL,
                    operating_metrics_json TEXT NOT NULL,
                    score_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def upsert_parsed(self, parsed: ParsedValueStock) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM value_stock_document WHERE checksum = ?",
                (parsed.checksum,),
            ).fetchone()
            if existing:
                document_id = int(existing["id"])
                status = "updated_existing_document"
                conn.execute(
                    """
                    UPDATE value_stock_document
                    SET company_key = ?, filename = ?, source = ?, source_date = ?,
                        uploaded_at = ?, extraction_status = ?, warnings_json = ?, raw_text = ?
                    WHERE id = ?
                    """,
                    (
                        parsed.company_key,
                        parsed.filename,
                        parsed.source,
                        parsed.source_date,
                        now,
                        "SUCCESS",
                        json.dumps(parsed.warnings),
                        parsed.raw_text,
                        document_id,
                    ),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO value_stock_document(
                        checksum, company_key, filename, source, source_date,
                        uploaded_at, extraction_status, warnings_json, raw_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        parsed.checksum,
                        parsed.company_key,
                        parsed.filename,
                        parsed.source,
                        parsed.source_date,
                        now,
                        "SUCCESS",
                        json.dumps(parsed.warnings),
                        parsed.raw_text,
                    ),
                )
                document_id = int(cursor.lastrowid)
                status = "created_document"

            conn.execute(
                """
                INSERT INTO value_stock_company(
                    company_key, company_name, sector, industry, exchange, screener_url,
                    business_description, latest_source_document_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_key) DO UPDATE SET
                    company_name = excluded.company_name,
                    sector = excluded.sector,
                    industry = excluded.industry,
                    exchange = excluded.exchange,
                    screener_url = excluded.screener_url,
                    business_description = excluded.business_description,
                    latest_source_document_id = excluded.latest_source_document_id,
                    updated_at = excluded.updated_at
                """,
                (
                    parsed.company_key,
                    parsed.company_name,
                    parsed.sector,
                    parsed.industry,
                    parsed.exchange,
                    parsed.screener_url,
                    parsed.business_description,
                    document_id,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO value_stock_snapshot(
                    company_key, metrics_json, annual_json, half_yearly_json,
                    balance_sheet_json, cash_flow_json, ratios_json, shareholding_json,
                    operating_metrics_json, score_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_key) DO UPDATE SET
                    metrics_json = excluded.metrics_json,
                    annual_json = excluded.annual_json,
                    half_yearly_json = excluded.half_yearly_json,
                    balance_sheet_json = excluded.balance_sheet_json,
                    cash_flow_json = excluded.cash_flow_json,
                    ratios_json = excluded.ratios_json,
                    shareholding_json = excluded.shareholding_json,
                    operating_metrics_json = excluded.operating_metrics_json,
                    score_json = excluded.score_json,
                    updated_at = excluded.updated_at
                """,
                (
                    parsed.company_key,
                    json.dumps(parsed.metrics),
                    json.dumps(parsed.annual),
                    json.dumps(parsed.half_yearly),
                    json.dumps(parsed.balance_sheet),
                    json.dumps(parsed.cash_flow),
                    json.dumps(parsed.ratios),
                    json.dumps(parsed.shareholding),
                    json.dumps(parsed.operating_metrics),
                    json.dumps(parsed.score),
                    now,
                ),
            )
        return {"status": status, "document_id": document_id, "company_key": parsed.company_key}

    def list_companies(self, search: str = "", sector: str = "", decision: str = "") -> list[dict[str, Any]]:
        query = """
            SELECT c.*, s.metrics_json, s.score_json, s.updated_at AS snapshot_updated_at,
                   d.filename, d.source_date, d.uploaded_at, d.warnings_json
            FROM value_stock_company c
            LEFT JOIN value_stock_snapshot s ON s.company_key = c.company_key
            LEFT JOIN value_stock_document d ON d.id = c.latest_source_document_id
        """
        rows: list[Any] = []
        clauses: list[str] = []
        if search:
            clauses.append("(LOWER(c.company_name) LIKE ? OR LOWER(c.industry) LIKE ?)")
            term = f"%{search.lower()}%"
            rows.extend([term, term])
        if sector:
            clauses.append("LOWER(c.sector) = ?")
            rows.append(sector.lower())
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self.connect() as conn:
            records = [self._hydrate_summary(row) for row in conn.execute(query, rows).fetchall()]
        if decision:
            records = [
                row for row in records
                if str(row.get("decision") or "").lower() == decision.lower()
            ]
        decision_rank = {"ACCUMULATE": 0, "WATCH": 1, "WAIT": 2, "AVOID": 3}
        records.sort(
            key=lambda row: (
                decision_rank.get(str(row.get("decision") or "").upper(), 9),
                -(float(row.get("score") or -1)),
                str(row.get("company_name") or "").lower(),
            )
        )
        return records

    def get_company(self, company_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT c.*, s.*, d.filename, d.source_date, d.uploaded_at, d.warnings_json, d.raw_text
                FROM value_stock_company c
                LEFT JOIN value_stock_snapshot s ON s.company_key = c.company_key
                LEFT JOIN value_stock_document d ON d.id = c.latest_source_document_id
                WHERE c.company_key = ?
                """,
                (company_key,),
            ).fetchone()
        if not row:
            return None
        return self._hydrate_detail(row)

    def delete_company(self, company_key: str) -> bool:
        key = str(company_key or "").strip()
        if not key:
            return False
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT company_key FROM value_stock_company WHERE company_key = ?",
                (key,),
            ).fetchone()
            if not existing:
                return False
            conn.execute("DELETE FROM value_stock_snapshot WHERE company_key = ?", (key,))
            conn.execute("DELETE FROM value_stock_document WHERE company_key = ?", (key,))
            conn.execute("DELETE FROM value_stock_company WHERE company_key = ?", (key,))
        return True

    def documents_missing_sector(self, limit: int = 25) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.company_key, d.filename, d.checksum, d.raw_text
                FROM value_stock_company c
                JOIN value_stock_document d ON d.id = c.latest_source_document_id
                WHERE (c.sector IS NULL OR c.sector = '' OR c.industry IS NULL OR c.industry = '')
                  AND d.raw_text IS NOT NULL
                  AND d.raw_text <> ''
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def sectors(self) -> list[str]:
        with self.connect() as conn:
            return [
                str(row["sector"])
                for row in conn.execute(
                    "SELECT DISTINCT sector FROM value_stock_company WHERE sector IS NOT NULL AND sector <> '' ORDER BY sector"
                ).fetchall()
            ]

    def _json(self, row: sqlite3.Row, key: str, default: Any) -> Any:
        try:
            return json.loads(row[key] or "")
        except Exception:
            return default

    def _metric_value(self, metrics: dict[str, Any], label: str) -> Any:
        item = metrics.get(label) or {}
        if isinstance(item, dict):
            return item.get("value")
        return None

    def _hydrate_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        metrics = self._json(row, "metrics_json", {})
        score = self._json(row, "score_json", {})
        return {
            "company_key": row["company_key"],
            "company_name": row["company_name"],
            "sector": row["sector"] or "",
            "industry": row["industry"] or "",
            "exchange": row["exchange"] or "",
            "screener_url": row["screener_url"] or "",
            "cmp": self._metric_value(metrics, "Current Price"),
            "market_cap": self._metric_value(metrics, "Market Cap"),
            "sales_last_year": self._metric_value(metrics, "Sales last year"),
            "pat_last_year": self._metric_value(metrics, "NP Ann"),
            "opm": self._metric_value(metrics, "OPM last year"),
            "roce": self._metric_value(metrics, "ROCE"),
            "roe": self._metric_value(metrics, "ROE") or self._metric_value(metrics, "Return on equity"),
            "debt_equity": self._metric_value(metrics, "Debt to equity"),
            "pe": self._metric_value(metrics, "Stock P/E"),
            "ev_ebitda": self._metric_value(metrics, "EVEBITDA"),
            "score": score.get("total"),
            "decision": score.get("decision") or "WATCH",
            "confidence": score.get("confidence") or "Low",
            "freshness": row["source_date"] or row["uploaded_at"] or "",
            "warnings": self._json(row, "warnings_json", []),
        }

    def _hydrate_detail(self, row: sqlite3.Row) -> dict[str, Any]:
        detail = dict(row)
        for key in (
            "metrics_json",
            "annual_json",
            "half_yearly_json",
            "balance_sheet_json",
            "cash_flow_json",
            "ratios_json",
            "shareholding_json",
            "operating_metrics_json",
            "score_json",
            "warnings_json",
        ):
            detail[key.removesuffix("_json")] = self._json(row, key, [] if key == "warnings_json" else {})
        return detail
