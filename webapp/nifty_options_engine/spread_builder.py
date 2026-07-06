from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4


def build_nifty_spread_strategy(selected_strategy: str, selected_legs: list[dict[str, Any]], lots: int = 1) -> dict[str, Any]:
    short_legs = [leg for leg in selected_legs if str(leg.get("transaction_type") or "").upper() == "SELL"]
    hedge_legs = [leg for leg in selected_legs if str(leg.get("transaction_type") or "").upper() == "BUY"]
    short_credit = sum(float(leg.get("price") or leg.get("ltp") or 0) for leg in short_legs)
    hedge_debit = sum(float(leg.get("price") or leg.get("ltp") or 0) for leg in hedge_legs)
    strikes = [float(leg.get("strike") or 0) for leg in selected_legs if leg.get("strike") is not None]
    width = max(strikes) - min(strikes) if len(strikes) >= 2 else 0.0
    net_credit = max(0.0, short_credit - hedge_debit)
    quantity = max(int(lots), 1) * 65
    max_gain = net_credit * quantity
    max_loss = max(0.0, (width - net_credit) * quantity) if width else 0.0
    return {
        "strategy_id": f"NIFTY-{datetime.now():%Y%m%d%H%M%S}-{uuid4().hex[:6]}",
        "selected_strategy": selected_strategy,
        "entry_datetime": datetime.now().isoformat(timespec="seconds"),
        "legs": selected_legs,
        "net_credit_points": net_credit,
        "spread_width_points": width,
        "credit_pct_of_spread_width": (net_credit / width * 100.0) if width else 0.0,
        "max_gain": max_gain,
        "max_loss": max_loss,
        "margin_required": max_loss,
    }
