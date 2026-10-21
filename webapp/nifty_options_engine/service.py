"""Connect NIFTY tickets/ledger to the shared durable execution service."""
from copy import deepcopy

from .ledger import NiftyStrategyRepository
from .reconciliation import allocate_nifty_positions
from .risk_validator import calculate_nifty_portfolio_risk
from .ticket import build_ticket, number, quote_values
from trade_protected_execution import ProtectedExecutionRepository, basket_remaining


def load_market_context(kite, account, db_path, selection, config, now, instruments,
                        live_ack_enabled=False):
    """Read broker data using the existing session; never submits orders."""
    from collections import defaultdict
    from datetime import datetime
    from monthly_risk_control import MonthlyRiskRepository
    from pnl_service import PnlRepository, snapshot_from_kite_positions

    ledger = NiftyStrategyRepository(db_path)
    ledger.ensure_schema()
    master = {row["tradingsymbol"]: row for row in instruments if row.get("name") == "NIFTY"}
    raw_positions = list((kite.positions() or {}).get("net") or [])
    mode = selection.get("mode", "PAPER")
    session_fingerprint = None
    if mode == "LIVE":
        import hashlib
        user_id = str((kite.profile() or {}).get("user_id") or "")
        if not user_id:
            raise PermissionError("Kite account identity could not be verified.")
        session_fingerprint = hashlib.sha256(user_id.encode()).hexdigest()
    allocations = ledger.position_allocations(account, mode)
    if mode == "PAPER":
        totals = defaultdict(int)
        for row in allocations:
            totals[row["tradingsymbol"]] += row["quantity"]
        positions = [{**next(row for row in allocations if row["tradingsymbol"] == symbol),
                      "quantity": quantity, "strategy_id": ""}
                     for symbol, quantity in totals.items() if quantity]
        orders = []
    else:
        positions = []
        for row in raw_positions:
            symbol = str(row.get("tradingsymbol") or "")
            if not symbol.startswith("NIFTY") or not row.get("quantity"):
                continue
            instrument = master.get(symbol) or {}
            positions.append({**row, "account_id": account, "strike": instrument.get("strike"),
                              "expiry": str(instrument.get("expiry") or "")[:10],
                              "option_type": instrument.get("instrument_type"),
                              "instrument_token": instrument.get("instrument_token")})
        orders = [{**row, "account_id": account} for row in kite.orders()
                  if str(row.get("tradingsymbol") or "").startswith("NIFTY")]
    symbols = {str(selection.get(key) or "") for key in ("short_pe", "hedge_pe", "short_ce", "hedge_ce")}
    symbols.update(row["tradingsymbol"] for row in positions)
    keys = ["NFO:" + symbol for symbol in symbols if symbol] + ["NSE:NIFTY 50", "NSE:INDIA VIX"]
    quotes = kite.quote(keys)
    spot_quote = quotes.get("NSE:NIFTY 50") or {}
    market_open = False
    try:
        stamp = datetime.fromisoformat(str(spot_quote.get("timestamp")))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=now.tzinfo)
        market_open = (now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) < (15, 30)
                       and 0 <= (now - stamp).total_seconds() <= 120)
    except (ValueError, TypeError):
        pass
    # Reuse the existing monthly ledger and its actual-position P&L snapshot.
    pnl = PnlRepository(db_path)
    daily = snapshot_from_kite_positions(raw_positions, account_id=account, trade_date=now.date())
    pnl.upsert_daily_records(daily, audit_event="NIFTY_V2_RISK_REFRESH")
    pnl.upsert_account_daily_summary(daily, account_id=account, trade_date=now.date(), source="ACCOUNT_DAILY")
    monthly = MonthlyRiskRepository(db_path).latest_snapshot(account, now.date())
    equity = (kite.margins() or {}).get("equity") or {}
    available = equity.get("available") or {}
    funds = number(available.get("live_balance"))
    if funds is None:
        funds = number(available.get("cash"))
    context = dict(now=now, instruments=instruments, quotes=quotes, positions=positions,
                   allocations=allocations, orders=orders, monthly=monthly, margin=None, funds=funds,
                   spot=spot_quote.get("last_price"), vix=(quotes.get("NSE:INDIA VIX") or {}).get("last_price"),
                   spot_timestamp=str(spot_quote.get("timestamp") or ""), market_open=market_open,
                   live_ack_enabled=live_ack_enabled, session_fingerprint=session_fingerprint)
    draft = build_ticket(selection, context, config)
    payloads = draft["order_payloads"]
    if payloads and all(row["price"] > 0 and row["quantity"] > 0 for row in payloads):
        margin = kite.basket_order_margins(payloads)
        amounts = [number((margin.get(key) or {}).get("total")) for key in ("initial", "final")]
        context["margin"] = max(amounts) if all(value is not None and value > 0 for value in amounts) else None
    return context


