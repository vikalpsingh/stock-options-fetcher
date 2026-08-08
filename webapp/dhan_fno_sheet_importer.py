"""Excel importer for DHAN F&O opportunity shortlist sheets.

The importer intentionally reads only workbook values from the two supported
shortlist tabs. It uses the xlsx zip/xml format directly so the app does not
depend on Excel or optional dataframe libraries at runtime.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile


SUPPORTED_SHEETS = ("CE_WHEEL_SHORTLIST", "PE_WHEEL_SHORTLIST")
SOURCE_TO_STRATEGY = {
    "CE_WHEEL_SHORTLIST": "BEAR_CALL_SPREAD",
    "PE_WHEEL_SHORTLIST": "BULL_PUT_SPREAD",
}

EXPECTED_COLUMNS = [
    "Stock",
    "Spot Price",
    "Strike",
    "Premium",
    "Lot Size",
    "Total Premium",
    "% OTM",
    "Expiry",
    "Beta",
    "Hist Vol %",
    "Downside Vol %",
    "ATR %",
    "Days to Expiry",
    "Expected Move %",
    "ITM Risk %",
    "Premium Yield %",
    "Monthly Yield %",
    "Move Cover",
    "Liquidity Tag",
    "Wheel Score",
    "Wheel Action",
    "Safety Band",
    "Volatility Tag",
    "1W Ret %",
    "1M Ret %",
    "3M Ret %",
    "YTD Ret %",
    "1Y Ret %",
    "% from 52W High",
    "RSI 14",
    "Rel Str vs Nifty 3M",
    "Dip Signal",
    "Insider Activity",
    "Block/Bulk Activity",
]

NUMERIC_FIELDS = {
    "spot_price",
    "strike",
    "premium",
    "lot_size",
    "total_premium",
    "otm_pct",
    "days_to_expiry",
    "itm_risk_pct",
    "premium_yield_pct",
    "monthly_yield_pct",
    "move_cover",
    "wheel_score",
    "rsi_14",
    "relative_strength_3m",
    "beta",
    "hist_vol_pct",
    "downside_vol_pct",
    "atr_pct",
    "expected_move_pct",
    "ret_1w_pct",
    "ret_1m_pct",
    "ret_3m_pct",
    "ytd_ret_pct",
    "ret_1y_pct",
    "pct_from_52w_high",
}

COLUMN_TO_FIELD = {
    "Stock": "symbol",
    "Spot Price": "spot_price",
    "Strike": "strike",
    "Premium": "premium",
    "Lot Size": "lot_size",
    "Total Premium": "total_premium",
    "% OTM": "otm_pct",
    "Expiry": "expiry",
    "Beta": "beta",
    "Hist Vol %": "hist_vol_pct",
    "Downside Vol %": "downside_vol_pct",
    "ATR %": "atr_pct",
    "Days to Expiry": "days_to_expiry",
    "Expected Move %": "expected_move_pct",
    "ITM Risk %": "itm_risk_pct",
    "Premium Yield %": "premium_yield_pct",
    "Monthly Yield %": "monthly_yield_pct",
    "Move Cover": "move_cover",
    "Liquidity Tag": "liquidity_tag",
    "Wheel Score": "wheel_score",
    "Wheel Action": "wheel_action",
    "Safety Band": "safety_band",
    "Volatility Tag": "volatility_tag",
    "1W Ret %": "ret_1w_pct",
    "1M Ret %": "ret_1m_pct",
    "3M Ret %": "ret_3m_pct",
    "YTD Ret %": "ytd_ret_pct",
    "1Y Ret %": "ret_1y_pct",
    "% from 52W High": "pct_from_52w_high",
    "RSI 14": "rsi_14",
    "Rel Str vs Nifty 3M": "relative_strength_3m",
    "Dip Signal": "dip_signal",
    "Insider Activity": "insider_activity",
    "Block/Bulk Activity": "block_bulk_activity",
}

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _col_to_idx(ref: str) -> int:
    letters = "".join(ch for ch in str(ref or "") if ch.isalpha()) or "A"
    out = 0
    for char in letters:
        out = out * 26 + ord(char.upper()) - 64
    return max(0, out - 1)


def _target_path(target: str) -> str:
    clean = str(target or "").lstrip("/")
    return clean if clean.startswith("xl/") else f"xl/{clean}"


def _clean_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _to_number(value: Any) -> float:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"-", "NA", "N/A"}:
        return 0.0
    text = text.rstrip("%")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _normalize_expiry(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    # Excel serial date fallback.
    serial = _to_number(text)
    if serial > 20_000:
        return datetime.fromtimestamp((serial - 25569) * 86400, timezone.utc).date().isoformat()
    return text


def _read_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.findall(".//a:t", NS)) for si in root.findall("a:si", NS)]


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "s":
        node = cell.find("a:v", NS)
        if node is not None and node.text:
            return shared_strings[int(node.text)]
        return ""
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//a:t", NS))
    value_node = cell.find("a:v", NS)
    if value_node is not None and value_node.text is not None:
        return value_node.text
    formula_node = cell.find("a:f", NS)
    return f"={formula_node.text}" if formula_node is not None and formula_node.text else ""


def _read_sheet_rows(zf: ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(zf.read(sheet_path))
    rows: list[list[str]] = []
    for row in root.findall(".//a:sheetData/a:row", NS):
        values: list[str] = []
        for cell in row.findall("a:c", NS):
            idx = _col_to_idx(cell.attrib.get("r", "A"))
            while len(values) <= idx:
                values.append("")
            values[idx] = _cell_value(cell, shared_strings)
        rows.append(values)
    return rows


def _workbook_sheet_paths(zf: ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
    out: dict[str, str] = {}
    for sheet in workbook.findall("a:sheets/a:sheet", NS):
        name = sheet.attrib.get("name", "")
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        if name and rel_id in rel_map:
            out[name] = _target_path(rel_map[rel_id])
    return out


def _normalize_row(raw: dict[str, Any], source_tab: str, row_number: int) -> dict[str, Any] | None:
    symbol = str(raw.get("Stock") or "").strip().upper()
    if not symbol:
        return None
    candidate: dict[str, Any] = {
        "symbol": symbol,
        "source_tab": source_tab,
        "dhan_strategy": SOURCE_TO_STRATEGY[source_tab],
        "source_row_number": row_number,
    }
    for column, field in COLUMN_TO_FIELD.items():
        value = raw.get(column, "")
        if field == "symbol":
            continue
        if field == "expiry":
            candidate[field] = _normalize_expiry(value)
        elif field in NUMERIC_FIELDS:
            candidate[field] = _to_number(value)
        else:
            candidate[field] = str(value or "").strip()
    return candidate


def parse_fno_opportunities_xlsx(
    content: bytes,
    *,
    selected_tabs: list[str] | tuple[str, ...] | None = None,
    source_file_name: str = "",
) -> dict[str, Any]:
    """Parse supported CE/PE shortlist tabs from an uploaded xlsx payload."""

    tabs = tuple(tab for tab in (selected_tabs or SUPPORTED_SHEETS) if tab in SUPPORTED_SHEETS)
    candidates: list[dict[str, Any]] = []
    rows_read = {"CE_WHEEL_SHORTLIST": 0, "PE_WHEEL_SHORTLIST": 0}
    missing_tabs: list[str] = []
    with ZipFile(Path(source_file_name) if isinstance(content, Path) else __import__("io").BytesIO(content)) as zf:
        shared_strings = _read_shared_strings(zf)
        sheet_paths = _workbook_sheet_paths(zf)
        for tab in tabs:
            sheet_path = sheet_paths.get(tab)
            if not sheet_path:
                missing_tabs.append(tab)
                continue
            rows = _read_sheet_rows(zf, sheet_path, shared_strings)
            if not rows:
                continue
            headers = [_clean_header(value) for value in rows[0]]
            header_index = {header: idx for idx, header in enumerate(headers) if header}
            for excel_row_number, row in enumerate(rows[1:], start=2):
                raw = {
                    column: row[header_index[column]] if column in header_index and header_index[column] < len(row) else ""
                    for column in EXPECTED_COLUMNS
                }
                candidate = _normalize_row(raw, tab, excel_row_number)
                if candidate:
                    candidates.append(candidate)
                    rows_read[tab] += 1
    return {
        "source_file_name": source_file_name,
        "candidates": candidates,
        "ce_rows_read": rows_read["CE_WHEEL_SHORTLIST"],
        "pe_rows_read": rows_read["PE_WHEEL_SHORTLIST"],
        "missing_tabs": missing_tabs,
    }

