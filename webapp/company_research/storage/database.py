from __future__ import annotations

import sqlite3
from pathlib import Path


def default_database_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "company_research" / "company_research.db"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path else default_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

