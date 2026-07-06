from __future__ import annotations

from datetime import date
from typing import Any

from nifty_tactical import select_spread_strikes_by_delta as _select


def select_spread_strikes_by_delta(
    option_chain: list[dict[str, Any]],
    selected_strategy: str,
    config: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    return _select(option_chain, selected_strategy, config, today)
