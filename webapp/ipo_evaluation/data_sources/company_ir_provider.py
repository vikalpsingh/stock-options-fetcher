from __future__ import annotations

from typing import Any


class CompanyIrProvider:
    """Explicit company-IR adapter boundary; no implicit crawling."""

    def fetch(self, ir_url: str) -> dict[str, Any]:
        return {"url": ir_url, "status": "NOT_CONFIGURED", "documents": []}
