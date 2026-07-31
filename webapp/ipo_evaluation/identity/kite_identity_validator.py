from __future__ import annotations

from typing import Any, Protocol

from ..models.security import SecurityIdentity


class QuoteClient(Protocol):
    def quote(self, instruments: list[str]) -> dict[str, Any]: ...


def validate_exact_kite_quote(identity: SecurityIdentity, client: QuoteClient) -> SecurityIdentity:
    if not identity.kite_key:
        return identity.model_copy(update={"quote_verified": False})
    try:
        quote = client.quote([identity.kite_key])
    except Exception:
        return identity.model_copy(update={"quote_verified": False})
    exact = quote.get(identity.kite_key) if isinstance(quote, dict) else None
    return identity.model_copy(update={"quote_verified": isinstance(exact, dict) and bool(exact)})
