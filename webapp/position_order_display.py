"""Pure per-order display calculations extracted from app.py."""
import math
from typing import Any

def completed_order_current_pnl(order: dict[str, Any]) -> float | None:
    """Display-only row MTM, not booked P&L or the whole position's MTM."""
    if str(order.get("status") or "").upper() in {"CANCELLED", "CANCELED", "REJECTED"}:
        return 0.0
    if str(order.get("status") or "").upper() != "COMPLETE":
        return None
    try:
        qty = float(order.get("filled_quantity", order.get("quantity")) or 0)
        avg = float(order.get("position_avg_price") or 0)
        ltp = float(order.get("ltp"))
        position_qty = float(order.get("position_qty") or 0)
        if not all(math.isfinite(v) for v in (qty, avg, ltp, position_qty)):
            return None
        if qty <= 0 or avg <= 0 or ltp < 0 or position_qty == 0:
            return None
        # Position direction matters: a closing BUY belongs to a short position.
        return qty * (avg - ltp) if position_qty < 0 else qty * (ltp - avg)
    except (TypeError, ValueError):
        return None

