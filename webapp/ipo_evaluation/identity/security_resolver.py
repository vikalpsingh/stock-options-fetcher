from __future__ import annotations

from .security_map_repository import SecurityMapRepository
from ..models.security import SecurityIdentity


def resolve_from_security_map(
    company_name: str,
    repository: SecurityMapRepository | None = None,
) -> SecurityIdentity | None:
    """Resolve only through the existing map; intentionally performs no fuzzy match."""
    return (repository or SecurityMapRepository()).get(company_name)
