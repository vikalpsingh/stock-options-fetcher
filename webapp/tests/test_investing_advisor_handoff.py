import json
import pytest
from investing.advisor_handoff import prompt,render,save_response,GPT_URL
from investing.presentation import lakh_amount


def test_prompt_only_shares_requested_holding_fields():
    row=dict(symbol='ABC',company='Example',quantity=10,avg_price=120,cmp=130,account='PRIVATE',access_token='SECRET')
    text=prompt([row])
    assert 'ABC' in text and '120' in text and '130' in text and 'management' in text
    assert 'SECRET' not in text and 'PRIVATE' not in text
    assert 'REVIEW' in text and 'cite links' in text


def test_saved_response_is_scoped_escaped_and_survives_reload(tmp_path):
    path=tmp_path/'advisor.db'
    assert 'Saved GPT response' not in render([],path,'A')
    assert not path.exists()
    save_response(path,'A','BUY ABC <script>alert(1)</script>')
    html=render([],path,'A')
    assert 'BUY ABC' in html and '&lt;script&gt;' in html and '<script>alert' not in html
    assert GPT_URL in html and 'manually pasted' in html
    assert 'BUY ABC' not in render([],path,'B')
    with pytest.raises(ValueError):save_response(path,'A','')


def test_pnl_lakh_sign_unknown_and_threshold():
    assert lakh_amount(-150000)=='₹-1.50 L'
    assert lakh_amount(1000)=='₹0.01 L'
    assert lakh_amount(None)=='N/A'
