"""Small actual-fill analytics fixtures; no database or broker access."""
from nifty_options_engine.analytics import strategy_performance, monthly_analytics, analyze_nifty_strategy_performance


def fill(side, price, qty=10, fees=1, day='2026-10-21'):
    return dict(purpose=side,price=price,quantity=qty,fees=fees,filled_at=day+'T10:00:00+05:30')


def spread(short_exit=80, hedge_exit=10, fees=1):
    return dict(strategy_id='S',strategy_type='BULL_PUT_SPREAD',legs=[
        dict(tradingsymbol='SHORT',entry_side='SELL',quantity=10,
             fills=[fill('ENTRY',100,fees=fees),fill('EXIT',short_exit,fees=fees)]),
        dict(tradingsymbol='HEDGE',entry_side='BUY',quantity=10,
             fills=[fill('ENTRY',20,fees=fees),fill('EXIT',hedge_exit,fees=fees)])])


def test_complete_spread_deducts_hedge_loss_and_fees():
    row=strategy_performance(spread())
    assert row['realised_gross']==100 and row['realised_net']==96
    assert row['hedge_cost']==200 and row['status']=='FULLY_CLOSED'
    stats=analyze_nifty_strategy_performance([row],'2026-10-01','2026-10-31')
    assert stats['winners']==1 and stats['worst_loss'] is None
    assert stats['profit_factor'] is None


def test_unknown_charges_do_not_create_verified_winner():
    result=monthly_analytics([spread(fees=None)],'2026-10')
    assert result['realised_net'] is None and result['fees'] is None
    assert result['stats']['verified_completed']==0
    assert result['stats']['unreconciled_charges']==1


def test_partial_exit_does_not_report_whole_spread_capture():
    strategy=spread()
    strategy['legs'][0]['fills'][1]['quantity']=5
    strategy['legs'][1]['fills']=strategy['legs'][1]['fills'][:1]
    row=strategy_performance(strategy,{'SHORT':{'ask':80},'HEDGE':{'bid':10}})
    assert row['status']=='PARTIALLY_CLOSED'
    assert row['captured_pct'] is None
    strategy['legs'][0]['fills'][1]['quantity']=10
    assert strategy_performance(strategy)['status']=='SHORT_CLOSED_HEDGE_OPEN'


def test_aborted_entry_cleanup_is_flat_but_not_completed_spread_sample():
    strategy=spread()
    strategy['legs'][0]['fills']=[]
    row=strategy_performance(strategy)
    assert row['status']=='CLOSED_INCOMPLETE_ENTRY' and row['open_mtm']==0
    stats=analyze_nifty_strategy_performance([row],'2026-10-01','2026-10-31')
    assert stats['completed']==0
    assert monthly_analytics([strategy],'2026-10')['realised_gross']==-100


def test_winning_and_losing_spread_statistics():
    rows=[strategy_performance(spread()),strategy_performance(spread(short_exit=110))]
    stats=analyze_nifty_strategy_performance(rows,'2026-10-01','2026-10-31')
    assert stats['winners']==1 and stats['losers']==1 and stats['win_rate']==50
    assert stats['worst_loss']==-204 and stats['expectancy']==-54
    assert stats['maximum_drawdown']==204
