from datetime import datetime, timezone
import pytest
from test_protected_execution import preview
from trade_protected_execution import ProtectedExecutionRepository,start_execution,reconcile_execution,confirm_short,reconcile_basket
from trade_pair_exit import prepare_pair_exit,close_pair,exit_prices
from execution_pair_analytics import pair_pnl

class Paper:
    paper_trading=True
    dry_run=False
    def __init__(self):self.sent=[]
    def place_order(self,p):
        self.sent.append(p);return {'order_id':str(len(self.sent))}
    def get_instruments(self,exchange):
        return [dict(tradingsymbol=p['tradingsymbol'],tick_size=0.05) for p in self.sent]
    def get_quote(self,keys):
        return {k:dict(timestamp=datetime.now(timezone.utc).isoformat(),depth=dict(buy=[dict(price=2,quantity=100)],sell=[dict(price=3,quantity=100)])) for k in keys}


def test_close_pair_reuses_durable_exit_and_prevents_duplicates(tmp_path,preview):
    repo=ProtectedExecutionRepository(tmp_path/'pair.db');broker=Paper()
    row=start_execution(repo,'A','key',preview,'PAPER',broker,lambda _:None)
    row=reconcile_execution(repo,'A',row['id'],broker)
    row=confirm_short(repo,'A',row['id'],broker,lambda _:dict(quantity=10,price=6),True)
    row=prepare_pair_exit(repo,'A',row['id'],broker)
    prices,quotes=exit_prices(row,broker)
    from pair_exit_review import save_exit_review
    row=save_exit_review(repo,row,prices)
    assert repo.owned_symbols('A','PAPER')
    assert not repo.owned_symbols('A','LIVE')
    assert not repo.owned_symbols('B','PAPER')
    pnl=pair_pnl(row,quotes,datetime.now(timezone.utc),costs=0)
    assert pnl['gross_pnl']==20
    row=close_pair(repo,'A',row['id'],broker,True)
    assert broker.sent[-1]['transaction_type']=='BUY'
    row=reconcile_basket(repo,'A',row['id'],broker)
    assert row['state']=='SHORT_CLOSED_HEDGE_OPEN'
    row=save_exit_review(repo,row,exit_prices(row,broker)[0])
    row=close_pair(repo,'A',row['id'],broker,True)
    assert broker.sent[-1]['transaction_type']=='SELL'
    row=reconcile_basket(repo,'A',row['id'],broker)
    assert row['state']=='CLOSED'
    assert row['closed_at']
    assert not repo.owned_symbols('A','PAPER')
    count=len(broker.sent)
    with pytest.raises(PermissionError):close_pair(repo,'A',row['id'],broker,True)
    assert len(broker.sent)==count
    assert pair_pnl(row,{},datetime.now(timezone.utc),costs=0)['realized_pnl']==20
