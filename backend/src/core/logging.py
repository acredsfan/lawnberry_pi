"""Privacy-aware logging helpers for LawnBerry Pi v2.

Provides a logging Filter that redacts sensitive fields (credentials, tokens,
authorization headers, secrets, API keys) from both structured extras and the
message string. Intended to be ARM64-safe and dependency-free.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence

REDACTED = "[REDACTED]"

_STD_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "exc_info",
    "exc_text",
    "stack_info",
    "getMessage",
}

DEFAULT_SENSITIVE_KEYS: tuple[str, ...] = (
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

# Backwards compatibility for modules importing the previous constant name.
SENSITIVE_KEYS = DEFAULT_SENSITIVE_KEYS

DEFAULT_REDACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(Authorization:\s*Bearer)\s+[^\s]+", re.IGNORECASE),
    re.compile(r"(token[:=]\s*)[^\s,;]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key[:=]\s*)[^\s,;]+", re.IGNORECASE),
    re.compile(r"(password[:=]\s*)[^\s,;]+", re.IGNORECASE),
)


def _as_pattern(pattern: str | re.Pattern[str]) -> re.Pattern[str]:
    if isinstance(pattern, re.Pattern):
        return pattern
    return re.compile(pattern, re.IGNORECASE)


class PrivacyFilter(logging.Filter):
    """Logging filter that redacts sensitive information.

    Parameters allow extending or replacing the default set of sensitive keys
    and message patterns at runtime (e.g. from configuration files).
    """

    def __init__(
        self,
        *,
        sensitive_keys: Sequence[str] | None = None,
        patterns: Iterable[str | re.Pattern[str]] | None = None,
    ) -> None:
        super().__init__()
        keys = sensitive_keys if sensitive_keys is not None else DEFAULT_SENSITIVE_KEYS
        self._sensitive_keys = {key.lower() for key in keys}
        pattern_source = patterns if patterns is not None else DEFAULT_REDACTION_PATTERNS
        self._patterns: tuple[re.Pattern[str], ...] = tuple(_as_pattern(p) for p in pattern_source)

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact extras on the record
        for key in list(record.__dict__.keys()):
            if key.lower() in self._sensitive_keys:
                setattr(record, key, REDACTED)

        # Redact message content
        if isinstance(record.msg, str):
            msg = record.msg
            for pat in self._patterns:
                msg = pat.sub(lambda match: f"{match.group(1)} {REDACTED}", msg)
            record.msg = msg

        return True


def _normalise_logger_input(
    loggers: logging.Logger | Iterable[logging.Logger],
) -> list[logging.Logger]:
    if isinstance(loggers, logging.Logger):
        return [loggers]
    return list(loggers)


def _merge_sensitive_keys(
    sensitive_keys: Iterable[str] | None,
    *,
    include_defaults: bool,
) -> tuple[str, ...]:
    keys: list[str] = []
    if include_defaults:
        keys.extend(DEFAULT_SENSITIVE_KEYS)
    if sensitive_keys:
        keys.extend(sensitive_keys)
    if not keys:
        # Guarantee minimum safety by falling back to defaults when everything
        # is explicitly disabled.
        keys = list(DEFAULT_SENSITIVE_KEYS)
    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        lowered = key.lower()
        if lowered not in seen:
            seen.add(lowered)
            ordered.append(key)
    return tuple(ordered)


def _merge_patterns(
    patterns: Iterable[str | re.Pattern[str]] | None,
    *,
    include_defaults: bool,
) -> tuple[re.Pattern[str], ...]:
    merged: list[str | re.Pattern[str]] = []
    if include_defaults:
        merged.extend(DEFAULT_REDACTION_PATTERNS)
    if patterns:
        merged.extend(patterns)
    if not merged:
        merged.extend(DEFAULT_REDACTION_PATTERNS)
    return tuple(_as_pattern(pattern) for pattern in merged)


def apply_privacy_filter(
    loggers: logging.Logger | Iterable[logging.Logger],
    *,
    sensitive_keys: Iterable[str] | None = None,
    sensitive_patterns: Iterable[str | re.Pattern[str]] | None = None,
    include_default_keys: bool = True,
    include_default_patterns: bool = True,
) -> PrivacyFilter:
    """Attach a :class:`PrivacyFilter` to the provided logger(s).

    Parameters allow extending or replacing the default redaction behaviour.
    The filter instance is returned so callers can retain a reference if
    necessary (e.g. to remove or introspect it later).
    """

    resolved_keys = _merge_sensitive_keys(
        sensitive_keys,
        include_defaults=include_default_keys,
    )
    resolved_patterns = _merge_patterns(
        sensitive_patterns,
        include_defaults=include_default_patterns,
    )
    privacy = PrivacyFilter(sensitive_keys=resolved_keys, patterns=resolved_patterns)

    for target in _normalise_logger_input(loggers):
        for existing in list(target.filters):
            if isinstance(existing, PrivacyFilter):
                target.removeFilter(existing)
        target.addFilter(privacy)
        for handler in target.handlers:
            for existing in list(handler.filters):
                if isinstance(existing, PrivacyFilter):
                    handler.removeFilter(existing)
            handler.addFilter(privacy)

    return privacy


class _ExtrasFormatter(logging.Formatter):
    """Formatter that appends any non-standard record extras for debugging."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras: list[str] = []
        for key, value in record.__dict__.items():
            if key not in _STD_KEYS:
                extras.append(f"{key}={value}")
        if extras:
            return base + " " + " ".join(extras)
        return base


def create_test_logger(
    stream,
    *,
    level: int = logging.INFO,
    sensitive_keys: Iterable[str] | None = None,
    sensitive_patterns: Iterable[str | re.Pattern[str]] | None = None,
    include_defaults: bool = True,
) -> logging.Logger:
    """Create an isolated logger with privacy filter for tests."""

    logger = logging.getLogger("privacy_test_logger")
    logger.setLevel(level)
    logger.propagate = False
    logger.handlers.clear()

    handler = logging.StreamHandler(stream)
    handler.setFormatter(_ExtrasFormatter("%(message)s"))
    logger.addHandler(handler)

    apply_privacy_filter(
        logger,
        sensitive_keys=sensitive_keys,
        sensitive_patterns=sensitive_patterns,
        include_default_keys=include_defaults,
        include_default_patterns=include_defaults,
    )
    return logger
