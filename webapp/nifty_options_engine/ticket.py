"""Pure NIFTY 2.0 ticket validation. App supplies fresh broker context."""
from datetime import datetime, date
import math
from app_time import to_ist, is_quote_fresh

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


def reviewed_quote_snapshot(quote):
    """Persist only ticket display fields, never the raw Kite SDK quote object."""
    stamp = quote.get('timestamp')
    try:
        stamp = to_ist(stamp).isoformat() if stamp is not None else None
    except (ValueError, TypeError):
        stamp = None
    return {'last_price': number(quote.get('last_price')),
            'ohlc': {'close': number((quote.get('ohlc') or {}).get('close'))},
            'timestamp': stamp}


def ltp_limit_price(quote, instrument):
    """Reviewed LTP rounded to the listed tick. No bid/ask fallback for orders."""
    from decimal import Decimal, ROUND_HALF_UP
    ltp, tick = number(quote.get('last_price')), number(instrument.get('tick_size'))
    if ltp is None or ltp <= 0 or tick is None or tick <= 0:
        return None
    units = (Decimal(str(ltp))/Decimal(str(tick))).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
    value = float(units*Decimal(str(tick)))
    return value if value>0 else None


def depth_limit(quote, action, quantity):
    """Conservative LIMIT using quoted depth; never asserts a fill guarantee.

    Insufficient displayed depth is advisory: the residual may rest unfilled at
    the worst visible limit. Existing hedge-fill checks still gate every short.
    """
    levels = []
    for row in (quote.get('depth') or {}).get('sell' if action=='BUY' else 'buy') or []:
        price, size = number(row.get('price')), number(row.get('quantity'))
        if price is not None and price>0 and size is not None and size>0:
            levels.append((price,size))
    levels.sort(reverse=action=='SELL')
    covered, limit = 0, None
    for price,size in levels:
        if covered >= quantity:
            break
        covered += min(size,max(0,quantity-covered))
        limit = price
    return dict(limit=limit, displayed_quantity=covered, shortfall=max(0,quantity-covered))


def is_hundred_strike(row):
    strike = number(row.get('strike'))
    return strike is not None and strike > 0 and strike % 100 == 0


def further_otm_contract(instruments, side, expiry, target):
    """Use a listed contract at/beyond target, never round towards ATM."""
    candidates = [row for row in instruments if row.get('name') == 'NIFTY'
        and row.get('instrument_type') == side and str(row.get('expiry'))[:10] == str(expiry)
        and is_hundred_strike(row)
        and (float(row['strike']) <= target if side == 'PE' else float(row['strike']) >= target)]
    return min(candidates, key=lambda row: abs(float(row['strike'])-target)) if candidates else None


