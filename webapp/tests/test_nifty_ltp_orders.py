from datetime import datetime, timedelta
import pytest
from test_nifty_ticket_service import market
from nifty_options_engine.ticket import build_ticket
from nifty_options_engine.service import persist_review
from trade_protected_execution import ProtectedExecutionRepository,submit_basket_hedges

def test_selected_payloads_use_ltp_and_conservative_risk(market):
    selection,context,config=market
    context['quotes']['NFO:NIFTY22000PE']['last_price']=20.03
    context['quotes']['NFO:NIFTY22300PE']['last_price']=60.08
    ticket=build_ticket(selection,context,config)
    assert ticket['eligible']
    assert [p['price'] for p in ticket['order_payloads']]==[20.05,60.10]
    assert all(p['order_type']=='LIMIT' for p in ticket['order_payloads'])
    assert ticket['net_credit']==39*130  # executable book, not optimistic LTP

def test_no_ltp_no_order(market):
    selection,context,config=market
    context['quotes']['NFO:NIFTY22000PE'].pop('last_price')
    assert not build_ticket(selection,context,config)['eligible']

def test_go_submits_only_hedge_with_reviewed_limit_once(market,tmp_path):
    selection,context,config=market
    context['quotes']['NFO:NIFTY22000PE']['last_price']=20.5
    ticket=build_ticket(selection,context,config)
    record=persist_review(tmp_path/'paper.db','A',ticket)
    repo=ProtectedExecutionRepository(tmp_path/'paper.db')
    class Paper:
        paper_trading=True
        dry_run=False
        def __init__(self):self.calls=[]
        def place_order(self,payload):
            self.calls.append(dict(payload));return {'order_id':'PAPER-ONLY'}
    broker=Paper();now=datetime.fromisoformat(record['reviewed_at'])+timedelta(seconds=11)
    submit_basket_hedges(repo,'A',record['id'],broker,lambda *args:None,True,now)
    assert len(broker.calls)==1
    assert broker.calls[0]['transaction_type']=='BUY'
    assert broker.calls[0]['price']==20.5
    with pytest.raises(PermissionError):
        submit_basket_hedges(repo,'A',record['id'],broker,lambda *args:None,True,now)
    assert len(broker.calls)==1
