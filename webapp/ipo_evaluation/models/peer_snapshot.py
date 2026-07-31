from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class PeerRelationship(StrEnum):
    EXACT_PEER = "EXACT_PEER"
    NEAR_PEER = "NEAR_PEER"
    BROAD_SECTOR_REFERENCE = "BROAD_SECTOR_REFERENCE"


class PeerSnapshot(BaseModel):
    company_name: str
    symbol: str
    industry: str = ""
    business_model_subtype: str = ""
    relationship: PeerRelationship
    metrics: dict[str, float | None] = Field(default_factory=dict)
    financial_data_available: bool = False
    liquidity_score: float | None = None
    listed_track_record_years: float | None = None
    market_cap: float | None = None
