from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models.evaluation_output import EvaluationOutput
from .database import connect
from .migrations import migrate


class EvaluationRepository:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = path
        migrate(path)

    def save(
        self,
        evaluation: EvaluationOutput,
        *,
        company_key: str,
        prompt_version: str = "1.0",
        model: str = "",
        payloads: dict[str, Any] | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with connect(self.path) as conn:
            conn.execute(
                """INSERT INTO evaluation_run VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    company_key,
                    evaluation.symbol,
                    evaluation.research_date.isoformat(),
                    evaluation.snapshot_hash,
                    evaluation.data_quality_score,
                    evaluation.investment_score,
                    evaluation.python_provisional_decision.value,
                    evaluation.gpt_proposed_decision.value if evaluation.gpt_proposed_decision else None,
                    evaluation.final_decision.value,
                    evaluation.decision_confidence,
                    prompt_version,
                    evaluation.schema_version,
                    model,
                    created_at,
                ),
            )
            conn.execute(
                "INSERT INTO evaluation_result(run_id, payload_json, created_at) VALUES (?, ?, ?)",
                (run_id, evaluation.model_dump_json(), created_at),
            )
            for table, payload in (payloads or {}).items():
                if table not in {
                    "security_identity", "market_snapshot", "financial_snapshot",
                    "business_snapshot", "governance_snapshot", "peer_snapshot", "source_evidence",
                }:
                    continue
                conn.execute(
                    f"INSERT INTO {table}(run_id, payload_json, created_at) VALUES (?, ?, ?)",
                    (run_id, json.dumps(payload, sort_keys=True, default=str), created_at),
                )
            conn.commit()
        return run_id

    def find_unchanged(self, company_key: str, snapshot_hash: str) -> dict[str, Any] | None:
        with connect(self.path) as conn:
            row = conn.execute(
                """SELECT r.*, e.payload_json FROM evaluation_run r
                   JOIN evaluation_result e ON e.run_id = r.run_id
                   WHERE r.company_key = ? AND r.snapshot_hash = ?
                   ORDER BY r.created_at DESC LIMIT 1""",
                (company_key, snapshot_hash),
            ).fetchone()
        return dict(row) if row else None

    def list_runs(self, company_key: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM evaluation_run"
        parameters: tuple[str, ...] = ()
        if company_key:
            query += " WHERE company_key = ?"
            parameters = (company_key,)
        query += " ORDER BY created_at DESC"
        with connect(self.path) as conn:
            return [dict(row) for row in conn.execute(query, parameters).fetchall()]

    def save_batch_job(self, batch_job_id: str, status: str, payload: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.path) as conn:
            conn.execute(
                """INSERT INTO batch_job(batch_job_id, status, payload_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(batch_job_id) DO UPDATE SET
                     status=excluded.status,
                     payload_json=excluded.payload_json,
                     updated_at=excluded.updated_at""",
                (batch_job_id, status, json.dumps(payload, sort_keys=True, default=str), now, now),
            )
            conn.commit()
