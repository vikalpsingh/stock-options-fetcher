"""Compact NIFTY 2.0 directional panel and charts using the existing chart library."""
import json
from html import escape


def render_directional_panel(data, config):
    from .directional_trend import settings
    cfg = settings(config)
    data = data or {}
    def value(key, multiplier=1, suffix=''):
        number = data.get(key)
        return 'Unavailable' if number is None else f'{number*multiplier:.2f}{suffix}'
    intraday = data.get('intraday') or {}
    status_rows = ''
    for side in ('CE','PE'):
        status = data.get(side.lower()+'_status','BLOCK')
        reason = (data.get('reasons') or {}).get(side,'Directional data unavailable. Refresh preview.')
        status_rows += f'<div class="dtv-direction" data-status="{escape(status)}"><strong>{side} SELL · {escape(status)}</strong><p>{escape(reason)}</p></div>'
    relationship = 'Unavailable'
    if data.get('ema20') is not None:
        relationship = ('Above' if data['close'] > data['ema20'] else 'Below' if data['close'] < data['ema20'] else 'At') + ' EMA20 · slope '+value('ema_slope')
    if data.get('market_session') and data.get('ema_slope_pct') is not None:
        relationship = relationship.split(' · slope')[0] + f" · slope {data['ema_slope_pct']:+.2f}% over 3 completed sessions"
    metrics = [('ADX14',value('adx14')),('+DI / −DI',value('plus_di')+' / '+value('minus_di')),
               ('ER5 / ER10',value('er5')+' / '+value('er10')),('5-day return',value('return_5d',100,'%')),
               ('Price / EMA',relationship),('ATR14 / ATR %',value('atr14')+' / '+value('atr_pct',1,'%'))]
    if data.get('market_session'):
        metrics.append(('Intraday validation', data.get('intraday_validation','UNAVAILABLE')))
    metric_html = ''.join(f'<div><small>{escape(label)}</small><strong>{escape(text)}</strong></div>' for label,text in metrics)
    gap = 'Unavailable' if intraday.get('gap_pct') is None else f"{intraday['gap_pct']:+.2f}%"
    gap_atr = 'Unavailable' if intraday.get('gap_atr') is None else f"{intraday['gap_atr']:.2f} × ATR%"
    vwap = 'UNAVAILABLE' if intraday.get('vwap') is None else f"{intraday['vwap']:.2f} ({data.get('future_symbol')})"
    payload = json.dumps(dict(data=data,config=cfg),allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    def stamp(raw):
        if not raw:
            return 'Unavailable'
        from .directional_trend import timestamp
        return timestamp(raw).strftime('%d %b %Y %H:%M IST')
    return f'''<div class="dtv-panel" id="nifty-dtv-panel"><span class="mmi-eyebrow">DIRECTIONAL RISK</span>
<h3>NIFTY Trend Strength &amp; Directional Risk</h3><strong>{escape(data.get('daily_regime') or data.get('market_regime','UNAVAILABLE'))}</strong>
<div class="dtv-metrics">{metric_html}</div><div class="dtv-directions">{status_rows}</div>
<p>Current-session gap {gap} · {gap_atr}<br>{escape(intraday.get('continuation','Intraday data unavailable'))}<br>Futures session VWAP {escape(vwap)}</p>
<p class="dtv-final" id="nifty-dtv-final" aria-live="polite">MMI {escape(data.get('mmi_recommendation','UNAVAILABLE'))} · CE {escape(data.get('ce_status','BLOCK'))} · PE {escape(data.get('pe_status','BLOCK'))}</p>
<small>Last successful daily candle {stamp(data.get('data_asof'))}<br>Intraday candle {stamp(intraday.get('asof'))}<br>Calculated {stamp(data.get('calculated_at'))}</small></div>
<div class="dtv-charts"><div class="dtv-chart-controls" role="group" aria-label="Directional chart">
<button type="button" data-dtv-chart="er" aria-pressed="true">Directional Efficiency</button>
<button type="button" data-dtv-chart="adx" aria-pressed="false">ADX / DMI</button>
<button type="button" data-dtv-chart="price" aria-pressed="false">NIFTY Trend</button>
<label>History <select id="dtv-range"><option value="1">1 month</option><option value="3">3 months</option><option value="6">6 months</option></select></label></div>
<p id="dtv-chart-legend">ER5 · ER10 · confirmed daily history</p><div id="dtv-chart" role="img" aria-label="Confirmed daily directional indicators"></div><p id="dtv-chart-hover" aria-live="polite">Hover a trading date to inspect values. C = CE SELL veto, P = PE SELL veto. Current intraday signals are shown above.</p></div>
<script type="application/json" id="dtv-data">{payload}</script>'''


DTV_STYLE = '''<style>
/* Keep market sentiment and trend charts together; avoid a blank half-row. */
.nifty-sentiment-grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:12px;align-items:start;color-scheme:light}
.nifty-sentiment-grid .mmi-focus{grid-column:1;grid-row:1;margin:0}
.dtv-panel{grid-column:2;grid-row:1/3;padding:14px;border:1px solid #c9dee5;border-top:3px solid #0d9488;border-radius:12px;background:#f8fcfd;color:#20384a;min-width:0}
.dtv-panel h3{margin:5px 0 8px;font-size:17px;color:#134e4a}.dtv-panel p{font-size:12px;line-height:1.5;margin:7px 0;color:#425a6b}
.dtv-panel>.mmi-eyebrow{color:#527084}.dtv-panel>small{display:block;font-size:11px;line-height:1.5;color:#607789}
.dtv-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:10px 0}
.dtv-metrics>div{background:#fff;border:1px solid #e0ebef;border-radius:7px;padding:8px;overflow-wrap:anywhere}
.dtv-metrics small,.dtv-metrics strong{display:block}.dtv-metrics small{color:#607789;font-size:11px}.dtv-metrics strong{font-size:13px;color:#243e51;margin-top:3px}
.dtv-directions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.dtv-direction{border:1px solid #a9d8c5;border-left:3px solid #16855e;border-radius:8px;padding:9px;background:#effbf5;color:#166344}
.dtv-direction strong{font-size:12px}.dtv-direction p{color:inherit;margin-bottom:0}
.dtv-direction[data-status=BLOCK]{border-color:#efb9b9;border-left-color:#c24141;background:#fff3f2;color:#9b3030}
.dtv-direction[data-status=CAUTION]{border-color:#e8ce93;border-left-color:#b77912;background:#fff9eb;color:#805b15}
.dtv-panel .dtv-final{font-weight:600;background:#edf5fb;border:1px solid #d3e4f0;border-radius:7px;padding:9px;color:#244b68}
.dtv-charts{grid-column:1;grid-row:2;border:1px solid #d3e3e9;border-radius:12px;padding:12px;min-width:0;background:#fff;color:#334155}
.dtv-chart-controls{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.dtv-chart-controls button{padding:7px 9px;font-size:12px;background:#f0f7fa;color:#355468;border:1px solid #d2e3e9;border-radius:7px;box-shadow:none}
.dtv-chart-controls button[aria-pressed=true]{background:#dff5ef;color:#075e55;border-color:#72b9aa;outline:none}
.dtv-chart-controls button:focus-visible{outline:2px solid #0f766e;outline-offset:2px}
.dtv-chart-controls label{display:flex;align-items:center;gap:5px;margin-left:auto;font-size:12px;color:#526a7c}
.dtv-chart-controls select{width:auto;margin:0;padding:5px;background:#fff;color:#334155;border:1px solid #cbdde5}
#dtv-chart{height:240px;min-width:0}#dtv-chart.dtv-empty{height:auto;min-height:64px;display:flex;align-items:center;padding:12px;background:#f7fafc;border:1px dashed #c9dce6;border-radius:8px;font-size:13px;color:#546c7f}
.dtv-charts p{font-size:11px;line-height:1.5;margin:7px 0;color:#607789}
@media(max-width:1000px){.nifty-sentiment-grid{grid-template-columns:1fr}.nifty-sentiment-grid .mmi-focus,.dtv-panel,.dtv-charts{grid-column:1;grid-row:auto}}
@media(max-width:480px){.dtv-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.dtv-directions{grid-template-columns:1fr}.dtv-chart-controls label{margin-left:0}#dtv-chart{height:220px}}
</style>''' 

DTV_SCRIPT = '''<script>
(()=>{
 const source=document.getElementById('dtv-data');if(!source)return;
 const {data,config}=JSON.parse(source.textContent), history=data.history||[];
 const box=document.getElementById('dtv-chart'), range=document.getElementById('dtv-range');
 const tooltip=document.getElementById('dtv-chart-hover'),legend=document.getElementById('dtv-chart-legend');
 let selected='er',chart=null,markers=null;
 try{selected=sessionStorage.getItem('nifty2-dtv-chart')||'er';range.value=sessionStorage.getItem('nifty2-dtv-range')||'1';}catch(e){}
 if(!['er','adx','price'].includes(selected))selected='er';if(!['1','3','6'].includes(range.value))range.value='1';
 const numeric=(v,digits=2)=>Number.isFinite(v)?v.toFixed(digits):'Unavailable';
 function finalMood(signal){
  const side=signal==='SELL CALL'?'CE':signal==='SELL PUT'?'PE':null;
  const status=side?data[side.toLowerCase()+'_status']:null;
  document.getElementById('nifty-dtv-final').textContent=side
   ?'MMI: '+signal+' · DTV: '+status+' '+side+' SELL · FINAL: '+(status==='BLOCK'?'NO NEW '+side+' SELL. '+(data.reasons?.[side]||''):'Existing strategy checks required.')
   :'MMI: '+signal+' · CE SELL '+data.ce_status+' · PE SELL '+data.pe_status;
 }
 finalMood(data.mmi_recommendation||'UNAVAILABLE');
 document.addEventListener('nifty-mmi-updated',event=>finalMood(event.detail));
 function updateControls(){
  document.querySelectorAll('[data-dtv-chart]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.dtvChart===selected)));
  try{sessionStorage.setItem('nifty2-dtv-chart',selected);sessionStorage.setItem('nifty2-dtv-range',range.value);}catch(e){}
 }
 async function loadLibrary(){
  if(window.LightweightCharts)return;
  await new Promise((resolve,reject)=>{const script=document.createElement('script');
   script.src='https://cdn.jsdelivr.net/npm/lightweight-charts@5.0.9/dist/lightweight-charts.standalone.production.js';
   script.onload=resolve;script.onerror=reject;document.head.appendChild(script);});
 }
 function draw(){
  updateControls();if(chart){chart.remove();chart=null;markers=null;}box.textContent='';box.classList.remove('dtv-empty');
  if(!history.length){box.classList.add('dtv-empty');box.textContent='Confirmed historical indicators unavailable. Use Refresh market data above to retry. Check Kite Setup if the issue persists.';return;}
  const LC=window.LightweightCharts;if(!LC)return;
  const cutoff=new Date(history.at(-1).date+'T00:00:00Z');cutoff.setUTCMonth(cutoff.getUTCMonth()-Number(range.value));
  const rows=history.filter(p=>p.date>=cutoff.toISOString().slice(0,10));
  chart=LC.createChart(box,{autoSize:true,layout:{background:{type:'solid',color:'#ffffff'},textColor:'#334155'},
   grid:{vertLines:{color:'#edf2f5'},horzLines:{color:'#edf2f5'}},timeScale:{timeVisible:false},localization:{locale:'en-IN'}});
  let fields=selected==='er'?['er5','er10']:selected==='adx'?['adx14','plus_di','minus_di']:['close','ema20'];
  const colors=['#168eab','#d68d21','#b64583'];let primary;
  for(const [index,field] of fields.entries()){
   const options={color:colors[index],lineWidth:2,title:field,priceFormat:{type:'price',precision:2,minMove:.01}};
   if(selected==='er')options.autoscaleInfoProvider=()=>({priceRange:{minValue:0,maxValue:1}});
   const series=chart.addSeries(LC.LineSeries,options);series.setData(rows.map(p=>({time:p.date,value:p[field]})));if(!index)primary=series;
  }
  const thresholds=selected==='er'?[config.er_veto_threshold,config.er_warning_threshold]:selected==='adx'?[config.adx_developing_threshold,config.adx_trend_threshold]:[];
  thresholds.forEach(value=>primary.createPriceLine({price:value,color:'#8994a3',lineWidth:1,lineStyle:LC.LineStyle.Dotted,axisLabelVisible:true}));
  const marks=[];for(const point of rows){
   if(point.ce_status==='BLOCK')marks.push({time:point.date,position:'aboveBar',color:'#d65c46',shape:'arrowDown',text:'C'});
   if(point.pe_status==='BLOCK')marks.push({time:point.date,position:'belowBar',color:'#8e67d8',shape:'arrowUp',text:'P'});
  }
  markers=LC.createSeriesMarkers(primary,marks);
  legend.textContent=fields.join(' · ')+' · Confirmed daily history · C = CE veto · P = PE veto';
  chart.subscribeCrosshairMove(param=>{
   const day=typeof param.time==='string'?param.time:param.time?String(param.time.year)+'-'+String(param.time.month).padStart(2,'0')+'-'+String(param.time.day).padStart(2,'0'):null;
   const p=rows.find(row=>row.date===day);if(!p)return;
   tooltip.textContent=p.date+' · ER5 '+numeric(p.er5)+' · ER10 '+numeric(p.er10)+' · ADX '+numeric(p.adx14)+' · +DI '+numeric(p.plus_di)+' / −DI '+numeric(p.minus_di)+' · NIFTY '+numeric(p.close)+' · 5D '+numeric(p.return_5d*100)+'% · '+p.market_regime+' · CE '+p.ce_status+' / PE '+p.pe_status;
  });chart.timeScale().fitContent();
 }
 document.querySelectorAll('[data-dtv-chart]').forEach(button=>button.onclick=()=>{selected=button.dataset.dtvChart;draw();});range.onchange=draw;
 updateControls();if(!history.length){draw();return;}
 loadLibrary().then(draw).catch(()=>{box.classList.add('dtv-empty');box.textContent='Chart library unavailable. Directional values and server checks remain available above.';});
})();
</script>'''
