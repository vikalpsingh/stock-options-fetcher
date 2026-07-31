from __future__ import annotations

from pydantic import BaseModel, Field

from .financial_snapshot import SourceEvidence


class BusinessSnapshot(BaseModel):
    business_summary: str = ""
    products: list[str] = Field(default_factory=list)
    end_markets: list[str] = Field(default_factory=list)
    business_model_subtype: str = ""
    domestic_export_mix: dict[str, float] = Field(default_factory=dict)
    customer_concentration: float | None = None
    order_book: float | None = None
    capacity_expansion: list[str] = Field(default_factory=list)
    competitive_advantages: list[str] = Field(default_factory=list)
    sector_tailwinds: list[str] = Field(default_factory=list)
    india_opportunity: str = ""
    global_opportunity: str = ""
    business_risks: list[str] = Field(default_factory=list)
    sector_metrics: dict[str, float | str | bool | None] = Field(default_factory=dict)
    sources: list[SourceEvidence] = Field(default_factory=list)

    @property
    def has_disclosures(self) -> bool:
        return bool(self.business_summary and self.sources)
