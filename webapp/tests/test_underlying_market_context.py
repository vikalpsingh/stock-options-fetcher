from underlying_market_context import context_values


def test_distances_use_underlying_and_true_annual_levels():
    spot=dict(last_price=120,ohlc=dict(close=100,low=115,high=125))
    assert context_values(spot,dict(low=80,high=150)) == dict(
        cmp=120,day=20,low=80,high=150,low_gap=50,high_gap=-20)
    assert context_values(spot,{})['low_gap'] is None


def test_annual_low_fallback_independent_of_available_high():
    data=context_values(dict(last_price=100,yearly_high=125,ohlc=dict(close=100)),dict(low=100))
    assert (data['day'],data['high_gap'],data['low_gap'])==(0,-20,0)
