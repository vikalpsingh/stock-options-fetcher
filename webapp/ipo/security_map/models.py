from __future__ import annotations

from typing import Any

try:  # Pydantic is available in the deployed app, but keep tests resilient.
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover - exercised only if pydantic is absent.
    from dataclasses import dataclass, field

    def Field(default: Any = None, default_factory: Any = None) -> Any:
        if default_factory is not None:
            return field(default_factory=default_factory)
        return default

    class BaseModel:
        def __init__(self, **data: Any) -> None:
            annotations = getattr(self, "__annotations__", {})
            for name in annotations:
                setattr(self, name, data.get(name, getattr(self.__class__, name, None)))

        def model_dump(self) -> dict[str, Any]:
            return {name: getattr(self, name) for name in getattr(self, "__annotations__", {})}

        def dict(self) -> dict[str, Any]:
            return self.model_dump()

        @classmethod
        def parse_obj(cls, obj: dict[str, Any]) -> "BaseModel":
            return cls(**obj)


class SecurityMapping(BaseModel):
    """One verified listing identity.

    ``bse_security_code`` is the Screener/BSE identifier. It is intentionally not
    treated as a Kite tradingsymbol unless an exact Kite master row validates it.
    """

    canonical_name: str
    legal_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    primary_exchange: str = ""
    segment: str = ""
    nse_symbol: str = ""
    bse_security_code: str = ""
    bse_security_id: str = ""
    isin: str = ""
    kite_tradingsymbol: str = ""
    kite_key: str = ""
    instrument_token: str | int = ""
    listing_date: str = ""
    source: str = "verified_seed"
    source_url: str = ""
    identity_verified: bool = True
    kite_verified: bool = False
    screener_verified: bool = True
    status: str = "SOURCE_VERIFIED"
    notes: str = "Listing identity found; Kite validation pending."
    forbidden_false_matches: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()
