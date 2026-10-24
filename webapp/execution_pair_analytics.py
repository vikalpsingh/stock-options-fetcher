"""Fill-based marks shared by execution monitors; no order submission."""
import math
from app_time import is_quote_fresh
from nifty_options_engine.ticket import depth_limit


def execution_legs(record):
    if record.get('legs'):
        return record['legs']
    return [dict(payload=p,filled=record.get(prefix+'_filled',0),average=record.get(prefix+'_average_price',0))
            for p,prefix in zip(record['preview']['order_payloads'],('hedge','short'))]


def pair_pnl(record, quotes, now, costs=None):
    legs=execution_legs(record)
    realized=0.0; unrealized=0.0; entry_credit=0.0; exit_debit=0.0
    open_qty=[]; reasons=[]
    for leg in legs:
        p=leg['payload']; qty=int(leg.get('filled') or 0); avg=float(leg.get('average') or 0)
        exits=[x for x in record.get('exit_legs',[]) if x['payload']['tradingsymbol']==p['tradingsymbol']]
        closed=sum(int(x.get('filled') or 0) for x in exits)
        remaining=qty-closed
        if remaining<0 or (qty and (not math.isfinite(avg) or avg<=0)):
            reasons.append('Fill quantities or average are unresolved');continue
        sign=1 if p['transaction_type']=='SELL' else -1
        for x in exits:
            realized+=sign*(avg-float(x.get('average') or 0))*int(x.get('filled') or 0)
        open_qty.append(remaining)
        entry_credit+=sign*avg*remaining
        if not remaining:continue
        quote=quotes.get('NFO:'+p['tradingsymbol'],{})
        action='BUY' if sign==1 else 'SELL'
        depth=depth_limit(quote,action,remaining)
        price=depth['limit']
        if not is_quote_fresh(quote,120,now) or depth['shortfall']>0 or not price:
            reasons.append(p['tradingsymbol']+': fresh executable depth unavailable');continue
        exit_debit+=sign*price*remaining
        unrealized+=sign*(avg-price)*remaining
    fees=costs if costs is not None else record['preview'].get('estimated_fees')
    if fees is None: fees=500.0
    fees=float(fees)
    margin=record['preview'].get('broker_margin') or record['preview'].get('final_margin')
    gross=None if reasons else unrealized
    net=None if gross is None else gross-fees
    return dict(entry_credit=entry_credit,exit_debit=None if reasons else exit_debit,
                gross_pnl=gross,estimated_net_pnl=net,realized_pnl=realized,estimated_costs=fees,
                return_on_margin=net/float(margin)*100 if net is not None and margin and float(margin)>0 else None,
                open_quantities=open_qty,unmatched=bool(open_qty and len(set(open_qty))>1),reasons=reasons)


def render_pair_pnl(record, quotes, now):
    import html
    data=pair_pnl(record,quotes,now)
    value=lambda v:'Unavailable' if v is None else f'{v:,.2f}'
    fields=(('Open entry credit',data['entry_credit']),('Estimated exit debit',data['exit_debit']),
            ('Gross open P&L',data['gross_pnl']),('Estimated net open P&L',data['estimated_net_pnl']),
            ('Realised gross P&L',data['realized_pnl']),('Estimated costs',data['estimated_costs']),('Return on margin %',data['return_on_margin']))
    return '<div class="pair-pnl"><h4>Fill-based pair P&amp;L</h4><div style="display:flex;flex-wrap:wrap;gap:12px">'+''.join(
        '<div><small>'+html.escape(k)+'</small><strong style="display:block;color:'+('#b91c1c' if v is not None and v<0 else '#134e4a')+'">'+value(v)+'</strong></div>' for k,v in fields)+'</div><p>Open quantities: '+html.escape(str(data['open_quantities']))+(' · Unmatched/partial legs; totals use each leg’s actual quantity.' if data['unmatched'] else '')+'</p><p>'+html.escape('; '.join(data['reasons']))+'</p></div>'