def persist_review(db_path, account, ticket):
    if not ticket["eligible"]:
        raise PermissionError("Resolve every blocking check before starting review.")
    repo = ProtectedExecutionRepository(db_path)
    record = repo.create_basket_review(account, ticket, ticket["mode"])
    ledger = NiftyStrategyRepository(db_path)
    ledger.ensure_schema()
    strategy = ledger.create_strategy(account, record["id"], ticket["strategy_type"],
                                      ticket["legs"], ticket["mode"])
    record["strategy_id"] = strategy
    return repo.save(record)


def sync_execution_fills(db_path, record):
    ledger = NiftyStrategyRepository(db_path)
    ledger.ensure_schema()
    for purpose, legs in (("ENTRY", record["legs"]), ("EXIT", record.get("exit_legs", []))):
        for leg in legs:
            if not leg["order_id"]:
                continue
            ledger.register_order(record["account_id"], record["strategy_id"],
                                  leg["payload"]["tradingsymbol"], leg["order_id"], purpose)
            for raw in leg.get("trades", []):
                ledger.record_fill(record["account_id"], {
                    **raw, "price": raw.get("average_price") or raw.get("price"),
                    "filled_at": raw.get("fill_timestamp"), "fees": raw.get("fees"),
                })


def approve_entry(record, context, config):
    """Reprice whole final basket, using actual hedge cost after BUY fills."""
    context = deepcopy(context)
    allocations = context.get("allocations") or []
    allocation = allocate_nifty_positions(context["positions"], allocations)
    if allocation["block_new_entries"]:
        raise PermissionError("Position allocations differ from fresh broker quantities.")
    own = [row for row in allocations if row["strategy_id"] == record["strategy_id"]]
    for position in context["positions"]:
        used = sum(row["quantity"] for row in own if row["tradingsymbol"] == position["tradingsymbol"]
                   and row.get("product", "NRML") == position.get("product", "NRML"))
        position["quantity"] -= used
    context["positions"] = [row for row in context["positions"] if row["quantity"]]
    context["allocations"] = [row for row in allocations if row["strategy_id"] != record["strategy_id"]]
    own_ids = {leg["order_id"] for leg in record["legs"] if leg["order_id"]}
    context["orders"] = [row for row in context["orders"] if str(row.get("order_id")) not in own_ids]
    fresh = build_ticket(record["preview"]["selection"], context, config)
    if not fresh["eligible"]:
        raise PermissionError("Fresh checks blocked entry: " + "; ".join(
            row["name"] for row in fresh["checks"] if row["status"] == "BLOCK"))
    saved = record["preview"]["order_payloads"]
    if [(row["tradingsymbol"], row["quantity"]) for row in fresh["order_payloads"]] != [
            (row["tradingsymbol"], row["quantity"]) for row in saved]:
        raise PermissionError("Contract/quantity changed. Build a new review.")
    worst = deepcopy(fresh["legs"])
    for row, payload, execution in zip(worst, saved, record["legs"]):
        filled = execution["filled"]
        quantity = payload["quantity"]
        # A partial fill is not the cost of the entire order. The remainder
        # remains constrained by its saved LIMIT, including resumed condors.
        price = (execution["average"] * filled + payload["price"] * (quantity - filled)) / quantity
        if payload["transaction_type"] == "BUY":
            if execution["filled"] == 0 and payload["price"] < row["ask"]:
                raise PermissionError("Hedge ask moved above the reviewed LIMIT. Rebuild review.")
            row["ask"] = price
        else:
            if execution["filled"] == 0 and payload["price"] > row["bid"]:
                raise PermissionError("Short bid moved below the reviewed LIMIT. Rebuild review.")
            row["bid"] = price
    risk = calculate_nifty_portfolio_risk(
        context["positions"], {"legs": worst}, config={**config, "estimated_execution_costs_inr": fresh["estimated_fees"]},
        strategy_allocations=context["allocations"], pending_orders=context["orders"])
    if (risk["risk_status"] != "PASS" or risk["new_strategy_max_loss"] is None
            or risk["new_strategy_max_loss"] + fresh["estimated_fees"] > record["preview"]["max_loss"]):
        raise PermissionError("Actual hedge cost or refreshed portfolio exceeds the reviewed risk.")
    return risk


