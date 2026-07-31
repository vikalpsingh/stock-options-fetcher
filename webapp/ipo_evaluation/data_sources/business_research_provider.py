from __future__ import annotations

from typing import Protocol

from ..models.business_snapshot import BusinessSnapshot
from ..models.security import SecurityIdentity


class BusinessResearchProvider(Protocol):
    def get_business_snapshot(self, identity: SecurityIdentity) -> BusinessSnapshot: ...
