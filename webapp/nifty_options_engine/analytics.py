"""Actual-fill strategy analytics. Missing prices/charges remain unknown."""
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from pnl_service import max_drawdown


def _day(value):
    stamp = datetime.fromisoformat(str(value))
    if stamp.tzinfo:
        stamp = stamp.astimezone(ZoneInfo("Asia/Kolkata"))
    return stamp.date().isoformat()


def strategy_performance(strategy, quotes=None):
    quotes = quotes or {}
    gross, known_fees, mtm, entry_cash, hedge_cost, closing_debit = 0., 0., 0., 0., 0., 0.
    fees_known, marks_known, closed, any_fill, partial = True, True, True, False, False
    events, legs = [], []
    entry_dates, exit_dates = [], []
    for leg in strategy["legs"]:
        entries = [fill for fill in leg["fills"] if fill["purpose"] == "ENTRY"]
        exits = [fill for fill in leg["fills"] if fill["purpose"] == "EXIT"]
        entered, exited = sum(f["quantity"] for f in entries), sum(f["quantity"] for f in exits)
        invalid = exited > entered or entered > leg["quantity"]
        any_fill |= bool(entries)
        partial |= invalid or entered != leg["quantity"]
        remaining = entered - exited
        closed &= entered > 0 and remaining == 0 and not invalid
        average = sum(f["quantity"] * f["price"] for f in entries) / entered if entered else 0
        direction = 1 if leg["entry_side"] == "BUY" else -1
        entry_cash -= direction * average * entered
        if direction == 1:
            hedge_cost += average * entered
        leg_gross = sum(direction * (f["price"] - average) * f["quantity"] for f in exits)
        gross += leg_gross
        for fill in leg["fills"]:
            day = _day(fill["filled_at"])
            fee = fill["fees"]
            fees_known &= fee is not None
            known_fees += fee or 0
            realised = direction * (fill["price"] - average) * fill["quantity"] if fill["purpose"] == "EXIT" else 0
            events.append({"day": day, "gross": realised, "fees": fee, "net": realised - fee if fee is not None else None})
            (entry_dates if fill["purpose"] == "ENTRY" else exit_dates).append(day)
        quote = quotes.get(leg["tradingsymbol"]) or {}
        mark = quote.get("bid" if direction == 1 else "ask")
        if remaining:
            if mark is None or mark <= 0 or invalid:
                marks_known = False
            else:
                mtm += direction * (mark - average) * remaining
                closing_debit -= direction * mark * remaining
        legs.append({**leg, "entered": entered, "exited": exited, "remaining": remaining, "invalid": invalid,
                     "average_entry": average, "realised_gross": leg_gross})
    shorts_open = any(leg["entry_side"] == "SELL" and leg["remaining"] for leg in legs)
    longs_open = any(leg["entry_side"] == "BUY" and leg["remaining"] for leg in legs)
    flat = any_fill and all(leg["remaining"] == 0 and not leg["invalid"] for leg in legs)
    status = ("CREATED" if not any_fill else "CLOSED_INCOMPLETE_ENTRY" if flat and partial else "FULLY_CLOSED" if closed else
              "SHORT_CLOSED_HEDGE_OPEN" if longs_open and not shorts_open and exit_dates else
              "PARTIAL_SPREAD" if partial else "PARTIALLY_CLOSED" if exit_dates else "OPEN_SPREAD")
    return {**strategy, "legs": legs, "status": status, "realised_gross": gross,
            "fees": known_fees if fees_known else None, "known_fees": known_fees,
            "realised_net": gross - known_fees if fees_known else None,
            "open_mtm": mtm if marks_known else None,
            "total_net": gross - known_fees + mtm if fees_known and marks_known else None,
            "entry_credit": entry_cash, "hedge_cost": hedge_cost,
            "closing_debit": closing_debit if marks_known else None,
            "captured_pct": (entry_cash - closing_debit) / entry_cash * 100
                            if entry_cash > 0 and marks_known and status == "OPEN_SPREAD" else None,
            "entry_date": min(entry_dates) if entry_dates else None,
            "exit_date": max(exit_dates) if flat and exit_dates else None,
            "events": events}


def analyze_nifty_strategy_performance(rows, start_date, end_date):
    completed = [row for row in rows if row["status"] == "FULLY_CLOSED"
                 and row["exit_date"] and start_date <= row["exit_date"] <= end_date]
    verified = [row for row in completed if row["realised_net"] is not None]
    pnls = [row["realised_net"] for row in sorted(verified, key=lambda row: row["exit_date"])]
    winners, losers = [value for value in pnls if value > 0], [value for value in pnls if value < 0]
    avg_win = sum(winners) / len(winners) if winners else 0
    avg_loss = abs(sum(losers) / len(losers)) if losers else 0
    count = len(pnls)
    return {"completed": len(completed), "verified_completed": count,
            "unreconciled_charges": len(completed) - count, "winners": len(winners), "losers": len(losers),
            "win_rate": len(winners) / count * 100 if count else None,
            "average_winner": avg_win if winners else None,
            "average_loser": -avg_loss if losers else None,
            "profit_factor": sum(winners) / abs(sum(losers)) if losers else None,
            "expectancy": (len(winners) * avg_win - len(losers) * avg_loss) / count if count else None,
            "maximum_drawdown": abs(max_drawdown(pnls)) if count else None,
            "worst_loss": min(losers) if losers else None}


