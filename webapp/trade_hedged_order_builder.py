"""Build verified same-expiry protective put and call credit spreads."""

from __future__ import annotations

from typing import Any, Callable


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def protective_contracts(short_contract: dict[str, Any], contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Match the option type, underlying, expiry and lot, with the protective strike direction."""
    expiry = str(short_contract.get("expiry") or "")[:10]
    underlying = str(short_contract.get("name") or "").upper()
    option_type = str(short_contract.get("instrument_type") or "").upper()
    if option_type not in {"PE", "CE"}:
        return []
    direction = 1 if option_type == "CE" else -1
    short_strike = _num(short_contract.get("strike"))
    return sorted(
        [row for row in contracts
         if str(row.get("instrument_type") or "").upper() == option_type
         and str(row.get("expiry") or "")[:10] == expiry
         and (not underlying or str(row.get("name") or "").upper() == underlying)
         and _num(row.get("lot_size")) == _num(short_contract.get("lot_size"))
         and _num(row.get("strike")) > 0
         and direction * (_num(row.get("strike")) - short_strike) > 0],
        key=lambda row: abs(_num(row.get("strike")) - short_strike),
    )


def build_protective_spreads(
    short_contract: dict[str, Any], contracts: list[dict[str, Any]], quotes: dict[str, Any],
    quantity: int, *, max_loss_cap: float, margin_provider: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
    selected_hedge_symbol: str = "", use_ltp_limits: bool = False,
) -> list[dict[str, Any]]:
    """Review an explicit verified hedge, or suggest up to three nearby hedges."""
    short_symbol = str(short_contract.get("tradingsymbol") or "").upper()
    option_type = str(short_contract.get("instrument_type") or "").upper()
    if option_type not in {"PE", "CE"}:
        return []
    direction = "higher" if option_type == "CE" else "lower"
    expiry = str(short_contract.get("expiry") or "")[:10]
    short_strike = _num(short_contract.get("strike"))
    short_quote = quotes.get(f"NFO:{short_symbol}", {}) or {}
    short_depth = short_quote.get("depth") or {}
    short_bid = _num(((short_depth.get("buy") or [{}])[0] or {}).get("price"))
    short_ask = _num(((short_depth.get("sell") or [{}])[0] or {}).get("price"))
    lot_size = int(_num(short_contract.get("lot_size")))
    if not short_symbol or short_strike <= 0 or quantity <= 0 or lot_size <= 0 or quantity % lot_size:
        return []
    candidates = protective_contracts(short_contract, contracts)
    if selected_hedge_symbol:
        candidates = [row for row in candidates
                      if str(row.get("tradingsymbol") or "").upper() == selected_hedge_symbol.upper()]
        if len(candidates) != 1:
            raise ValueError(f"Selected BUY hedge must be a verified {direction}-strike {option_type} with the same underlying, expiry and lot size.")
    else:
        candidates = candidates[:6]
    alternatives: list[dict[str, Any]] = []
    for hedge in candidates:
        hedge_symbol = str(hedge.get("tradingsymbol") or "").upper()
        quote = quotes.get(f"NFO:{hedge_symbol}", {}) or {}
        depth = quote.get("depth") or {}
        ask = _num(((depth.get("sell") or [{}])[0] or {}).get("price"))
        bid = _num(((depth.get("buy") or [{}])[0] or {}).get("price"))
        volume, oi = _num(quote.get("volume")), _num(quote.get("oi"))
        hedge_lot = int(_num(hedge.get("lot_size")))
        liquid = ask > 0 and bid > 0 and volume >= 1 and oi >= quantity and hedge_lot == lot_size
        width = (_num(hedge.get("strike")) - short_strike) if option_type == "CE" else (short_strike - _num(hedge.get("strike")))
        def unavailable(reason):
            # Keep identity/observed prices in review, but never supply executable payloads.
            return dict(strategy_type="BEAR_CALL_SPREAD" if option_type=="CE" else "BULL_PUT_SPREAD",
                option_type=option_type,short_symbol=short_symbol,hedge_symbol=hedge_symbol,
                expiry=expiry,short_strike=short_strike,hedge_strike=_num(hedge.get('strike')),
                quantity=quantity,lot_size=lot_size,spread_width=width,
                short_bid=short_bid or None,short_ask=short_ask or None,
                hedge_bid=bid or None,hedge_ask=ask or None,
                eligible=False,status="BLOCK",liquidity="BLOCK",reason=reason,order_payloads=[])
        if short_bid <= 0 or ask <= 0:
            alternatives.append(unavailable("Executable SELL bid or protective BUY ask is missing. Refresh market quotes; no executable spread can be priced."))
            continue
        credit = short_bid - ask
        gross_profit = credit * quantity
        gross_loss = max(0.0, (width - credit) * quantity)
        payloads = [
            {"exchange": "NFO", "tradingsymbol": hedge_symbol, "transaction_type": "BUY", "quantity": quantity, "product": "NRML", "order_type": "LIMIT", "price": ask, "variety": "regular", "validity": "DAY"},
            {"exchange": "NFO", "tradingsymbol": short_symbol, "transaction_type": "SELL", "quantity": quantity, "product": "NRML", "order_type": "LIMIT", "price": short_bid, "variety": "regular", "validity": "DAY"},
        ]
        if use_ltp_limits:
            from nifty_options_engine.ticket import ltp_limit_price
            buy_limit=ltp_limit_price(quote,hedge)
            sell_limit=ltp_limit_price(short_quote,short_contract)
            if buy_limit is None or sell_limit is None:
                alternatives.append(unavailable("Current LTP or instrument tick size is missing for a selected leg. Refresh quotes/instrument master before reviewing LIMIT orders."))
                continue
            # Conservative risk never counts optimistic resting-limit proceeds.
            ask=max(ask,buy_limit)
            short_price=min(short_bid,sell_limit)
            credit=short_price-ask
            gross_profit=credit*quantity
            gross_loss=max(0.0,(width-credit)*quantity)
            payloads[0]['price']=buy_limit
            payloads[1]['price']=sell_limit
        margin = margin_provider(payloads) if margin_provider else {}
        initial = _num((margin.get("initial") or {}).get("total") if isinstance(margin.get("initial"), dict) else margin.get("initial"))
        final = _num((margin.get("final") or {}).get("total") if isinstance(margin.get("final"), dict) else margin.get("final"))
        eligible = liquid and credit > 0 and gross_loss > 0 and gross_loss <= max_loss_cap
        failures = []
        if not liquid:
            failures.append("Hedge bid/ask, volume, open interest or lot size failed liquidity checks.")
        if credit <= 0:
            failures.append("The spread must receive a positive net credit.")
        if gross_loss <= 0 or gross_loss > max_loss_cap:
            failures.append(f"Maximum loss {gross_loss:,.2f} must be positive and within cap {max_loss_cap:,.2f}.")
        alternatives.append({
            "strategy_type": "BEAR_CALL_SPREAD" if option_type == "CE" else "BULL_PUT_SPREAD",
            "option_type": option_type, "short_symbol": short_symbol, "hedge_symbol": hedge_symbol,
            "expiry": expiry, "short_strike": short_strike, "hedge_strike": _num(hedge.get("strike")),
            "quantity": quantity, "lot_size": lot_size, "short_limit_price": payloads[1]["price"], "hedge_limit_price": payloads[0]["price"],
            "short_bid": short_bid, "short_ask": short_ask, "hedge_bid": bid, "hedge_ask": ask,
            "spread_width": width, "hedge_cost": round(ask * quantity, 2),
            "short_premium": round(short_bid * quantity, 2),
            "net_credit": round(credit * quantity, 2), "net_credit_per_share": round(credit, 2),
            "max_profit": round(gross_profit, 2), "max_loss": round(gross_loss, 2),
            "breakeven": round(short_strike + credit if option_type == "CE" else short_strike - credit, 2), "initial_margin": round(initial, 2),
            "final_margin": round(final, 2), "credit_margin_pct": round(gross_profit / final * 100, 2) if final > 0 else None,
            "liquidity": "PASS" if liquid else "BLOCK", "eligible": eligible,
            "status": "PASS" if eligible else "BLOCK",
            "reason": f"Verified {direction}-strike same-expiry hedge." if eligible else " ".join(failures),
            "order_payloads": payloads,
        })
    return sorted(alternatives, key=lambda row: (not row["eligible"], row.get("max_loss", float("inf")), -(row.get("credit_margin_pct") or 0)))[:3]


def protective_pe_contracts(short_contract, contracts):
    """Compatibility entry point for PE-only callers."""
    return protective_contracts(short_contract, contracts) if str(short_contract.get("instrument_type")).upper() == "PE" else []


def build_protective_pe_spreads(short_contract, contracts, quotes, quantity, **kwargs):
    """Compatibility entry point for PE-only callers."""
    if str(short_contract.get("instrument_type")).upper() != "PE":
        return []
    return build_protective_spreads(short_contract, contracts, quotes, quantity, **kwargs)
