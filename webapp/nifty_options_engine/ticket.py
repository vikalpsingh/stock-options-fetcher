"""Pure NIFTY 2.0 ticket validation. App supplies fresh broker context."""
from datetime import datetime, date
import math

from .risk_validator import calculate_nifty_portfolio_risk


def quote_values(quote):
    depth = quote.get("depth") or {}
    buy = (depth.get("buy") or [{}])[0]
    sell = (depth.get("sell") or [{}])[0]
    return {"bid": buy.get("price"), "ask": sell.get("price"),
            "bid_quantity": buy.get("quantity"), "ask_quantity": sell.get("quantity"),
            "oi": quote.get("oi"), "volume": quote.get("volume"),
            "timestamp": quote.get("timestamp")}


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def build_ticket(selection, context, config):
    """No order limit/LTP substitutes for missing executable bid/ask data."""
    now = context["now"]
    checks, legs, payloads = [], [], []

    def check(name, okay, reason):
        checks.append({"name": name, "status": "PASS" if okay else "BLOCK", "reason": reason})

    master = {str(row["tradingsymbol"]): row for row in context["instruments"]
              if row.get("name") == "NIFTY" and row.get("instrument_type") in {"PE", "CE"}}
    selected_sides = [side for side in ("PE", "CE") if selection.get("include_" + side.lower())]
    check("Protected structure", bool(selected_sides), "Select PE, CE, or both for a protected iron condor.")
    try:
        lots = int(selection.get("lots", 2))
        if str(lots) != str(selection.get("lots", 2)):
            raise ValueError()
    except (TypeError, ValueError):
        lots = 0
    check("Lot limit", 0 < lots <= config["maximum_lots_per_new_trade"], "Quantity uses the selected contracts' current NFO lot size.")
    try:
        expiry = date.fromisoformat(str(selection.get("expiry")))
        dte = (expiry - now.date()).days
    except (ValueError, TypeError):
        expiry, dte = None, -1
    check("Expiry", dte > config["force_exit_dte"], f"Expiry must be beyond the {config['force_exit_dte']}-DTE exit threshold.")
    for side in selected_sides:
        for action, field in (("BUY", "hedge_"), ("SELL", "short_")):
            symbol = str(selection.get(field + side.lower()) or "")
            instrument = master.get(symbol)
            valid = bool(instrument and instrument["instrument_type"] == side
                         and str(instrument["expiry"])[:10] == str(expiry))
            check(f"{action} {side} contract", valid, "Contract, type and expiry must match the current instrument master.")
            if not valid:
                continue
            lot = int(instrument.get("lot_size") or 0)
            qty = lot * lots
            quote = quote_values(context["quotes"].get("NFO:" + symbol) or {})
            bid, ask = number(quote["bid"]), number(quote["ask"])
            valid_book = bid is not None and ask is not None and 0 < bid <= ask
            check(f"{symbol} bid/ask", valid_book, "Positive uncrossed executable quotes required; LTP is not used.")
            fresh = False
            try:
                stamp = datetime.fromisoformat(str(quote["timestamp"]))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=now.tzinfo)
                fresh = 0 <= (now - stamp).total_seconds() <= config.get("max_quote_age_seconds", 120)
            except (ValueError, TypeError):
                pass
            check(f"{symbol} quote age", fresh, "Broker quote timestamp must be within the freshness limit.")
            spread_ok = valid_book and (ask - bid) / bid * 100 <= config.get("max_bid_ask_spread_pct", 8)
            check(f"{symbol} liquidity", spread_ok and (number(quote["ask_quantity" if action == "BUY" else "bid_quantity"]) or 0) >= qty > 0,
                  "Best-price depth must cover quantity and the bid/ask spread must pass.")
            price = ask if action == "BUY" else bid
            leg = dict(tradingsymbol=symbol, instrument_token=instrument["instrument_token"],
                       option_type=side, strike=float(instrument["strike"]), expiry=str(expiry),
                       quantity=qty, lot_size=lot, transaction_type=action, product="NRML",
                       bid=bid, ask=ask, oi=quote["oi"], volume=quote["volume"])
            legs.append(leg)
            payloads.append(dict(variety="regular", exchange="NFO", tradingsymbol=symbol,
                                 transaction_type=action, quantity=qty, product="NRML",
                                 order_type="LIMIT", price=price or 0, validity="DAY"))
    legs.sort(key=lambda row: row["transaction_type"] != "BUY")
    payloads.sort(key=lambda row: row["transaction_type"] != "BUY")
    check("Matched lot sizes", bool(legs) and len({leg["lot_size"] for leg in legs}) == 1
          and all(leg["lot_size"] > 0 for leg in legs), "All selected legs must use the same verified lot size.")
    fees = config.get("estimated_execution_costs_inr", 500)
    risk = calculate_nifty_portfolio_risk(
        context["positions"], {"legs": legs}, config={**config, "estimated_execution_costs_inr": fees},
        strategy_allocations=context.get("allocations"), pending_orders=context.get("orders"))
    check("Portfolio risk", risk["risk_status"] == "PASS", ", ".join(risk["hard_block_reasons"]) or "Within the aggregate defined-loss cap, including estimated costs.")
    credit = sum((leg["bid"] or 0) * leg["quantity"] if leg["transaction_type"] == "SELL"
                 else -(leg["ask"] or 0) * leg["quantity"] for leg in legs)
    check("Net income", credit > fees, "Executable credit must exceed estimated total trading costs.")
    monthly = context.get("monthly") or {}
    check("Monthly loss guard", bool(monthly) and monthly.get("risk_state") not in {None, "UNKNOWN", "UNAVAILABLE"}
          and not monthly.get("hard_locked"), "New entries are blocked when monthly risk data is unavailable or hard-locked.")
    mode = selection.get("mode", "PAPER")
    check("Mode", mode in {"PAPER", "LIVE"}, "Explicit PAPER or LIVE mode required.")
    if mode == "LIVE":
        check("LIVE enabled", config["live_enabled"] and context.get("live_ack_enabled", False),
              "Enable NIFTY 2.0 LIVE in settings and the existing broker live-order acknowledgement.")
        check("Market session", context.get("market_open", False), "LIVE orders require an open exchange session.")
        check("Broker account", bool(context.get("session_fingerprint")), "Verified broker session required.")
        guard = context.get("live_risk_gate") or {}
        check("NIFTY live risk gate", guard.get("allowed") is True,
              guard.get("reason") or "Fresh existing NIFTY regime, confidence and data-quality checks are required.")
    margin = number(context.get("margin"))
    funds = number(context.get("funds"))
    check("Broker margin", margin is not None and funds is not None and 0 < margin <= funds,
          "Fresh verified basket margin must fit available broker funds.")
    strategy = "IRON_CONDOR" if len(selected_sides) == 2 else "BULL_PUT_SPREAD" if selected_sides == ["PE"] else "BEAR_CALL_SPREAD"
    check("NIFTY enabled", config.get("enabled") is True, "NIFTY 2.0 must be enabled in settings.")
    check("Allowed strategy", strategy in config.get("allowed_strategies", []),
          "The selected strategy must be enabled in settings.")
    return dict(strategy_type=strategy, legs=legs, order_payloads=payloads, selection=selection,
                mode=mode, eligible=not any(row["status"] == "BLOCK" for row in checks),
                checks=checks, risk=risk, monthly=monthly, net_credit=credit, estimated_fees=fees,
                net_max_profit=credit - fees,
                max_loss=(None if risk["new_strategy_max_loss"] is None
                          else risk["new_strategy_max_loss"] + fees),
                broker_margin=margin, available_funds=funds, spot=context.get("spot"),
                session_fingerprint=context.get("session_fingerprint"),
                reviewed_at=now.isoformat(), expiry=str(expiry), dte=dte)
