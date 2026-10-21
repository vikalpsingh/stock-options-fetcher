from datetime import datetime, timezone, timedelta
from nifty_options_engine.ui import contract_border_class
from nifty_options_engine.analytics import position_close_preview


def test_sell_and_buy_borders():
    for option in ('PE','CE'):
        up={'last_price':110,'ohlc':{'close':100},'type':option}
        down={'last_price':90,'ohlc':{'close':100},'type':option}
        assert contract_border_class('SELL',up)=='contract-green'
        assert contract_border_class('BUY',up)=='contract-red'
        assert contract_border_class('SELL',down)=='contract-red'
        assert contract_border_class('BUY',down)=='contract-green'


def test_missing_and_unchanged_are_neutral():
    for quote in [{},{'last_price':100,'ohlc':{'close':100}}, {'last_price':100,'ohlc':{'close':0}}]:
        for action in ('BUY','SELL'):
            assert contract_border_class(action,quote)=='contract-neutral'


def example():
    now=datetime.now(timezone.utc)
    row=dict(tradingsymbol='NIFTY_TEST',quantity=130,free_long_qty=130,average_price=100,hedge_status='UNALLOCATED_LONG')
    quote=dict(timestamp=now.isoformat(),depth={'buy':[{'price':110,'quantity':200}], 'sell':[{'price':111,'quantity':200}]})
    return row,quote,now


def test_close_pnl_uses_entry_cost_not_cash_flow():
    row,quote,now=example()
    result=position_close_preview(row,quote,now=now)
    assert not result['blockers']
    assert result['cash_flow']==14300 and result['estimated_realised_gross']==1300
    row['quantity']=-130
    result=position_close_preview(row,quote,now=now)
    assert result['side']=='BUY' and result['cash_flow']==-14430
    assert result['estimated_realised_gross']==-1430


def test_reserved_hedge_cannot_be_closed():
    row,quote,now=example();row['free_long_qty']=0
    result=position_close_preview(row,quote,now=now)
    assert result['quantity']==0 and result['blockers']
    assert result['estimated_realised_gross'] is None


def test_stale_or_pending_close_requires_reconciliation():
    row,quote,now=example()
    result=position_close_preview(row,quote,[{'tradingsymbol':'NIFTY_TEST','status':'OPEN'}],now)
    assert any('Existing orders' in text for text in result['blockers'])
    quote['timestamp']=(now-timedelta(minutes=3)).isoformat()
    result=position_close_preview(row,quote,now=now)
    assert result['estimated_realised_gross'] is None
    assert any('Refresh' in text for text in result['blockers'])
