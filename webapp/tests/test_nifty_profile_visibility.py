"""Profile visibility regression tests without importing the runtime app."""
import ast
from pathlib import Path
from typing import Any
import pytest

@pytest.fixture(scope='module')
def helpers():
    source = Path('app.py').read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    names = {'kite_profile_nifty_income_enabled','kite_profile_nifty_grow_enabled','profile_flag'}
    nodes = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    ns = dict(Any=Any,selected_kite_profile_name=lambda name:name,
              normalize_profile_visible_tabs=lambda value:list(value),
              blank_kite_profile=lambda name:{},
              default_nifty_income_enabled_for_profile=lambda name:False,
              default_nifty_grow_enabled_for_profile=lambda name:False)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<isolated>','exec'),ns)
    return ns

@pytest.mark.parametrize('tabs,income,grow', [(['nifty-2'],True,False),
    (['nifty-income'],True,False),(['nifty-grow'],True,True),([],False,False)])
def test_tabs_override_contradictory_legacy_switches(helpers,tabs,income,grow):
    profiles={'test':{'VISIBLE_TABS':tabs,'NIFTY_INCOME_ENABLED':not income,'NIFTY_GROW_ENABLED':not grow}}
    assert helpers['kite_profile_nifty_income_enabled']('test',profiles) is income
    assert helpers['kite_profile_nifty_grow_enabled']('test',profiles) is grow
    assert not helpers['kite_profile_nifty_income_enabled']('other',profiles)


def test_old_profiles_fallback(helpers):
    assert helpers['kite_profile_nifty_income_enabled']('test',{'test':{'NIFTY_INCOME_ENABLED':True}})
