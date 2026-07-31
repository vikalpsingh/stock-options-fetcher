from __future__ import annotations

from pathlib import Path

from .database import connect


def migrate(path: str | Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS company_identity (
                company_key TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                legal_name TEXT,
                exchange TEXT,
                segment TEXT,
                nse_symbol TEXT,
                bse_security_code TEXT,
                isin TEXT,
                kite_key TEXT,
                instrument_token INTEGER,
                row_payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS company_source_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_identifier TEXT,
                source_url TEXT,
                mapping_status TEXT NOT NULL,
                identity_match_score REAL,
                verified_at TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(company_key, source_name, source_identifier)
            );
            CREATE TABLE IF NOT EXISTS market_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                ltp REAL,
                previous_close REAL,
                open REAL,
                high REAL,
                low REAL,
                volume REAL,
                average_price REAL,
                best_bid REAL,
                best_ask REAL,
                one_week_return REAL,
                one_month_return REAL,
                three_month_return REAL,
                six_month_return REAL,
                one_year_return REAL,
                high_52w REAL,
                low_52w REAL,
                drawdown_52w REAL,
                average_traded_value_20d REAL,
                liquidity_status TEXT,
                source TEXT,
                snapshot_hash TEXT NOT NULL,
                UNIQUE(company_key, snapshot_hash)
            );
            CREATE TABLE IF NOT EXISTS financial_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                financial_period TEXT,
                statement_type TEXT,
                market_cap REAL,
                enterprise_value REAL,
                pe TEXT,
                pb REAL,
                ps REAL,
                ev_ebitda REAL,
                sales_yoy REAL,
                pat_yoy REAL,
                opm REAL,
                roce REAL,
                roe REAL,
                debt_equity REAL,
                interest_coverage REAL,
                cfo_pat REAL,
                debtor_days REAL,
                inventory_days REAL,
                promoter_holding REAL,
                promoter_pledge REAL,
                source TEXT,
                source_url TEXT,
                data_quality_score REAL,
                raw_values_json TEXT NOT NULL DEFAULT '[]',
                snapshot_hash TEXT NOT NULL,
                UNIQUE(company_key, snapshot_hash)
            );
            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                provider TEXT NOT NULL,
                fetch_type TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT,
                records_saved INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS research_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                UNIQUE(company_key, snapshot_hash)
            );
            """
        )

