"""Escaped server-rendered execution window. No automatic order submission."""
from html import escape
from datetime import datetime, timezone
from .ticket import number


def e(value):
    return escape(str(value if value is not None else ''), quote=True)


def money(value):
    return 'UNKNOWN' if value is None else f'₹{value:,.2f}'


def get_day_change_color(change_pct):
    """Continuous user-requested day-change palette; missing data stays neutral."""
    value = number(change_pct)
    stops = [(-80, '#7F1D1D'), (-40, '#DC2626'), (-20, '#FCA5A5'),
             (0, '#9CA3AF'), (20, '#86EFAC'), (40, '#22C55E'),
             (80, '#15803D'), (100, '#14532D')]
    if value is None:
        return '#9CA3AF'
    value = max(-80, min(100, value))
    for (lo, left), (hi, right) in zip(stops, stops[1:]):
        if lo <= value <= hi:
            fraction = (value-lo)/(hi-lo)
            channels = [round(int(left[i:i+2],16)*(1-fraction)+int(right[i:i+2],16)*fraction)
                        for i in (1,3,5)]
            return '#' + ''.join(f'{channel:02X}' for channel in channels)


def day_change_badge(quote):
    last = number(quote.get('last_price'))
    close = number((quote.get('ohlc') or {}).get('close'))
    change = last-close if last is not None and close is not None and close > 0 else None
    pct = change/close*100 if change is not None else None
    color = get_day_change_color(pct)
    channels = [int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear = [x/12.92 if x <= .04045 else ((x+.055)/1.055)**2.4 for x in channels]
    luminance = sum(x*w for x,w in zip(linear, (.2126,.7152,.0722)))
    foreground = '#000000' if luminance > .179 else '#FFFFFF'
    text = 'N/A' if pct is None else f'{change:+.2f} ({pct:+.2f}%)'
    return f'<span class="day-change" style="background:{color};color:{foreground};padding:3px 7px;border-radius:4px">Today {e(text)}</span>'


def contract_border_class(action, quote):
    last = number(quote.get('last_price'))
    close = number((quote.get('ohlc') or {}).get('close'))
    if last is None or close is None or close <= 0 or last == close:
        return 'contract-neutral'
    favorable = (last > close) if action == 'SELL' else (last < close)
    return 'contract-green' if favorable else 'contract-red'


def contract_quote(quote):
    last = number(quote.get('last_price'))
    from app_time import to_ist
    try:
        stamp = to_ist(quote.get('timestamp')).strftime('%d %b %Y %H:%M:%S IST')
    except (ValueError, TypeError):
        stamp = 'Unavailable'
    return f'<div class="contract-quote"><b>LTP {e(money(last))}</b>{day_change_badge(quote)}<small>vs previous close · Quote: {e(stamp)}</small></div>'


def ticket_risk_header(saved):
    risk = saved.get('risk') or {}
    passed = saved.get('eligible') is True and risk.get('risk_status')=='PASS'
    values = [('MAX LOSS CAP',risk.get('risk_cap')),('NEW ORDER MAX LOSS',saved.get('max_loss')),
              ('TOTAL AFTER ORDER',risk.get('projected_portfolio_max_loss')),('CAP REMAINING',risk.get('risk_remaining'))]
    result = '<div class="ticket-mindset">The objective today is not to recover yesterday’s loss. The objective is to execute the next valid setup correctly.</div><p class="ticket-intro">Simple defined-risk execution: choose PE spread, CE spread, or both. BUY hedges go first; SELL requires verified hedge fills and renewed approval.</p><h3 class="risk-heading">Risk</h3><div class="risk-grid">'
    for label,value in values:
        result += f'<div class="risk-cell"><small>{label}</small><strong>{e(money(value) if value is not None else "UNKNOWN / UNCAPPED")}</strong></div>'
    result += f'<div class="risk-cell"><small>STATUS</small><strong class="risk-{"pass" if passed else "fail"}">{"PASS" if passed else "FAIL"}</strong></div></div>'
    if not passed:
        reasons = [check['name'] for check in saved.get('checks',[]) if check.get('status')=='BLOCK']
        result += '<p class="risk-banner">FAIL: order cannot be placed. '+e(', '.join(reasons or risk.get('hard_block_reasons') or ['Risk verification required']))+'</p>'
    result += '<div class="spread-choices">'
    for kind in ('PE','CE'):
        selected = bool((saved.get('selection') or {}).get('include_'+kind.lower()))
        result += f'<div class="spread-choice {"selected" if selected else ""}"><input type="checkbox" disabled {"checked" if selected else ""}><div><b>{kind} spread</b><p>BUY {kind} hedge + SELL {kind} short</p></div></div>'
    result += '<div class="spread-choice selected"><input type="checkbox" checked disabled><div><b>BUY hedge</b><p>Required before SELL short</p></div></div></div><div class="coverage"><b>Hedge Coverage</b><p>Owned, confirmed BUY fills are required. Unverified existing positions are not reused. Change the spread selection on the page and create a new review.</p></div>'
    return result


def saved_ticket_details(saved):
    margin = saved.get('broker_margin')
    profit = saved.get('net_max_profit')
    rom = f'{profit / margin * 100:.2f}%' if margin and profit is not None else 'UNKNOWN'
    legs = saved.get('legs') or []
    qty = legs[0].get('quantity') if legs else None
    lots = (saved.get('selection') or {}).get('lots')
    metrics = [('Expiry', saved.get('expiry')), ('NIFTY spot', saved.get('spot')),
               ('Lots / quantity', f'{lots} / {qty}'), ('Net credit', money(saved.get('net_credit'))),
               ('Net maximum gain', money(profit)), ('Estimated margin', money(margin)),
               ('Estimated costs', money(saved.get('estimated_fees'))),
               ('Projected portfolio loss', money((saved.get('risk') or {}).get('projected_portfolio_max_loss'))),
               ('Return on margin (estimated)', rom), ('Maximum loss incl. costs', money(saved.get('max_loss')))]
    result = '<div class="metrics">' + ''.join(f'<div class="metric"><small>{e(label)}</small><strong>{e(value)}</strong></div>' for label,value in metrics) + '</div>'
    display = saved.get('display_legs') or legs
    result += '<table class="ticket-legs"><thead><tr><th>Selected / Leg</th><th>Contract</th><th>Lots / Qty</th><th>LTP / Day change</th><th>Bid / Ask</th></tr></thead><tbody>'
    for leg in display:
        selected = leg.get('selected', True)
        quote = leg.get('reviewed_quote') or {}
        result += f'<tr class="{"" if selected else "inactive-leg"}"><td><input type="checkbox" disabled {"checked" if selected else ""}> {e(leg["transaction_type"])} {e(leg.get("option_type"))}</td><td>{e(leg["tradingsymbol"])}<br>{e(leg.get("strike"))} · {e(leg.get("expiry"))}</td><td>{e(leg.get("lots",lots))} lots / {e(leg.get("quantity"))}</td><td>{money(number(quote.get("last_price")))}<br>{day_change_badge(quote)}</td><td>{money(leg.get("bid"))} / {money(leg.get("ask"))}</td></tr>'
    result += '</tbody></table>'
    return result + '<p>Hedge coverage: BUY fills must be verified before any short SELL. POP: unavailable until a validated model is connected.</p>'


def execution_guidance(record):
    state = record['state']
    if state == 'RECOVERY_READY':
        has_shorts = any(leg['filled'] for leg in record['legs']
                         if leg['payload']['transaction_type'] == 'SELL')
        return ('Entry stopped. All submitted entry orders are terminal. Close only the filled short quantity first; keep hedges until closure is verified.'
                if has_shorts else 'Entry stopped. All submitted entry orders are terminal. No short fills remain; close the owned BUY fills as orphan hedges.')
    if state == 'CLOSED' and not any(leg['filled'] for leg in record['legs']):
        return 'Entry ended without fills. No position was opened.'
    return {
        'REVIEW': 'Review saved risk, wait for the countdown, then explicitly confirm BUY submission.',
        'HEDGE_PENDING': 'A BUY receipt is not a fill. Reconcile broker orders and trades before SELL.',
        'HEDGE_PARTIAL': 'Hedge is partially filled. SELL and cleanup remain blocked while entry orders are pending.',
        'HEDGE_FILLED': 'Hedges are verified filled. Renew risk approval before SELL, or close the unused hedge.',
        'SHORT_PENDING': 'SELL is pending. Reconcile before continuing; do not resubmit an existing order.',
        'SHORT_PARTIAL': 'Keep protective hedges. Pending entry orders must finish or be confirmed terminal before cleanup.',
        'OPEN': 'Entry fills are verified. Close shorts first while retaining protective hedges.',
        'EXIT_PENDING': 'Reconcile exit fills. No automatic retry or hedge disposal is allowed.',
        'EXIT_RECOVERY_READY': 'Previous exits are terminal. Explicitly confirm closing only the remaining short quantity at fresh prices; retain hedges until fills are verified.',
        'PARTIALLY_CLOSED': 'Exit is partially filled. Keep protection and reconcile remaining quantities.',
        'SHORT_CLOSED_HEDGE_OPEN': 'Short closures are verified. Separately confirm closure of remaining owned hedges.',
        'RECONCILIATION_REQUIRED': 'Order identity or fills are uncertain. Reconcile broker evidence; never retry blindly.',
        'CLOSED': 'Recorded positions are closed. Review charges and strategy P&L below.',
    }.get(state, 'Reconcile execution before continuing.')


def active_positions_section(data):
    """One broker snapshot, one positions table, existing ticket for linked exits."""
    from datetime import date
    positions = (data.get('active_positions') or {}).get('positions', [])
    context = data['context']
    mode = data['selection']['mode']
    result = '<section id="active-positions"><h2>NIFTY Active Positions &amp; Management</h2>'
    result += '<p>'+e(mode)+' positions · Suggested matches reserve quantity but need confirmed ownership before new short exposure.</p>'
    mtms = [number(row.get('unrealised')) for row in positions]
    total = sum(mtms) if all(value is not None for value in mtms) else None
    expiries = sorted(row['expiry'] for row in positions if row.get('expiry'))
    metrics = [('Active positions',len(positions)), ('Current open MTM',money(total)),
        ('Confirmed protected qty',sum(row['confirmed_hedge_qty'] for row in positions)),
        ('Unmatched short qty',sum(row['unmatched_short_qty'] for row in positions)),
        ('Available long qty',sum(row['free_long_qty'] for row in positions)),
        ('Current defined max risk',money(data['risk']['current_defined_max_loss'])),
        ('Risk cap',money(data['config']['max_total_nifty_defined_loss_inr'])),
        ('Next expiry',expiries[0] if expiries else 'None')]
    result += '<div class="metrics">'+''.join(f'<div class="metric"><small>{e(k)}</small><strong>{e(v)}</strong></div>' for k,v in metrics)+'</div>'
    result += '<h3>All positions</h3><table class="positions-table"><thead><tr>'
    for label,css in [('Symbol',''),('Side',''),('Qty',''),('Lots','detail'),('Avg / LTP','detail'),('Day %','detail'),('P&L',''),('Expiry / DTE','detail'),('Hedge status',''),('Available qty','detail'),('Action','')]:
        result += f'<th class="{css}">{label}</th>'
    result += '</tr></thead><tbody>'
    dialogs = ''
    for index,row in enumerate(positions):
        symbol, qty = row['tradingsymbol'],row['quantity']
        quote = context['quotes'].get('NFO:'+symbol) or {}
        pnl = number(row.get('pnl'))
        lot = number(row.get('lot_size'))
        lots = abs(qty)/lot if lot and lot>0 else 'UNKNOWN'
        try:
            dte = (date.fromisoformat(row['expiry'])-context['now'].date()).days
        except ValueError:
            dte = 'UNKNOWN'
        status = row['hedge_status']
        tone = 'block' if status in {'UNHEDGED_SHORT','UNKNOWN'} else 'partial' if status in {'PARTIALLY_HEDGED','SUGGESTED_HEDGE_MATCH'} else 'pass'
        values = [(symbol,''),('BUY' if qty>0 else 'SELL',''),(qty,''),(lots,'detail'),
            (money(number(row.get('average_price')))+' / '+money(number(quote.get('last_price'))),'detail')]
        result += '<tr>'+''.join(f'<td class="{css}">{e(value)}</td>' for value,css in values)
        result += f'<td class="detail">{day_change_badge(quote)}</td><td class="{"block" if pnl is not None and pnl<0 else "pass"}">{money(pnl)}</td><td class="detail">{e(row["expiry"])} / {e(dte)}</td><td class="{tone}">{e(status.replace("_"," "))}</td><td class="detail">{e(row["free_long_qty"] if qty>0 else row["unmatched_short_qty"])}</td><td><button type="button" data-open-execution="position-{index}">Manage</button></td></tr>'
        dialogs += f'<article hidden id="execution-position-{index}" data-position-management="true"><h3>{e(symbol)}</h3><p>{"BUY" if qty>0 else "SELL"} · Qty {e(qty)} · Average {money(number(row.get("average_price")))} · P&amp;L {money(pnl)} · Strike {e(row["strike"])} · Expiry {e(row["expiry"])} · DTE {e(dte)}</p>{contract_quote(quote)}<p>{e(status)} · Confirmed protection {e(row["confirmed_hedge_qty"])} · Suggested protection {e(row["suggested_hedge_qty"])} · Unmatched short {e(row["unmatched_short_qty"])} · Free long {e(row["free_long_qty"])}</p>'
        if row['suggested_matches']:
            dialogs += '<p class="partial">Suggested Hedge Match — ownership confirmation is required. These quantities are reserved and cannot support an additional SELL.</p>'
        if qty>0 and not row['free_long_qty']:
            dialogs += '<p>This long is reserved or already protects short exposure. Sell Against Long and independent hedge disposal are blocked.</p>'
        if qty<0:
            avg = number(row.get('average_price'))
            dialogs += '<p>20% short-premium capture target: '+money(avg*.8 if avg is not None else None)+'. Existing close orders must be reconciled before submitting.</p>'
            dialogs += '<p>Suggested repair quantity: '+e(row['unmatched_short_qty'])+' at the same expiry, default 300-point protective width. Suggested matches require confirmation first.</p>'
        from .analytics import position_close_preview
        close = position_close_preview(row, quote, context.get('orders') or [], context['now'])
        dialogs += '<h4>Close preview — estimate only</h4><p>'+e(close['side'] or 'UNKNOWN')+' close · Qty '+e(close['quantity'])+' · Executable reference '+money(close['price'])+'</p>'
        dialogs += '<p>Estimated Order Cash Flow: '+money(close['cash_flow'])+' · Estimated Realised P&amp;L on Close (before fees): '+money(close['estimated_realised_gross'])+'</p>'
        if close['blockers']:
            dialogs += '<p class="block">'+e(' '.join(close['blockers']))+'</p>'
        dialogs += '<p>Estimates do not change realised P&amp;L. Final execution refreshes positions, orders, quotes and ownership.</p>'
        linked = [r for r in data['executions'] if r['mode']==mode and r['state'] not in {'CLOSED','REVIEW'} and any(leg['payload']['tradingsymbol']==symbol for leg in r['legs'])]
        for record in linked:
            dialogs += f'<button type="button" data-linked-execution="{e(record["id"])}">Manage Spread / Close using verified fills</button>'
        if not linked:
            dialogs += '<p>No durable execution record is linked. Position import/allocation confirmation is required before this window can safely submit contract actions.</p>'
        dialogs += '<p>Opening-order proceeds are cash flow, not realised profit. Closing P&amp;L uses entry cost and confirmed exit fills.</p></article>'
    result += '</tbody></table>'
    if not positions:
        result += '<p>No open positions in this execution mode.</p>'
    result += '<details><summary>Grouped strategies / hedge matches</summary><ul>'
    for match in (data.get('active_positions') or {}).get('matches',[]):
        result += '<li>'+e(f"{match['short_symbol']} + {match['long_symbol']} · {match['quantity']} qty · "+('Confirmed' if match['confirmed'] else 'Suggested Hedge Match'))+'</li>'
    return result+'</ul></details>'+dialogs+'</section>'


def nearer_liquidity_form(data):
    selection = data.get('selection') or {}
    alternatives = data.get('nearer_alternatives') or {}
    result = '<details><summary>Review liquid strikes closer to NIFTY CMP</summary><p>Moving closer to spot increases short-option exposure. Choose a pair explicitly, then review refreshed credit, risk and quantity. Listed 100-point strikes only; same-expiry protective hedge retained.</p>'
    for side in ('PE','CE'):
        if not selection.get('include_'+side.lower()):
            continue
        candidates = alternatives.get(side,[])
        if not candidates:
            result += '<p>'+side+': No verified liquid pair closer to spot within 500 points. Refresh quotes or reduce lots.</p>'
        for candidate in candidates:
            fields = dict(selection)
            fields['structure'] = 'BOTH' if selection.get('include_pe') and selection.get('include_ce') else side
            fields['short_'+side.lower()] = candidate['short']
            fields['hedge_'+side.lower()] = candidate['hedge']
            result += '<form method="post" action="/nifty-2/preview">'
            for key,value in fields.items():
                if key not in {'include_pe','include_ce'}:
                    result += f'<input type="hidden" name="{e(key)}" value="{e(value)}">'
            result += f'<button>Review {e(candidate["short"])} + {e(candidate["hedge"])}</button></form>'
    return result+'</details>'


def render_page(data=None, error='', message='', review=None, test_mode=False, account_name=''):
    data = data or {}
    account = data.get('account', account_name)
    body = ''
    if data:
        selection, ticket, context = data['selection'], data['ticket'], data['context']
        risk, analytics = data['risk'], data['analytics']
        def card(label, value):
            return f'<div class="metric"><small>{e(label)}</small><strong>{e(value)}</strong></div>'
        body += '<section><h2>Market &amp; risk</h2><div class="metrics">'
        for label, value in [('NIFTY spot', context.get('spot')), ('India VIX', context.get('vix')),
                             ('Portfolio max loss', money(risk['current_defined_max_loss'])),
                             ('Risk remaining', money(risk['risk_remaining'])),
                             ('Loss cap', money(data['config']['max_total_nifty_defined_loss_inr'])),
                             ('Monthly guard', (context.get('monthly') or {}).get('risk_state', 'UNKNOWN'))]:
            body += card(label, value)
        body += f'</div><p>Data refreshed {e(__import__('app_time').to_ist(context["now"]).strftime('%d %b %Y %H:%M:%S IST'))}. Mode: <b>{e(selection["mode"])}</b>.</p></section>'
        body += '<section><h2>New protected trade</h2><p>Choose contracts, refresh the preview, then save a review. Changing a ticket requires a new review.</p><form method="post" action="/nifty-2/preview"><div class="fields">'
        def select(name, label, choices, value):
            return f'<label>{e(label)}<select name="{e(name)}">' + ''.join(
                f'<option value="{e(key)}" {"selected" if str(key)==str(value) else ""}>{e(text)}</option>' for key, text in choices) + '</select></label>'
        structure = 'BOTH' if selection['include_pe'] and selection['include_ce'] else 'CE' if selection['include_ce'] else 'PE'
        body += select('structure', 'Strategy', [('PE','PE credit spread'), ('CE','CE credit spread'), ('BOTH','Iron condor')], structure)
        body += select('mode', 'Execution mode', [('PAPER','PAPER · simulated fills'), ('LIVE','LIVE · real broker orders')], selection['mode'])
        body += select('expiry', 'Expiry', [(x,x) for x in data['expiries']], selection['expiry'])
        body += '<fieldset><legend>Lots</legend>' + ''.join(
            f'<label><input type="radio" name="lots" value="{n}" {"checked" if str(n)==str(selection["lots"]) else ""} required>{n}</label>'
            for n in data['config'].get('allowed_lots', [1,2,3,4]) if n <= data['config']['maximum_lots_per_new_trade']) + '</fieldset>'
        body += '</div>'
        for kind in ('PE','CE'):
            body += f'<div class="spread-row"><h4>{kind} SELL + protective BUY</h4>'
            contracts = [row for row in data['instruments'] if row['instrument_type']==kind and str(row['expiry'])[:10]==selection['expiry']]
            choices = []
            for row in contracts:
                spot = float(context.get('spot') or 0)
                otm = ((spot-float(row['strike'])) if kind=='PE' else (float(row['strike'])-spot))/spot*100 if spot else 0
                choices.append((row['tradingsymbol'], f'{row["strike"]:g} {kind} · {otm:.1f}% OTM · lot {row["lot_size"]}'))
            for prefix, label in [('short_', 'SELL'), ('hedge_', 'Protective BUY')]:
                symbol = selection[prefix+kind.lower()]
                quote = context['quotes'].get('NFO:'+symbol) or {}
                action = 'SELL' if prefix=='short_' else 'BUY'
                border = contract_border_class(action, quote)
                body += f'<div class="contract-card {border}">' + select(prefix+kind.lower(), label+' '+kind, choices, symbol)
                body += contract_quote(quote) + '</div>'
            for candidate in (data.get('liquid_alternatives') or {}).get(kind, []):
                body += f'<button type="button" data-liquid-side="{kind.lower()}" data-short="{e(candidate["short"])}" data-hedge="{e(candidate["hedge"])}">Review liquid pair: {e(candidate["short"])} + {e(candidate["hedge"])}</button>'
            body += '</div>'
        body += '<div class="actions"><button>Refresh preview / expiry contracts</button><button formaction="/nifty-2/review">Save order review</button><button formaction="/nifty-2/review" name="open_ticket" value="yes">EXECUTE</button><button formaction="/nifty-2/save-mode">Save mode for today</button></div></form><div class="metrics">'
        for label, value in [('Executable credit',ticket['net_credit']), ('Estimated costs',ticket['estimated_fees']), ('Net max profit',ticket['net_max_profit']), ('Max loss incl. costs',ticket['max_loss']), ('Projected portfolio loss',ticket['risk']['projected_portfolio_max_loss']), ('Broker margin',ticket['broker_margin'])]:
            body += card(label,money(value))
        body += '</div><p>Saved mode for today: <b>'+e(data.get('saved_day_mode', 'PAPER'))+'</b>. Resets to PAPER at midnight IST; LIVE permission and confirmations remain required.</p>'
        sizing = data.get('lot_recommendation') or {}
        if sizing:
            body += '<p>Maximum lots within risk cap: <b>'+e(sizing['recommended_lots'] or 'None')+'</b>. Selection is unchanged; liquidity, margin and other checks still apply.</p><ul>'
            for n, loss in sizing['projected_max_loss_by_lots'].items():
                budget = sizing['remaining_risk_budget'][n]
                status = 'PASS' if n in sizing['allowed_lots'] else 'BLOCK'
                body += f'<li>{n} lots: {status} · Projected loss {e(money(loss))} · Remaining budget {e(money(budget))}</li>'
            body += '</ul>'
        remaining = ticket['risk'].get('risk_remaining')
        if remaining is not None and remaining < 0:
            body += '<p role="alert">Cap shortfall: '+e(money(-remaining))+'. Select fewer lots and review again. GO is disabled.</p>'
        body += '<h3>'+('READY FOR REVIEW' if ticket['eligible'] else 'PREVIEW ONLY — resolve blocks')+'</h3><ul class="checks">'
        for check in ticket['checks']:
            body += f'<li class="{e(check["status"].lower())}"><b>{e(check["status"])} · {e(check["name"])}</b> — {e(check["reason"])}</li>'
        body += '</ul>' + nearer_liquidity_form(data) + '<p>Portfolio checks govern new entries only. P&amp;L and position review remain available when entry risk is blocked.</p><p>POP is unavailable: no validated probability model is connected. Risk uses executable bid/ask and current master quantity.</p></section>'
        body += active_positions_section(data)
        body += '<section id="execution"><h2>Execution window</h2><p>GO submits protective BUY legs only. Reconcile fills, then explicitly approve SELL using fresh risk checks. LIVE sends real LIMIT orders to the broker only after explicit acknowledgement and fresh approval.</p>'
        records = data['executions']
        if not records:
            body += '<p>No saved executions. Save an eligible ticket review above.</p>'
        for record in records[:30]:
            saved = record['preview']
            body += f'<p role="status"><strong>Next step:</strong> {e(execution_guidance(record))}</p>'
            body += f'<button type="button" data-open-execution="{e(record["id"])}">OPEN NIFTY ORDER TICKET</button>'
            body += f'<article id="execution-{e(record["id"])}"><h3>{e(saved.get("strategy_type"))} · {e(record["mode"])} · {e(record["state"])}</h3><p>Execution {e(record["id"])} · Strategy {e(record.get("strategy_id", "pending"))}</p>'
            body += ticket_risk_header(saved)
            body += saved_ticket_details(saved)
            if record['state']=='REVIEW':
                reviewed_selection = saved.get('selection') or {}
                reviewed_structure = 'BOTH' if reviewed_selection.get('include_pe') and reviewed_selection.get('include_ce') else 'CE' if reviewed_selection.get('include_ce') else 'PE'
                body += '<form method="post" action="/nifty-2/review"><input type="hidden" name="open_ticket" value="yes">'
                for key,value in {**reviewed_selection,'structure':reviewed_structure}.items():
                    body += f'<input type="hidden" name="{e(key)}" value="{e(value)}">'
                body += '<button class="refresh-ticket">Refresh details</button></form>'

            body += '<details><summary>Saved review checks</summary><ul>' + ''.join(
                '<li>'+e(check['status'])+' · '+e(check['name'])+': '+e(check['reason'])+'</li>'
                for check in saved.get('checks', [])) + '</ul></details>'
            body += '<table><thead><tr><th>Stage</th><th>Side / contract</th><th>Filled / quantity</th><th>Average</th><th>Status / order ID</th></tr></thead><tbody>'
            for stage, legs in [('ENTRY',record['legs']),('EXIT',record.get('exit_legs',[]))]:
                for leg in legs:
                    p = leg['payload']
                    body += f'<tr><td>{stage}</td><td>{e(p["transaction_type"])} {e(p["tradingsymbol"])}</td><td>{e(leg["filled"])} / {e(p["quantity"])}</td><td>{money(leg["average"])}</td><td>{e(leg["status"])}<br>{e(leg["order_id"])}</td></tr>'
            body += f'</tbody></table><p>{e(record.get("note"))}</p>'
            if record['mode'] in {'PAPER', 'LIVE'}:
                body += f'<form method="post"><input type="hidden" name="open_ticket" value="yes"><input type="hidden" name="execution_id" value="{e(record["id"])}"><label class="ack"><input type="checkbox" name="ack" value="yes"> I accept the shown maximum loss and the selected execution action.</label><div class="actions">'
                if record['mode'] == 'LIVE':
                    body += '<label>Type PLACE LIVE ORDERS for any submission<input name="live_ack" autocomplete="off" placeholder="PLACE LIVE ORDERS"></label>'
                state = record['state']
                if state == 'REVIEW':
                    remaining = max(0, data['config']['countdown_seconds'] - (datetime.now(timezone.utc)-datetime.fromisoformat(record['reviewed_at'])).total_seconds())
                    body += f'<button formaction="/nifty-2/start" data-countdown="{int(remaining)+1}" disabled>GO · submit BUY hedges</button>'
                else:
                    body += '<button formaction="/nifty-2/reconcile">Reconcile fills</button>'
                if state in {'HEDGE_FILLED','SHORT_PENDING','SHORT_PARTIAL'}:
                    body += '<button formaction="/nifty-2/confirm-sell">Revalidate risk &amp; submit unsent SELL</button>'
                if state in {'OPEN','HEDGE_FILLED','RECOVERY_READY','EXIT_RECOVERY_READY'}:
                    has_shorts = any(leg['filled'] for leg in record['legs'] if leg['payload']['transaction_type']=='SELL')
                    body += '<button formaction="/nifty-2/close-shorts">'+('Close shorts first' if has_shorts else 'Close orphan hedge')+'</button>'
                if state == 'SHORT_CLOSED_HEDGE_OPEN':
                    body += '<button formaction="/nifty-2/close-hedges">Close remaining hedges</button>'
                body += '</div></form>'
            body += '</article>'
        body += '</section><section><h2>Monthly performance</h2><p>Saved NIFTY 2.0 strategy ledger only; not the complete broker account. PAPER fees are simulated as zero. Unknown LIVE charges remain unknown. Incomplete-entry cleanup P&amp;L is included, but these attempts are excluded from completed-spread win rates and scaling samples.</p>'
        body += f'<form method="get" action="/nifty-2"><label>Month<input type="month" name="month" value="{e(analytics["month"])}" required></label><input type="hidden" name="mode" value="{e(selection["mode"])}"><button>Show month</button></form><div class="metrics">'
        for label, key in [('Realised gross','realised_gross'),('Charges','fees'),('Realised net','realised_net'),('Current open MTM','open_mtm'),('Total net','total_net')]:
            body += card(label,money(analytics[key]))
        for label,key in [('Completed spreads','completed'),('Verified winners','winners'),('Verified losers','losers'),('Win rate %','win_rate'),('Profit factor','profit_factor'),('Expectancy','expectancy')]:
            body += card(label, analytics['stats'][key] if analytics['stats'][key] is not None else 'UNKNOWN')
        body += '</div><h3>'+e(analytics['scale_status'])+'</h3><p>'+e(analytics['scale_reason'])+'</p><table><tr><th>Strategy</th><th>Status</th><th>Gross realised</th><th>Hedge entry cost</th><th>Net realised</th><th>Open MTM</th></tr>'
        for row in analytics['rows']:
            body += f'<tr><td>{e(row["strategy_type"])}<br>{e(row["strategy_id"])}</td><td>{e(row["status"])}</td><td>{money(row["realised_gross"])}</td><td>{money(row["hedge_cost"])}</td><td>{money(row["realised_net"])}</td><td>{money(row["open_mtm"])}</td></tr>'
        body += '</table><h3>Daily realised results</h3><table><tr><th>Date</th><th>Gross realised</th><th>Known charges</th><th>Net realised</th></tr>'
        for day in analytics['daily']:
            body += f'<tr><td>{e(day["day"])}</td><td>{money(day["gross"])}</td><td>{money(day["known_fees"])}</td><td>{money(day["net"])}</td></tr>'
        body += '</table></section>'
        body += '<section><h2>LIVE permission</h2><p>Default is disabled. Enable only to allow reviewed real LIMIT orders. Kite Setup live acknowledgement and all risk checks must also pass. Localhost TEST never sends LIVE orders.</p><form method="post" action="/nifty-2/live-settings">'
        body += f'<label class="ack"><input type="checkbox" name="live_enabled" value="yes" {"checked" if data["config"]["live_enabled"] else ""}> Enable Nifty Income LIVE entries</label>'
        body += '<label class="ack"><input type="checkbox" name="settings_ack" value="yes" required> I confirm this permission change.</label><button>Save LIVE permission</button></form></section>'
    target = data.get('open_execution', '')
    popup_error = f'<p role="alert" class="error">{e(error)}</p>' if error else ''
    blocked = ''
    if data.get('open_ticket') and not target:
        blocked = ticket_risk_header(data.get('ticket') or {}) + '<p>Order review is blocked. No order was submitted.</p><ul>' + ''.join(
            '<li>'+e(check['name'])+': '+e(check['reason'])+'</li>'
            for check in (data.get('ticket') or {}).get('checks', []) if check['status']=='BLOCK') + '</ul>'
    if data.get('open_ticket') and not target:
        blocked += nearer_liquidity_form(data)
    body += f'<dialog id="order-ticket" aria-labelledby="ticket-title" data-auto="{str(bool(data.get("open_ticket"))).lower()}" data-execution="{e(target)}"><header><h2 id="ticket-title">NIFTY Order Ticket</h2><button type="button" id="close-ticket" aria-label="Close ticket">×</button></header>{popup_error}{blocked}<div id="ticket-content"></div><footer class="ticket-footer"><button type="button" id="ticket-cancel">Cancel</button><button type="button" id="ticket-refresh">Refresh details</button><button type="button" id="ticket-review">Review &amp; Start 10s</button><button type="button" id="ticket-go" disabled>GO</button></footer></dialog>'
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nifty 2.0 · Income Desk</title><style>
.spread-row{display:grid;grid-template-columns:1fr 1fr;gap:18px;border:1px solid #d7e1eb;border-radius:8px;padding:16px;margin:14px 0}.spread-row h4{grid-column:1/-1;margin:0}.contract-quote{display:flex;flex-wrap:wrap;gap:8px 16px;margin-top:10px}.contract-quote small{width:100%}@media(max-width:650px){.spread-row{grid-template-columns:1fr}}dialog{width:min(1100px,92vw);max-height:88vh;overflow:auto;border:1px solid #afbfce;border-radius:12px;padding:24px}dialog::backdrop{background:#102439aa}dialog header{display:flex;align-items:center;justify-content:space-between;gap:20px}body{margin:0;background:#f3f6fa;color:#15283d;font:15px system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:24px}nav{display:flex;gap:20px;padding:16px 24px;background:#142b43}nav a{color:white;text-decoration:none}nav .active{border-bottom:3px solid #57d5bd}h1{margin-bottom:8px}h2{font-size:21px}section{background:white;border:1px solid #d7e1eb;border-radius:12px;padding:22px;margin:20px 0}.metrics,.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:14px}.metric{background:#f3f7fb;padding:14px;border-radius:8px}.metric small{display:block;color:#52677b}.metric strong{display:block;font-size:22px;margin-top:8px}label{display:block;font-weight:600}input,select,button{box-sizing:border-box;padding:10px;border:1px solid #afbfce;border-radius:6px;font:inherit}label select,label input{display:block;width:100%;margin-top:6px}button{background:#163e63;color:white;cursor:pointer}button:disabled{opacity:.5;cursor:wait}.actions{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.ack input{display:inline;width:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:12px;border-bottom:1px solid #dce4ec}article{border:1px solid #cddae5;border-radius:8px;padding:16px;margin:16px 0;overflow:auto}.block,.error{color:#9b2431}.error{padding:16px;background:#fff0f0}.pass{color:#216148}.checks{padding-left:20px;line-height:1.8}p{line-height:1.6;color:#53677b}@media(max-width:650px){main{padding:10px}section{padding:14px}table{min-width:600px}section{overflow:auto}}
#order-ticket{width:min(810px,94vw);padding:24px 14px 0;border:0;border-radius:14px}#order-ticket header{justify-content:center;position:relative}#ticket-title{font-size:28px;margin:8px 0 24px}#close-ticket{position:absolute;right:0;top:0;background:transparent;color:#405166;border:0}#order-ticket article{border:0;padding:0;margin:0;overflow:visible}#order-ticket article>h3,#order-ticket article>h3+p{font-size:12px;color:#60718b}.ticket-mindset{background:#eff6ff;border:1px solid #8db8ff;border-radius:10px;padding:14px 18px;color:#244493;text-align:center;font-weight:750}.ticket-intro{text-align:center;font-size:14px}.risk-heading{text-align:center;font-size:15px;color:#008679}.risk-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.risk-cell{border:1px solid #b1e5e8;background:#f7fafb;border-radius:10px;padding:12px;text-align:center}.risk-cell small{font-size:12px;font-weight:800;color:#647792}.risk-cell strong{display:block;font-size:20px;color:#0c394b;margin-top:8px}.risk-fail,.risk-banner{background:#fee2e2!important;color:#a91515!important}.risk-pass{background:#d8f5e9}.risk-banner{text-align:center;padding:10px;font-weight:750;border-radius:5px}.spread-choices{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0}.spread-choice{display:flex;align-items:center;gap:16px;border:1px solid #c8d5e5;background:#f1f5f9;border-radius:9px;padding:12px;text-align:center}.spread-choice>div{flex:1}.spread-choice p{margin:5px 0}.spread-choice.selected{border-color:#45d6bd;background:#ecfdf5}.coverage{background:#f0fdfa;border:1px solid #91e7da;border-radius:10px;padding:14px;margin:18px 0;color:#087b72}.ticket-footer{position:sticky;bottom:0;background:#f1f5f9;padding:14px 0;display:flex;gap:10px;justify-content:center;z-index:2;border-top:1px solid #d8e3ed}#ticket-cancel{background:#4b5563}#ticket-refresh{background:#137d89}#ticket-go{background:#a52525}#order-ticket .refresh-ticket,#order-ticket [data-countdown]{display:none}@media(max-width:550px){.risk-grid{grid-template-columns:1fr 1fr}.ticket-footer{flex-wrap:wrap}.spread-choices{grid-template-columns:1fr}}
.inactive-leg{opacity:.55}.ticket-legs td{padding:7px;overflow-wrap:anywhere}.contract-card{border:3px solid #94a3b8;border-radius:9px;padding:14px}.contract-green{border-color:#15803d}.contract-red{border-color:#dc2626}.contract-neutral{border-color:#94a3b8}.partial{color:#92400e}.positions-table{table-layout:fixed}.positions-table td{overflow-wrap:anywhere;padding:7px}.positions-table button{padding:6px}@media(max-width:900px){.positions-table .detail{display:none}.positions-table{min-width:0;font-size:12px}}
</style></head><body><nav><a href="/home">Income Desk</a><a href="/trade">TRADE</a><a href="/nifty-income/legacy">Legacy scan</a><a href="/nifty-income" class="active">Nifty Income</a><a href="/kite-setup">Kite Setup</a></nav><main>'''
        + f'<h1>Nifty Income</h1><p>Protected execution &amp; strategy analytics · Profile {e(account)}'+(' · localhost TEST' if test_mode else '')+'</p>'
        + (f'<div role="alert" class="error">{e(error)}</div>' if error else '')
        + (f'<p role="status">{e(message)}</p>' if message else '') + body
        + '''</main><script>
for(const select of document.querySelectorAll('input[name="lots"],select[name="structure"],select[name="short_pe"],select[name="hedge_pe"],select[name="short_ce"],select[name="hedge_ce"]')){
  select.addEventListener('change',()=>select.form.requestSubmit());
}
for(const button of document.querySelectorAll('[data-liquid-side]'))button.onclick=()=>{
 const form=button.closest('form'),side=button.dataset.liquidSide;
 form.elements['short_'+side].value=button.dataset.short;
 form.elements['hedge_'+side].value=button.dataset.hedge;
 form.requestSubmit();
};
const ticketDialog=document.getElementById('order-ticket');
let originalPosition=null, reviewTimer=null;
const footerGo=document.getElementById('ticket-go'), footerReview=document.getElementById('ticket-review');
document.getElementById('ticket-cancel').onclick=()=>ticketDialog.close();
document.getElementById('ticket-refresh').onclick=()=>document.querySelector('#ticket-content .refresh-ticket')?.click();
footerReview.onclick=()=>{clearInterval(reviewTimer);let left=10;footerGo.disabled=true;footerReview.disabled=true;footerReview.textContent='Review '+left+'s';reviewTimer=setInterval(()=>{left--;footerReview.textContent='Review '+left+'s';if(left<=0){left=0;const waiting=Boolean(document.querySelector('#ticket-content [data-countdown]')?.disabled ?? true);footerReview.textContent=waiting?'Waiting for review timer':'Review complete';if(!waiting){clearInterval(reviewTimer);footerGo.disabled=false;}}},1000);};
footerGo.onclick=()=>document.querySelector('#ticket-content [data-countdown]')?.click();
function openTicket(id){
  const article=document.getElementById('execution-'+id);
  document.getElementById('ticket-title').textContent=article?.dataset.positionManagement?'Manage NIFTY Position':'NIFTY Order Ticket';
  if(article){article.hidden=false;originalPosition=document.createComment('execution-position');article.before(originalPosition);document.getElementById('ticket-content').append(article);}
  footerGo.disabled=true;footerReview.disabled=!document.querySelector('#ticket-content [data-countdown]');footerReview.textContent='Review & Start 10s';document.getElementById('ticket-refresh').disabled=!document.querySelector('#ticket-content .refresh-ticket');
  ticketDialog.showModal();
}
document.getElementById('close-ticket').addEventListener('click',()=>ticketDialog.close());
ticketDialog.addEventListener('close',()=>{clearInterval(reviewTimer);if(originalPosition){const article=document.querySelector('#ticket-content article');if(article){originalPosition.replaceWith(article);if(article.dataset.positionManagement)article.hidden=true;}originalPosition=null;}});
for(const button of document.querySelectorAll('[data-open-execution]'))button.addEventListener('click',()=>openTicket(button.dataset.openExecution));
for(const button of document.querySelectorAll('[data-linked-execution]'))button.onclick=()=>{ticketDialog.addEventListener('close',()=>openTicket(button.dataset.linkedExecution),{once:true});ticketDialog.close();};
if(ticketDialog.dataset.auto==='true')openTicket(ticketDialog.dataset.execution);
for(const button of document.querySelectorAll('[data-countdown]')){let left=Number(button.dataset.countdown);const update=()=>{button.disabled=left>0;button.textContent=left>0?'Review risk · '+left+'s':'GO · submit BUY hedges';left-=1;};update();const timer=setInterval(()=>{update();if(left<0)clearInterval(timer);},1000);}</script></body></html>''').encode('utf-8')
