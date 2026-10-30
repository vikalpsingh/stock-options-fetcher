import math
from types import SimpleNamespace
from pathlib import Path

SOURCE=Path('app.py').read_text(encoding='utf-8-sig')
def load(name,scope):
    start=SOURCE.index('def '+name+'(');end=SOURCE.index('\ndef ',start+5)
    exec(compile(SOURCE[start:end],name,'exec'),scope)
    return scope[name]

def test_independent_sell_setting_and_invalid_fallback():
    settings={}
    scope={'load_app_settings':lambda:settings,'position_close_discount_percent_setting':lambda:20}
    setting=load('position_close_sell_markup_percent_setting',scope)
    assert setting()==20
    settings['position_close_sell_markup_percent']=35
    assert setting()==35
    settings['position_close_sell_markup_percent']=float('nan')
    assert setting()==20

def test_buy_and_sell_prices_use_separate_percentages():
    scope={'load_app_settings':lambda:{},'Any':object,'math':math,'nifty_cmp_close_price':lambda *a:None,'fresh_kite_ltp_map':lambda *a:{'NFO:XPE':100},
           'option_position_pnl':lambda *a:0,'floor_to_tick':lambda price,tick:round(math.floor(price/tick)*tick,2),
           'ceil_to_tick':lambda price,tick:round(math.ceil(price/tick-1e-9)*tick,2),
           'position_close_sell_markup_percent_setting':lambda:30}
    refresh=load('refresh_position_buy_order_prices',scope)
    rows=[dict(tradingsymbol='XPE',quantity=10,average_price=100,transaction_type=side) for side in ('BUY','SELL')]
    results=refresh(rows,object(),SimpleNamespace(discount_percent=10,tick_size=.05))
    assert [r['price'] for r in results]==[90,130]
    results=refresh(rows[:1],object(),SimpleNamespace(discount_percent=0,tick_size=.05))
    assert results[0]['price']==100

def test_both_paths_reference_shared_settings():
    start=SOURCE.index('def build_missing_option_close_orders(');end=SOURCE.index('\ndef ',start+5)
    assert 'position_close_sell_markup_percent_setting()' in SOURCE[start:end]
    assert '(1 + sell_markup / 100)' in SOURCE[start:end]
    assert 'position_include_long=not position_stop_option_sell_setting()' in SOURCE