def monthly_analytics(strategies, month, quotes=None):
    datetime.strptime(month, "%Y-%m")
    rows = [strategy_performance(strategy, quotes) for strategy in strategies]
    days = defaultdict(lambda: {"gross": 0., "known_fees": 0., "fees_known": True})
    for row in rows:
        for event in row["events"]:
            if event["day"].startswith(month):
                day = days[event["day"]]
                day["gross"] += event["gross"]
                day["known_fees"] += event["fees"] or 0
                day["fees_known"] &= event["fees"] is not None
    daily = [{"day": day, **data, "net": data["gross"] - data["known_fees"] if data["fees_known"] else None}
             for day, data in sorted(days.items())]
    known = all(day["fees_known"] for day in daily)
    gross, fees = sum(day["gross"] for day in daily), sum(day["known_fees"] for day in daily)
    current_month = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m") == month
    marks_known = all(row["open_mtm"] is not None for row in rows)
    mtm = sum(row["open_mtm"] for row in rows) if current_month and marks_known else None
    stats = analyze_nifty_strategy_performance(rows, month + "-01", month + "-31")
    return {"month": month, "rows": rows, "daily": daily, "realised_gross": gross,
            "fees": fees if known else None, "realised_net": gross - fees if known else None,
            "open_mtm": mtm, "total_net": gross - fees + mtm if known and mtm is not None else None,
            "stats": stats, "by_strategy": {
                kind: analyze_nifty_strategy_performance([row for row in rows if row["strategy_type"] == kind],
                                                         month + "-01", month + "-31")
                for kind in ("BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "IRON_CONDOR")},
            "scale_status": "NOT_ENOUGH_DATA" if stats["verified_completed"] < 30 else
                            "REDUCE_RISK" if (stats["expectancy"] or 0) <= 0 else "MAINTAIN_SIZE",
            "scale_reason": "No automatic sizing increase. Execution incidents, adverse-regime evidence and slippage must also be reviewed."}


def position_close_preview(position, quote, orders=(), now=None):
    """Estimate closing cash/P&L without changing realised results or placing orders.

    Long closures are limited to reconciled free quantity. Active orders reserve
    the contract until reconciled, including unknown broker statuses.
    """
    from .reconciliation import finite_number
    qty = finite_number(position.get('quantity'))
    average = finite_number(position.get('average_price'))
    result = dict(side=None, quantity=0, price=None, cash_flow=None,
                  estimated_realised_gross=None, blockers=[])
    if qty is None or not qty or not qty.is_integer() or average is None or average < 0:
        result['blockers'].append('Position quantity or entry cost is unavailable.')
        return result
    side = 'SELL' if qty>0 else 'BUY'
    free = finite_number(position.get('free_long_qty')) if qty>0 else abs(qty)
    quantity = min(abs(qty), max(0,free or 0))
    if position.get('hedge_status')=='UNKNOWN':
        quantity=0
    result.update(side=side, quantity=quantity)
    if not quantity:
        result['blockers'].append('No confirmed free quantity; retain protection for existing shorts.')
    pending = [order for order in orders
        if order.get('tradingsymbol')==position.get('tradingsymbol')
        and (order.get('product') or 'NRML')==(position.get('product') or 'NRML')
        and str(order.get('status') or '').upper() not in {'COMPLETE','CANCELLED','REJECTED'}]
    if pending:
        result['blockers'].append('Existing orders require reconciliation before another close.')
    depth = quote.get('depth') or {}
    best = (depth.get('buy' if side=='SELL' else 'sell') or [{}])[0]
    price = finite_number(best.get('price'))
    size = finite_number(best.get('quantity'))
    fresh=False
    try:
        stamp=datetime.fromisoformat(str(quote.get('timestamp')))
        if stamp.tzinfo is None:
            stamp=stamp.replace(tzinfo=ZoneInfo('Asia/Kolkata'))
        fresh=now is not None and now.tzinfo is not None and 0 <= (now-stamp).total_seconds() <= 120
    except (ValueError,TypeError):
        pass
    if not fresh:
        result['blockers'].append('Refresh required for current close prices.')
    if price is None or price <= 0 or size is None or size < quantity:
        result['blockers'].append('Executable close depth is unavailable for this quantity.')
    else:
        result['price']=price
        if quantity and fresh:
            result['cash_flow']=quantity*price*(1 if side=='SELL' else -1)
            result['estimated_realised_gross']=quantity*(price-average)*(1 if side=='SELL' else -1)
    return result
