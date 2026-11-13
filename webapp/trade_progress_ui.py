"""Honest progress feedback for synchronous, read-only TRADE actions."""
TRADE_PROGRESS_MARKUP = '''
<div id="trade-work-progress" hidden>
  <div class="trade-work-meta"><span>Processing request</span><span id="trade-work-elapsed" aria-live="off">0s elapsed</span></div>
  <div class="trade-work-track" role="progressbar" aria-label="Waiting for TRADE analysis" aria-valuetext="Processing; completion percentage unavailable"><i></i></div>
  <p class="trade-work-caption">Checks included in this request</p>
  <ol id="trade-work-steps"></ol>
  <p id="trade-work-note" role="status" aria-live="polite">Results appear when the server responds. No orders are placed by this action.</p>
</div>
<style>
#trade-work-progress{width:100%;text-align:left;color:#334155}#trade-work-progress[hidden]{display:none}
.trade-work-meta{display:flex;justify-content:space-between;gap:12px;font-size:12px;color:#526879}
.trade-work-track{height:5px;border-radius:6px;overflow:hidden;background:#dfeeee;margin:10px 0 16px}
.trade-work-track i{display:block;width:35%;height:100%;background:#0d9488;border-radius:6px;animation:trade-work-slide 1.6s ease-in-out infinite}
.trade-work-caption{margin:0 0 8px;font-size:12px;font-weight:700;color:#527084}
#trade-work-steps{list-style:none;counter-reset:work;padding:0;margin:0;display:grid;gap:8px}
#trade-work-steps li{counter-increment:work;display:flex;align-items:center;gap:10px;background:#fff;border:1px solid #deeaee;border-radius:9px;padding:9px 11px;font-size:13px;line-height:1.4}
#trade-work-steps li:before{content:counter(work);display:grid;place-items:center;flex:0 0 24px;height:24px;border-radius:50%;background:#e4f4f0;color:#086f61;font-weight:700}
#trade-work-note{font-size:12px;line-height:1.5;margin:12px 0 0;color:#526879}
@keyframes trade-work-slide{from{transform:translateX(-110%)}to{transform:translateX(390%)}}
@media(prefers-reduced-motion:reduce){.trade-work-track i{animation:none;width:100%;opacity:.5}}
</style>'''

TRADE_PROGRESS_SCRIPT = r'''
(() => {
 const paths=new Set(['/trade/load','/trade/chart/reload','/trade/best','/trade/best/recalculate','/trade/best/live','/trade/best/select','/trade/review','/trade/direction','/trade/direction/apply','/trade/analyse-gpt','/trade/workflow/intelligence','/trade/workflow/chart']);
 const panel=document.getElementById('trade-work-progress'), steps=document.getElementById('trade-work-steps');
 if(!panel||!steps)return;
 let busy=false,timer=null,form=null;
 const note=document.getElementById('trade-work-note'),elapsed=document.getElementById('trade-work-elapsed');
 function reset(){
  clearInterval(timer);timer=null;panel.hidden=true;
  if(form)form.removeAttribute('aria-busy');form=null;
  if(busy)endGlobalWork();busy=false;
 }
 function start(path,target){
  busy=true;form=target;form.setAttribute('aria-busy','true');panel.hidden=false;
  const scan=['/trade/best','/trade/best/recalculate','/trade/best/live'].includes(path);
  const review=path==='/trade/review';
  const chart=path==='/trade/chart/reload';
  const labels=chart?['Load confirmed Kite candles','Prepare the selected chart range']:scan?
   ['Load watchlist and market quotes','Evaluate stock, sector and NIFTY trends','Apply existing strategy and risk checks','Prepare ranked opportunities']:
   ['Refresh selected contracts and quotes','Evaluate stock, sector and NIFTY trends',review?'Revalidate hedge, liquidity and risk':'Prepare analysis and chart details','Display the updated results'];
  steps.replaceChildren(...labels.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
  note.textContent='Results appear when the server responds. No orders are placed by this action.';
  beginGlobalWork(chart?'Loading your chart…':review?'Preparing your order review…':scan?'Evaluating trading opportunities…':'Updating your selected stock…',
   'Waiting for server analysis. Individual stage completion is not reported by this request.');
  const started=performance.now();elapsed.textContent='0s elapsed';
  timer=setInterval(()=>{
   const seconds=Math.floor((performance.now()-started)/1000);
   elapsed.textContent=seconds<60?seconds+'s elapsed':Math.floor(seconds/60)+'m '+seconds%60+'s elapsed';
   if(seconds>=45)note.textContent='Still waiting for the server. The first history load or a large watchlist can take longer. Keep this tab open; do not submit the same request again. No automatic retry is made.';
  },1000);
 }
 document.addEventListener('submit',event=>{
  const target=event.target,button=event.submitter;
  const path=new URL(button?.formAction||target.action||location.href,location.href).pathname;
  if(!paths.has(path))return;
  if(busy){event.preventDefault();return;}
  // Run after existing confirmation/validation handlers; leave native payload,
  // submitter name/value and browser navigation untouched.
  queueMicrotask(()=>{if(!event.defaultPrevented&&!busy)start(path,target);});
 });
 window.addEventListener('pageshow',reset); // Includes back/forward-cache restores.
})();
'''
