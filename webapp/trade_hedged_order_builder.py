"""Build verified same-expiry protective bull-put spread alternatives."""

from __future__ import annotations

from typing import Any, Callable


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_protective_pe_spreads(
    short_contract: dict[str, Any], contracts: list[dict[str, Any]], quotes: dict[str, Any],
    quantity: int, *, max_loss_cap: float, margin_provider: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return up to three lower-strike PE hedges, best risk efficiency first."""
    short_symbol = str(short_contract.get("tradingsymbol") or "").upper()
    expiry = str(short_contract.get("expiry") or "")[:10]
    short_strike = _num(short_contract.get("strike"))
    short_quote = quotes.get(f"NFO:{short_symbol}", {}) or {}
    short_depth = short_quote.get("depth") or {}
    short_bid = _num(((short_depth.get("buy") or [{}])[0] or {}).get("price"))
    lot_size = int(_num(short_contract.get("lot_size")))
    if not short_symbol or short_strike <= 0 or short_bid <= 0 or quantity <= 0 or lot_size <= 0 or quantity % lot_size:
        return []
    candidates = sorted(
        [row for row in contracts if str(row.get("instrument_type") or "").upper() == "PE"
         and str(row.get("expiry") or "")[:10] == expiry and 0 < _num(row.get("strike")) < short_strike],
        key=lambda row: short_strike - _num(row.get("strike")),
    )[:6]
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
        width = short_strike - _num(hedge.get("strike"))
        credit = short_bid - ask
        gross_profit = credit * quantity
        gross_loss = max(0.0, (width - credit) * quantity)
        payloads = [
            {"exchange": "NFO", "tradingsymbol": hedge_symbol, "transaction_type": "BUY", "quantity": quantity, "product": "NRML", "order_type": "LIMIT", "price": ask, "variety": "regular", "validity": "DAY"},
            {"exchange": "NFO", "tradingsymbol": short_symbol, "transaction_type": "SELL", "quantity": quantity, "product": "NRML", "order_type": "LIMIT", "price": short_bid, "variety": "regular", "validity": "DAY"},
        ]
        margin = margin_provider(payloads) if margin_provider else {}
        initial = _num((margin.get("initial") or {}).get("total") if isinstance(margin.get("initial"), dict) else margin.get("initial"))
        final = _num((margin.get("final") or {}).get("total") if isinstance(margin.get("final"), dict) else margin.get("final"))
        eligible = liquid and credit > 0 and gross_loss > 0 and gross_loss <= max_loss_cap
        alternatives.append({
            "strategy_type": "BULL_PUT_SPREAD", "short_symbol": short_symbol, "hedge_symbol": hedge_symbol,
            "expiry": expiry, "short_strike": short_strike, "hedge_strike": _num(hedge.get("strike")),
            "quantity": quantity, "lot_size": lot_size, "short_limit_price": short_bid, "hedge_limit_price": ask,
            "net_credit": round(credit * quantity, 2), "net_credit_per_share": round(credit, 2),
            "max_profit": round(gross_profit, 2), "max_loss": round(gross_loss, 2),
            "breakeven": round(short_strike - credit, 2), "initial_margin": round(initial, 2),
            "final_margin": round(final, 2), "credit_margin_pct": round(gross_profit / final * 100, 2) if final > 0 else None,
            "liquidity": "PASS" if liquid else "BLOCK", "eligible": eligible,
            "status": "PASS" if eligible else "BLOCK",
            "reason": "Verified lower-strike same-expiry hedge." if eligible else "Credit, liquidity, lot size or maximum-loss control failed.",
            "order_payloads": payloads,
        })
    return sorted(alternatives, key=lambda row: (not row["eligible"], row["max_loss"], -(row["credit_margin_pct"] or 0)))[:3]
