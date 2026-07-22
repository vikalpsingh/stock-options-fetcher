"""Covered-call capacity and sizing calculations."""

from __future__ import annotations

from .config import COVERED_CALL_CONFIG, CoveredCallConfig
from .models import CoveredCallCapacity


def _positive_int(value: object) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def calculate_covered_call_capacity(
    *,
    symbol: str,
    holding_qty: int,
    lot_size: int,
    spot_price: float = 0.0,
    existing_short_ce_qty: int = 0,
    user_max_lots: int | None = None,
    category: str = "NORMAL",
    config: CoveredCallConfig = COVERED_CALL_CONFIG,
) -> CoveredCallCapacity:
    """Separate raw capacity from recommended lots.

    capacity_lots is the mechanical lot coverage from shares held.
    recommended_lots applies portfolio guardrails and should be used for fresh
    order sizing.
    """

    holding_qty = _positive_int(holding_qty)
    lot_size = _positive_int(lot_size)
    existing_short_ce_qty = _positive_int(abs(existing_short_ce_qty))
    reason_codes: list[str] = []

    if lot_size <= 0:
        return CoveredCallCapacity(
            symbol=symbol,
            holding_qty=holding_qty,
            lot_size=0,
            capacity_lots=0,
            existing_short_ce_lots=0,
            unencumbered_shares=holding_qty,
            max_lots_by_coverage_pct=0,
            recommended_lots=0,
            recommended_quantity=0,
            max_total_covered_pct=0.0,
            current_covered_pct=0.0,
            recommended_covered_pct=0.0,
            reason_codes=["LOT_SIZE_MISSING"],
        )

    rule = config.category_rules.get(category, config.category_rules["NORMAL"])
    capacity_lots = holding_qty // lot_size
    existing_short_ce_lots = existing_short_ce_qty // lot_size
    unencumbered_shares = max(0, holding_qty - existing_short_ce_qty)
    unencumbered_lots = unencumbered_shares // lot_size

    max_covered_shares = int(holding_qty * rule.max_total_covered_pct / 100.0)
    max_lots_by_coverage_pct = max(0, (max_covered_shares - existing_short_ce_qty) // lot_size)

    max_lots_from_user = config.default_user_max_lots if user_max_lots is None else _positive_int(user_max_lots)
    max_lots_from_user = max(0, min(max_lots_from_user, rule.max_recommended_lots))

    recommended_lots = min(unencumbered_lots, max_lots_by_coverage_pct, max_lots_from_user)
    recommended_quantity = recommended_lots * lot_size

    if capacity_lots <= 0:
        reason_codes.append("NEED_MORE_SHARES")
    if existing_short_ce_lots >= capacity_lots and capacity_lots > 0:
        reason_codes.append("EXISTING_CE_ALREADY_USES_CAPACITY")
    if max_lots_by_coverage_pct <= 0 and capacity_lots > 0:
        reason_codes.append("NO_TRADE_EXCESSIVE_COVERAGE")
    if max_lots_from_user <= 0:
        reason_codes.append("USER_MAX_LOTS_ZERO")

    current_covered_pct = (existing_short_ce_qty / holding_qty * 100.0) if holding_qty else 0.0
    recommended_covered_pct = (
        ((existing_short_ce_qty + recommended_quantity) / holding_qty) * 100.0
        if holding_qty
        else 0.0
    )

    return CoveredCallCapacity(
        symbol=symbol,
        holding_qty=holding_qty,
        lot_size=lot_size,
        capacity_lots=capacity_lots,
        existing_short_ce_lots=existing_short_ce_lots,
        unencumbered_shares=unencumbered_shares,
        max_lots_by_coverage_pct=max_lots_by_coverage_pct,
        recommended_lots=recommended_lots,
        recommended_quantity=recommended_quantity,
        max_total_covered_pct=rule.max_total_covered_pct,
        current_covered_pct=current_covered_pct,
        recommended_covered_pct=recommended_covered_pct,
        reason_codes=reason_codes,
    )

