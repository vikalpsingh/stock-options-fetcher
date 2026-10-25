from __future__ import annotations

from typing import Any
from collections import defaultdict

from .reconciliation import allocate_nifty_positions, finite_number, reconcile_nifty_positions


def _expiry_payoff_loss(legs):
    """Exact piecewise-linear expiry payoff, segregated by account and expiry."""
    buckets = defaultdict(list)
    for leg in legs:
        if not leg["valid"] or leg["average_price"] is None or leg["average_price"] < 0:
            return None
        buckets[(leg["account_id"], leg["expiry"])].append(leg)
    total = 0.0
    for members in buckets.values():
        # Negative call slope makes the upper tail unbounded.
        if sum(leg["quantity"] for leg in members if leg["option_type"] == "CE") < 0:
            return None
        spots = {0.0, *(leg["strike"] for leg in members)}
        worst = min(sum(
            leg["quantity"] * (
                max(0.0, spot - leg["strike"]) if leg["option_type"] == "CE"
                else max(0.0, leg["strike"] - spot)
            ) - leg["quantity"] * leg["average_price"]
            for leg in members
        ) for spot in spots)
        total += max(0.0, -worst)
    return round(total, 2)


def calculate_nifty_portfolio_risk(existing_positions, proposed_strategy=None,
                                  execution_prices=None, config=None, *,
                                  strategy_allocations=None, pending_orders=None):
    """Canonical expiry risk; margin and optimistic order limits never price risk.

    Existing average fills are the cost basis. Proposed legs require best bid
    (SELL) / ask (BUY), or explicitly supplied verified execution prices.
    Missing ownership, metadata or prices returns unknown rather than zero.
    """
    config = config or {}
    cap = finite_number(config.get("max_total_nifty_defined_loss_inr", 100000))
    # User's hard ceiling cannot be lifted by a per-ticket override.
    cap = cap if cap is not None and cap > 0 else 100000.0
    allocation = None
    if strategy_allocations is not None or pending_orders is not None:
        allocation = allocate_nifty_positions(
            existing_positions, strategy_allocations or [], pending_orders)
        existing_positions = allocation["positions"]
    current = reconcile_nifty_positions(existing_positions)
    existing = [leg for group in current["groups"] for leg in group["legs"]]
    current_loss = None if current["block_new_entries"] else _expiry_payoff_loss(existing)
    reasons = []
    if allocation and allocation["block_new_entries"]:
        reasons.extend(allocation["errors"])
        if allocation["pending_sell_present"]:
            reasons.append("PENDING_SELL_REQUIRES_RECONCILIATION")
    if current_loss is None:
        reasons.append("CURRENT_RISK_UNKNOWN_OR_UNHEDGED")
    proposed = []
    quotes = execution_prices or {}
    for raw in (proposed_strategy or {}).get("legs", []):
        row = dict(raw)
        side = str(row.get("transaction_type") or row.get("action") or "").upper()
        qty = finite_number(row.get("quantity"))
        quote = quotes.get(row.get("tradingsymbol"), row)
        price = finite_number(quote.get("bid" if side == "SELL" else "ask"))
        row.update(quantity=(-qty if side == "SELL" else qty) if qty is not None else None,
                   average_price=price, strategy_id="PROPOSED")
        if side not in {"BUY", "SELL"} or qty is None or qty <= 0 or price is None or price <= 0:
            reasons.append("EXECUTABLE_PRICE_OR_QUANTITY_MISSING")
        proposed.append(row)
    proposed_check = reconcile_nifty_positions(proposed)
    new_legs = [leg for group in proposed_check["groups"] for leg in group["legs"]]
    new_loss = _expiry_payoff_loss(new_legs)
    if proposed_strategy is not None and not proposed:
        reasons.append("PROPOSED_LEGS_MISSING")
    if proposed_check["block_new_entries"]:
        reasons.append("NEW_ORDER_NOT_HEDGED")
    costs = finite_number(config.get("estimated_execution_costs_inr", 0))
    if costs is None or costs < 0:
        reasons.append("EXECUTION_COST_ESTIMATE_INVALID")
        costs = 0
    if reasons:
        projected = None
    else:
        projected = _expiry_payoff_loss(existing + new_legs)
        if projected is not None:
            projected = round(projected + costs, 2)
    if projected is None and not reasons:
        reasons.append("PAYOFF_UNKNOWN")
    if projected is not None and projected > cap:
        reasons.append("MAX_LOSS_CAP_BREACH")
    return {
        "current_defined_max_loss": current_loss,
        "new_strategy_max_loss": None if proposed_check["block_new_entries"] else new_loss,
        "projected_portfolio_max_loss": projected,
        "estimated_execution_costs": costs,
        "risk_cap": cap,
        "risk_remaining": None if projected is None else cap - projected,
        "uncapped_risk_present": current_loss is None or proposed_check["block_new_entries"],
        "risk_status": "PASS" if not reasons else "BLOCK",
        "hard_block_reasons": list(dict.fromkeys(reasons)),
        "reconciliation": current,
        "allocation_reconciliation": allocation,
        "allow_exit_orders": True,
        "allow_hedge_repair_orders": True,
    }


