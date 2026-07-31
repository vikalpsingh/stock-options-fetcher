from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .financial_snapshot import SourceEvidence


class GovernanceStatus(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    DATA_PENDING = "DATA_PENDING"


class GovernanceSnapshot(BaseModel):
    promoter_holding: float | None = None
    promoter_change_qoq: float | None = None
    promoter_pledge: float | None = None
    pledge_change_qoq: float | None = None
    fii_holding: float | None = None
    dii_holding: float | None = None
    flags: list[str] = Field(default_factory=list)
    immaterial_flags: list[str] = Field(default_factory=list)
    status: GovernanceStatus = GovernanceStatus.DATA_PENDING
    sources: list[SourceEvidence] = Field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return bool(self.sources and self.promoter_holding is not None)
