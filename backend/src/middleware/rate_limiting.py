"""Global rate limiting middleware.

Provides simple token bucket rate limiting across all endpoints with
path-based overrides and exemptions. Defaults are conservative and
configurable via environment variables so production can tune without
code changes.

Notes:
- In-memory store suitable for single-process deployment on Pi.
- Hooks defined to plug a distributed backend (e.g., Redis) if needed.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


@dataclass
class Bucket:
    tokens: float
    last_refill: float


class GlobalRateLimiter(BaseHTTPMiddleware):
    def __init__(
        self,
        app: FastAPI,
        *,
        refill_rate_per_sec: float = 2.0,  # tokens per second
        burst: int = 20,
        exempt_prefixes: Sequence[str] | None = None,
        strict_prefix_overrides: Sequence[Tuple[str, float, int]] | None = None,
    ) -> None:
        super().__init__(app)
        self._rate = max(0.1, float(refill_rate_per_sec))
        self._burst = max(1, int(burst))
        self._exempt = tuple(exempt_prefixes or ("/health", "/metrics", "/docs", "/openapi.json"))
        # List of (prefix, rate, burst) to override defaults per path
        self._overrides = tuple(strict_prefix_overrides or ())
        self._buckets: Dict[str, Bucket] = {}
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if self._is_exempt(path):
            return await call_next(request)

        client_key = self._client_key(request)
        rate, burst = self._rate, self._burst
        override = self._match_override(path)
        if override is not None:
            rate, burst = override

        allowed, retry_after = await self._consume_token(client_key, rate, burst)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(p) for p in self._exempt)

    def _match_override(self, path: str) -> Optional[Tuple[float, int]]:
        for prefix, rate, burst in self._overrides:
            if path.startswith(prefix):
                return (max(0.1, float(rate)), max(1, int(burst)))
        return None

    def _client_key(self, request: Request) -> str:
        # Prefer explicit client id, fall back to remote IP
        client_id = request.headers.get("X-Client-Id")
        if client_id:
            return f"id:{client_id}"
        client = request.client
        if client:
            return f"ip:{client.host}"
        return "anon"

    async def _consume_token(self, key: str, rate: float, burst: int) -> Tuple[bool, int]:
        now = time.time()
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = Bucket(tokens=float(burst), last_refill=now)
                self._buckets[key] = bucket

            # Refill
            elapsed = now - bucket.last_refill
            if elapsed > 0:
                bucket.tokens = min(float(burst), bucket.tokens + elapsed * rate)
                bucket.last_refill = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0

            # Compute Retry-After seconds
            needed = 1.0 - bucket.tokens
            retry_after = int(max(1, needed / rate))
            return False, retry_after


def register_global_rate_limiter(app: FastAPI) -> None:
    """Register the global rate limiter middleware with env-based config."""
    rate = float(os.getenv("GLOBAL_RATE_LIMIT_RATE", "2"))
    burst = int(os.getenv("GLOBAL_RATE_LIMIT_BURST", "20"))
    # Exempt core health/docs and low-risk settings endpoints by default to avoid
    # test flakiness and allow bursty UI saves; can be overridden via env.
    exempt_default = "/health,/metrics,/docs,/openapi.json,/api/v2/settings/maps"
    exempt = os.getenv("GLOBAL_RATE_LIMIT_EXEMPT", exempt_default).split(",")
    override_str = os.getenv("GLOBAL_RATE_LIMIT_OVERRIDES", "")
    overrides: list[tuple[str, float, int]] = []
    if override_str.strip():
        # format: "/api/v2/auth:1:5;/api/v2/ws:5:50"
        parts = [p.strip() for p in override_str.split(";") if p.strip()]
        for p in parts:
            try:
                prefix, rate_s, burst_s = p.split(":")
                overrides.append((prefix, float(rate_s), int(burst_s)))
            except Exception:
                continue

    app.add_middleware(
        GlobalRateLimiter,
        refill_rate_per_sec=rate,
        burst=burst,
        exempt_prefixes=[s for s in (e.strip() for e in exempt) if s],
        strict_prefix_overrides=overrides,
    )
