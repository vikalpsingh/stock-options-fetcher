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
    assert price("NIFTY26N1722000PE","BUY",100)==(90,10)
    assert price("NIFTY26N1722000CE","SELL",100)==(125,25)
    assert price("BANKNIFTY26N1722000CE","SELL",100) is None
    assert price("NIFTYNXT5026N1722000CE","SELL",100) is None


def test_defaults_zero_invalid_and_missing_cmp():
    scope=functions(dict(nifty_close_buy_discount_percent=0,nifty_close_sell_markup_percent=float("nan")))
    assert scope["nifty_close_percent_setting"]("BUY")==0
    assert scope["nifty_close_percent_setting"]("SELL")==30
    import pytest
    with pytest.raises(ValueError):
        scope["nifty_cmp_close_price"]("NIFTY26N1722000PE","BUY",0)


def test_both_pricing_paths_use_shared_helper():
    for name in ("build_missing_option_close_orders", "refresh_position_buy_order_prices"):
        a=SOURCE.index("def "+name+"("); b=SOURCE.index("\ndef ",a+5)
        assert "nifty_cmp_close_price(" in SOURCE[a:b]
        compile(SOURCE[a:b],name,"exec")
