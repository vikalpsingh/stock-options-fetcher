"""Feature-gated enhancement of existing Investing markup; read-only rendering."""
import html
import json
import sqlite3
from .config import enabled


def e(value):return html.escape(str(value if value is not None else 'UNKNOWN'),quote=True)


def load(path,account):
    try:
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as db:
            snapshots=db.execute('SELECT data FROM investing_v2_snapshots WHERE account=? ORDER BY evaluated_at DESC',(account,)).fetchall()
            jobs=db.execute('SELECT state,progress FROM investing_v2_jobs WHERE account=? ORDER BY created_at DESC LIMIT 1',(account,)).fetchone()
            try:outcomes=db.execute('SELECT symbol,exchange,data FROM investing_v2_results WHERE account=?',(account,)).fetchall()
            except sqlite3.OperationalError:outcomes=[]
        latest={};history={}
        for row in snapshots:
            item=json.loads(row[0]);result=item['result'];symbol=item['exchange']+':'+result.get('symbol','')
            history.setdefault(symbol,[]).append(result)
            latest.setdefault(symbol,result)
        for symbol,exchange,payload in outcomes:
            latest[exchange+':'+symbol]=json.loads(payload)
        from datetime import datetime,timezone
        for key,result in list(latest.items()):
            if (datetime.now(timezone.utc)-datetime.fromisoformat(result['evaluated_at'])).total_seconds()>86400:
                latest[key]={**result,'decision':'REVIEW','portfolio_action':'NO_ACTION','warnings':result.get('warnings',[])+['Evaluation older than 24 hours; re-evaluate before acting.']}
        # Missing-evidence/failed evaluations are visible results too. Never leave
        # a previous BUY on screen after a newer failed re-evaluation.
        if jobs:
            for item in json.loads(jobs[1]):
                if item.get('result'):
                    result=item['result'];key=item.get('exchange','NSE')+':'+item['symbol']
                    if key not in latest or result['evaluated_at']>=latest[key].get('evaluated_at',''):
                        latest[key]=result
        return latest,history,jobs
    except (sqlite3.Error,ValueError,KeyError,TypeError):return {},{},None


