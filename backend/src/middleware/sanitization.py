"""Request/Response sanitization middleware.

Redacts sensitive fields in JSON bodies for responses and prevents
accidental echoing of secrets. Also adds standard security headers
on all responses as a backstop.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Set

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

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


def _strip_framing_headers(headers: dict[str, str]) -> dict[str, str]:
    """Remove headers that must be recomputed when body content changes."""
    for key in (
        "content-length",
        "Content-Length",
        "transfer-encoding",
        "Transfer-Encoding",
        "content-type",
        "Content-Type",
    ):
        headers.pop(key, None)
    return headers


class SanitizationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, *, max_process_bytes: int = 256_000) -> None:
        super().__init__(app)
        self._max = max(1024, int(max_process_bytes))
        self._skip_response_redaction = (
            "/api/v2/settings/maps",
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Apply security headers if missing
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")

        if any(request.url.path.startswith(prefix) for prefix in self._skip_response_redaction):
            return response

        # Redact JSON bodies up to a reasonable size to avoid overhead.
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "application/json" not in ctype:
            return response

        # --- Drain the body so we can inspect / redact it. ---
        # Starlette's _StreamingResponse (returned by call_next) does NOT
        # set a 'body' attribute — its body lives only in body_iterator.
        # Reading body_iterator exhausts it, so we MUST never return the
        # original _StreamingResponse after draining; we always reconstruct.
        raw: bytes | None = None
        body_was_drained = False

        body_attr = getattr(response, "body", None)
        if isinstance(body_attr, (bytes, bytearray)) and body_attr:
            # Direct body attribute present (e.g. pre-rendered Response subclass).
            raw = bytes(body_attr)
        elif getattr(response, "body_iterator", None) is not None:
            chunks: list[bytes] = []
            try:
                async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                    chunks.append(chunk)
            except Exception as exc:
                logger.debug("SanitizationMiddleware: body drain interrupted: %s", exc)
            raw = b"".join(chunks)
            body_was_drained = True

        # --- Try JSON redaction ---
        if raw is not None and len(raw) <= self._max:
            try:
                parsed = json.loads(raw.decode("utf-8") if raw else "null")
                redacted = _redact(parsed)
                headers = _strip_framing_headers(dict(response.headers))
                # Build a fresh JSONResponse — init_headers recalculates
                # Content-Length from the new body, preventing any mismatch.
                return JSONResponse(
                    content=redacted,
                    status_code=response.status_code,
                    headers=headers,
                    media_type=response.media_type or "application/json",
                    background=getattr(response, "background", None),
                )
            except Exception as exc:
                logger.debug("SanitizationMiddleware: JSON redaction failed: %s", exc)

        # --- Fallback: body too large or JSON processing failed. ---
        # If we drained body_iterator the original _StreamingResponse is now
        # exhausted.  Returning it would cause a Content-Length mismatch at
        # the ASGI layer (uvicorn raises "shorter/longer than Content-Length").
        # Reconstruct a plain Response from the drained bytes instead.
        if body_was_drained and raw is not None:
            headers = _strip_framing_headers(dict(response.headers))
            return Response(
                content=raw,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
                background=getattr(response, "background", None),
            )

        # Non-streaming body that we couldn't redact — return unchanged.
        return response


def register_sanitization_middleware(app: FastAPI) -> None:
    app.add_middleware(SanitizationMiddleware)
