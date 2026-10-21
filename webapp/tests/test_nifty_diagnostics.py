from nifty_options_engine.diagnostics import loading_error
from nifty_options_engine.ui import render_page


def test_diagnostic_hides_exception_details_and_keeps_profile():
    class TokenException(Exception):
        pass
    try:
        raise TokenException('sensitive-broker-response')
    except TokenException as exc:
        error = loading_error(exc,'instrument master')
    assert 'sensitive-broker-response' not in error
    assert 'access token' in error and 'TokenException' in error
    html = render_page(error=error,account_name='Selected profile').decode('utf-8')
    assert 'Selected profile' in html
    assert 'sensitive-broker-response' not in html