def enhance(markup,rows,path,account,settings=None):
    if not enabled(settings=settings):return markup
    latest,history,jobs=load(path,account)
    headings=['Score','Confidence','Growth','Quality','Valuation','Guidance','Thesis','Portfolio %','Decision']
    markup=markup.replace('<th>Debt</th><th>Note</th>','<th>Debt</th><th>Note</th>'+''.join('<th><button type="button" class="sort-header" data-sort-col="'+str(19+i)+'">'+e(x)+'</button></th>' for i,x in enumerate(headings)),1)
    start=markup.find('<tbody>');end=markup.find('</tbody>',start)
    if start<0 or end<0:return markup
    parts=markup[start+7:end].split('</tr>');dialogs=[]
    for i,row in enumerate(rows):
        if i>=len(parts)-1:break
        symbol=str(row.get('symbol',''));identity=str(row.get('quote_key') or 'NSE:'+symbol);result=latest.get(identity,{})
        current_weight=row.get('portfolio_pct')
        if result and isinstance(current_weight,(int,float)) and result.get('portfolio_weight') is not None and abs(current_weight-result['portfolio_weight'])>0.1:
            result={**result,'decision':'REVIEW','portfolio_action':'NO_ACTION','warnings':result.get('warnings',[])+['Portfolio weight changed; re-evaluate allocation before adding.']}
        decision=result.get('decision','REVIEW');component=result.get('component_scores',{})
        values=[result.get('score'),result.get('confidence'),component.get('Growth'),component.get('Quality'),result.get('valuation'),result.get('guidance'),result.get('thesis_status'),result.get('portfolio_weight')]
        parts[i]=parts[i].replace('<tr>',f'<tr data-invest-decision="{e(decision)}" data-invest-score="{e(result.get("score",-1))}" data-invest-weight="{e(result.get("portfolio_weight",-1))}" data-invest-growth="{e(component.get("Growth",-1))}" data-invest-valuation="{e({"CHEAP":5,"ATTRACTIVE":4,"FAIR":3,"EXPENSIVE":2,"EXTREME":1}.get(result.get("valuation"),-1))}" data-invest-correction="{e(row.get("pct_to_52_high",-1))}" data-invest-incomplete="{str(result.get("status")!="RATABLE").lower()}">',1)
        if result.get('score') is not None:
            badge=f'<button class="invest-score" type="button" title="Open score evidence and stock suggestions" onclick="document.getElementById(\'invest-detail-{i}\').showModal()">Score {e(result["score"])}/100</button>'
            parts[i]=parts[i].replace('</a>','</a>'+badge,1)
        parts[i]+=''.join('<td>'+e(v)+'</td>' for v in values)+f'<td><button type="button" onclick="document.getElementById(\'invest-detail-{i}\').showModal()">{e(decision)} · {e(result.get("portfolio_action","NO_ACTION"))}</button><small>{e(result.get("evaluated_at","Not evaluated"))}</small></td>'
        detail=f'<h2>{e(symbol)} · {e(decision)}</h2><p>Rule decision: {e(decision)} · Suggested action: {e(result.get("portfolio_action","NO_ACTION"))} · Confidence {e(result.get("confidence"))}/100 · Coverage {e(result.get("data_coverage"))}%</p>'
        detail+='<p>Research only. No orders are placed. Missing evidence requires REVIEW.</p>'
        if result.get('diagnostic_code'):detail+='<p role="status">'+e(result['diagnostic_code'])+'</p>'
        detail+='<h3>Components and evidence</h3><table><tr><th>Component / metric</th><th>Value / unit</th><th>Points</th><th>Period / source</th></tr>'
        for item in result.get('evidence',[]):
            detail+=f'<tr><td>{e(item["component"])} / {e(item["metric"])}</td><td>{e(item["value"])} {e(item["unit"])}</td><td>{e(item["score"])} / {e(item["maximum"])}</td><td>{e(item["period"])} · {e(item["source"])}</td></tr>'
        detail+='</table><h3>Valuation, thesis and allocation</h3><p>'+e(result.get('valuation'))+' · MOS '+e(result.get('margin_of_safety'))+'% · Thesis '+e(result.get('thesis_status'))+' · Portfolio '+e(result.get('portfolio_weight'))+'%</p>'
        detail+='<h3>Warnings / suggested changes</h3><ul>'+''.join('<li>'+e(w)+'</li>' for w in result.get('warnings',['Import sourced fundamentals and re-evaluate.']))+'</ul>'
        ai=result.get('ai') or {}
        detail+='<h3>Optional GPT review</h3><p>'+e(ai.get('summary','Not requested'))+'</p>'
        if ai.get('disagreement'):detail+='<p role="alert">GPT disagrees. The displayed rule decision remains authoritative.</p>'
        for title,key in [('Positives','top_positives'),('Risks','top_risks')]:detail+='<h4>'+title+'</h4><ul>'+''.join('<li>'+e(x)+'</li>' for x in ai.get(key,[]))+'</ul>'
        detail+='<p>Next trigger: '+e(ai.get('next_trigger','New verified results or material events'))+'</p><h3>Evaluation history</h3><ul>'+''.join('<li>'+e(x.get('evaluated_at'))+' · '+e(x.get('model_version'))+' · '+e(x.get('score'))+' · '+e(x.get('thesis_status'))+'</li>' for x in history.get(identity,[])[:12])+'</ul>'
        dialogs.append(f'<dialog id="invest-detail-{i}" style="max-width:92vw;max-height:85vh;overflow:auto;border:1px solid #9cc;border-radius:12px;padding:20px">{detail}<button type="button" onclick="this.closest(\'dialog\').close()">Close</button></dialog>')
    markup=markup[:start+7]+'</tr>'.join(parts)+markup[end:]
    counts=' · '.join(e(key)+': '+str(sum(r.get('decision')==key for r in latest.values())) for key in ('BUY','HOLD','SELL','REVIEW'))
    controls='<section class="panel"><h3>Investment Decision Engine · 5–10 years</h3><p>'+counts+'</p><p>Configured portfolio · Advisory suggestions only · Model investing-v2.0-rules-1</p>'
    controls+='<label>Evaluate stock<select name="invest_symbol"><option value="">All configured stocks</option>'+''.join('<option>'+e(r.get('symbol'))+'</option>' for r in rows)+'</select></label><label><input type="checkbox" name="invest_ai" value="yes"> Include optional GPT review (may incur API cost)</label><button formaction="/investing/evaluate" type="submit">Re-evaluate selected / all</button><button formaction="/investing/load" type="submit">Refresh prices / progress</button>'
    controls+='<label>Filter<select onchange="document.querySelectorAll(\'[data-invest-decision]\').forEach(r=>r.hidden=this.value===\'DATA INCOMPLETE\'?r.dataset.investIncomplete!==\'true\':this.value!==\'ALL\' &amp;&amp; r.dataset.investDecision!==this.value)">'+''.join('<option>'+x+'</option>' for x in ['ALL','BUY','HOLD','SELL','REVIEW','DATA INCOMPLETE'])+'</select></label>'
    controls+='<button type="button" onclick="const b=document.querySelector(\'#investing-holdings-table tbody\');[...b.rows].sort((a,c)=>Number(c.dataset.investScore||-1)-Number(a.dataset.investScore||-1)).forEach(r=>b.appendChild(r))">Sort score ↓</button>'
    controls+='<label>Sort results<select onchange="const b=document.querySelector(\'#investing-holdings-table tbody\');const key=this.value;[...b.rows].sort((a,c)=>Number(c.dataset[key]||-1)-Number(a.dataset[key]||-1)).forEach(r=>b.appendChild(r))">'+''.join('<option value="'+key+'">'+label+'</option>' for key,label in [('investScore','Score'),('investWeight','Portfolio weight'),('investValuation','Valuation'),('investGrowth','Growth'),('investCorrection','Correction')])+'</select></label>'
    controls+='<p>Weakening thesis: '+str(sum(r.get('thesis_status')=='WEAKENING' for r in latest.values()))+' · Concentration / unknown weight: '+str(sum(any('NO ADD' in w for w in r.get('warnings',[])) for r in latest.values()))+' · Data needing evaluation: '+str(sum(str(r.get('quote_key') or 'NSE:'+str(r.get('symbol'))) not in latest for r in rows))+'</p>'
    controls+='<details><summary>Refresh fundamentals · manual evidence import</summary><p>No provider is connected. Paste sourced CSV/JSON observations. Sector must be an explicit model such as BANK or INDUSTRIAL. See docs/investing-v2-progress.md.</p><select name="invest_format"><option value="json">JSON</option><option value="csv">CSV</option></select><textarea name="invest_evidence" placeholder="Source-tagged observations"></textarea><label><input name="invest_identity_ack" value="yes" type="checkbox"> I verified symbol, exchange and ISIN mappings and source evidence.</label><button formaction="/investing/import" type="submit">Import fundamentals</button></details>'
    if jobs:controls+='<p>Job '+e(jobs[0])+'</p><ul>'+''.join('<li>'+e(x.get('symbol'))+': '+e(x.get('status'))+' '+e(x.get('reason',''))+'</li>' for x in json.loads(jobs[1]))+'</ul>'
    controls+='</section>'
    return markup.replace('<section class="panel investing-table-panel">',controls+'<section class="panel investing-table-panel">',1).replace('</form>',''.join(dialogs)+'</form>',1)
