import pytest

from trade_environment import (
    is_local_request, test_environment_active as active, execution_mode, require_test_safe_execution,
)


@pytest.mark.parametrize("host,peer", [
    ("localhost:8765", "127.0.0.1"),
    ("127.0.0.1:8765", "127.0.0.1"),
    ("[::1]:8765", "::1"),
    ("localhost:8765", "::ffff:127.0.0.1"),
])
def test_local_test_forces_paper_even_for_forged_live(host, peer):
    assert is_local_request(host, peer)
    assert active("TEST", host, peer)
    assert execution_mode("LIVE", active("TEST", host, peer)) == "PAPER"


@pytest.mark.parametrize("host,peer", [
    ("localhost:8765", "192.168.1.9"),
    ("example.com", "127.0.0.1"),
    ("localhost.example.com", "127.0.0.1"),
    ("192.168.1.1:8765", "127.0.0.1"),
    ("localhost:8765", "invalid"),
    ("user@localhost", "127.0.0.1"),
    ("[bad", "127.0.0.1"),
])
def test_test_flag_does_not_apply_to_nonlocal_requests(host, peer):
    assert not active("TEST", host, peer)


def test_normal_environment_preserves_mode_controls():
    assert not active("NORMAL", "localhost", "127.0.0.1")
    assert execution_mode("LIVE", False) == "LIVE"
    assert execution_mode("PAPER", False) == "PAPER"
    with pytest.raises(PermissionError):
        execution_mode("invalid", False)


def test_test_cannot_continue_saved_live_execution():
    with pytest.raises(PermissionError):
        require_test_safe_execution("LIVE", True)
    require_test_safe_execution("PAPER", True)
    require_test_safe_execution("LIVE", False)
