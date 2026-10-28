from position_close_preview import preview_rows, render_preview


def test_preview_long_short_and_pending():
    positions = [dict(exchange='NFO',tradingsymbol='ABC26NOV100CE',product='NRML',quantity=q,average_price=10,last_price=8) for q in [-50]]
    order = {**positions[0], 'quantity':50,'transaction_type':'BUY','price':6.4}
    rows = preview_rows(positions, [], [order], set(), False, {})
    assert rows[0]['status'] == 'PROPOSED — NOT SENT'
    assert rows[0]['position_qty'] == -50
    positions[0]['quantity'] = 50
    assert preview_rows(positions,[],[order],set(),False,{})[0]['status'] == 'BLOCKED'
    order['transaction_type'] = 'SELL'
    assert preview_rows(positions,[],[order],set(),False,{})[0]['side'] == 'SELL'
    assert preview_rows(positions,[dict(order,status='OPEN')],[order],set(),False,{})[0]['status'] == 'BLOCKED'
    assert preview_rows(positions,[],[order],{order['tradingsymbol']},False,{})[0]['status'] == 'BLOCKED'
    assert preview_rows(positions,[],[order],set(),True,{})[0]['status'] == 'BLOCKED'


def test_render_escapes_and_empty():
    assert 'No active option positions' in render_preview([])
    assert '&lt;script&gt;' in render_preview([dict(symbol='<script>')])
    assert 'TEST RUN — NO ORDERS SENT' in render_preview([])

def test_planners_are_read_only_and_keep_intraday_priority():
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    from typing import Any
    source = Path('app.py').read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == 'preview_position_close_job')
    pos = dict(exchange='NFO',tradingsymbol='ABC26NOV100CE',product='NRML',quantity=-50)
    order = dict(pos,quantity=50,transaction_type='BUY',price=6)
    class ReadOnlyBroker:
        def positions(self): return {'net':[pos]}
        def orders(self): return []
        def place_order(self,*a,**kw): raise AssertionError('Must never submit')
        modify_order = cancel_order = place_order
    ns = dict(Any=Any, kite_buy_positions=SimpleNamespace(kite_client=ReadOnlyBroker),
              position_stop_option_sell_setting=lambda:False,
              position_close_discount_percent_setting=lambda:20,
              PageState=SimpleNamespace, build_position_buy_orders=lambda state:[order],
              build_intraday_loss_limit_close_orders=lambda *a:([order],[]),
              build_intraday_pe_risk_exit_orders=lambda *a:([dict(order,price=7)],[]),
              build_missing_option_close_orders_for_scheduler=lambda *a:([dict(order,price=8)],[]),
              INTRADAY_LOSS_LIMIT_TRIGGER_PERCENT=100,APP_DB_PATH='unused',
              ProtectedExecutionRepository=lambda path:SimpleNamespace(owned_symbols=lambda account:set()),
              selected_kite_profile_name=lambda:'test')
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<isolated>','exec'),ns)
    for job in ['default','intraday']:
        result = ns['preview_position_close_job'](job)
        assert len(result)==1
        assert result[0]['price']==6
        assert result[0]['status']=='PROPOSED — NOT SENT'
