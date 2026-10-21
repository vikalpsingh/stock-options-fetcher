"""HTML view for durable protected executions; rendering makes no broker calls."""
import html
import math


def render_spread_summary(preview, checks=None, *, snapshot=False):
    """One consistent financial summary for the rebuilt review and saved execution."""
    esc = lambda value: html.escape(str(value), quote=True)

    def number(value, prefix="", suffix=""):
        try:
            amount = float(value)
            return f"{prefix}{amount:,.2f}{suffix}" if math.isfinite(amount) else "Unavailable"
        except (ValueError, TypeError):
            return "Unavailable"

    spread = preview if preview.get("strategy_type") else next(
        (row for row in preview.get("hedge_alternatives") or []
         if row.get("hedge_symbol") == preview.get("selected_hedge_symbol")), {}
    )
    blocks = [row for row in checks or [] if row.get("status") == "BLOCK"]
    approved = bool(preview.get("strategy_type")) and not blocks
    title = "Saved spread review" if snapshot else "Revalidated spread" if preview.get("hedge_revalidated") else "Spread review"
    status = "REVIEW SNAPSHOT" if snapshot else "CHECKS PASSED" if approved else "REVIEW BLOCKED"
    strategy = "Bear Call Spread" if spread.get("strategy_type") == "BEAR_CALL_SPREAD" else "Bull Put Spread" if spread.get("strategy_type") else "Select a protective hedge"
    metrics = [
        ("Net credit", number(spread.get("net_credit"), "₹"), "SELL premium − BUY cost", "credit"),
        ("Maximum profit", number(spread.get("max_profit"), "₹"), "At expiry · before charges", "profit"),
        ("Maximum loss", number(spread.get("max_loss"), "₹"), "Defined spread risk · before charges", "loss"),
        ("Spread POP", number(spread.get("spread_pop"), suffix="%"), "Model estimate at breakeven", "pop"),
    ]
    cards = "".join(f'<article class="spread-metric {kind}"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>'
                    for label, value, note, kind in metrics)
    details = [
        ("Breakeven", number(spread.get("breakeven"), "₹")),
        ("Strike width", number(spread.get("spread_width"))),
        ("Quantity", esc(spread.get("quantity") or preview.get("quantity") or "Unavailable")),
        ("Initial margin", number(spread.get("initial_margin"), "₹")),
        ("Final margin", number(spread.get("final_margin"), "₹")),
        ("Return on final margin", number(spread.get("credit_margin_pct"), suffix="%")),
    ]
    detail_html = "".join(f"<div><span>{label}</span><strong>{value}</strong></div>" for label, value in details)
    leg_rows = "".join(
        f'<tr><td><span class="spread-leg {side.lower()}">{side}</span><small>{purpose}</small></td>'
        f'<td><strong>{esc(spread.get(symbol) or "Not selected")}</strong></td>'
        f'<td>{number(spread.get(bid), "₹")}</td><td>{number(spread.get(ask), "₹")}</td>'
        f'<td>{number(spread.get(limit), "₹")}</td><td>{esc(spread.get("quantity") or "—")}</td>'
        f'<td>{number(spread.get(total), "₹")}</td></tr>'
        for side, purpose, symbol, bid, ask, limit, total in [
            ("BUY", "Protective hedge · first", "hedge_symbol", "hedge_bid", "hedge_ask", "hedge_limit_price", "hedge_cost"),
            ("SELL", "After verified hedge fill", "short_symbol", "short_bid", "short_ask", "short_limit_price", "short_premium"),
        ]
    )
    blocker_html = "".join(f'<li><strong>{esc(row.get("name"))}</strong> — {esc(row.get("reason"))}</li>' for row in blocks)
    blockers = f'<div class="spread-blockers"><strong>Resolve before placing orders</strong><ul>{blocker_html}</ul></div>' if blocks else ""
    missing = '<p class="status">A valid spot, implied volatility and positive time to expiry are required for spread POP. No estimate is substituted.</p>' if spread.get("spread_pop") is None else ""
    leg_table = "" if snapshot else f'<div class="table-wrap"><table class="ipo-table spread-leg-table"><thead><tr><th>Leg / sequence</th><th>Verified contract</th><th>Bid</th><th>Ask</th><th>LIMIT</th><th>Qty</th><th>Premium</th></tr></thead><tbody>{leg_rows}</tbody></table></div>'
    return f'''<section class="spread-review-summary" aria-label="Spread financial summary">
      <header><div><span class="spread-eyebrow">{title}</span><h3>{strategy}</h3><p>{esc(preview.get("symbol") or "")} · {esc(spread.get("expiry") or preview.get("expiry") or "")} · {esc(preview.get("mode") or "PAPER")}</p></div><span class="ipo-badge {"neutral" if snapshot else "good" if approved else "bad"}">{status}</span></header>
      <div class="spread-metrics">{cards}</div>
      <div class="spread-details">{detail_html}</div>
      {leg_table}
      {blockers}
      <p class="spread-model-note">Credit and profit exclude brokerage, taxes and slippage. POP is a constant-volatility, risk-neutral expiry estimate using short-option IV at the spread breakeven; it is not a guarantee or historical win rate. Short-leg delta estimate: {number(preview.get("short_leg_pop"), suffix="%")}.</p>
      {missing}<p class="status">{"Saved snapshot; use Reconcile for execution status. Values are not live P&amp;L." if snapshot else "Rebuilt from current quotes and the selected hedge. Changing either leg requires revalidation."} Review time: {esc(preview.get("reviewed_at") or "Unavailable")}.</p>
    </section>'''


