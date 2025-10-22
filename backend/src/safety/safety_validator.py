from __future__ import annotations

"""Safety configuration validator and startup checks (T120).

Responsibilities:
- Validate SafetyLimits constraints at startup and on-demand
- Log structured results through observability
- Provide a compact health snapshot for /health and monitors

SIM-first: no hardware side effects. This module must not actuate.
"""

from dataclasses import dataclass, asdict
from typing import Any, Tuple

from ..core.observability import observability
from ..core.config_loader import ConfigLoader
from ..models.safety_limits import SafetyLimits


@dataclass
class SafetyValidationReport:
    ok: bool
    detail: str
    limits: dict[str, Any]


def validate_limits(limits: SafetyLimits) -> SafetyValidationReport:
    """Validate semantic relationships beyond Pydantic field validators.

    Pydantic already enforces constitutional ceilings. Here we can add
    cross-field constraints and sanity checks if needed.
    """
    problems: list[str] = []

    # Example cross-check: watchdog must be >= e-stop latency (gives time budget)
    if limits.watchdog_timeout_ms < limits.estop_latency_ms:
        problems.append(
            "watchdog_timeout_ms must be >= estop_latency_ms"
        )

    ok = not problems
    detail = "ok" if ok else "; ".join(problems)

    # Emit structured event
    level = "INFO" if ok else "ERROR"
    observability.record_event(
        event_type="safety",
        level=level,
        message="Safety limits validation" + (" passed" if ok else " failed"),
        origin="safety.validation",
        metadata={
            "problems": problems,
            "limits": limits.model_dump(),
        },
    )

    return SafetyValidationReport(ok=ok, detail=detail, limits=limits.model_dump())


def validate_on_start(loader: ConfigLoader | None = None) -> Tuple[bool, SafetyValidationReport]:
    """Load limits via ConfigLoader and validate; returns (ok, report)."""
    loader = loader or ConfigLoader()
    _hw, limits = loader.get()
    report = validate_limits(limits)
    status = "healthy" if report.ok else "critical"
    observability.log_system_health(
        component="safety_limits",
        status=status,
        details={"detail": report.detail, "limits": report.limits},
    )
    return report.ok, report


def get_health_snapshot(loader: ConfigLoader | None = None) -> dict[str, Any]:
    """Small helper for inclusion in health endpoints if desired."""
    loader = loader or ConfigLoader()
    _hw, limits = loader.get()
    report = validate_limits(limits)
    return {
        "status": "healthy" if report.ok else "critical",
        "detail": report.detail,
        "limits": report.limits,
    }


__all__ = [
    "validate_limits",
    "validate_on_start",
    "SafetyValidationReport",
    "get_health_snapshot",
]
