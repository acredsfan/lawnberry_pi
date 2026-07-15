"""Trusted local-proxy client identity contracts."""

from types import SimpleNamespace

from backend.src.core.client_identity import client_ip


def _connection(peer: str, forwarded: str | None = None):
    headers = {}
    if forwarded is not None:
        headers["X-LawnBerry-Client-IP"] = forwarded
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_loopback_proxy_can_supply_one_valid_canonical_client_ip():
    assert client_ip(_connection("127.0.0.1", "203.0.113.7")) == "203.0.113.7"


def test_direct_lan_client_cannot_spoof_canonical_client_ip():
    assert client_ip(_connection("192.168.1.50", "203.0.113.7")) == "192.168.1.50"


def test_invalid_or_chained_proxy_identity_is_rejected():
    assert client_ip(_connection("127.0.0.1", "bad-address")) == "127.0.0.1"
    assert client_ip(_connection("127.0.0.1", "203.0.113.7, 198.51.100.2")) == "127.0.0.1"
