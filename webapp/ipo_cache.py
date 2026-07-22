"""Daily SQLite cache helpers for the IPO dashboard.

The IPO page can later be wired to live data vendors, but this cache boundary
keeps expensive fetches to one refresh per day unless the user explicitly asks.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable


def ensure_ipo_cache_schema(db_path: Path) -> None:
    """Create the cache table used by the IPO tab if it does not exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ipo_daily_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT NOT NULL UNIQUE,
                generated_date TEXT NOT NULL,
                cached_json TEXT NOT NULL,
                source TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def make_ipo_cache_key(ipo_year: int, quarter: str, data_type: str) -> str:
    normalized_quarter = str(quarter or "Latest Available").strip().upper().replace(" ", "_")
    normalized_type = str(data_type or "dashboard").strip().lower()
    return f"ipo:{int(ipo_year)}:{normalized_quarter}:{normalized_type}"


def get_cached_json(
    db_path: Path,
    cache_key: str,
    today: date | None = None,
) -> dict[str, Any] | None:
    """Return today's cached payload for a key, or None when absent/stale."""
    ensure_ipo_cache_schema(db_path)
    today_text = (today or date.today()).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT cached_json, generated_date, source, created_at
            FROM ipo_daily_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
    if not row or row["generated_date"] != today_text:
        return None
    payload = json.loads(row["cached_json"])
    payload["_cache"] = {
        "cache_key": cache_key,
        "generated_date": row["generated_date"],
        "source": row["source"] or "",
        "created_at": row["created_at"],
        "hit": True,
    }
    return payload


def set_cached_json(
    db_path: Path,
    cache_key: str,
    payload: dict[str, Any],
    source: str = "",
    today: date | None = None,
) -> dict[str, Any]:
    """Persist payload for the current day and return it with cache metadata."""
    ensure_ipo_cache_schema(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    today_text = (today or date.today()).isoformat()
    clean_payload = dict(payload)
    clean_payload.pop("_cache", None)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ipo_daily_cache(cache_key, generated_date, cached_json, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                generated_date = excluded.generated_date,
                cached_json = excluded.cached_json,
                source = excluded.source,
                created_at = excluded.created_at
            """,
            (cache_key, today_text, json.dumps(clean_payload), source, now),
        )
        conn.commit()
    clean_payload["_cache"] = {
        "cache_key": cache_key,
        "generated_date": today_text,
        "source": source,
        "created_at": now,
        "hit": False,
    }
    return clean_payload


def load_or_generate(
    db_path: Path,
    cache_key: str,
    generator: Callable[[], dict[str, Any]],
    source: str = "",
    force_refresh: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    """Use today's cache unless force_refresh is requested."""
    if not force_refresh:
        cached = get_cached_json(db_path, cache_key, today)
        if cached is not None:
            return cached
    payload = generator()
    return set_cached_json(db_path, cache_key, payload, source=source, today=today)
