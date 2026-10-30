from position_close_safety import close_failure_summary


def test_failure_reason_visible_not_candidate_price():
    result = close_failure_summary([dict(status='ERROR',tradingsymbol='NIFTY26NOV23200CE', detail='Close blocked: outstanding contract order requires reconciliation.')])
    assert 'outstanding contract order' in result
    assert 'NIFTY26NOV23200CE' in result
    assert 'No automatic retry' in result


def test_success_and_secret_redaction():
    assert close_failure_summary([dict(status='LIVE_SENT')]) == ''
    result = close_failure_summary([dict(status='ERROR',detail='api_key=secret access_token=private')])
    assert 'secret' not in result and 'private' not in result