def strategy_risk_summary(strategy, legs, cap=100000):
    """Compatibility summary for existing NIFTY tickets, using canonical math.

    Quantities and expiry must be on actual legs. No legacy lot-size assumption,
    synthetic hedge, LTP quote substitution or optimistic limit-price fallback.
    """
    result = calculate_nifty_portfolio_risk(
        [], {"legs": legs}, config={"max_total_nifty_defined_loss_inr": cap})
    normalized, credit = [], 0.0
    prices_valid = bool(legs)
    for leg in legs:
        side = str(leg.get("transaction_type") or leg.get("action") or "").upper()
        qty = finite_number(leg.get("quantity"))
        price = finite_number(leg.get("bid" if side == "SELL" else "ask"))
        if qty is None or price is None or price <= 0 or side not in {"BUY", "SELL"}:
            prices_valid = False
            continue
        credit += qty * price * (1 if side == "SELL" else -1)
        normalized.append({**leg, "quantity": qty * (-1 if side == "SELL" else 1),
                           "average_price": 0, "strategy_id": "PROPOSED"})
    gross_legs = [leg for group in reconcile_nifty_positions(normalized)["groups"] for leg in group["legs"]]
    gross = _expiry_payoff_loss(gross_legs) if prices_valid else None
    quantities = {finite_number(leg.get("quantity")) for leg in legs}
    lotsizes = {finite_number(leg.get("lot_size")) for leg in legs}
    quantity = next(iter(quantities)) if len(quantities) == 1 else None
    lot_size = next(iter(lotsizes)) if len(lotsizes) == 1 else None
    defined = prices_valid and result["new_strategy_max_loss"] is not None and not any(
        reason in result["hard_block_reasons"]
        for reason in ("NEW_ORDER_NOT_HEDGED", "PROPOSED_LEGS_MISSING", "EXECUTABLE_PRICE_OR_QUANTITY_MISSING"))
    return {
        "strategy": strategy, "quantity": quantity, "lot_size": lot_size,
        "lots": quantity / lot_size if quantity and lot_size else None,
        "gross_risk": gross, "net_credit_value": round(credit, 2) if prices_valid else None,
        "net_credit_points": credit / quantity if prices_valid and quantity else None,
        "max_loss": result["new_strategy_max_loss"] if defined else None,
        "max_loss_cap": result["risk_cap"], "cap_remaining": result["risk_remaining"],
        "cap_status": "PASS" if result["risk_status"] == "PASS" else "FAIL",
        "defined_risk": defined, "side_details": {},
        "unhedged_sides": sorted({str(row.get("option_type") or "") for row in legs
                                 if str(row.get("transaction_type") or "").upper() == "SELL"}) if not defined else [],
        "hard_block_reasons": result["hard_block_reasons"],
    }


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def validate_nifty_strategy(
    strategy: dict[str, Any],
    account_state: dict[str, Any] | None = None,
    risk_state: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    account_state = account_state or {}
    risk_state = risk_state or {}
    warnings: list[str] = []
    blocks: list[str] = []

    legs = list(strategy.get("legs") or [])
    portfolio = calculate_nifty_portfolio_risk(
        account_state.get("nifty_positions") or [], {"legs": legs},
        config=config,
        strategy_allocations=account_state.get("nifty_strategy_allocations"),
        pending_orders=account_state.get("nifty_open_orders"),
    )
    blocks.extend(portfolio["hard_block_reasons"])
    short_legs = [leg for leg in legs if str(leg.get("transaction_type") or "").upper() == "SELL"]
    hedge_legs = [leg for leg in legs if str(leg.get("transaction_type") or "").upper() == "BUY"]
    if config.get("disallow_naked_short_options", True) and short_legs and len(hedge_legs) < len(short_legs):
        blocks.append("NAKED_SHORT_OPTION_BLOCKED")

    width = _float(strategy.get("spread_width_points"))
    credit = _float(strategy.get("net_credit_points"))
    credit_pct = credit / width * 100 if width > 0 else 0.0
    min_credit = _float(config.get("min_credit_pct_of_spread_width"), 8.0)
    if width <= 0 or credit_pct < min_credit:
        blocks.append("CREDIT_BELOW_MINIMUM")

    vix = _float(risk_state.get("india_vix") or strategy.get("india_vix"))
    if 0 < vix < 11:
        warnings.append("LOW_VIX_POOR_PREMIUM")
    if vix > 24:
        blocks.append("HIGH_VIX_NO_TRADE")

    if risk_state.get("breakout_day"):
        blocks.append("BREAKOUT_DAY_NO_TRADE")
    if risk_state.get("panic_fall"):
        blocks.append("PANIC_FALL_NO_TRADE")
    if risk_state.get("major_event_within_3_days"):
        blocks.append("MAJOR_EVENT_RISK")
    if _float(account_state.get("nifty_margin_heat_pct")) > _float(config.get("max_nifty_margin_heat_pct"), 20.0):
        blocks.append("NIFTY_MARGIN_HEAT_LIMIT")
    if _float(account_state.get("total_margin_heat_pct")) > _float(config.get("max_total_margin_heat_pct"), 40.0):
        blocks.append("TOTAL_MARGIN_HEAT_LIMIT")

    return {
        "allowed": not blocks,
        "risk_status": "ALLOWED" if not blocks else "BLOCKED",
        "warnings": warnings,
        "skip_reason": ", ".join(blocks),
        "credit_pct_of_spread_width": credit_pct,
        "portfolio_risk": portfolio,
    }


def get_max_safe_lots(existing_positions, proposed_spread, allowed_lots=(1, 2, 3, 4),
                      risk_cap=100000, *, config=None, strategy_allocations=None, pending_orders=None):
    """Risk-only sizing advice using the canonical payoff engine; never changes selection.

    Broker margin, quote freshness and liquidity must still pass at review/GO.
    Lot sizes must come from the current instrument master, never inferred from qty.
    """
    settings = {**(config or {}), "max_total_nifty_defined_loss_inr": risk_cap}
    passed, rejected, projected, remaining = [], {}, {}, {}
    for lots in allowed_lots:
        legs = proposed_spread.get("legs", [])
        if (type(lots) is not int or lots not in (1, 2, 3, 4) or not legs
                or any(not isinstance(leg.get("lot_size"), int) or leg["lot_size"] <= 0 for leg in legs)):
            rejected[lots] = ["VERIFIED_LOT_SIZE_OR_SELECTION_MISSING"]
            projected[lots] = remaining[lots] = None
            continue
        candidate = {**proposed_spread, "legs": [{**leg, "quantity": lots * leg["lot_size"]} for leg in legs]}
        risk = calculate_nifty_portfolio_risk(existing_positions, candidate, config=settings,
                    strategy_allocations=strategy_allocations, pending_orders=pending_orders)
        projected[lots] = risk["projected_portfolio_max_loss"]
        remaining[lots] = risk["risk_remaining"]
        if risk["risk_status"] == "PASS":
            passed.append(lots)
        else:
            rejected[lots] = risk["hard_block_reasons"]
    return dict(allowed_lots=passed, recommended_lots=max(passed) if passed else None,
                rejected_lots_with_reasons=rejected, projected_max_loss_by_lots=projected,
                remaining_risk_budget=remaining)
