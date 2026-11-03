"""Exercise the actual route branch and submission boundary without importing app.py."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

SOURCE = Path('app.py').read_text(encoding='utf-8-sig')


def test_flag_save_without_discount_field():
    import textwrap
    start = SOURCE.index('            elif request_path == "/positions/save-option-sell-flag":')
    end = SOURCE.index('            elif ', start+20)
    code = textwrap.dedent(SOURCE[start:end]).replace('elif request_path','if request_path',1)
    saved = {}
    for stop in (False, True):
        state = SimpleNamespace(position_stop_option_sell=stop)
        exec(code,dict(request_path='/positions/save-option-sell-flag',
                       form={'position_stop_option_sell_present':['1']}, state=state,
                       save_app_settings=saved.update, position_stop_option_sell_setting=lambda:saved['position_stop_option_sell']))
        assert saved['position_stop_option_sell'] is stop


def test_owned_contract_does_not_suppress_independent_sell(monkeypatch):
    import position_close_reconcile
    start = SOURCE.index('def execute_position_buy_orders(')
    end = SOURCE.index('\ndef ',start+5)
    dispatch = Mock(return_value=('LIVE_SENT','fake-order','placed'))
    monkeypatch.setattr(position_close_reconcile,'execute_close',dispatch)
    scope = dict(Any=object, os=SimpleNamespace(getenv=lambda key:'YES'), APP_DB_PATH='unused',
                 ProtectedExecutionRepository=lambda path: SimpleNamespace(owned_symbols=lambda account:{'OWNEDPE'}),
                 selected_kite_profile_name=lambda:'mock',kite_buy_positions=SimpleNamespace(kite_client=lambda:object()),
                 ORDER_FIELDS={'tradingsymbol','transaction_type','quantity'},
                 app_now=lambda:__import__('datetime').datetime(2026,11,3))
    exec(SOURCE[start:end],scope)
    orders = [dict(tradingsymbol=s,transaction_type='SELL',quantity=275) for s in ('OWNEDPE','FREEPE')]
    _, results = scope['execute_position_buy_orders'](orders,{0,1},False,True,False)
    assert [r['status'] for r in results] == ['BLOCKED_OWNED','LIVE_SENT']
    assert dispatch.call_count==1 and dispatch.call_args.args[1]==orders[1]
