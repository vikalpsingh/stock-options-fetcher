from __future__ import annotations

from typing import Any


def load_nifty_option_chain(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
    """App-level Kite option chain loading lives in app.py; this seam keeps the engine package importable in tests."""
    return []
