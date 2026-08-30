"""SQLite persistence for accepted and pending FII sector snapshots."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fii_sector_pdf_parser import ParsedFiiSectorSnapshot


class FiiSectorSnapshotRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS fii_sector_snapshot (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_date TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_filename TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    parser_version TEXT NOT NULL,
                    extraction_status TEXT NOT NULL,
                    recognized_sector_count INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_fii_sector_snapshot_active
                ON fii_sector_snapshot(active, uploaded_at);

                CREATE TABLE IF NOT EXISTS sector_income_score_snapshot (
                    score_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    selected_sector TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    fii_snapshot_id INTEGER,
                    score_json TEXT NOT NULL,
                    ranking_json TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_sector_income_score_snapshot_active
                ON sector_income_score_snapshot(active, generated_at);
                """
            )

    def save_pending_snapshot(self, snapshot: ParsedFiiSectorSnapshot) -> dict[str, Any]:
        payload = snapshot.to_dict()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO fii_sector_snapshot(
                    report_date, source_name, source_filename, uploaded_at,
                    parser_version, extraction_status, recognized_sector_count,
                    snapshot_json, checksum, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    snapshot.report_date,
                    snapshot.source_name,
                    snapshot.source_filename,
                    snapshot.uploaded_at,
                    snapshot.parser_version,
                    snapshot.extraction_status,
                    snapshot.recognized_sector_count,
                    json.dumps(payload, default=str),
                    snapshot.checksum,
                ),
            )
            snapshot_id = int(cursor.lastrowid)
        return self.get_snapshot(snapshot_id) or {}

    def activate_snapshot(self, snapshot_id: int) -> dict[str, Any]:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT snapshot_id FROM fii_sector_snapshot WHERE snapshot_id=? AND extraction_status='VALID'",
                (snapshot_id,),
            ).fetchone()
            if not row:
                raise ValueError("Only a valid parsed FII snapshot can be activated.")
            conn.execute("UPDATE fii_sector_snapshot SET active=0 WHERE active=1")
            conn.execute(
                "UPDATE fii_sector_snapshot SET active=1, uploaded_at=COALESCE(uploaded_at, ?) WHERE snapshot_id=?",
                (stamp, snapshot_id),
            )
        return self.get_snapshot(snapshot_id) or {}

    def get_snapshot(self, snapshot_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM fii_sector_snapshot WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_active_snapshot(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM fii_sector_snapshot
                WHERE active=1 AND extraction_status='VALID'
                ORDER BY uploaded_at DESC, snapshot_id DESC
                LIMIT 1
                """
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def latest_pending_snapshot(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM fii_sector_snapshot
                WHERE active=0
                ORDER BY uploaded_at DESC, snapshot_id DESC
                LIMIT 1
                """
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def save_sector_score_snapshot(
        self,
        *,
        selected_sector: str,
        score: dict[str, Any],
        ranking: dict[str, Any],
        source: str = "SECTOR_SCORE_DETAILS",
        fii_snapshot_id: int | None = None,
    ) -> dict[str, Any]:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute("UPDATE sector_income_score_snapshot SET active=0 WHERE active=1")
            cursor = conn.execute(
                """
                INSERT INTO sector_income_score_snapshot(
                    selected_sector, generated_at, source, fii_snapshot_id,
                    score_json, ranking_json, active
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    selected_sector,
                    stamp,
                    source,
                    fii_snapshot_id,
                    json.dumps(score, default=str),
                    json.dumps(ranking, default=str),
                ),
            )
            score_snapshot_id = int(cursor.lastrowid)
        return self.get_sector_score_snapshot(score_snapshot_id) or {}

    def get_latest_sector_score_snapshot(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM sector_income_score_snapshot
                WHERE active=1
                ORDER BY generated_at DESC, score_snapshot_id DESC
                LIMIT 1
                """
            ).fetchone()
        return self._score_row_to_dict(row) if row else None

    def get_sector_score_snapshot(self, score_snapshot_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sector_income_score_snapshot WHERE score_snapshot_id=?",
                (score_snapshot_id,),
            ).fetchone()
        return self._score_row_to_dict(row) if row else None

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        try:
            payload = json.loads(str(data.get("snapshot_json") or "{}"))
        except json.JSONDecodeError:
            payload = {}
        data["snapshot_id"] = int(data["snapshot_id"])
        data["active"] = bool(data.get("active"))
        data["snapshot"] = payload
        data["rows"] = list(payload.get("rows") or [])
        return data

    def _score_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        try:
            score = json.loads(str(data.get("score_json") or "{}"))
        except json.JSONDecodeError:
            score = {}
        try:
            ranking = json.loads(str(data.get("ranking_json") or "{}"))
        except json.JSONDecodeError:
            ranking = {}
        data["score_snapshot_id"] = int(data["score_snapshot_id"])
        data["active"] = bool(data.get("active"))
        data["score"] = score
        data["ranking"] = ranking
        return data
