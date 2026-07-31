from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class ScreenerImportProvider:
    """Reads only a user-authorized export; it never scrapes Screener HTML."""

    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)

    def rows(self) -> list[dict[str, Any]]:
        if not self.csv_path.exists():
            return []
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
