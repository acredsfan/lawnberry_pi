"""HTTP utility helpers shared across API and control layers."""
from __future__ import annotations

import uuid
from typing import Any


def client_key(request: Any) -> str:
    """Return a stable per-client key from the request for emergency tracking."""
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        return auth
    cid = request.headers.get("X-Client-Id") or request.headers.get("x-client-id")
    if cid:
        return cid
    try:
        anon = getattr(request.state, "_anon_client_id", None)
        if not anon:
            anon = "anon-" + uuid.uuid4().hex
            try:
                request.state._anon_client_id = anon
            except Exception:
                pass
        return anon
    except Exception:
        return "anon-" + uuid.uuid4().hex
