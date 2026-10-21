from test_nifty_ticket_service import market
from nifty_options_engine.ticket import build_ticket

def test_multilevel_buy_risk_uses_worst_limit(market):
    selection,context,config=market
    context['quotes']['NFO:NIFTY22000PE']['depth']['sell']=[{'price':21,'quantity':65},{'price':22,'quantity':65}]
    ticket=build_ticket(selection,context,config)
    assert ticket['eligible']
    assert ticket['order_payloads'][0]['price']==21  # reviewed LTP; risk still uses depth 22
    assert ticket['net_credit']==(60-22)*130
    assert ticket['max_loss']==(300-38)*130+500

def test_thin_depth_warns_without_blanket_veto(market):
    selection,context,config=market
    context['quotes']['NFO:NIFTY22000PE']['depth']['sell'][0]['quantity']=1
    ticket=build_ticket(selection,context,config)
    assert ticket['eligible']
    assert any(c['status']=='WARNING' and 'shortfall 129' in c['reason'] for c in ticket['checks'])

def test_sell_consumes_bids_conservatively(market):
    selection,context,config=market
    context['quotes']['NFO:NIFTY22300PE']['depth']['buy']=[{'price':60,'quantity':65},{'price':59,'quantity':65}]
    ticket=build_ticket(selection,context,config)
    assert ticket['order_payloads'][1]['price']==60  # reviewed LTP; risk still uses depth 59
    assert ticket['net_credit']==(59-21)*130

def test_missing_quote_still_blocks(market):
    selection,context,config=market
    context['quotes']['NFO:NIFTY22000PE']['depth']['sell']=[]
    assert not build_ticket(selection,context,config)['eligible']
