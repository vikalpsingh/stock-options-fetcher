from __future__ import annotations

from pathlib import Path

from .database import connect


TABLES = (
    "security_identity",
    "market_snapshot",
    "financial_snapshot",
    "business_snapshot",
    "governance_snapshot",
    "peer_snapshot",
    "evaluation_result",
    "source_evidence",
)


def migrate(path: str | Path | None = None) -> None:
    with connect(path) as conn:
        for table in TABLES:
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS evaluation_run (
                run_id TEXT PRIMARY KEY,
                company_key TEXT NOT NULL,
                symbol TEXT NOT NULL,
                research_date TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                data_quality_score REAL NOT NULL,
                investment_score REAL NOT NULL,
                python_decision TEXT NOT NULL,
                gpt_decision TEXT,
                final_decision TEXT NOT NULL,
                confidence REAL NOT NULL,
                prompt_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                model TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS batch_job (
                batch_job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_snapshot ON evaluation_run(company_key, snapshot_hash)")
        conn.commit()