def render_hedge_selector(preview):
    """Offer verified contracts even when the automatic spread review is blocked."""
    esc = lambda value: html.escape(str(value), quote=True)
    choices = preview.get("hedge_contract_choices") or []
    selected = str(preview.get("selected_hedge_symbol") or "")
    option_type = "CE" if preview.get("option_type") == "CE" else "PE"
    direction = "higher" if option_type == "CE" else "lower"
    def market_label(row):
        def numeric(value, suffix="", decimals=0):
            try:
                number = float(value)
                return f"{number:,.{decimals}f}{suffix}" if math.isfinite(number) else "Unavailable"
            except (TypeError, ValueError):
                return "Unavailable"
        return f'OTM from spot {numeric(row.get("otm_pct"), "%", 2)} · OI {numeric(row.get("oi"))}'

    default_label = "Default: nearest 4% above SELL strike" if option_type == "CE" else "Automatic nearby hedge selection"
    options = f'<option value="">{default_label}</option>'
    if selected and not any(row["tradingsymbol"] == selected for row in choices):
        options += f'<option value="{esc(selected)}" selected>Unavailable: {esc(selected)}</option>'
    options += "".join(
        f'<option value="{esc(row["tradingsymbol"])}"{" selected" if row["tradingsymbol"] == selected else ""}>'
        f'BUY {esc(row["tradingsymbol"])} · Strike {esc(row["strike"])} · {market_label(row)} · Expiry {esc(row["expiry"])} · Lot {esc(row["lot_size"])}</option>'
        for row in choices
    )
    return f'''<div class="trade-hedge-selection">
      <p>Choose a farther-OTM BUY {option_type} to protect this SELL. Every choice is a verified {direction}-strike contract with the same underlying, expiry and lot size. A wider spread can increase maximum loss.</p>
      <p class="status">OTM % is measured from current spot (negative means ITM). OI is open interest; check bid/ask liquidity as well. {"The default CE cover is the available strike nearest 4% above the SELL strike." if option_type == "CE" else ""}</p>
      <label><span>Protective BUY {option_type}</span><select id="trade-hedge-symbol" name="trade_hedge_symbol">{options}</select></label>
      <button type="submit" class="secondary" name="trade_add_hedge" value="1" formaction="/trade/review" formnovalidate{"" if choices else " disabled"}>Add BUY hedge &amp; revalidate</button>
      <p class="status">{f"No matching protective {option_type} contracts are available in the current Kite instrument master." if not choices else "Selection rebuilds credit, maximum loss, liquidity and margin checks; it does not place an order. After approval and the countdown, only the hedge BUY is submitted. SELL requires verified hedge fills."}</p>
    </div>'''


def render_execution_monitor(rows, account):
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for row in rows:
        preview = row["preview"]
        buy, sell = preview["order_payloads"]
        ready = row["state"] == "HEDGE_FILLED" and row["short_status"] == "NOT_SUBMITTED"
        cards.append(f'''<section class="panel">
          <div class="panel-title">{esc(preview.get("symbol", ""))} · {"Bear Call Spread" if preview.get("strategy_type") == "BEAR_CALL_SPREAD" else "Bull Put Spread"} · {esc(row["mode"])}</div>
          <p><strong>{esc(row["state"])}</strong> · {esc(row["note"])} · Updated {esc(row["updated_at"])}</p>
          {render_spread_summary(preview, snapshot=True)}
          <div class="table-wrap"><table class="ipo-table"><thead><tr><th>Leg</th><th>Contract</th><th>LIMIT</th><th>Filled / Qty</th><th>Status</th><th>Order ID</th></tr></thead><tbody>
          <tr><td>Hedge BUY</td><td>{esc(buy["tradingsymbol"])}</td><td>{buy["price"]:.2f}</td><td>{row["hedge_filled"]} / {buy["quantity"]}</td><td>{esc(row["hedge_status"])}</td><td>{esc(row["hedge_order_id"])}</td></tr>
          <tr><td>Short SELL</td><td>{esc(sell["tradingsymbol"])}</td><td>{sell["price"]:.2f}</td><td>{row["short_filled"]} / {sell["quantity"]}</td><td>{esc(row["short_status"])}</td><td>{esc(row["sell_order_id"])}</td></tr>
          </tbody></table></div>
          <p>Actual hedge average ₹{row["hedge_average_price"]:.2f} · Execution quantities and statuses above are separate from the saved financial review.</p>
          <form method="post" action="/trade/execution/reconcile">
          <input type="hidden" name="kite_profile" value="{esc(account)}">
          <input type="hidden" name="execution_id" value="{esc(row["id"])}">
          <button type="submit">Monitor / Reconcile</button>
          <label><input type="checkbox" name="protected_sell_ack" value="1"> I accept the displayed maximum risk and authorise this SELL limit only after fresh risk checks.</label>
          <button type="submit" formaction="/trade/execution/confirm-sell" {"" if ready else "disabled"}>Confirm SELL</button>
          </form></section>''')
    return '<section id="trade-terminal-panel"><h2>TRADE → EXECUTION</h2><a href="/trade">Back to TRADE</a><p>Monitoring never places orders. PAPER fills are simulated when reconciled. A standalone hedge remains open until managed; unknown submissions must be reconciled, never retried.</p>' + ("".join(cards) or "<p>No protected executions for this account.</p>") + "</section>"
