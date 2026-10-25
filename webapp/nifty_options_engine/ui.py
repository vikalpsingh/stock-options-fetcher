"""Escaped server-rendered execution window. No automatic order submission."""
from execution_presentation import render_discipline_cards
from execution_pair_analytics import render_pair_pnl
from pair_exit_review import render_exit_review
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
    result += '<table class="ticket-legs"><thead><tr><th>Selected / Leg</th><th>Contract</th><th>Lots / Qty</th><th>LTP / Day change</th><th>Bid / Ask</th><th>Order LIMIT</th></tr></thead><tbody>'
    for leg in display:
        selected = leg.get('selected', True)
        quote = leg.get('reviewed_quote') or {}
        limit = next((p.get('price') for p in saved.get('order_payloads',[]) if p['tradingsymbol']==leg['tradingsymbol'] and p['transaction_type']==leg['transaction_type']),None)
        result += f'<tr class="{"" if selected else "inactive-leg"}"><td><input type="checkbox" disabled {"checked" if selected else ""}> {e(leg["transaction_type"])} {e(leg.get("option_type"))}</td><td>{e(leg["tradingsymbol"])}<br>{e(leg.get("strike"))} · {e(leg.get("expiry"))}</td><td>{e(leg.get("lots",lots))} lots / {e(leg.get("quantity"))}</td><td>{money(number(quote.get("last_price")))}<br>{day_change_badge(quote)}</td><td>{money(leg.get("bid"))} / {money(leg.get("ask"))}</td><td>{money(limit) if selected else "Not selected"}</td></tr>'
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
    from urllib.parse import urlencode
    positions = (data.get('active_positions') or {}).get('positions', [])
    context = data['context']
    mode = data.get('active_positions_mode', data['selection']['mode'])
    result = '<section id="active-positions"><h2>NIFTY Active Positions &amp; Management</h2>'
    result += '<p>'+e(mode)+' positions · Suggested matches reserve quantity but need confirmed ownership before new short exposure.</p>'
    mtms = [number(row.get('unrealised')) for row in positions]
    total = sum(mtms) if all(value is not None for value in mtms) else None
    expiries = sorted(row['expiry'] for row in positions if row.get('expiry'))
    metrics = [('Active positions',len(positions)), ('Current open MTM',money(total)),
        ('Confirmed protected qty',sum(row['confirmed_hedge_qty'] for row in positions)),
        ('Unmatched short qty',sum(row['unmatched_short_qty'] for row in positions)),
        ('Available long qty',sum(row['free_long_qty'] for row in positions)),
        ('Current defined max risk',money(data.get('active_positions_risk',data['risk'])['current_defined_max_loss'])),
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
        close = position_close_preview(row, quote, context.get('broker_orders',context.get('orders')) or [], context['now'])
        dialogs += '<h4>Close preview — estimate only</h4><p>'+e(close['side'] or 'UNKNOWN')+' close · Qty '+e(close['quantity'])+' · Executable reference '+money(close['price'])+'</p>'
        dialogs += '<p>Estimated Order Cash Flow: '+money(close['cash_flow'])+' · Estimated Realised P&amp;L on Close (before fees): '+money(close['estimated_realised_gross'])+'</p>'
        if close['blockers']:
            dialogs += '<p class="block">'+e(' '.join(close['blockers']))+'</p>'
        dialogs += '<p>Estimates do not change realised P&amp;L. Final execution refreshes positions, orders, quotes and ownership.</p>'
        linked = [r for r in data['executions'] if r['mode']==mode and r['state'] not in {'CLOSED','REVIEW'} and any(leg['payload']['tradingsymbol']==symbol for leg in r['legs'])]
        for record in linked:
            dialogs += f'<button type="button" data-linked-execution="{e(record["id"])}">Manage Spread / Close using verified fills</button>'
        if mode == 'LIVE':
            dialogs += '<div class="actions">'
            actions = [('CREATE_HEDGE','Create hedge')] if qty<0 and row['unmatched_short_qty']>0 else []
            if qty>0 and row['free_long_qty']>0:
                actions += [('ROLL_SELL','Roll over'),('SELL_AGAINST_LONG','Sell against free long')]
            for action,label in actions:
                url='/nifty-income/legacy?'+urlencode({'manage_symbol':symbol,'manage_action':action})
                dialogs += f'<a class="desk-tab" href="{e(url)}">{e(label)} — legacy review</a>'
            dialogs += '<a class="desk-tab" href="/positions">Close position — Position screen</a></div><p>These are actual broker positions, including when new-trade mode is PAPER. Legacy management requires its own LIVE review and confirmation.</p>'
        if not linked:
            dialogs += '<p>No NIFTY 2.0 execution record is linked. Use the existing management screens above; no order is sent by opening them.</p>' 
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


def spread_comparison(side, rows, selection, context):
    result = '<h3>Best '+side+' SELL + Protective BUY</h3><div class="pair-table" id="pair-table-'+e(side)+'"><table><thead><tr>'
    headings = ('Select','Position','SELL','BUY hedge','Width','OTM %','SELL / BUY quotes','Credit pts','Credit INR','Credit % width','Net max profit','Max loss','Reward/risk','Score /100','Status')
    result += ''.join('<th>'+e(h)+'</th>' for h in headings)+'</tr></thead><tbody>'
    for row in rows:
        short, hedge, ticket = row['short'], row['hedge'], row['ticket']
        selected = short and short['tradingsymbol']==selection.get('short_'+side.lower()) and hedge and hedge['tradingsymbol']==selection.get('hedge_'+side.lower())
        executable = ticket and not any('bid/ask' in reason or 'PREVIEW_ONLY' in reason for reason in row['reasons'])
        qty = ticket['legs'][0]['quantity'] if ticket and ticket['legs'] else 0
        credit = ticket['net_credit'] if executable else None
        pts = credit/qty if credit is not None and qty else None
        visibility = '' if selected else ' data-pair-alternative hidden'
        result += '<tr'+visibility+' class="'+('pair-selected' if selected else '' if row['eligible'] else 'pair-blocked')+'"><td>'
        if row['eligible']:
            result += f'<button type="button" data-liquid-side="{side.lower()}" data-short="{e(short["tradingsymbol"])}" data-hedge="{e(hedge["tradingsymbol"])}">'+('Selected' if selected else 'Select')+'</button>'
        result += '</td>'
        values = [row['label'], row['strike'], hedge['strike'] if hedge else 'N/A',row.get('width','N/A'),f'{row["otm"]:.2f}' if row['otm'] is not None else 'N/A']
        result += ''.join('<td>'+e(v)+'</td>' for v in values)
        quotes = [context['quotes'].get('NFO:'+r['tradingsymbol'],{}) if r else {} for r in (short,hedge)]
        result += '<td>'+''.join(contract_quote(q) for q in quotes)+'</td>'
        values = [money(pts),money(credit),f'{pts/row["width"]*100:.2f}%' if pts is not None else 'N/A',
                  money(ticket['net_max_profit']) if executable else 'N/A',money(ticket['max_loss']) if executable else 'N/A',
                  f'{row["reward_risk"]:.3f}' if executable and row.get('reward_risk') is not None else 'N/A', row['score'],
                  'RECOMMENDED' if row.get('recommended') and not selected else 'SELECTED' if selected and row['eligible'] else 'PASS' if row['eligible'] else 'BLOCKED']
        result += ''.join('<td>'+e(v)+'</td>' for v in values)+'</tr><tr'+visibility+'><td colspan="15"><details><summary>Liquidity / checks / scoring</summary><p>'+e('; '.join(row['reasons']) or 'Mandatory checks and displayed depth passed')+'</p><p>'+e(row['confidence'])+'</p>'
        for label, quote in zip(('SELL','BUY'), quotes):
            result += '<p>'+e(label+' exchange timestamp: '+str(quote.get('timestamp') or 'Unavailable'))+'</p><pre>'+e(str({'depth':quote.get('depth'), 'OI':quote.get('oi'), 'volume':quote.get('volume')}))+'</pre>'
        result += '<p>Score: execution 25 + credit efficiency 25 + OTM distance 20. Missing optional factors earn zero. Costs use the existing conservative combined estimate.</p></details></td></tr>'
    has_selection = any(r['short'] and r['hedge'] and r['short']['tradingsymbol']==selection.get('short_'+side.lower()) and r['hedge']['tradingsymbol']==selection.get('hedge_'+side.lower()) for r in rows)
    if not has_selection:
        result += '<tr><td colspan="15">No selected pair in these candidates. Show more to review alternatives.</td></tr>'
    return result+'</tbody></table></div>'+f'<button type="button" data-pair-toggle="pair-table-{e(side)}" aria-controls="pair-table-{e(side)}" aria-expanded="false">Show more · all {e(side)} options</button>'


def desk_header(account, tabs):
    routes = {'place':'/', 'order-management':'/orders', 'nifty-income':'/nifty-income/legacy'}
    links = ''.join(f'<a class="desk-tab {"active" if key=="nifty-2" else ""}" data-tab="{e(key)}" href="{e(routes.get(key,"/"+key))}"'+(' aria-current="page"' if key=='nifty-2' else '')+f'>{e(label)}</a>' for key,label in tabs)
    return ('<header class="desk-header"><div class="desk-header-inner"><div class="desk-brand"><div class="desk-mark">विकल्प</div><div><h1>Income Desk</h1><p>Wheel income, positions, ETF actions, and calm execution.</p><div class="desk-profile">Kite profile: <strong>'+e(account)+'</strong></div></div></div><div class="desk-blessing">ॐ | Jai Sri Ram | Jai Laxmi Mata</div><p class="desk-quote">&quot;Trade money for time, not time for money. You’re going to run out of time first.&quot; <strong>— Naval</strong></p></div></header><main><nav class="desk-tabs" aria-label="Income Desk tabs">'+links+'</nav>')


def render_page(data=None, error='', message='', review=None, test_mode=False, account_name='', navigation=None):
    data = data or {}
    account = data.get('account', account_name)
    body = ''
    if data:
        selection, ticket, context = data['selection'], data['ticket'], data['context']
        body += '<form method="post" action="/nifty-2/loss-cap" class="fields"><label>Portfolio loss cap (₹)<input type="number" name="loss_cap" min="1" step="1" required value="'+e(data['config']['max_total_nifty_defined_loss_inr'])+'"></label><button type="submit">Save loss cap</button><small>Shared NIFTY setting · default ₹1,00,000. Saving requires fresh entry reviews. Monthly-loss and hedge checks remain active.</small></form>'
        risk, analytics = data['risk'], data['analytics']
        def card(label, value):
            return f'<div class="metric"><small>{e(label)}</small><strong>{e(value)}</strong></div>'
        body += '<section id="market-risk"><h2>Market &amp; risk</h2><div class="metrics">'
        for label, value in [('NIFTY spot', context.get('spot')), ('India VIX', context.get('vix')),
                             ('Portfolio max loss', money(risk['current_defined_max_loss'])),
                             ('Risk remaining', money(risk['risk_remaining'])),
                             ('Loss cap', money(data['config']['max_total_nifty_defined_loss_inr'])),
                             ('Monthly guard', (context.get('monthly') or {}).get('risk_state', 'UNKNOWN'))]:
            body += card(label, value)
        index_quote = context.get('quotes', {}).get('NSE:NIFTY 50') or {}
        spot = number(index_quote.get('last_price'))
        previous = number((index_quote.get('ohlc') or {}).get('close'))
        movement = spot-previous if spot is not None and previous is not None and previous>0 else None
        movement_text = 'Unavailable' if movement is None else f'{movement:+,.2f} points ({movement/previous*100:+.2f}%)'
        tone = 'pass' if movement is not None and movement>0 else 'block' if movement is not None and movement<0 else ''
        body += f'<div class="metric"><small>NIFTY today · vs previous close</small><strong class="{tone}">{e(movement_text)}</strong></div>'
        body += '</div><div class="mmi-focus" id="nifty-mmi-panel" data-mood="unknown" aria-label="Market Mood Index decision context"><div class="mmi-heading"><div><span class="mmi-eyebrow">MARKET SENTIMENT</span><h3>Market Mood Index</h3></div><span id="nifty-mmi-zone">Checking sentiment</span></div><div class="mmi-content"><div class="mmi-reading"><strong id="nifty-mmi-value" aria-live="polite">Loading…</strong><span> / 100</span></div><div class="mmi-decision"><small>Current strategy signal</small><strong id="nifty-mmi-signal" aria-live="polite">Checking…</strong><span>Sentiment context · confirm with price action and risk checks</span></div><div class="mmi-scale-wrap"><div class="mmi-scale" role="meter" aria-label="Market Mood Index from fear to greed" aria-valuemin="0" aria-valuemax="100" id="nifty-mmi-meter"><span id="nifty-mmi-marker" hidden></span></div><div class="mmi-scale-labels"><span>0 · Fear</span><span>50</span><span>Greed · 100</span></div></div></div>'
        body += f'</div><p class="snapshot-meta">Data refreshed {e(__import__('app_time').to_ist(context["now"]).strftime('%d %b %Y %H:%M:%S IST'))}. Mode: <b>{e(selection["mode"])}</b>.</p></section>'
        body += active_positions_section(data)
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
        body += select('auto_best', 'Auto Select Best', [('yes','ON'),('no','OFF')], 'yes' if selection.get('auto_best',True) else 'no')
        for side in ('pe','ce'):
            body += f'<input type="hidden" name="base_{side}" value="{e(selection.get("base_"+side,""))}">'
        for side, rows in (data.get('optimizer') or {}).get('tables',{}).items():
            body += spread_comparison(side, rows, selection, context)
            if not (data.get('optimizer') or {}).get('chosen',{}).get(side):
                body += '<p class="block">'+side+(': Maximum quoted net-credit fallback selected for preview. Review all blocking checks before execution.' if (data.get('optimizer') or {}).get('fallback',{}).get(side) else ': NO_ELIGIBLE_SPREAD')+'</p>'
        body += '<p>Last recalculated '+e(__import__('app_time').to_ist(context['now']).strftime('%H:%M:%S IST'))+'</p>'
        for kind in ('PE','CE'):
            body += f'<div class="spread-row"><h4>{kind} SELL + protective BUY</h4>'
            contracts = [row for row in data['instruments'] if row['instrument_type']==kind and str(row['expiry'])[:10]==selection['expiry']]
            choices = [('', 'Select a contract / no eligible automatic spread')]
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
        body += '<div class="actions"><button name="optimize" value="yes">Refresh Preview</button><button name="optimize" value="force">Auto Select Best</button><button formaction="/nifty-2/review">Save order review</button><button formaction="/nifty-2/review" name="open_ticket" value="yes">EXECUTE</button><button formaction="/nifty-2/save-mode">Save mode for today</button></div></form><div class="metrics">'
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
        body += '<section id="execution"><h2>Execution window</h2>'+render_discipline_cards()+'<p>GO submits protective BUY legs only. Reconcile fills, then explicitly approve SELL using fresh risk checks. LIVE sends real LIMIT orders to the broker only after explicit acknowledgement and fresh approval.</p>'
        body += '<form method="post" action="/nifty-2/clear-reviews"><button type="submit">Clear all reviews</button><p>Clears unsubmitted reviews for this profile in PAPER and LIVE. Pending orders and filled executions are preserved. Older reviews clear at 9:00 AM IST on weekdays while the app is running, or on next page load.</p></form>'
        body += '<datalist id="pair-exit-targets"><option value="40"><option value="50"><option value="60"><option value="70"></datalist>'
        records = sorted(data['executions'],key=lambda row:row['state']=='CLOSED')
        body += '<h3>Active / Recovery</h3>'
        closed_history = False
        if not records:
            body += '<p>No saved executions. Save an eligible ticket review above.</p>'
        for record in records[:30]:
            if record['state']=='CLOSED' and not closed_history:
                body += '<h3>Closed History</h3>'
                closed_history = True
            saved = record['preview']
            body += f'<p role="status"><strong>Next step:</strong> {e(execution_guidance(record))}</p>'
            body += f'<button type="button" data-open-execution="{e(record["id"])}">OPEN NIFTY ORDER TICKET</button>'
            body += f'<article id="execution-{e(record["id"])}"><h3>{e(saved.get("strategy_type"))} · {e(record["mode"])} · {e(record["state"])}</h3><p>Execution {e(record["id"])} · Strategy {e(record.get("strategy_id", "pending"))}</p>'
            body += render_pair_pnl(record, context['quotes'], context['now'])
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
                if state in {'OPEN','HEDGE_FILLED','RECOVERY_READY','EXIT_RECOVERY_READY','SHORT_CLOSED_HEDGE_OPEN'}:
                    body += '<label>Profit target % (advisory)<input name="pair_profit_target" type="number" min="0" max="100" value="50" list="pair-exit-targets"></label><button formaction="/nifty-2/review-exit">CLOSE PAIR · Review Exit</button>'
                    body += render_exit_review(record,'','','')
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

:root{--ink:#17202a;--muted:#627084;--line:#d6e6e3;--accent:#0f766e;--panel-soft:#f8fdfc}*{box-sizing:border-box}body{font-family:Arial,Helvetica,sans-serif;background:linear-gradient(135deg,#eef7f6 0%,#f7fbff 42%,#f2fbf4 100%);color:var(--ink)}main{max-width:1440px;width:calc(100% - 32px);padding:20px 0;margin:auto}.desk-header{background:radial-gradient(circle at 16% 12%,#2dd4bf33,transparent 26%),linear-gradient(120deg,#0b1220,#123b52 48%,#0f766e);padding:7px 18px;color:white;box-shadow:0 10px 26px #0f172a29}.desk-header-inner{max-width:1440px;margin:auto;display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:14px;align-items:center}.desk-brand{display:flex;align-items:center;gap:10px}.desk-mark{display:grid;place-items:center;min-width:92px;height:38px;border-radius:12px;background:linear-gradient(135deg,#38bdf8,#14b8a6);font-size:21px;font-weight:900}.desk-header h1{margin:0 0 2px;font-size:22px}.desk-header p{margin:0;color:#d5eef3;font-size:11.5px}.desk-profile{display:inline-block;margin-top:5px;padding:4px 9px;border:1px solid #ffffff40;border-radius:20px;font-size:11px}.desk-blessing{color:#fef3c7;font-size:15px;font-weight:900;text-align:center;border-radius:999px;padding:8px 12px;background:#ffffff14;border:1px solid #fef3c72e}.desk-quote{text-align:right;padding:8px 10px;border:1px solid #bae6fd33;border-radius:12px;background:#ffffff14}.desk-tabs{display:flex;gap:8px;margin-bottom:16px;padding:10px;border:1px solid #bde8e3;border-radius:16px;background:linear-gradient(135deg,#ffffffe6,#ecfeffd6);box-shadow:0 16px 38px #0f172a14;overflow-x:auto}.desk-tabs .desk-tab{flex-shrink:0;border:1px solid #94a3b857;border-radius:12px;background:linear-gradient(135deg,#e2e8f0,#f8fafc);color:#17202a;padding:10px 14px;font-size:14px;text-decoration:none;font-weight:600}.desk-tabs .active{background:linear-gradient(135deg,#0f766e,#115e59);color:white;border-color:#0f766e}.desk-tabs .desk-tab[data-tab="trade"],.desk-tabs .desk-tab[data-tab="nifty-2"]{background:linear-gradient(135deg,#ccfbf1,#e0f2fe);color:#115e59;border-color:#99dcd5}.desk-tabs .desk-tab.active{box-shadow:inset 0 -3px 0 #115e59}.desk-tab:hover{filter:brightness(.96)}.desk-tab:focus-visible,button:focus-visible{outline:3px solid #38bdf8;outline-offset:2px}section{border-color:var(--line);box-shadow:0 14px 34px #0f172a0d}section h2{color:#134e4a}.metric{background:var(--panel-soft);border:1px solid var(--line)}button{background:var(--accent);border-color:#0f766e}input,select{border-color:#b5ceca}p{color:var(--muted)}@media(max-width:900px){.desk-header-inner{grid-template-columns:1fr}.desk-blessing,.desk-quote{display:none}main{width:calc(100% - 20px)}.desk-tabs{gap:6px}.desk-tabs .desk-tab{padding:9px 12px}}

/* Compact overview: eight metrics share a desktop row without an orphan card. */
.pair-table{overflow-x:auto}.pair-table td,.pair-table th{text-align:right;padding:6px;font-size:12px}.pair-selected{background:#dcfce7}.pair-blocked{color:#64748b;background:#f8fafc}main{padding-top:12px}.desk-tabs{margin-bottom:10px}
.page-title{margin:6px 0 3px;font-size:25px}.page-subtitle{margin:0 0 10px;font-size:13px}
#market-risk,#active-positions{padding:14px 16px;margin:12px 0}
#market-risk h2,#active-positions h2{margin:0 0 10px;font-size:19px}
#active-positions>p{margin:0 0 10px;font-size:13px;line-height:1.4}
#market-risk>.metrics,#active-positions>.metrics{grid-template-columns:repeat(8,minmax(0,1fr));gap:8px}
#market-risk .metric,#active-positions>.metrics .metric{min-width:0;padding:10px;border-radius:7px}
#market-risk .metric small,#active-positions>.metrics .metric small{font-size:11px;line-height:1.25}
#market-risk .metric strong,#active-positions>.metrics .metric strong{font-size:18px;margin-top:5px;line-height:1.2;overflow-wrap:anywhere}
#market-risk>.metrics{grid-template-columns:repeat(7,minmax(0,1fr))}
.mmi-focus{--mood:#64748b;margin-top:10px;border:1px solid #cbd5e1;border-left:5px solid var(--mood);border-radius:10px;padding:12px 16px;background:linear-gradient(110deg,#f0fdfa,#f8fafc)}
.mmi-focus[data-mood="fear"]{--mood:#b45309;background:linear-gradient(110deg,#fff7ed,#fffbeb)}
.mmi-focus[data-mood="greed"]{--mood:#047857;background:linear-gradient(110deg,#ecfdf5,#f0fdfa)}
.mmi-focus[data-mood="neutral"]{--mood:#0369a1;background:linear-gradient(110deg,#eff6ff,#f0fdfa)}
.mmi-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.mmi-eyebrow{font-size:10px;font-weight:800;letter-spacing:.12em;color:#475569}.mmi-heading h3{margin:2px 0 8px;font-size:18px}
#nifty-mmi-zone{padding:5px 10px;border:1px solid var(--mood);border-radius:20px;color:var(--mood);font-size:13px;font-weight:800}
.mmi-content{display:grid;grid-template-columns:auto 1fr minmax(200px,32%);align-items:center;gap:22px}.mmi-reading{white-space:nowrap;color:var(--mood)}#nifty-mmi-value{font-size:38px;font-weight:850;line-height:1.1}.mmi-reading>span{font-size:14px;color:#64748b}
.mmi-decision{display:grid;gap:3px}.mmi-decision small{font-size:11px;color:#475569}#nifty-mmi-signal{font-size:20px;color:var(--mood)}.mmi-decision>span{font-size:11px;color:#475569}
.mmi-scale{position:relative;height:10px;border-radius:8px;background:linear-gradient(90deg,#c2410c,#fbbf24 40%,#cbd5e1 50%,#6ee7b7 60%,#047857)}#nifty-mmi-marker{position:absolute;top:-5px;height:20px;width:4px;transform:translateX(-50%);background:#0f172a;border:1px solid white;border-radius:3px}.mmi-scale-labels{display:flex;justify-content:space-between;margin-top:8px;font-size:10px;color:#475569}
@media(max-width:700px){.mmi-content{grid-template-columns:auto 1fr;gap:12px}.mmi-scale-wrap{grid-column:1/-1}#nifty-mmi-value{font-size:32px}#nifty-mmi-signal{font-size:17px}}
#market-risk .snapshot-meta{margin:8px 0 0;font-size:12px;line-height:1.4}
#active-positions>h3{margin:12px 0 6px;font-size:16px}
@media(max-width:1100px){#market-risk>.metrics,#active-positions>.metrics{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:600px){#market-risk,#active-positions{padding:12px}#market-risk>.metrics,#active-positions>.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.page-title{font-size:23px}}
</style></head><body>'''
        + desk_header(account, navigation if navigation is not None else [('home','Home'),('trade','TRADE'),('nifty-2','NIFTY'),('kite-setup','Kite Setup')])
        + f'<h1 class="page-title">Nifty Income</h1><p class="page-subtitle">Protected execution &amp; strategy analytics · Profile {e(account)}'+(' · localhost TEST' if test_mode else '')+'</p>'
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
for(const button of document.querySelectorAll('[data-pair-toggle]'))button.onclick=()=>{
 const expanded=button.getAttribute('aria-expanded')!=='true';
 const table=document.getElementById(button.dataset.pairToggle);
 table.querySelectorAll('[data-pair-alternative]').forEach(row=>row.hidden=!expanded);
 button.setAttribute('aria-expanded',String(expanded));
 button.textContent=expanded?'Show less · selected pair only':'Show more · all options';
};
async function refreshNiftyMood(){
 const value=document.getElementById('nifty-mmi-value'), zone=document.getElementById('nifty-mmi-zone'), signal=document.getElementById('nifty-mmi-signal');
 if(!value)return;
 try{
  const response=await fetch('/market-mmi',{cache:'no-store'});
  if(!response.ok)throw new Error('MMI unavailable');
  const data=await response.json();
  if(!data.ok || data.value==null || !Number.isFinite(Number(data.value)) || Number(data.value)<0 || Number(data.value)>100)throw new Error('MMI unavailable');
  const mmi=Number(data.value);
  value.textContent=mmi.toFixed(2);zone.textContent=data.zone||'';
  signal.textContent=mmi>60?'SELL CALL':mmi<40?'SELL PUT':'WAIT / NEUTRAL';
  document.getElementById('nifty-mmi-panel').dataset.mood=mmi>60?'greed':mmi<40?'fear':'neutral';
  const marker=document.getElementById('nifty-mmi-marker');marker.hidden=false;marker.style.left=mmi+'%';
  const meter=document.getElementById('nifty-mmi-meter');meter.setAttribute('aria-valuenow',String(mmi));meter.setAttribute('aria-valuetext',mmi.toFixed(2)+' '+(data.zone||''));
 }catch(error){value.textContent='Unavailable';zone.textContent='Data unavailable';signal.textContent='Signal unavailable';document.getElementById('nifty-mmi-panel').dataset.mood='unknown';document.getElementById('nifty-mmi-marker').hidden=true;document.getElementById('nifty-mmi-meter').removeAttribute('aria-valuenow');}
}
refreshNiftyMood();
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
