"""Request/Response sanitization middleware.

Redacts sensitive fields in JSON bodies for responses and prevents
accidental echoing of secrets. Also adds standard security headers
on all responses as a backstop.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Set

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


SENSITIVE_KEYS: Set[str] = {
    "password",
    "pass",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
}


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("***REDACTED***" if k.lower() in SENSITIVE_KEYS else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


class SanitizationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, *, max_process_bytes: int = 256_000) -> None:
        super().__init__(app)
        self._max = max(1024, int(max_process_bytes))

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Apply security headers if missing
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")

        # Redact JSON bodies up to a reasonable size to avoid overhead
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "application/json" in ctype:
            raw: bytes | None = None
            # Try direct body access first
            body_attr = getattr(response, "body", None)
            if isinstance(body_attr, (bytes, bytearray)):
                raw = bytes(body_attr)
            # Fallback: attempt to drain body iterator if present
            if raw is None and getattr(response, "body_iterator", None) is not None:
                chunks: list[bytes] = []
                try:
                    async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                except Exception:
                    raw = None
            if raw is not None and len(raw) <= self._max:
                try:
                    parsed = json.loads(raw.decode("utf-8") if raw else "null")
                    redacted = _redact(parsed)
                    headers = dict(response.headers)
                    for key in [
                        "content-length",
                        "Content-Length",
                        "transfer-encoding",
                        "Transfer-Encoding",
                        "content-type",
                        "Content-Type",
                    ]:
                        headers.pop(key, None)
                    # Build a fresh JSON response so content-length is recalculated.
                    new_resp = JSONResponse(
                        content=redacted,
                        status_code=response.status_code,
                        headers=headers,
                        media_type=response.media_type or "application/json",
                        background=getattr(response, "background", None),
                    )
                    return new_resp
                except Exception:
                    pass
        return response


def register_sanitization_middleware(app: FastAPI) -> None:
    app.add_middleware(SanitizationMiddleware)
