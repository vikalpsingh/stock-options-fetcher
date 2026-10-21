from nifty_options_engine.ui import get_day_change_color, day_change_badge, contract_quote, saved_ticket_details

def test_palette_stops_and_clamps():
    for value, color in [(-100,'#7F1D1D'),(-80,'#7F1D1D'),(-40,'#DC2626'),
                         (-20,'#FCA5A5'),(0,'#9CA3AF'),(20,'#86EFAC'),
                         (40,'#22C55E'),(80,'#15803D'),(100,'#14532D'),(200,'#14532D')]:
        assert get_day_change_color(value) == color

def test_interpolation():
    assert get_day_change_color(10) == '#91C9AE'

def test_missing_close_is_not_zero_change():
    for quote in [{}, {'last_price':70}, {'last_price':70,'ohlc':{'close':0}}]:
        assert 'Today N/A' in day_change_badge(quote)
    assert get_day_change_color(float('nan')) == '#9CA3AF'

def test_parent_and_saved_ticket_use_same_contract_change():
    quote = {'last_price':70,'ohlc':{'close':100}}
    badge = day_change_badge(quote)
    assert '-30.00 (-30.00%)' in badge
    assert badge in contract_quote(quote)
    saved = {'selection':{'lots':2}, 'legs':[{'option_type':'PE',
        'transaction_type':'BUY','tradingsymbol':'NIFTY_TEST','reviewed_quote':quote}]}
    assert badge in saved_ticket_details(saved)

def test_text_contrast_and_signed_values():
    assert 'color:#FFFFFF' in day_change_badge({'last_price':10,'ohlc':{'close':100}})
    assert 'color:#000000' in day_change_badge({'last_price':120,'ohlc':{'close':100}})
    assert '+20.00 (+20.00%)' in day_change_badge({'last_price':120,'ohlc':{'close':100}})