def build_ticket(selection, context, config, *, for_execution=True):
    """No order limit/LTP substitutes for missing executable bid/ask data."""
    now = to_ist(context["now"])
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
    check("Lot limit", lots in config.get("allowed_lots", [1, 2, 3, 4]) and 0 < lots <= config["maximum_lots_per_new_trade"], "Quantity uses the selected contracts' current NFO lot size.")
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
            check(f"{action} {side} strike grid", is_hundred_strike(instrument),
                  "Choose a listed 100-point strike and create a fresh review.")
            lot = int(instrument.get("lot_size") or 0)
            qty = lot * lots
            quote = quote_values(context["quotes"].get("NFO:" + symbol) or {})
            bid, ask = number(quote["bid"]), number(quote["ask"])
            valid_book = bid is not None and ask is not None and 0 < bid <= ask
            check(f"{symbol} bid/ask", valid_book, "Positive uncrossed executable quotes required; LTP is not used.")
            fresh = is_quote_fresh(quote, min(120, config.get("max_quote_age_seconds", 120)), now)
            if not fresh and selection.get('mode', 'PAPER') == 'PAPER':
                # Explicit testing exception: only the simulated order adapter may
                # consume old prices. LIVE, even on localhost, still fails closed.
                checks.append(dict(name=f'{symbol} simulated quote', status='WARNING',
                    reason='PAPER simulation uses an old or undated quote; this is not a current executable market price.'))
            else:
                check(f"{symbol} quote freshness", fresh, "Refresh required — quote timestamp is missing or prices are older than 2 minutes." if not fresh else "Current quote verified in IST.")
            spread_pct = (ask-bid)/bid*100 if valid_book else None
            execution = depth_limit(context['quotes'].get('NFO:'+symbol) or {}, action, qty)
            price = execution['limit'] or (ask if action=='BUY' else bid)
            # User-requested removal of the blanket liquidity veto. Valid quotes,
            # conservative LIMIT risk and confirmed hedge fills remain mandatory.
            warning = execution['shortfall'] > 0 or (spread_pct is not None and spread_pct > config.get('max_bid_ask_spread_pct',8))
            checks.append(dict(name=f'{symbol} execution depth', status='WARNING' if warning else 'PASS',
                reason=f"Requested {qty}; quoted depth {execution['displayed_quantity']:g}; shortfall {execution['shortfall']:g}. "
                + (f"Spread {spread_pct:.2f}%. " if spread_pct is not None else '')
                + 'LIMIT orders can remain partially or wholly unfilled; SELL waits for confirmed hedge fills.'))
            if valid_book and price is not None:
                # Price the entire quantity at the worst consumed/visible level,
                # not at optimistic top-of-book or VWAP.
                price = max(price,ask) if action=='BUY' else min(price,bid)
                if action=='BUY':
                    ask=price
                else:
                    bid=price
            limit_price = ltp_limit_price(context['quotes'].get('NFO:'+symbol) or {}, instrument)
            check(f'{symbol} LTP limit', limit_price is not None,
                  'A positive LTP and instrument-master tick size are required for the LIMIT order.')
            if limit_price is not None and valid_book:
                # Do not count optimistic LTP sell proceeds as executable credit.
                ask = max(ask,limit_price) if action=='BUY' else ask
                bid = min(bid,limit_price) if action=='SELL' else bid
            leg = dict(tradingsymbol=symbol, instrument_token=instrument["instrument_token"],
                       option_type=side, strike=float(instrument["strike"]), expiry=str(expiry),
                       quantity=qty, lot_size=lot, transaction_type=action, product="NRML",
                       bid=bid, ask=ask, oi=quote["oi"], volume=quote["volume"],
                       reviewed_quote=reviewed_quote_snapshot(context["quotes"].get("NFO:" + symbol) or {}))
            legs.append(leg)
            payloads.append(dict(variety="regular", exchange="NFO", tradingsymbol=symbol,
                                 transaction_type=action, quantity=qty, product="NRML",
                                 order_type="LIMIT", price=limit_price or 0, validity="DAY"))
    legs.sort(key=lambda row: row["transaction_type"] != "BUY")
    payloads.sort(key=lambda row: row["transaction_type"] != "BUY")
    check("Matched lot sizes", bool(legs) and len({leg["lot_size"] for leg in legs}) == 1
          and all(leg["lot_size"] > 0 for leg in legs), "All selected legs must use the same verified lot size.")
    fees = config.get("estimated_execution_costs_inr", 500)
    risk = calculate_nifty_portfolio_risk(
        context["positions"], {"legs": legs}, config={**config, "estimated_execution_costs_inr": fees},
        strategy_allocations=context.get("allocations"), pending_orders=context.get("orders"))
    check("Portfolio risk", risk["risk_status"] == "PASS",
          "Existing NIFTY exposure needs hedge allocation or repair before adding short exposure. New hedges do not resolve unrelated uncovered shorts."
          if risk['uncapped_risk_present'] else
          "Projected portfolio loss exceeds the configured cap; reduce quantity." if risk['risk_status'] != 'PASS'
          else "Within the aggregate defined-loss cap, including estimated costs.")
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
        if for_execution:
            check("Market session", context.get("market_open", False), "Exchange is closed or current session data is unavailable. Refresh during the trading session before GO.")
        check("Broker account", bool(context.get("session_fingerprint")), "Verified broker session required.")
        guard = context.get("live_risk_gate") or {}
        # User-requested relaxation is limited to duplicate legacy model advice.
        # Event/monthly/unknown evaluation vetoes remain blocking, as do actual
        # quote, ownership, portfolio cap and hedge-fill checks elsewhere.
        advisory = {'Existing NIFTY data quality is not GOOD',
                    'Requested lots exceed the existing confidence sizing allowance',
                    'NIFTY_HEDGE_INTEGRITY_CRITICAL',
                    'Selected structure differs from the existing NIFTY strategy approval'}
        if guard.get('allowed') is not True:
            reasons = [text.strip() for text in str(guard.get('reason') or '').split(';') if text.strip()]
            if reasons and all(reason in advisory for reason in reasons):
                checks.append(dict(name='Strategy advisory',status='WARNING',
                    reason='Legacy scan advice differs from this manual ticket. Review selected contracts and risk.'))
            else:
                check('NIFTY risk approval', False, 'Event or risk approval is unavailable or blocked. Refresh before entry.')
    margin = number(context.get("margin"))
    funds = number(context.get("funds"))
    # Explicit user policy: margin is informational for NIFTY tickets. Kite is
    # the final authority and may reject any leg; never retry that rejection here.
    # This does not relax payoff risk, ownership or BUY-fill-before-SELL checks.
    margin_ok = margin is not None and funds is not None and 0 < margin <= funds
    checks.append(dict(name='Broker margin estimate', status='PASS' if margin_ok else 'WARNING',
        reason=(f'Estimated margin {margin:,.2f}; reported funds {funds:,.2f}. '
                if margin is not None and funds is not None else 'Margin estimate unavailable. ')
               + 'Informational only. Kite decides order acceptance; insufficient margin may reject the order.'))
    strategy = "IRON_CONDOR" if len(selected_sides) == 2 else "BULL_PUT_SPREAD" if selected_sides == ["PE"] else "BEAR_CALL_SPREAD"
    check("NIFTY enabled", config.get("enabled") is True, "NIFTY 2.0 must be enabled in settings.")
    check("Allowed strategy", strategy in config.get("allowed_strategies", []),
          "The selected strategy must be enabled in settings.")
    display_legs = []
    for side in ('PE', 'CE'):
        for action, field in (('BUY', 'hedge_'), ('SELL', 'short_')):
            symbol = str(selection.get(field+side.lower()) or '')
            instrument = master.get(symbol) or {}
            raw_quote = context['quotes'].get('NFO:'+symbol) or {}
            selected = side in selected_sides
            display_legs.append(dict(tradingsymbol=symbol, transaction_type=action,
                option_type=side, strike=instrument.get('strike'), expiry=str(instrument.get('expiry') or ''),
                selected=selected, lots=lots if selected else 0,
                quantity=(instrument.get('lot_size') or 0)*lots if selected else 0,
                reviewed_quote=reviewed_quote_snapshot(raw_quote), **{k:v for k,v in quote_values(raw_quote).items() if k in {'bid','ask'}}))
    return dict(price_policy="REVIEWED_LTP_LIMIT", strategy_type=strategy, display_legs=display_legs, legs=legs, order_payloads=payloads, selection=selection,
                mode=mode, eligible=not any(row["status"] == "BLOCK" for row in checks),
                checks=checks, risk=risk, monthly=monthly, net_credit=credit, estimated_fees=fees,
                net_max_profit=credit - fees,
                max_loss=(None if risk["new_strategy_max_loss"] is None
                          else risk["new_strategy_max_loss"] + fees),
                broker_margin=margin, available_funds=funds, spot=context.get("spot"),
                session_fingerprint=context.get("session_fingerprint"),
                reviewed_at=now.isoformat(), expiry=str(expiry), dte=dte)


