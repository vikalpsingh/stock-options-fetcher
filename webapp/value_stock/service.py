from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import UploadedPdf
from .pdf_parser import PdfExtractionError, parse_pdf_content, parse_screener_pdf_text
from .repository import ValueStockRepository


class ValueStockService:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.repository = ValueStockRepository(db_path)

    def upload_pdf(self, upload: UploadedPdf) -> dict[str, Any]:
        filename = Path(upload.filename or "").name
        if not filename:
            raise ValueError("Upload a PDF file.")
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Only PDF files are supported.")
        if upload.content_type and "pdf" not in upload.content_type.lower():
            raise ValueError("The uploaded file content type is not PDF.")
        try:
            parsed = parse_pdf_content(filename, upload.content)
        except PdfExtractionError:
            raise
        except Exception as exc:
            raise PdfExtractionError(f"Could not parse PDF: {exc}") from exc
        result = self.repository.upsert_parsed(parsed)
        result.update(
            {
                "company_name": parsed.company_name,
                "score": parsed.score.get("total"),
                "decision": parsed.score.get("decision"),
                "warnings": parsed.warnings,
            }
        )
        return result

    def list_companies(self, search: str = "", sector: str = "", decision: str = "") -> list[dict[str, Any]]:
        return self.repository.list_companies(search=search, sector=sector, decision=decision)

    def refresh_missing_sector_from_saved_text(self, limit: int = 25) -> int:
        refreshed = 0
        for document in self.repository.documents_missing_sector(limit):
            raw_text = str(document.get("raw_text") or "")
            checksum = str(document.get("checksum") or "")
            filename = str(document.get("filename") or "saved.pdf")
            if not raw_text or not checksum:
                continue
            parsed = parse_screener_pdf_text(raw_text, filename, checksum)
            if parsed.sector or parsed.industry:
                self.repository.upsert_parsed(parsed)
                refreshed += 1
        return refreshed

    def sectors(self) -> list[str]:
        return self.repository.sectors()

    def get_company(self, company_key: str) -> dict[str, Any] | None:
        return self.repository.get_company(company_key)
