"""Local TRADE test policy. TEST always means simulated broker execution."""
from ipaddress import ip_address
from urllib.parse import urlsplit


def is_local_request(host: str, peer: str) -> bool:
    try:
        address = ip_address(peer)
        address = getattr(address, "ipv4_mapped", None) or address
        url = urlsplit("//" + host)
        return (address.is_loopback and url.hostname in {"localhost", "127.0.0.1", "::1"}
                and not url.username and not url.password and not url.path and not url.query)
    except ValueError:
        return False


def test_environment_active(configured: str, host: str, peer: str) -> bool:
    return str(configured).upper() == "TEST" and is_local_request(host, peer)


def execution_mode(requested: str, test_active: bool) -> str:
    if test_active:
        return "PAPER"
    mode = str(requested).upper()
    if mode not in {"PAPER", "LIVE"}:
        raise PermissionError("Choose PAPER or LIVE execution.")
    return mode


def require_test_safe_execution(saved_mode: str, test_active: bool) -> None:
    if test_active and saved_mode != "PAPER":
        raise PermissionError("TEST cannot submit orders for a saved LIVE execution. Use a PAPER execution.")
