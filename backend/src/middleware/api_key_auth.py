"""API Key authentication middleware for service-to-service requests.

This middleware enforces an API key on configured path prefixes. It supports
keys provided via either the `X-API-Key` header or `Authorization: ApiKey <key>`.

Configuration via environment variables:
- API_KEY_REQUIRED: set to "1" to enable enforcement (default: disabled)
- API_KEY_SECRET: the required API key value; fetched via SecretsManager if unset
- API_KEY_PATH_PREFIXES: comma-separated list of prefixes to protect

The feature is off by default to avoid breaking user-facing flows.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from ..core.secrets_manager import SecretsManager


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, *, prefixes: Iterable[str], secret: Optional[str] = None) -> None:
        super().__init__(app)
        self._prefixes = tuple(p.strip() for p in prefixes if p.strip())
        self._secret = secret
        self._secrets = SecretsManager()

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not any(path.startswith(p) for p in self._prefixes):
            return await call_next(request)

        provided = self._extract_key(request)
        expected = self._secret or self._secrets.get("API_KEY_SECRET", default=None, purpose="api_key_auth")
        if not expected:
            return JSONResponse(status_code=503, content={"detail": "API key not configured"})

        if not provided or not self._constant_time_equals(provided, expected):
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

        return await call_next(request)

    def _extract_key(self, request: Request) -> Optional[str]:
        key = request.headers.get("X-API-Key")
        if key:
            return key.strip()
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("apikey "):
            return auth.split(" ", 1)[1].strip()
        return None

    def _constant_time_equals(self, a: str, b: str) -> bool:
        if len(a) != len(b):
            return False
        # simple constant-time compare
        result = 0
        for x, y in zip(a.encode(), b.encode()):
            result |= x ^ y
        return result == 0


def register_api_key_auth_middleware(app: FastAPI) -> None:
    if os.getenv("API_KEY_REQUIRED", "0") != "1":
        return
    prefixes = os.getenv("API_KEY_PATH_PREFIXES", "/api/v2/internal").split(",")
    secret = os.getenv("API_KEY_SECRET")
    app.add_middleware(APIKeyAuthMiddleware, prefixes=[p.strip() for p in prefixes if p.strip()], secret=secret)
