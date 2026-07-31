from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SourceEvidence(BaseModel):
    field_group: str
    source_name: str
    source_url: str
    period: str
    fetched_at: datetime
    publication_date: str = ""
    evidence_summary: str = ""
    confidence: float = Field(default=1.0, ge=0, le=1)
    is_audited: bool = False
    is_consolidated: bool = True


class EvidenceValue(BaseModel):
    value: float | str | bool | None
    period: str
    unit: str
    source_name: str
    source_url: str
    fetched_at: datetime
    confidence: float = Field(default=1.0, ge=0, le=1)
    is_audited: bool = False
    is_consolidated: bool = True

    @model_validator(mode="after")
    def require_provenance(self) -> "EvidenceValue":
        if self.value is not None and (not self.period.strip() or not self.source_name.strip()):
            raise ValueError("Every financial value requires a period and source_name")
        return self


class FinancialPeriod(BaseModel):
    period: str
    values: dict[str, EvidenceValue] = Field(default_factory=dict)


class FinancialSnapshot(BaseModel):
    annual_periods: list[FinancialPeriod] = Field(default_factory=list)
    quarterly_periods: list[FinancialPeriod] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceEvidence] = Field(default_factory=list)
    calculation_warnings: list[str] = Field(default_factory=list)

    def metric(self, name: str) -> float | None:
        value: Any = self.metrics.get(name)
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def has_annual(self) -> bool:
        return bool(self.annual_periods)

    @property
    def has_quarterly(self) -> bool:
        return bool(self.quarterly_periods)

    @property
    def has_cash_flow(self) -> bool:
        names = {"cash_flow_from_operations", "cfo_pat", "cumulative_cfo_pat_3y"}
        return any(name in self.metrics and self.metrics[name] is not None for name in names)
