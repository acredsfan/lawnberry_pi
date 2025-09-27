"""Privacy-aware logging helpers for LawnBerry Pi v2.

Provides a logging Filter that redacts sensitive fields (credentials, tokens,
authorization headers, secrets, API keys) from both structured extras and the
message string. Intended to be ARM64-safe and dependency-free.
"""
from __future__ import annotations
import logging
import re
from typing import Iterable

_STD_KEYS = {
    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
    'module', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
    'thread', 'threadName', 'processName', 'process', 'exc_info', 'exc_text',
    'stack_info', 'getMessage'
}


SENSITIVE_KEYS: tuple[str, ...] = (
    "token",
    "credential",
    "password",
    "authorization",
    "auth",
    "jwt",
    "secret",
    "api_key",
    "apikey",
    "access_key",
    "refresh_token",
)


REDACTED = "[REDACTED]"

# Common sensitive value patterns inside message text
_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(Authorization:\s*Bearer)\s+[^\s]+", re.IGNORECASE),
    re.compile(r"(token[:=]\s*)[^\s,;]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key[:=]\s*)[^\s,;]+", re.IGNORECASE),
    re.compile(r"(password[:=]\s*)[^\s,;]+", re.IGNORECASE),
]


class PrivacyFilter(logging.Filter):
    """Logging filter that redacts sensitive information.

    - Redacts known sensitive keys present as attributes on the LogRecord
      (often provided via `extra=...`).
    - Redacts tokens/keys/passwords present in the message string via regex.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact extras on the record
        for key in list(record.__dict__.keys()):
            if key.lower() in SENSITIVE_KEYS:
                setattr(record, key, REDACTED)
        # Redact message content
        if isinstance(record.msg, str):
            msg = record.msg
            for pat in _PATTERNS:
                msg = pat.sub(lambda m: f"{m.group(1)} {REDACTED}", msg)
            record.msg = msg
        return True


def apply_privacy_filter(logger: logging.Logger) -> None:
    """Attach PrivacyFilter to the provided logger and its handlers."""
    privacy = PrivacyFilter()
    logger.addFilter(privacy)
    for h in logger.handlers:
        h.addFilter(privacy)


class _ExtrasFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = []
        for k, v in record.__dict__.items():
            if k not in _STD_KEYS:
                extras.append(f"{k}={v}")
        if extras:
            return base + " " + " ".join(extras)
        return base


def create_test_logger(stream) -> logging.Logger:
    """Create an isolated logger with privacy filter for tests."""
    import sys
    from logging import StreamHandler, Formatter
    logger = logging.getLogger("privacy_test_logger")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # clear previous handlers
    logger.handlers.clear()
    handler = StreamHandler(stream)
    handler.setFormatter(_ExtrasFormatter('%(message)s'))
    logger.addHandler(handler)
    apply_privacy_filter(logger)
    return logger
