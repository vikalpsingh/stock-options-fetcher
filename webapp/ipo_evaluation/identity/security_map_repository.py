from __future__ import annotations

from pathlib import Path

from ipo.security_map.repository import get_security_mapping

from ..models.security import SecurityIdentity


class SecurityMapRepository:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = path

    def get(self, company_name: str) -> SecurityIdentity | None:
        mapping = get_security_mapping(company_name, self.path)
        if mapping is None:
            return None
        status = str(getattr(mapping, "mapping_status", "") or mapping.status or "")
        if status in {"SOURCE_VERIFIED", "KITE_VERIFIED"}:
            status = "VERIFIED" if mapping.kite_verified else "PARTIALLY_VERIFIED"
        token = mapping.instrument_token
        try:
            parsed_token = int(token) if token not in {None, ""} else None
        except (TypeError, ValueError):
            parsed_token = None
        return SecurityIdentity(
            canonical_name=mapping.canonical_name,
            legal_name=mapping.legal_name,
            aliases=mapping.aliases,
            primary_exchange=mapping.primary_exchange,
            segment=mapping.segment,
            nse_symbol=mapping.nse_symbol,
            bse_security_code=mapping.bse_security_code,
            isin=mapping.isin,
            kite_tradingsymbol=mapping.kite_tradingsymbol,
            kite_key=mapping.kite_key,
            instrument_token=parsed_token,
            mapping_status=status,
            kite_verified=mapping.kite_verified,
        )
