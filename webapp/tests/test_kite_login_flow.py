from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import app


def test_kite_login_url_uses_v3_then_encoded_api_key():
    url = app.kite_login_url("key with+/symbols")

    assert url == "https://kite.zerodha.com/connect/login?v=3&api_key=key+with%2B%2Fsymbols"
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "kite.zerodha.com"
    assert parse_qs(parsed.query) == {"v": ["3"], "api_key": ["key with+/symbols"]}


def test_extract_kite_request_token_accepts_redirect_url():
    redirected = "https://trading.example/kite/callback?request_token=request-123&status=success&action=login"

    assert app.extract_kite_request_token(redirected) == "request-123"


def test_extract_kite_request_token_accepts_plain_token():
    assert app.extract_kite_request_token("request-456") == "request-456"
