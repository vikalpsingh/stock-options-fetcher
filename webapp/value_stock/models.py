from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UploadedPdf:
    filename: str
    content: bytes
    content_type: str = "application/pdf"


@dataclass
class ParsedValueStock:
    company_name: str
    company_key: str
    checksum: str
    filename: str
    source: str = "Screener PDF"
    source_date: str = ""
    exchange: str = ""
    sector: str = ""
    industry: str = ""
    screener_url: str = ""
    business_description: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    annual: dict[str, dict[str, Any]] = field(default_factory=dict)
    half_yearly: dict[str, dict[str, Any]] = field(default_factory=dict)
    balance_sheet: dict[str, dict[str, Any]] = field(default_factory=dict)
    cash_flow: dict[str, dict[str, Any]] = field(default_factory=dict)
    ratios: dict[str, dict[str, Any]] = field(default_factory=dict)
    shareholding: dict[str, dict[str, Any]] = field(default_factory=dict)
    operating_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    score: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""

