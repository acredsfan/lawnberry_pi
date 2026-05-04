"""Deprecation header middleware.

Injects RFC 8594 `Deprecation`, `Sunset`, and `Link` headers on any response
whose path matches a configured prefix or exact path set.

Usage in main.py:
    from .middleware.deprecation import register_deprecation_middleware
    register_deprecation_middleware(app)
"""
from __future__ import annotations

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Routes that should carry deprecation headers.
# Keys are path prefixes (startswith match). Values are (sunset_date, link_to_canonical).
# Bare-path legacy WebSocket routes use exact matching via the EXACT_DEPRECATED set.
_PREFIX_DEPRECATED: dict[str, tuple[str, str]] = {
    "/api/v1/": (
        "2026-09-01",
        "https://github.com/acredsfan/lawnberry/blob/main/docs/api-inventory.md",
    ),
}

_EXACT_DEPRECATED: dict[str, tuple[str, str]] = {
    "/ws/telemetry": (
        "2026-09-01",
        "/api/v2/ws/telemetry",
    ),
    "/ws/control": (
        "2026-09-01",
        "/api/v2/ws/control",
    ),
    "/health": (
        "2026-12-01",
        "/api/v2/health/liveness",
    ),
    "/healthz": (
        "2026-12-01",
        "/api/v2/health/liveness",
    ),
}


def _deprecation_value(sunset_date: str) -> str:
    """Return an RFC 8594 `Deprecation` header value (ISO date as HTTP-date string)."""
    # RFC 8594 allows a boolean "true" or an HTTP-date. Use the sunset date as
    # the deprecation date so callers know when the notice was issued.
    return f'@"{sunset_date}T00:00:00Z"'


class DeprecationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        path = request.url.path

        sunset: str | None = None
        link: str | None = None

        if path in _EXACT_DEPRECATED:
            sunset, link = _EXACT_DEPRECATED[path]
        else:
            for prefix, (s, l) in _PREFIX_DEPRECATED.items():
                if path.startswith(prefix):
                    sunset, link = s, l
                    break

        if sunset is not None:
            response.headers["Deprecation"] = _deprecation_value(sunset)
            response.headers["Sunset"] = f"{sunset}T00:00:00Z"
            if link:
                response.headers["Link"] = f'<{link}>; rel="successor-version"'

        return response


def register_deprecation_middleware(app) -> None:
    """Register the deprecation header middleware on the FastAPI app."""
    app.add_middleware(DeprecationMiddleware)
