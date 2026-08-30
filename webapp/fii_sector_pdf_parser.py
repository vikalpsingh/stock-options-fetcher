"""Deterministic parser for Screener-style FII sector investment PDFs."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any


MAX_FII_PDF_SIZE_MB = 10
MIN_RECOGNIZED_FII_SECTORS = 8
MIN_ROW_EXTRACTION_CONFIDENCE = 0.85
FII_PARSER_VERSION = "fii-sector-parser-v1"
ALLOWED_MIME_TYPES = {"application/pdf"}

FII_SECTOR_ALIASES: dict[str, str] = {
    "Financial Services": "FINANCIAL_SERVICES",
    "Automobile and Auto Components": "AUTOMOBILE_AUTO_COMPONENTS",
    "Automobile & Auto Components": "AUTOMOBILE_AUTO_COMPONENTS",
    "Healthcare": "HEALTHCARE_PHARMA",
    "Healthcare & Pharmaceuticals": "HEALTHCARE_PHARMA",
    "Capital Goods": "CAPITAL_GOODS",
    "Oil, Gas & Consumable Fuels": "OIL_GAS",
    "Oil Gas & Consumable Fuels": "OIL_GAS",
    "Information Technology": "INFORMATION_TECHNOLOGY",
    "Telecommunication": "TELECOMMUNICATION",
    "Fast Moving Consumer Goods": "FMCG",
    "FMCG": "FMCG",
    "Metals & Mining": "METALS_MINING",
    "Metals and Mining": "METALS_MINING",
    "Consumer Services": "CONSUMER_SERVICES",
    "Power": "POWER",
    "Consumer Durables": "CONSUMER_DURABLES",
    "Realty": "REALTY",
    "Construction Materials": "CONSTRUCTION_MATERIALS",
}


class FiiSectorPdfError(ValueError):
    """Raised when a FII sector PDF cannot be safely accepted."""


@dataclass
class FiiSectorRow:
    sector_code: str
    source_sector_name: str
    fii_aum_pct: float | None
    fortnight_flow_cr: float | None
    one_year_flow_cr: float | None
    extraction_confidence: float
    validation_status: str
    validation_messages: list[str] = field(default_factory=list)
    fii_regime: str = "DATA_UNAVAILABLE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector_code": self.sector_code,
            "source_sector_name": self.source_sector_name,
            "fii_aum_pct": self.fii_aum_pct,
            "fortnight_flow_cr": self.fortnight_flow_cr,
            "one_year_flow_cr": self.one_year_flow_cr,
            "extraction_confidence": self.extraction_confidence,
            "validation_status": self.validation_status,
            "validation_messages": list(self.validation_messages),
            "fii_regime": self.fii_regime,
        }


@dataclass
class ParsedFiiSectorSnapshot:
    snapshot_id: str
    report_date: str
    source_name: str
    source_filename: str
    uploaded_at: str
    parser_version: str
    extraction_status: str
    recognized_sector_count: int
    rows: list[FiiSectorRow]
    checksum: str
    active: bool = False
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0

    def valid_rows(self) -> list[FiiSectorRow]:
        return [row for row in self.rows if row.sector_code != "UNMAPPED" and row.validation_status == "VALID"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "report_date": self.report_date,
            "source_name": self.source_name,
            "source_filename": self.source_filename,
            "uploaded_at": self.uploaded_at,
            "parser_version": self.parser_version,
            "extraction_status": self.extraction_status,
            "recognized_sector_count": self.recognized_sector_count,
            "rows": [row.to_dict() for row in self.rows],
            "checksum": self.checksum,
            "active": self.active,
            "warnings": list(self.warnings),
            "page_count": self.page_count,
        }


def normalize_fii_sector_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("&", "and")).strip().lower()


FII_SECTOR_ALIAS_NORMALIZED: dict[str, str] = {
    normalize_fii_sector_name(name): code for name, code in FII_SECTOR_ALIASES.items()
}


def map_fii_sector_name(value: str) -> str:
    return FII_SECTOR_ALIAS_NORMALIZED.get(normalize_fii_sector_name(value), "UNMAPPED")


def normalize_indian_currency(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        raise ValueError("missing numeric value")
    text = (
        text.replace("₹", "")
        .replace("Cr", "")
        .replace("cr", "")
        .replace(",", "")
        .replace("%", "")
        .replace("▲", "")
        .replace("▼", "")
        .replace("−", "-")
    )
    text = re.sub(r"\s+", "", text)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError(f"numeric value not found: {value}")
    return float(match.group(0))


def classify_fii_regime(one_year_flow_cr: Any, fortnight_flow_cr: Any) -> str:
    try:
        one_year = float(one_year_flow_cr)
        fortnight = float(fortnight_flow_cr)
    except (TypeError, ValueError):
        return "DATA_UNAVAILABLE"
    if one_year < 0 and fortnight > 0:
        return "RELIEF_RALLY_SELL_ON_RISE"
    if one_year < 0 and fortnight <= 0:
        return "STRUCTURAL_WEAKNESS"
    if one_year >= 0 and fortnight < 0:
        return "PROFIT_BOOKING_ONLY"
    return "ACCUMULATION"


def validate_pdf_upload(pdf_bytes: bytes, filename: str, content_type: str) -> None:
    safe_name = Path(filename or "").name
    if not safe_name.lower().endswith(".pdf"):
        raise FiiSectorPdfError("Only PDF files are accepted for FII sector upload.")
    if content_type and content_type.lower() not in ALLOWED_MIME_TYPES:
        raise FiiSectorPdfError("Upload rejected: MIME type must be application/pdf.")
    if not pdf_bytes:
        raise FiiSectorPdfError("Upload rejected: empty PDF file.")
    if len(pdf_bytes) > MAX_FII_PDF_SIZE_MB * 1024 * 1024:
        raise FiiSectorPdfError(f"Upload rejected: PDF exceeds {MAX_FII_PDF_SIZE_MB} MB.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise FiiSectorPdfError("Upload rejected: invalid PDF signature.")


def validate_fii_rows(rows: list[FiiSectorRow]) -> tuple[list[FiiSectorRow], list[str], int]:
    warnings: list[str] = []
    seen: set[str] = set()
    recognized_valid = 0
    validated: list[FiiSectorRow] = []
    for row in rows:
        messages = list(row.validation_messages)
        status = row.validation_status
        if not row.source_sector_name.strip():
            messages.append("sector name missing")
        if row.sector_code == "UNMAPPED":
            status = "UNMAPPED"
            messages.append("UNMAPPED - NOT USED IN RANKING")
        if row.sector_code in seen and row.sector_code != "UNMAPPED":
            status = "INVALID"
            messages.append("duplicate sector in uploaded PDF")
        if row.sector_code != "UNMAPPED":
            seen.add(row.sector_code)
        if row.fii_aum_pct is None or not math.isfinite(float(row.fii_aum_pct)) or not 0 <= float(row.fii_aum_pct) <= 100:
            status = "INVALID"
            messages.append("AUM percentage must be between 0 and 100")
        for label, value in (("fortnight flow", row.fortnight_flow_cr), ("one-year flow", row.one_year_flow_cr)):
            if value is None or not math.isfinite(float(value)):
                status = "INVALID"
                messages.append(f"{label} must be numeric")
        if row.extraction_confidence < MIN_ROW_EXTRACTION_CONFIDENCE:
            status = "REVIEW_REQUIRED"
            messages.append("low extraction confidence")
        if row.sector_code != "UNMAPPED" and status == "VALID":
            recognized_valid += 1
        row.fii_regime = classify_fii_regime(row.one_year_flow_cr, row.fortnight_flow_cr)
        row.validation_status = status
        row.validation_messages = list(dict.fromkeys(messages))
        validated.append(row)
    if recognized_valid < MIN_RECOGNIZED_FII_SECTORS:
        warnings.append(
            f"Only {recognized_valid} recognized valid sector(s) extracted; minimum is {MIN_RECOGNIZED_FII_SECTORS}."
        )
    return validated, warnings, recognized_valid


class FiiSectorPdfParser:
    def parse(self, pdf_bytes: bytes, filename: str = "fii-sector.pdf", content_type: str = "application/pdf") -> ParsedFiiSectorSnapshot:
        validate_pdf_upload(pdf_bytes, filename, content_type)
        text, page_count = self._extract_text(pdf_bytes)
        return self.parse_text(
            text,
            source_filename=Path(filename).name,
            checksum=hashlib.sha256(pdf_bytes).hexdigest(),
            page_count=page_count,
        )

    def parse_text(
        self,
        text: str,
        *,
        source_filename: str = "fii-sector.pdf",
        checksum: str | None = None,
        page_count: int = 0,
    ) -> ParsedFiiSectorSnapshot:
        if not text or len(text.strip()) < 50:
            raise FiiSectorPdfError("Upload rejected: PDF text is not extractable.")
        rows = self._extract_rows(text)
        rows, warnings, recognized = validate_fii_rows(rows)
        if recognized < MIN_RECOGNIZED_FII_SECTORS:
            raise FiiSectorPdfError("; ".join(warnings))
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return ParsedFiiSectorSnapshot(
            snapshot_id="",
            report_date=self._extract_report_date(text) or stamp[:10],
            source_name="Screener FII Investment PDF",
            source_filename=Path(source_filename).name,
            uploaded_at=stamp,
            parser_version=FII_PARSER_VERSION,
            extraction_status="VALID",
            recognized_sector_count=recognized,
            rows=rows,
            checksum=checksum or hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
            warnings=warnings,
            page_count=page_count,
        )

    def _extract_text(self, pdf_bytes: bytes) -> tuple[str, int]:
        try:
            import pdfplumber  # type: ignore
        except ModuleNotFoundError as exc:
            raise FiiSectorPdfError("PDF extraction requires pdfplumber in the app Python environment.") from exc
        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                if getattr(pdf, "is_encrypted", False):
                    raise FiiSectorPdfError("Upload rejected: encrypted PDFs are not accepted.")
                page_count = len(pdf.pages)
                if page_count <= 0:
                    raise FiiSectorPdfError("Upload rejected: PDF has no readable pages.")
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except FiiSectorPdfError:
            raise
        except Exception as exc:
            raise FiiSectorPdfError(f"Upload rejected: malformed or unreadable PDF. {exc}") from exc
        if not text.strip():
            raise FiiSectorPdfError("Upload rejected: no extractable text found in PDF.")
        return text, page_count

    def _extract_rows(self, text: str) -> list[FiiSectorRow]:
        normalized_text = re.sub(r"\r\n?", "\n", text)
        sector_names = sorted(FII_SECTOR_ALIASES, key=len, reverse=True)
        rows: list[FiiSectorRow] = []
        for sector_name in sector_names:
            pattern = re.compile(rf"(?im)^\s*{re.escape(sector_name)}\s*$")
            for match in pattern.finditer(normalized_text):
                block = normalized_text[match.start() : match.start() + 450]
                rows.append(self._row_from_block(sector_name, block))
        for match in re.finditer(
            r"(?ims)^\s*([A-Z][A-Za-z &,/-]{3,70})\s*\n\s*([-+]?\d+(?:\.\d+)?)\s*%\s*of\s*AUM",
            normalized_text,
        ):
            name = re.sub(r"\s+", " ", match.group(1)).strip()
            if map_fii_sector_name(name) == "UNMAPPED":
                block = normalized_text[match.start() : match.start() + 450]
                rows.append(self._row_from_block(name, block))
        return rows

    def _row_from_block(self, sector_name: str, block: str) -> FiiSectorRow:
        aum = self._match_number(block, r"([-+]?\d+(?:\.\d+)?)\s*%\s*of\s*AUM")
        fortnight = self._match_number(block, r"([-+−]?\s*[\d,]+(?:\.\d+)?)\s*Cr\s*Last\s*fortnight")
        one_year = self._match_number(block, r"([-+−]?\s*[\d,]+(?:\.\d+)?)\s*Cr\s*(?:1Y|One\s*year|1\s*Year)\s*net\s*flow")
        confidence = 0.55 + (0.15 if aum is not None else 0) + (0.15 if fortnight is not None else 0) + (0.15 if one_year is not None else 0)
        return FiiSectorRow(
            sector_code=map_fii_sector_name(sector_name),
            source_sector_name=sector_name,
            fii_aum_pct=aum,
            fortnight_flow_cr=fortnight,
            one_year_flow_cr=one_year,
            extraction_confidence=round(min(0.99, confidence), 2),
            validation_status="VALID",
        )

    def _match_number(self, text: str, pattern: str) -> float | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return None
        return normalize_indian_currency(match.group(1))

    def _extract_report_date(self, text: str) -> str | None:
        match = re.search(r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", text)
        if not match:
            return None
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(match.group(1), fmt).date().isoformat()
            except ValueError:
                continue
        return None
