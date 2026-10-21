from copy import deepcopy
from datetime import datetime, timezone

import pytest
from test_nifty_ticket_service import market
from nifty_options_engine.preferences import mode_update, saved_mode
from nifty_options_engine.page import page_data
from nifty_options_engine.service import persist_review
from nifty_options_engine.ticket import build_ticket
from nifty_options_engine.ui import render_page


def test_mode_is_per_profile_and_expires_at_ist_midnight():
    now = datetime(2026,10,21,18,29,tzinfo=timezone.utc)
    settings = mode_update({}, 'A', 'LIVE', now)
    assert saved_mode(settings,'A',now)=='LIVE'
    assert saved_mode(settings,'B',now)=='PAPER'
    assert saved_mode(settings,'A',now.replace(minute=30))=='PAPER'
    assert saved_mode(mode_update(settings,'A','PAPER',now),'A',now)=='PAPER'
    with pytest.raises(ValueError):mode_update(settings,'A','INVALID',now)


def test_execute_popup_reuses_saved_execution_controls(tmp_path, market):
    selection, context, config = market
    path = tmp_path/'popup.db'
    record = persist_review(path,'A',build_ticket(selection,context,config))
    form = {key:[str(value)] for key,value in selection.items()}
    form['structure']=['PE']
    data = page_data('A',path,config,lambda _:deepcopy(context),form)
    data.update(open_ticket=True,open_execution=record['id'],saved_day_mode='LIVE')
    html = render_page(data).decode('utf-8')
    assert '>EXECUTE</button>' in html
    assert 'formaction="/nifty-2/save-mode"' in html
    assert '<dialog id="order-ticket"' in html and 'data-auto="true"' in html
    assert f'id="execution-{record["id"]}"' in html
    assert html.count('name="execution_id"')==1
    assert 'data-countdown=' in html and 'formaction="/nifty-2/start"' in html
    assert 'name="open_ticket" value="yes"' in html
    assert 'append(article)' in html  # move existing controls, never duplicate their forms
    assert 'Resets to PAPER at midnight IST' in html


def test_nifty_handler_passes_aware_ist_clock_without_app_import():
    import ast
    from pathlib import Path
    source = (Path(__file__).parents[1]/'app.py').read_text(encoding='utf-8-sig')
    start = source.index('    def send_nifty_v2(')
    end = source.index('    def send_login(',start)
    tree = ast.parse('class Handler:\n'+source[start:end])
    calls = [node for node in ast.walk(tree) if isinstance(node,ast.Call)]
    assert not any(isinstance(call.func,ast.Name) and call.func.id=='app_now' for call in calls)
    clocks = [call for call in calls if isinstance(call.func,ast.Attribute)
              and isinstance(call.func.value,ast.Name) and call.func.value.id=='datetime'
              and call.func.attr=='now']
    assert len(clocks)==5
    assert all(len(call.args)==1 and isinstance(call.args[0],ast.Name)
               and call.args[0].id=='INDIA_TIME_ZONE' for call in clocks)


def test_contract_daily_change_and_saved_ticket_details():
    from nifty_options_engine.ui import contract_quote, saved_ticket_details
    quote = contract_quote({'last_price':110,'ohlc':{'close':100},'timestamp':'2026-10-21 10:30'})
    assert '+10.00 (+10.00%)' in quote and '2026-10-21 10:30' in quote
    assert 'UNKNOWN' in contract_quote({'last_price':110})
    saved = dict(expiry='2026-11-24',spot=23000,selection={'lots':2},broker_margin=50000,
                 net_max_profit=5000,max_loss=34000,net_credit=5500,legs=[])
    html = saved_ticket_details(saved)
    assert '10.00%' in html and 'Lots / quantity' in html and 'Maximum loss incl. costs' in html


def test_legacy_style_risk_header_does_not_invent_coverage():
    from nifty_options_engine.ui import ticket_risk_header
    markup=ticket_risk_header({'eligible':False,'selection':{'include_ce':True},
        'max_loss':30082,'risk':{'risk_cap':60000,'risk_status':'BLOCK',
                               'hard_block_reasons':['CURRENT_RISK_UNKNOWN_OR_UNHEDGED']}})
    assert 'MAX LOSS CAP' in markup and 'NEW ORDER MAX LOSS' in markup
    assert 'UNKNOWN / UNCAPPED' in markup and 'FAIL: order cannot be placed' in markup
    assert 'CURRENT_RISK_UNKNOWN_OR_UNHEDGED' in markup
    assert 'Unverified existing positions are not reused' in markup
    assert 'type="checkbox" disabled checked' in markup
