import math
import re
from pathlib import Path

SOURCE = Path("app.py").read_text(encoding="utf-8-sig")

def functions(settings):
    scope = dict(re=re, math=math, load_app_settings=lambda:settings,
        position_close_discount_percent_setting=lambda:20,
        position_close_sell_markup_percent_setting=lambda:30,
        floor_to_tick=lambda p,t: round(math.floor(p/t+1e-8)*t,2),
        ceil_to_tick=lambda p,t: round(math.ceil(p/t-1e-8)*t,2))
    a=SOURCE.index("def nifty_close_percent_setting(")
    b=SOURCE.index("def position_stop_option_sell_setting(",a)
    exec(compile(SOURCE[a:b],"nifty_close_settings","exec"),scope)
    return scope


def test_independent_cmp_prices_and_exact_index():
    scope=functions(dict(nifty_close_buy_discount_percent=10,nifty_close_sell_markup_percent=25))
    price=scope["nifty_cmp_close_price"]
    assert price("NIFTY26N1722000PE","BUY",100,100)==(90,10)
    assert price("NIFTY26N1722000CE","SELL",100,100)==(125,25)
    assert price("BANKNIFTY26N1722000CE","SELL",100,100) is None
    assert price("NIFTYNXT5026N1722000CE","SELL",100,100) is None


def test_defaults_zero_invalid_and_missing_cmp():
    scope=functions(dict(nifty_close_buy_discount_percent=0,nifty_close_sell_markup_percent=float("nan")))
    assert scope["nifty_close_percent_setting"]("BUY")==0
    assert scope["nifty_close_percent_setting"]("SELL")==30
    import pytest
    with pytest.raises(ValueError):
        scope["nifty_cmp_close_price"]("NIFTY26N1722000PE","BUY",0,100)


def test_both_pricing_paths_use_shared_helper():
    for name in ("build_missing_option_close_orders", "refresh_position_buy_order_prices"):
        a=SOURCE.index("def "+name+"("); b=SOURCE.index("\ndef ",a+5)
        assert "nifty_cmp_close_price(" in SOURCE[a:b]
        compile(SOURCE[a:b],name,"exec")


def test_nifty_matches_stock_reference_for_both_sides_and_market_moves():
    import pytest
    scope=functions(dict(nifty_close_buy_discount_percent=30,nifty_close_sell_markup_percent=30))
    price=scope['nifty_cmp_close_price']
    for option in ['CE','PE']:
        symbol='NIFTY26NOV23200'+option
        for cmp,avg,buy,sell in [(60.25,65,42.15,84.5),(16.5,37,11.55,48.1),(100,80,56,130)]:
            assert price(symbol,'BUY',cmp,avg)[0]==pytest.approx(buy)
            assert price(symbol,'SELL',cmp,avg)[0]==pytest.approx(sell)
        for avg in [0,float('nan'),-1]:
            with pytest.raises(ValueError): price(symbol,'SELL',100,avg)


def test_default_job_reprice_uses_nifty_entry_reference():
    scope=functions(dict(nifty_close_buy_discount_percent=30,nifty_close_sell_markup_percent=30))
    scope.update(Any=object, fresh_kite_ltp_map=lambda *a:{'NFO:NIFTY26NOV23200CE':60.25},
                 option_position_pnl=lambda q,a,p:q*(p-a))
    a=SOURCE.index('def refresh_position_buy_order_prices(');b=SOURCE.index('\ndef ',a+5)
    exec(compile(SOURCE[a:b],'<isolated>','exec'),scope)
    for side,expected in [('BUY',42.15),('SELL',84.5)]:
        order=dict(tradingsymbol='NIFTY26NOV23200CE',exchange='NFO',transaction_type=side,quantity=195,average_price=65)
        result=scope['refresh_position_buy_order_prices']([order],None)
        assert result[0]['price']==expected
        assert 'average entry price' in result[0]['price_basis']
