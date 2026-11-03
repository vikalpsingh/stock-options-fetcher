"""Display-only underlying market context used by order tickets and the DHAN list."""
import math
from html import escape


def positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def context_values(quote, levels):
    cmp = positive(quote.get('last_price'))
    ohlc = quote.get('ohlc') or {}
    previous = positive(ohlc.get('close'))
    def reference(side):
        return (positive(quote.get('yearly_'+side)) or positive(quote.get(side+'_52w'))
                or positive(ohlc.get('yearly_'+side)) or positive(levels.get(side)))
    high, low = reference('high'), reference('low')
    def change(base):
        return round(100*(cmp/base-1), 2) if cmp and base else None
    return dict(cmp=cmp, day=change(previous), high=high, low=low,
                high_gap=change(high), low_gap=change(low))


def context_panel(symbol):
    return (f'<aside data-market-context="{escape(str(symbol or ""), quote=True)}" class="status">'
            'Underlying CMP · Day change · 52-week high / low: loading…</aside>')


CONTEXT_SCRIPT = """<script>
(()=>{
 const requests=new Map();
 const fmt=n=>Number.isFinite(n)?n.toFixed(2):'Unavailable';
 const pct=n=>Number.isFinite(n)?(n>0?'+':'')+n.toFixed(2)+'%':'Unavailable';
 async function show(el){
   const symbol=el.dataset.marketContext;
   if(!requests.has(symbol))requests.set(symbol,fetch('/api/underlying-context?symbol='+encodeURIComponent(symbol))
     .then(r=>r.ok?r.json():{}).catch(()=>({})));
   const d=await requests.get(symbol);
   if(el.hasAttribute('data-low-only')){
     const cmp=Number(el.dataset.cmp)||d.cmp;
     const gap=cmp>0&&d.low>0?(cmp/d.low-1)*100:null;
     el.textContent=Number.isFinite(gap)?pct(gap)+' from low (₹'+fmt(d.low)+')':'52W low unavailable';
     if(Number.isFinite(gap))el.dataset.sortValue=String(gap);
   }else{
     el.textContent=symbol+' · Underlying CMP '+fmt(d.cmp)+' · Today '+pct(d.day)
       +' · From 52W high '+pct(d.high_gap)+' · From 52W low '+pct(d.low_gap);
   }
 }
 const io=new IntersectionObserver(entries=>entries.forEach(({target,isIntersecting})=>{
   if(isIntersecting){io.unobserve(target);show(target);}
 }));
 document.querySelectorAll('[data-market-context]').forEach(el=>io.observe(el));
})();
</script>"""
