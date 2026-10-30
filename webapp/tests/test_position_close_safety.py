import pytest
from position_close_safety import bind_close_order, validate_close_submission


def row(quantity=125, side='BUY', symbol='ABB26NOV7100CE', product='NRML'):
    return dict(exchange='NFO', tradingsymbol=symbol, product=product,
                quantity=quantity, transaction_type=side)


@pytest.mark.parametrize('symbol', ['ABB26NOV7100CE', 'NIFTY26NOV22000PE'])
@pytest.mark.parametrize('qty,side', [(125, 'SELL'), (-125, 'BUY')])
def test_direction(symbol, qty, side):
    position = row(qty, symbol=symbol)
    order = bind_close_order(row(symbol=symbol), position)
    assert order['transaction_type'] == side
    assert order['quantity'] == 125
    validate_close_submission(order, [position], [])


@pytest.mark.parametrize('position,order', [
    (row(125), row()), (row(-125), row(side='SELL')),
    (row(0), row()), (row(-50), row()),
    (row(-125, product='MIS'), row()),
])
def test_wrong_side_flat_reduced_or_wrong_product(position, order):
    with pytest.raises(ValueError):
        validate_close_submission(order, [position], [])


def test_pending_order_blocks_duplicate_even_other_side():
    with pytest.raises(ValueError, match='outstanding'):
        validate_close_submission(row(), [row(-125)], [dict(row(side='SELL'), status='OPEN')])
    validate_close_submission(row(), [row(-125)], [dict(row(), status='CANCELLED')])
# Extract only the reviewed functions: never import app.py or its runtime state.
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SOURCE = Path(__file__).parents[1].joinpath('app.py').read_text(encoding='utf-8-sig')

def extracted(name, namespace):
    tree = ast.parse(SOURCE)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<isolated>', 'exec'), namespace)
    return namespace[name]


def test_default_builder_corrects_legacy_buy_before_pricing():
    positions = [row(-125), row(125, symbol='NIFTY26NOV22000PE')]
    def legacy(position, *args):
        return {**position, 'quantity': abs(position['quantity']), 'transaction_type': 'BUY'}
    ns = dict(Any=Any, PageState=object, position_args_from_state=lambda s: SimpleNamespace(max_orders=None),
        kite_buy_positions=SimpleNamespace(kite_client=lambda: object(), current_positions=lambda *a: positions,
                                          build_buy_order=legacy),
        refresh_option_positions_with_live_ltp=lambda p,k:p,
        open_option_close_orders_by_symbol_side=lambda *a:{},
        refresh_position_buy_order_prices=lambda orders,*a:orders)
    result = extracted('build_position_buy_orders',ns)(SimpleNamespace(position_stop_option_sell=False))
    assert [o['transaction_type'] for o in result] == ['BUY','SELL']


def test_normal_price_uses_side_and_config():
    from math import floor, ceil
    ns = dict(load_app_settings=lambda:{}, Any=Any, fresh_kite_ltp_map=lambda *a:{'NFO:ABB26NOV7100CE':80},
        option_position_pnl=lambda q,a,p:q*(p-a), position_close_sell_markup_percent_setting=lambda:30,
        floor_to_tick=lambda p,t:floor(p/t)*t, ceil_to_tick=lambda p,t:ceil(p/t)*t,
        nifty_cmp_close_price=lambda *a:None)
    price = extracted('refresh_position_buy_order_prices', ns)
    args = SimpleNamespace(discount_percent=20, tick_size=.05)
    for side, expected in [('BUY',64),('SELL',130)]:
        result = price([{**row(side=side), 'average_price':100}],None,args)
        assert result[0]['price'] == pytest.approx(expected)


def test_schedule_ui_uses_shared_saved_values():
    assert 'schedule.get("schedule_time")' in SOURCE
    assert 'intraday.get("start_time")' in SOURCE
    assert 'intraday.get("end_time")' in SOURCE
    assert 'effective_from = now.date().isoformat()' in SOURCE