def approve_exit(record, context, close_hedges=False):
    """Only actual reducing quantities; never infer safety from an 'exit' label."""
    orphan_cleanup = not any(leg["filled"] for leg in record["legs"]
                             if leg["payload"]["transaction_type"] == "SELL")
    if record["mode"] == "LIVE" and not context.get("market_open"):
        raise PermissionError("Exchange session is closed.")
    if record["mode"] == "LIVE":
        allocation = allocate_nifty_positions(context["positions"], context.get("allocations") or [])
        if allocation["block_new_entries"]:
            raise PermissionError("Reconcile strategy ownership before submitting an automated exit.")
        if close_hedges or orphan_cleanup:
            from .reconciliation import reconcile_nifty_positions
            if reconcile_nifty_positions(context.get("allocations") or [])["block_new_entries"]:
                raise PermissionError("Resolve uncovered shorts before disposing of protective hedges.")
    original_shorts = {leg["payload"]["tradingsymbol"] for leg in record["legs"]
                       if leg["payload"]["transaction_type"] == "SELL"}
    if close_hedges and any(row["tradingsymbol"] in original_shorts and row["quantity"] < 0
                           for row in context["positions"]):
        raise PermissionError("A short position remains open. Keep the protective hedge.")
    prices = {}
    for leg in record["legs"]:
        payload = leg["payload"]
        symbol = payload["tradingsymbol"]
        target = payload["transaction_type"] == ("BUY" if close_hedges or orphan_cleanup else "SELL")
        if not leg["filled"]:
            continue
        quote = quote_values(context["quotes"].get("NFO:" + symbol) or {})
        price = number(quote["bid" if payload["transaction_type"] == "BUY" else "ask"])
        prices[symbol] = price
        if not target:
            continue
        remaining = basket_remaining(record, leg)
        if remaining <= 0:
            continue
        if record["mode"] == "LIVE":
            owned = sum(row["quantity"] for row in context.get("allocations") or []
                        if row.get("strategy_id") == record["strategy_id"]
                        and row.get("tradingsymbol") == symbol and row.get("product") == "NRML")
            direction = 1 if payload["transaction_type"] == "BUY" else -1
            if direction * owned < remaining:
                raise PermissionError("Exit exceeds this strategy's remaining allocated fills.")
        from datetime import datetime
        try:
            stamp = datetime.fromisoformat(str(quote["timestamp"]))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=context["now"].tzinfo)
            fresh = 0 <= (context["now"] - stamp).total_seconds() <= 120
        except (ValueError, TypeError):
            fresh = False
        qty = sum(row["quantity"] for row in context["positions"] if row["tradingsymbol"] == symbol
                  and row.get("product") == "NRML")
        sign = 1 if payload["transaction_type"] == "BUY" else -1
        pending = any(row.get("tradingsymbol") == symbol and row.get("status") not in
                      {"COMPLETE", "CANCELLED", "REJECTED"} for row in context["orders"])
        if not fresh or not price or sign * qty < remaining or pending:
            raise PermissionError("Exit needs fresh prices, available position quantity and no conflicting open order.")
    return prices


def live_snapshot_gate(snapshot, lots=2, maximum_lots=2, strategy_type=None):
    """Retain the existing NIFTY vetoes; missing evaluations never mean PASS."""
    no_trade = snapshot.get('no_trade_decision') or {}
    quality = snapshot.get('data_quality') or {}
    confidence = snapshot.get('confidence_score') or {}
    reasons = []
    if snapshot.get('error'):
        reasons.append('Existing NIFTY risk evaluation failed')
    if no_trade.get('allowed') is not True or no_trade.get('no_trade') is not False:
        reasons.extend(no_trade.get('reasons') or ['Regime/event/monthly evaluation unavailable or blocked'])
    if quality.get('status') != 'GOOD' or quality.get('live_order_enabled') is not True:
        reasons.append('Existing NIFTY data quality is not GOOD')
    if confidence.get('action') not in {'FULL_SIZE', 'HALF_SIZE'} or confidence.get('hard_blocks'):
        reasons.extend(confidence.get('hard_blocks') or ['Existing NIFTY confidence gate blocked'])
    multiplier = number(confidence.get('position_size_multiplier'))
    if multiplier is None or lots > int(maximum_lots * min(1, max(0, multiplier))):
        reasons.append('Requested lots exceed the existing confidence sizing allowance')
    suggestion = snapshot.get('suggestion') or {}
    if suggestion.get('allowed') is not True:
        reasons.append(str(suggestion.get('skip_reason') or 'Existing NIFTY allocation/layer/strategy gate blocked'))
    if strategy_type and suggestion.get('selected_strategy') != strategy_type:
        reasons.append('Selected structure differs from the existing NIFTY strategy approval')
    return {'allowed': not reasons, 'reason': '; '.join(str(x) for x in reasons) or 'Existing NIFTY live risk checks passed.'}
