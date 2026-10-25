"""Isolated draft binding checks: no app import, broker or runtime database."""
from pathlib import Path
from types import SimpleNamespace


def draft_loader():
    source=Path(__file__).resolve().parents[1].joinpath('app.py').read_text(encoding='utf-8-sig')
    start=source.index('def load_trade_workflow_draft(')
    end=source.index('\ndef ',start+1)
    class Repo:
        def __init__(self,*args):pass
        def get(self,*args):
            return dict(symbol='TCS',stage='validate',data=dict(suggested_trade=dict(contract='OLDPE',side='SELL')))
    scope=dict(PageState=SimpleNamespace,TradeWorkflowRepository=Repo,APP_DB_PATH='unused',selected_kite_profile_name=lambda p:p)
    exec(compile(source[start:end],'<isolated draft loader>','exec'),scope)
    return scope['load_trade_workflow_draft'],source


def test_posted_contract_and_side_survive_draft_restore():
    load,_=draft_loader()
    state=SimpleNamespace(trade_draft_id='d',kite_profile='A',trade_contract_symbol='NEWCE',trade_side='BUY',trade_stage='validate')
    load(state)
    assert state.trade_contract_symbol=='NEWCE' and state.trade_side=='BUY'
    assert state.trade_applied_suggestion['contract']=='NEWCE'


def test_get_navigation_restores_saved_contract_and_direction():
    load,_=draft_loader()
    state=SimpleNamespace(trade_draft_id='d',kite_profile='A',trade_contract_symbol='',trade_side='BUY',trade_stage='validate')
    load(state)
    assert state.trade_contract_symbol=='OLDPE' and state.trade_side=='SELL'


def test_selector_posts_distinct_override_and_automatic_hedge_is_bound():
    _,source=draft_loader()
    assert 'formaction="/trade/review" name="trade_contract_symbol"' not in source
    assert "state.trade_hedge_symbol = (preferred_hedge or hedge_alternatives[0])" in source
    assert 'state.trade_contracts = instruments[:1200]' not in source
