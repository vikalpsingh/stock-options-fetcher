from __future__ import annotations

from typing import Any

from nifty_tactical import classify_nifty_market_regime as _classify
from nifty_tactical import select_nifty_tactical_strategy


def classify_nifty_market_regime(market_data: dict[str, Any]) -> dict[str, Any]:
    regime = _classify(market_data)
    strategy = select_nifty_tactical_strategy({**regime, **market_data})
    return {
        "market_regime": regime.get("regime"),
        "selected_strategy": strategy.get("selected_strategy"),
        "reason": strategy.get("reason") or regime.get("reason"),
        "no_trade_reason": strategy.get("skip_reason"),
        "allowed": bool(strategy.get("allowed")),
        "allow_pe_spread": bool(strategy.get("allow_pe_spread")),
        "allow_ce_spread": bool(strategy.get("allow_ce_spread")),
        "indicators_used": regime.get("indicators_used", {}),
    }