def nearby_spread_candidates(selection, instruments, width=300):
    """Listed same-expiry pairs, original then +/-100 steps only."""
    output = {}
    for side in ('PE','CE'):
        rows = [row for row in instruments if row.get('name')=='NIFTY'
                and row.get('instrument_type')==side
                and str(row.get('expiry'))[:10]==selection.get('expiry') and is_hundred_strike(row)]
        chosen = next((row for row in rows if row['tradingsymbol']==selection.get('short_'+side.lower())),None)
        if not chosen:
            continue
        by_strike = {float(row['strike']):row for row in rows}
        pairs=[]
        offsets=[0]+[sign*n for n in range(100,501,100) for sign in (-1,1)]
        for offset in offsets:
            short=by_strike.get(float(chosen['strike'])+offset)
            hedge=by_strike.get(float(chosen['strike'])+offset+(-width if side=='PE' else width))
            if short and hedge:
                pairs.append((short,hedge))
        output[side]=pairs
    return output


def find_nearby_liquid_spreads(selection, context, config, *, toward_spot=False):
    """Discovery only. User selection triggers full canonical risk review."""
    result={}
    try:
        lots=int(selection.get('lots',2))
    except (ValueError,TypeError):
        return result
    for side,pairs in nearby_spread_candidates(selection,context['instruments'],config['default_hedge_width_points']).items():
        if toward_spot:
            spot=number(context.get('spot'))
            original=next((row for row in context['instruments'] if row.get('tradingsymbol')==selection.get('short_'+side.lower())),{})
            original_strike=number(original.get('strike'))
            if spot is None or original_strike is None:
                continue
            pairs=[pair for pair in pairs if (original_strike < float(pair[0]['strike']) < spot if side=='PE'
                   else spot < float(pair[0]['strike']) < original_strike)]
            pairs.sort(key=lambda pair:abs(float(pair[0]['strike'])-original_strike))
        for short,hedge in pairs:
            okay=True
            for row,action in ((short,'SELL'),(hedge,'BUY')):
                quote=context['quotes'].get('NFO:'+row['tradingsymbol']) or {}
                book=quote_values(quote)
                bid,ask=number(book['bid']),number(book['ask'])
                qty=lots*int(row.get('lot_size') or 0)
                okay &= bool(qty>0 and bid and ask and 0<bid<=ask and
                    (ask-bid)/bid*100<=config.get('max_bid_ask_spread_pct',8) and
                    (number(book['bid_quantity' if action=='SELL' else 'ask_quantity']) or 0)>=qty and
                    is_quote_fresh(quote,120,context['now']))
            if okay and short['tradingsymbol'] != selection.get('short_'+side.lower()):
                result.setdefault(side,[]).append(dict(short=short['tradingsymbol'],hedge=hedge['tradingsymbol'],strike=short['strike']))
                if len(result[side])==3:
                    break
    return result
