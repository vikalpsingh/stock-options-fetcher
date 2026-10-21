"""Escaped server-rendered execution window. No automatic order submission."""
from html import escape
from datetime import datetime, timezone


def e(value):
    return escape(str(value if value is not None else ''), quote=True)


def money(value):
    return 'UNKNOWN' if value is None else f'â‚¹{value:,.2f}'


def render_page(data=None, error='', message='', review=None, test_mode=False):
    data = data or {}
    account = data.get('account', '')
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
        body += f'</div><p>Data refreshed {e(context["now"].isoformat())}. Mode: <b>{e(selection["mode"])}</b>.</p></section>'
        body += '<section><h2>New protected trade</h2><p>Choose contracts, refresh the preview, then save a review. Changing a ticket requires a new review.</p><form method="post" action="/nifty-2/preview"><div class="fields">'
        def select(name, label, choices, value):
            return f'<label>{e(label)}<select name="{e(name)}">' + ''.join(
                f'<option value="{e(key)}" {"selected" if str(key)==str(value) else ""}>{e(text)}</option>' for key, text in choices) + '</select></label>'
        structure = 'BOTH' if selection['include_pe'] and selection['include_ce'] else 'CE' if selection['include_ce'] else 'PE'
        body += select('structure', 'Strategy', [('PE','PE credit spread'), ('CE','CE credit spread'), ('BOTH','Iron condor')], structure)
        body += select('mode', 'Execution mode', [('PAPER','PAPER Â· simulated fills'), ('LIVE','LIVE Â· preview only')], selection['mode'])
        body += select('expiry', 'Expiry', [(x,x) for x in data['expiries']], selection['expiry'])
        body += f'<label>Lots<input type="number" name="lots" min="1" max="{data["config"]["maximum_lots_per_new_trade"]}" value="{e(selection["lots"])}" required></label>'
        for kind in ('PE','CE'):
            contracts = [row for row in data['instruments'] if row['instrument_type']==kind and str(row['expiry'])[:10]==selection['expiry']]
            choices = []
            for row in contracts:
                spot = float(context.get('spot') or 0)
                otm = ((spot-float(row['strike'])) if kind=='PE' else (float(row['strike'])-spot))/spot*100 if spot else 0
                choices.append((row['tradingsymbol'], f'{row["strike"]:g} {kind} Â· {otm:.1f}% OTM Â· lot {row["lot_size"]}'))
            for prefix, label in [('short_', 'SELL'), ('hedge_', 'Protective BUY')]:
                body += select(prefix+kind.lower(), label+' '+kind, choices, selection[prefix+kind.lower()])
        body += '</div><div class="actions"><button>Refresh preview / expiry contracts</button><button formaction="/nifty-2/review">Save order review</button></div></form><div class="metrics">'
        for label, value in [('Executable credit',ticket['net_credit']), ('Estimated costs',ticket['estimated_fees']), ('Net max profit',ticket['net_max_profit']), ('Max loss incl. costs',ticket['max_loss']), ('Projected portfolio loss',ticket['risk']['projected_portfolio_max_loss']), ('Broker margin',ticket['broker_margin'])]:
            body += card(label,money(value))
        body += '</div><h3>'+('READY FOR REVIEW' if ticket['eligible'] else 'PREVIEW ONLY â€” resolve blocks')+'</h3><ul class="checks">'
        for check in ticket['checks']:
            body += f'<li class="{e(check["status"].lower())}"><b>{e(check["status"])} Â· {e(check["name"])}</b> â€” {e(check["reason"])}</li>'
        body += '</ul><p>POP is unavailable: no validated probability model is connected. Risk uses executable bid/ask and current master quantity.</p></section>'
        body += '<section id="execution"><h2>Execution window</h2><p>GO submits protective BUY legs only. Reconcile fills, then explicitly approve SELL using fresh risk checks. LIVE sends real LIMIT orders to the broker only after explicit acknowledgement and fresh approval.</p>'
        records = data['executions']
        if not records:
            body += '<p>No saved executions. Save an eligible ticket review above.</p>'
        for record in records[:30]:
            saved = record['preview']
            body += f'<article><h3>{e(saved.get("strategy_type"))} Â· {e(record["mode"])} Â· {e(record["state"])}</h3><p>Execution {e(record["id"])} Â· Strategy {e(record.get("strategy_id", "pending"))}</p>'
            body += f'<p>Reviewed credit <b>{money(saved.get("net_credit"))}</b> Â· Net max profit <b>{money(saved.get("net_max_profit"))}</b> Â· Max loss incl. costs <b>{money(saved.get("max_loss"))}</b></p>'
            body += '<table><thead><tr><th>Stage</th><th>Side / contract</th><th>Filled / quantity</th><th>Average</th><th>Status / order ID</th></tr></thead><tbody>'
            for stage, legs in [('ENTRY',record['legs']),('EXIT',record.get('exit_legs',[]))]:
                for leg in legs:
                    p = leg['payload']
                    body += f'<tr><td>{stage}</td><td>{e(p["transaction_type"])} {e(p["tradingsymbol"])}</td><td>{e(leg["filled"])} / {e(p["quantity"])}</td><td>{money(leg["average"])}</td><td>{e(leg["status"])}<br>{e(leg["order_id"])}</td></tr>'
            body += f'</tbody></table><p>{e(record.get("note"))}</p>'
            if record['mode'] in {'PAPER', 'LIVE'}:
                body += f'<form method="post"><input type="hidden" name="execution_id" value="{e(record["id"])}"><label class="ack"><input type="checkbox" name="ack" value="yes"> I accept the shown maximum loss and the selected execution action.</label><div class="actions">'
                if record['mode'] == 'LIVE':
                    body += '<label>Type PLACE LIVE ORDERS for any submission<input name="live_ack" autocomplete="off" placeholder="PLACE LIVE ORDERS"></label>'
                state = record['state']
                if state == 'REVIEW':
                    remaining = max(0, data['config']['countdown_seconds'] - (datetime.now(timezone.utc)-datetime.fromisoformat(record['reviewed_at'])).total_seconds())
                    body += f'<button formaction="/nifty-2/start" data-countdown="{int(remaining)+1}" disabled>GO Â· submit BUY hedges</button>'
                else:
                    body += '<button formaction="/nifty-2/reconcile">Reconcile fills</button>'
                if state in {'HEDGE_FILLED','SHORT_PENDING','SHORT_PARTIAL'}:
                    body += '<button formaction="/nifty-2/confirm-sell">Revalidate risk &amp; submit unsent SELL</button>'
                if state in {'OPEN','HEDGE_FILLED','RECOVERY_READY'}:
                    has_shorts = any(leg['filled'] for leg in record['legs'] if leg['payload']['transaction_type']=='SELL')
                    body += '<button formaction="/nifty-2/close-shorts">'+('Close shorts first' if has_shorts else 'Close orphan hedge')+'</button>'
                if state == 'SHORT_CLOSED_HEDGE_OPEN':
                    body += '<button formaction="/nifty-2/close-hedges">Close remaining hedges</button>'
                body += '</div></form>'
            body += '</article>'
        body += '</section><section><h2>Monthly performance</h2><p>Saved NIFTY 2.0 strategy ledger only; not the complete broker account. PAPER fees are simulated as zero. Unknown LIVE charges remain unknown.</p>'
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
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nifty 2.0 Â· Income Desk</title><style>
body{margin:0;background:#f3f6fa;color:#15283d;font:15px system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:24px}nav{display:flex;gap:20px;padding:16px 24px;background:#142b43}nav a{color:white;text-decoration:none}nav .active{border-bottom:3px solid #57d5bd}h1{margin-bottom:8px}h2{font-size:21px}section{background:white;border:1px solid #d7e1eb;border-radius:12px;padding:22px;margin:20px 0}.metrics,.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:14px}.metric{background:#f3f7fb;padding:14px;border-radius:8px}.metric small{display:block;color:#52677b}.metric strong{display:block;font-size:22px;margin-top:8px}label{display:block;font-weight:600}input,select,button{box-sizing:border-box;padding:10px;border:1px solid #afbfce;border-radius:6px;font:inherit}label select,label input{display:block;width:100%;margin-top:6px}button{background:#163e63;color:white;cursor:pointer}button:disabled{opacity:.5;cursor:wait}.actions{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.ack input{display:inline;width:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:12px;border-bottom:1px solid #dce4ec}article{border:1px solid #cddae5;border-radius:8px;padding:16px;margin:16px 0;overflow:auto}.block,.error{color:#9b2431}.error{padding:16px;background:#fff0f0}.pass{color:#216148}.checks{padding-left:20px;line-height:1.8}p{line-height:1.6;color:#53677b}@media(max-width:650px){main{padding:10px}section{padding:14px}table{min-width:600px}section{overflow:auto}}
</style></head><body><nav><a href="/home">Income Desk</a><a href="/trade">TRADE</a><a href="/nifty-income/legacy">Legacy scan</a><a href="/nifty-income" class="active">Nifty Income</a><a href="/kite-setup">Kite Setup</a></nav><main>'''
        + f'<h1>Nifty Income</h1><p>Protected execution &amp; strategy analytics Â· Profile {e(account)}'+(' Â· localhost TEST' if test_mode else '')+'</p>'
        + (f'<div role="alert" class="error">{e(error)}</div>' if error else '')
        + (f'<p role="status">{e(message)}</p>' if message else '') + body
        + '''</main><script>for(const button of document.querySelectorAll('[data-countdown]')){let left=Number(button.dataset.countdown);const update=()=>{button.disabled=left>0;button.textContent=left>0?'Review risk Â· '+left+'s':'GO Â· submit BUY hedges';left-=1;};update();const timer=setInterval(()=>{update();if(left<0)clearInterval(timer);},1000);}</script></body></html>''').encode('utf-8')
