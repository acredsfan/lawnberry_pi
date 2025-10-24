"""Security-related FastAPI middleware and helpers.

The middleware layer enforces security headers, correlates requests,
performs lightweight rate limiting for authentication endpoints, and
configures CORS for production deployments.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections import deque
from typing import Deque, Dict, Iterable, Optional, Sequence

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..core.context import set_correlation_id


class SecurityMiddleware(BaseHTTPMiddleware):
    """Apply security headers, correlation IDs, and auth rate limiting."""

    def __init__(
        self,
        app: FastAPI,
        *,
        rate_limit_window_seconds: int = 60,
        rate_limit_max_attempts: int = 3,
        lockout_failures: int = 3,
        lockout_seconds: int = 60,
        protected_prefixes: Sequence[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._window = max(1, rate_limit_window_seconds)
        self._max_attempts = max(1, rate_limit_max_attempts)
        self._lockout_failures = max(1, lockout_failures)
        self._lockout_seconds = max(1, lockout_seconds)
        self._protected_prefixes = tuple(protected_prefixes or ("/api/v2/auth", "/api/v1/auth"))

        self._attempts: Dict[str, Deque[float]] = {}
        self._failures: Dict[str, int] = {}
        self._lockout_until: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = getattr(request.state, "correlation_id", None)
        if not correlation_id:
            correlation_id = self._extract_correlation_id(request)
            request.state.correlation_id = correlation_id
        set_correlation_id(correlation_id)

        is_protected = self._is_protected_path(request.url.path)
        client_token = self._client_identifier(request)

        if is_protected:
            limited_response = await self._preprocess_rate_limit(client_token)
            if limited_response is not None:
                limited_response.headers.setdefault("X-Correlation-ID", correlation_id)
                self._apply_security_headers(limited_response)
                return limited_response

        try:
            validation_response = None
            if is_protected and request.method in {"POST", "PUT", "PATCH"}:
                validation_response = self._validate_request_content(request)
            if validation_response is not None:
                validation_response.headers.setdefault("X-Correlation-ID", correlation_id)
                self._apply_security_headers(validation_response)
                return validation_response

            response = await call_next(request)
        except Exception:
            raise

        try:
            if is_protected:
                await self._postprocess_rate_limit(client_token, response.status_code)

            self._apply_security_headers(response)
            response.headers.setdefault("X-Correlation-ID", correlation_id)
        finally:
            pass

        return response

    def _extract_correlation_id(self, request: Request) -> str:
        header_names = ("X-Correlation-ID", "X-Request-ID", "X-Amzn-Trace-Id")
        for name in header_names:
            value = request.headers.get(name)
            if value:
                return value
        return uuid.uuid4().hex

    def _client_identifier(self, request: Request) -> str:
        header_client = request.headers.get("X-Client-Id")
        if header_client:
            return header_client
        if os.getenv("SIM_MODE", "0") == "1":
            return f"sim:{uuid.uuid4().hex}"
        client = request.client
        if client:
            return f"ip:{client.host}"
        return f"anon:{uuid.uuid4().hex}"

    def _is_protected_path(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in self._protected_prefixes)

    async def _preprocess_rate_limit(self, client_token: str) -> Optional[Response]:
        now = time.time()
        async with self._lock:
            lock_until = self._lockout_until.get(client_token)
            if lock_until and now < lock_until:
                retry_after = int(max(1, lock_until - now))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many authentication attempts"},
                    headers={"Retry-After": str(retry_after)},
                )

            attempts = self._attempts.get(client_token)
            if attempts is not None:
                cutoff = now - self._window
                while attempts and attempts[0] < cutoff:
                    attempts.popleft()

                if not attempts:
                    self._attempts.pop(client_token, None)
                elif len(attempts) >= self._max_attempts:
                    oldest = attempts[0]
                    retry_after = int(max(1, self._window - (now - oldest)))
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many authentication attempts"},
                        headers={"Retry-After": str(retry_after)},
                    )
        return None

    async def _postprocess_rate_limit(self, client_token: str, status_code: int) -> None:
        now = time.time()
        async with self._lock:
            attempts = self._attempts.get(client_token)
            if attempts is not None:
                cutoff = now - self._window
                while attempts and attempts[0] < cutoff:
                    attempts.popleft()
                if not attempts:
                    self._attempts.pop(client_token, None)
                    attempts = None

            if status_code == 401:
                if attempts is None:
                    attempts = self._attempts.setdefault(client_token, deque())
                attempts.append(now)
                failures = self._failures.get(client_token, 0) + 1
                self._failures[client_token] = failures
                if failures >= self._lockout_failures:
                    self._lockout_until[client_token] = now + self._lockout_seconds
            elif status_code < 400:
                # Successful authentication resets counters and lockout timers
                self._failures.pop(client_token, None)
                self._lockout_until.pop(client_token, None)
                self._attempts.pop(client_token, None)

    def _validate_request_content(self, request: Request) -> Optional[Response]:
        content_type = request.headers.get("Content-Type", "").lower()
        if "application/json" not in content_type:
            return JSONResponse(status_code=415, content={"detail": "Content-Type must be application/json"})
        return None

    def _apply_security_headers(self, response: Response) -> None:
        security_headers = {
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
            "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "X-XSS-Protection": "1; mode=block",
        }
        for header, value in security_headers.items():
            response.headers.setdefault(header, value)


def _default_allowed_origins() -> list[str]:
    env_value = os.getenv("LAWN_BERRY_ALLOWED_ORIGINS")
    if env_value:
        return [origin.strip() for origin in env_value.split(",") if origin.strip()]
    return [
        "https://app.lawnberry.ai",
        "https://control.lawnberry.ai",
        "http://localhost:3000",
    ]


def register_security_middleware(app: FastAPI, *, allowed_origins: Iterable[str] | None = None) -> None:
    """Attach security middleware stack to the FastAPI application."""
    origins = list(allowed_origins or _default_allowed_origins())
    app.add_middleware(
        SecurityMiddleware,
        rate_limit_window_seconds=int(os.getenv("AUTH_RATE_LIMIT_WINDOW", "45")),
        rate_limit_max_attempts=int(os.getenv("AUTH_RATE_LIMIT_MAX_ATTEMPTS", "6")),
        lockout_failures=int(os.getenv("AUTH_LOCKOUT_FAILURES", "5")),
        lockout_seconds=int(os.getenv("AUTH_LOCKOUT_SECONDS", "30")),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Requested-With",
            "X-Client-Id",
            "X-Correlation-ID",
        ],
        expose_headers=["X-Correlation-ID"],
        max_age=86400,
    )
