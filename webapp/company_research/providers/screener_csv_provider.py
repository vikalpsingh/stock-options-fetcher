from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class ScreenerCsvProvider:
    """Reads a user-authorized Screener export from disk; never scrapes HTML."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else Path(__file__).resolve().parents[2] / "data" / "company_research" / "screener_fundamentals.csv"

    def find_row(self, mapping: dict[str, Any]) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        nse_symbol = str(mapping.get("nse_symbol") or mapping.get("symbol") or "").strip().upper()
        bse_code = str(mapping.get("bse_security_code") or mapping.get("bse_code") or "").strip().upper()
        company = str(mapping.get("canonical_name") or mapping.get("company_name") or "").strip().upper()
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                row_nse = str(row.get("NSE Code") or row.get("NSE") or row.get("Symbol") or "").strip().upper()
                row_bse = str(row.get("BSE Code") or row.get("BSE") or "").strip().upper()
                row_company = str(row.get("Company Name") or row.get("Name") or "").strip().upper()
                if nse_symbol and row_nse == nse_symbol:
                    return dict(row)
                if bse_code and row_bse == bse_code:
                    return dict(row)
                if company and row_company == company:
                    return dict(row)
        return None

