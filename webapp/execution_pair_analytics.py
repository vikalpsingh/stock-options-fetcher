"""Fill-based marks shared by execution monitors; no order submission."""
import math
from app_time import is_quote_fresh
from nifty_options_engine.ticket import depth_limit, quote_values, number


def execution_legs(record):
    if record.get('legs'):
        return record['legs']
    return [dict(payload=p,filled=record.get(prefix+'_filled',0),average=record.get(prefix+'_average_price',0))
            for p,prefix in zip(record['preview']['order_payloads'],('hedge','short'))]


def pair_pnl(record, quotes, now, costs=None):
    legs=execution_legs(record)
    realized=unrealized=entry_credit=exit_debit=original_credit=0.0
    open_qty=[]; reasons=[]; invalid=False; stale=False; filled_total=0
    seen_exit_orders=set()
    try:
        for leg in legs:
            p=leg['payload']; qty=int(leg.get('filled') or 0); avg=float(leg.get('average') or 0)
            if qty<0 or qty>int(p['quantity']) or (qty and (not math.isfinite(avg) or avg<=0)):
                raise ValueError('Entry fill quantity/price unresolved')
            filled_total+=qty
            sign=1 if p['transaction_type']=='SELL' else -1
            exits=[]
            for x in record.get('exit_legs',[]):
                xp=x['payload']
                if xp['tradingsymbol']!=p['tradingsymbol']:continue
                if xp.get('product')!=p.get('product') or xp.get('exchange')!=p.get('exchange') or xp['transaction_type']==p['transaction_type']:
                    raise ValueError('Exit allocation does not match the owned entry leg')
                xqty=int(x.get('filled') or 0); xavg=float(x.get('average') or 0)
                if xqty<0 or xqty>int(xp['quantity']) or (xqty and (not math.isfinite(xavg) or xavg<=0)):
                    raise ValueError('Exit fill quantity/price unresolved')
                oid=x.get('order_id')
                if xqty and (not oid or oid in seen_exit_orders):
                    raise ValueError('Duplicate or missing closing order identity')
                if xqty:seen_exit_orders.add(oid)
                exits.append((xqty,xavg))
            closed=sum(q for q,_ in exits);remaining=qty-closed
            if remaining<0:raise ValueError('Exit fills exceed owned entry quantity')
            realized+=sum(sign*(avg-price)*q for q,price in exits)
            original_credit+=sign*avg*qty
            open_qty.append(remaining);entry_credit+=sign*avg*remaining
            if not remaining:continue
            quote=quotes.get('NFO:'+p['tradingsymbol'],{})
            book=quote_values(quote)
            bid,ask=number(book['bid']),number(book['ask'])
            if bid is None or ask is None or not 0 < bid <= ask:
                stale=True;reasons.append(p['tradingsymbol']+': UNKNOWN bid/ask');continue
            depth=depth_limit(quote,'BUY' if sign==1 else 'SELL',remaining)
            price=depth['limit']
            if not is_quote_fresh(quote,120,now) or depth['shortfall']>0 or not price or not math.isfinite(price):
                stale=True;reasons.append(p['tradingsymbol']+': STALE/UNKNOWN executable quote');continue
            exit_debit+=sign*price*remaining;unrealized+=sign*(avg-price)*remaining
    except (ValueError,TypeError,KeyError,OverflowError) as exc:
        invalid=True;reasons.append(str(exc))
    if record.get('state')=='RECONCILIATION_REQUIRED':
        invalid=True;reasons.append('Broker reconciliation required')
    if not filled_total:
        invalid=True;reasons.append('No confirmed fills yet')
    def valid_number(value):
        try:
            n=float(value)
            return n if math.isfinite(n) and n>=0 else None
        except (TypeError,ValueError):return None
    fees=valid_number(costs if costs is not None else record['preview'].get('estimated_fees'))
    margin=valid_number(record['preview'].get('allocated_margin',record['preview'].get('broker_margin') or record['preview'].get('final_margin')))
    gross=None if invalid or stale else unrealized
    net=gross-fees if gross is not None and fees is not None else None
    total=None if gross is None else realized+gross
    # Actual net is available only with complete charge coverage. Never treat
    # missing LIVE contract-note charges as zero or allocate estimates as actual.
    confirmed_fees=0.0
    for leg in legs+record.get('exit_legs',[]):
        if not leg.get('filled'):continue
        trades=leg.get('trades') or []
        if sum(int(t.get('quantity') or 0) for t in trades)!=leg['filled']:
            confirmed_fees=None;break
        charges=[valid_number(t.get('fees')) for t in trades]
        if any(fee is None for fee in charges):
            confirmed_fees=None;break
        confirmed_fees+=sum(charges)
    realized_net=realized-confirmed_fees if not invalid and not any(open_qty) and confirmed_fees is not None else None
    return dict(entry_credit=None if invalid else entry_credit,original_entry_credit=None if invalid else original_credit,
        exit_debit=None if invalid or stale else exit_debit,gross_pnl=gross,estimated_net_pnl=net,
        realized_pnl=None if invalid else realized,estimated_costs=fees,
        realized_net_pnl=realized_net,
        estimated_total_net_pnl=total-fees if total is not None and fees is not None else None,
        net_profit_captured_pct=(total-fees)/original_credit*100 if total is not None and fees is not None and original_credit>0 else None,
        profit_captured_pct=total/original_credit*100 if total is not None and original_credit>0 else None,
        return_on_margin=net/margin*100 if net is not None and margin and not invalid else None,
        open_quantities=open_qty,unmatched=bool(open_qty and len(set(open_qty))>1),reasons=reasons)


def render_pair_pnl(record, quotes, now):
    import html
    data=pair_pnl(record,quotes,now)
    value=lambda v:'UNKNOWN' if v is None else f'{v:,.2f}'
    fields=(('Original filled credit',data['original_entry_credit']),('Profit captured % (gross)',data['profit_captured_pct']),('Open entry credit',data['entry_credit']),('Estimated exit debit',data['exit_debit']),
            ('Gross open P&L',data['gross_pnl']),('Estimated net open P&L',data['estimated_net_pnl']),
            ('Realised gross P&L',data['realized_pnl']),('Realised net P&L (confirmed charges)',data['realized_net_pnl']),('Estimated total net P&L',data['estimated_total_net_pnl']),('Profit captured % (estimated net)',data['net_profit_captured_pct']),('Estimated costs',data['estimated_costs']),('Return on margin %',data['return_on_margin']))
    return '<div class="pair-pnl"><h4>Fill-based pair P&amp;L</h4><div style="display:flex;flex-wrap:wrap;gap:12px">'+''.join(
        '<div><small>'+html.escape(k)+'</small><strong style="display:block;color:'+('#b91c1c' if v is not None and v<0 else '#134e4a')+'">'+value(v)+'</strong></div>' for k,v in fields)+'</div><p>Open quantities: '+html.escape(str(data['open_quantities']))+(' Â· Unmatched/partial legs; totals use each legâ€™s actual quantity.' if data['unmatched'] else '')+'</p><p>'+html.escape('; '.join(data['reasons']))+'</p></div>'
