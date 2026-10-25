from trade_hedged_order_builder import build_protective_spreads
from trade_execution_ui import render_spread_summary
import pytest

@pytest.mark.parametrize('missing',['bid','ltp','tick',None])
def test_irfc_selected_hedge_remains_visible_when_blocked(missing):
    short=dict(name='IRFC',tradingsymbol='IRFC26NOV78CE',instrument_type='CE',expiry='2026-11-23',strike=78,lot_size=5425,tick_size=0.05)
    hedge=dict(short,tradingsymbol='IRFC26NOV81CE',strike=81)
    quote=lambda price:dict(last_price=price,volume=10000,oi=300000,depth=dict(buy=[dict(price=price-0.05)],sell=[dict(price=price+0.05)]))
    quotes={'NFO:'+short['tradingsymbol']:quote(2),'NFO:'+hedge['tradingsymbol']:quote(1)}
    if missing=='bid':quotes['NFO:'+short['tradingsymbol']]['depth']['buy']=[]
    if missing=='ltp':quotes['NFO:'+hedge['tradingsymbol']].pop('last_price')
    if missing=='tick':hedge.pop('tick_size')
    rows=build_protective_spreads(short,[short,hedge],quotes,5425,max_loss_cap=1,selected_hedge_symbol=hedge['tradingsymbol'],use_ltp_limits=True)
    assert len(rows)==1 and not rows[0]['eligible']
    preview=dict(hedge_alternatives=rows,selected_hedge_symbol=hedge['tradingsymbol'],quantity=5425,symbol='IRFC')
    rendered=render_spread_summary(preview)
    assert short['tradingsymbol'] in rendered and hedge['tradingsymbol'] in rendered
    assert 'Bear Call Spread' in rendered and 'REVIEW BLOCKED' in rendered
    assert rows[0]['reason'] in rendered
    if missing:assert rows[0]['order_payloads']==[]
    else:assert rows[0]['net_credit']>0 and rows[0]['max_loss']>0
