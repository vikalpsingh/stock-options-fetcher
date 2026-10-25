"""Manual custom-GPT handoff: explicit copy/open and pasted advisory response."""
from datetime import datetime, timezone
import html
import json
import sqlite3

GPT_URL='https://chatgpt.com/g/g-6a0329877ef08191af2120f5a3378d34-indianstockadvisor'


def prompt(rows):
    data=[{key:row.get(source) for key,source in [('stock','symbol'),('company','company'),('quantity','quantity'),('buy_price_inr','avg_price'),('cmp_inr','cmp')]} for row in rows]
    return ('Evaluate these Indian equity shares for a 5–10 year horizon. Classify each as BUY, HOLD, SELL or REVIEW if evidence is insufficient. '
            'Assess financial strength, recent quarterly/annual results, sector growth, management quality/governance and valuation. '
            'Research current sources and cite links plus reporting dates. Do not invent missing financials, CMP, news or target prices. '
            'Quantity and buy price are portfolio context, not indicators of business quality. '
            'For each stock give category, reasons, key risks, valuation view, confidence, and next review trigger. '
            'Separate fundamental opinion from portfolio action; no order instructions. Values below are a portfolio snapshot, not guaranteed live quotes.\n\n'
            +json.dumps(data,ensure_ascii=False,indent=2,default=str))


def save_response(path,account,body):
    body=str(body).strip()
    if not account or not body or len(body)>100000:raise ValueError('Paste a response between 1 and 100,000 characters.')
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS investing_advisor_responses(account TEXT NOT NULL,saved_at TEXT NOT NULL,body TEXT NOT NULL)')
        db.execute('INSERT INTO investing_advisor_responses VALUES(?,?,?)',(account,datetime.now(timezone.utc).isoformat(),body))


def render(rows,path,account):
    e=lambda v:html.escape(str(v),quote=True)
    saved=None
    try:
        from pathlib import Path
        with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as db:
            saved=db.execute('SELECT saved_at,body FROM investing_advisor_responses WHERE account=? ORDER BY rowid DESC LIMIT 1',(account,)).fetchone()
    except sqlite3.OperationalError:pass
    options='<option value="'+e(prompt(rows))+'">All configured stocks</option>'+''.join('<option value="'+e(prompt([row]))+'">'+e(row.get('symbol',''))+'</option>' for row in rows)
    result='<section class="panel"><div class="panel-title">Indian Stock Advisor · ChatGPT review</div><p>Choose stocks, copy the prompt, open your GPT and paste it there. It shares stock names, quantities, buy prices and CMP only. ChatGPT responses cannot be fetched automatically from this custom GPT; paste the response below to display it here.</p>'
    result+='<label>Stocks<select onchange="document.getElementById(\'invest-advisor-prompt\').value=this.value">'+options+'</select></label><textarea id="invest-advisor-prompt" readonly rows="7" style="width:100%">'+e(prompt(rows))+'</textarea>'
    result+='<div class="actions"><button type="button" onclick="const t=document.getElementById(\'invest-advisor-prompt\');t.select();if(navigator.clipboard &amp;&amp; window.isSecureContext){navigator.clipboard.writeText(t.value).then(()=>document.getElementById(\'invest-copy-status\').textContent=\'Copied. Open GPT and paste the prompt.\').catch(()=>document.getElementById(\'invest-copy-status\').textContent=\'Press Ctrl/Cmd+C to copy the selected prompt.\')}else{document.getElementById(\'invest-copy-status\').textContent=\'Press Ctrl/Cmd+C to copy the selected prompt.\'}">Copy review prompt</button><a class="button-link" href="'+GPT_URL+'" target="_blank" rel="noopener noreferrer">Open Indian Stock Advisor GPT</a></div><p id="invest-copy-status" role="status"></p>'
    result+='<label>Paste GPT response<textarea name="invest_advisor_response" rows="8" maxlength="100000" style="width:100%" placeholder="Paste the response from your GPT here"></textarea></label><button type="submit" formaction="/investing/advisor-response" formnovalidate>Save &amp; show response</button>'
    if saved:result+='<article><h3>Saved GPT response · manually pasted</h3><small>'+e(saved[0])+'</small><p>Unverified external commentary; does not change engine scores or place orders.</p><div style="white-space:pre-wrap;overflow-wrap:anywhere">'+e(saved[1])+'</div></article>'
    return result+'</section>'
