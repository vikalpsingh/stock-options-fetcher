from __future__ import annotations

from pydantic import BaseModel, Field

from .business_snapshot import BusinessSnapshot
from .financial_snapshot import FinancialSnapshot, SourceEvidence
from .governance_snapshot import GovernanceSnapshot
from .market_snapshot import MarketSnapshot
from .peer_snapshot import PeerSnapshot
from .security import SecurityIdentity


class IpoSnapshot(BaseModel):
    ipo_year: int
    listing_date: str = ""
    ipo_price: float | None = None
    listing_price: float | None = None
    issue_size: float | None = None
    fresh_issue: float | None = None
    offer_for_sale: float | None = None
    ipo_market_cap: float | None = None
    current_return_pct: float | None = None
    use_of_proceeds: list[str] = Field(default_factory=list)
    promoter_dilution: float | None = None
    listed_quarters: int | None = None
    sources: list[SourceEvidence] = Field(default_factory=list)


class ValuationSnapshot(BaseModel):
    market_cap: float | None = None
    enterprise_value: float | None = None
    pe: float | None = None
    pb: float | None = None
    ps: float | None = None
    ev_ebitda: float | None = None
    ev_sales: float | None = None
    peg: float | None = None
    earnings_yield: float | None = None
    fcf_yield: float | None = None
    peer_median_pe: float | None = None
    peer_median_pb: float | None = None
    peer_median_ps: float | None = None
    peer_median_ev_ebitda: float | None = None
    share_count_reliable: bool = False
    sources: list[SourceEvidence] = Field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return bool(self.sources and self.market_cap is not None and any(
            value is not None for value in (self.pe, self.pb, self.ps, self.ev_ebitda)
        ))


class EvaluationInput(BaseModel):
    identity: SecurityIdentity
    ipo: IpoSnapshot
    market: MarketSnapshot = Field(default_factory=MarketSnapshot)
    financials: FinancialSnapshot = Field(default_factory=FinancialSnapshot)
    business: BusinessSnapshot = Field(default_factory=BusinessSnapshot)
    governance: GovernanceSnapshot = Field(default_factory=GovernanceSnapshot)
    valuation: ValuationSnapshot = Field(default_factory=ValuationSnapshot)
    peers: list[PeerSnapshot] = Field(default_factory=list)
    sector: str = ""
    market_type: str = "Mainboard"
    analysis_type: str = "selected"
