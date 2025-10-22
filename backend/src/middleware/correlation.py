"""Correlation ID middleware for LawnBerry Pi.

This middleware ensures every inbound HTTP request receives a correlation
identifier that propagates through structured logging, metrics, and responses.
It also records request metrics via the observability subsystem.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.context import reset_correlation_id, set_correlation_id
from ..core.observability import observability


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach and propagate correlation IDs for every HTTP request."""

    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)
        self._logger = observability.get_logger("middleware.correlation")

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        correlation_id = self._get_or_generate_correlation_id(request)
        set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:  # pragma: no cover - re-raise after logging
            duration_ms = (time.perf_counter() - start) * 1000
            observability.record_error(
                origin="http_request",
                message=f"Unhandled exception processing {request.method} {request.url.path}",
                exception=exc,
                metadata={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            self._logger.exception(
                "Unhandled request error", extra={"method": request.method, "path": request.url.path}
            )
            reset_correlation_id()
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        observability.log_api_request(request.method, request.url.path, response.status_code, duration_ms)

        response.headers.setdefault("X-Correlation-ID", correlation_id)
        reset_correlation_id()
        return response

    def _get_or_generate_correlation_id(self, request: Request) -> str:
        header_names = ("X-Correlation-ID", "X-Request-ID", "X-Amzn-Trace-Id")
        for header in header_names:
            value = request.headers.get(header)
            if value:
                return value
        return uuid.uuid4().hex


def register_correlation_middleware(app: FastAPI) -> None:
    """Attach the correlation ID middleware to the FastAPI application."""
    app.add_middleware(CorrelationIdMiddleware)
