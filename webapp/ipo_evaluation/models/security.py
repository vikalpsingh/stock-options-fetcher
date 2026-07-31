from __future__ import annotations

from pydantic import BaseModel, Field


class SecurityIdentity(BaseModel):
    canonical_name: str
    legal_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    primary_exchange: str = ""
    segment: str = ""
    nse_symbol: str = ""
    bse_security_code: str = ""
    isin: str = ""
    kite_tradingsymbol: str = ""
    kite_key: str = ""
    instrument_token: int | None = None
    mapping_status: str = ""
    kite_verified: bool = False
    quote_verified: bool = False

    @property
    def is_valid(self) -> bool:
        return (
            self.mapping_status.upper() in {"VERIFIED", "PARTIALLY_VERIFIED"}
            and bool(self.primary_exchange)
            and bool(self.kite_tradingsymbol)
            and bool(self.kite_key)
            and self.instrument_token is not None
            and self.kite_verified
            and self.quote_verified
        )
