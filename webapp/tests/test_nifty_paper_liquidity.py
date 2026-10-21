from copy import deepcopy
from test_nifty_ticket_service import market
from nifty_options_engine.ticket import build_ticket, find_nearby_liquid_spreads
from nifty_options_engine.ui import nearer_liquidity_form

def test_stale_paper_warns_live_blocks(market):
    selection,context,config=market
    for quote in context['quotes'].values():
        quote.pop('timestamp')
    paper=build_ticket(selection,context,config)
    assert paper['eligible']
    assert any(c['status']=='WARNING' for c in paper['checks'])
    selection['mode']='LIVE';config['live_enabled']=True
    context.update(live_ack_enabled=True, session_fingerprint='test',live_risk_gate={'allowed':True})
    live=build_ticket(selection,context,config)
    assert not live['eligible']
    assert any(c['name'].endswith('quote freshness') and c['status']=='BLOCK' for c in live['checks'])

def test_nearer_liquid_pair_requires_explicit_selection(market):
    selection,context,config=market
    for strike in (22100,22400):
        context['instruments'].append(dict(context['instruments'][0],tradingsymbol=f'NIFTY{strike}PE',strike=strike))
        context['quotes'][f'NFO:NIFTY{strike}PE']=deepcopy(context['quotes']['NFO:NIFTY22000PE'])
    result=find_nearby_liquid_spreads(selection,context,config,toward_spot=True)
    assert result['PE'][0]['short']=='NIFTY22400PE'
    assert result['PE'][0]['hedge']=='NIFTY22100PE'
    assert selection['short_pe']=='NIFTY22300PE'
    html=nearer_liquidity_form({'selection':selection,'nearer_alternatives':result})
    assert 'action="/nifty-2/preview"' in html
    assert 'value="NIFTY22400PE"' in html
    assert '/nifty-2/start' not in html

def test_paper_still_checks_portfolio_cap(market):
    selection,context,config=market
    selection['lots']='4'
    assert not build_ticket(selection,context,config)['eligible']
