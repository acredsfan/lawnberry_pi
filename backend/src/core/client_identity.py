"""Canonical client network identity behind the local frontend proxy."""

from __future__ import annotations

import ipaddress
from typing import Any

CANONICAL_CLIENT_IP_HEADER = "X-LawnBerry-Client-IP"


def _normalized_ip(value: Any) -> str | None:
    candidate = str(value or "").strip()
    if not candidate or "," in candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def client_ip(connection: Any) -> str | None:
    """Return a validated peer IP, trusting the canonical hop only locally.

    Uvicorn deliberately ignores generic proxy headers. The production
    frontend computes one canonical address from either its TCP peer or, only
    for a loopback Cloudflare-tunnel hop, Cloudflare's client address. A direct
    LAN caller cannot spoof this header because the backend accepts it only
    when the immediate TCP peer is loopback.
    """
    peer = getattr(connection, "client", None)
    peer_value = (
        peer[0]
        if isinstance(peer, (tuple, list)) and peer
        else getattr(peer, "host", None)
    )
    peer_ip = _normalized_ip(peer_value)
    if peer_ip is None:
        return None
    if ipaddress.ip_address(peer_ip).is_loopback:
        forwarded = _normalized_ip(
            getattr(connection, "headers", {}).get(CANONICAL_CLIENT_IP_HEADER)
        )
        if forwarded is not None:
            return forwarded
    return peer_ip


__all__ = ["CANONICAL_CLIENT_IP_HEADER", "client_ip"]
