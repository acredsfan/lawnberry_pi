"""Request-scoped context helpers.

Provides a lightweight way to share correlation IDs and other security
metadata across services without introducing heavyweight dependencies.
"""

from __future__ import annotations

from contextvars import ContextVar

# Default correlation identifier used when middleware has not populated the value yet.
_DEFAULT_CORRELATION_ID = "anonymous"

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default=_DEFAULT_CORRELATION_ID)


def set_correlation_id(value: str) -> None:
    """Set the correlation ID for the current execution context."""
    _correlation_id.set(value or _DEFAULT_CORRELATION_ID)


def get_correlation_id() -> str:
    """Return the correlation ID for the current execution context."""
    return _correlation_id.get()


def reset_correlation_id() -> None:
    """Reset the correlation ID to the default anonymous value."""
    _correlation_id.set(_DEFAULT_CORRELATION_ID)
