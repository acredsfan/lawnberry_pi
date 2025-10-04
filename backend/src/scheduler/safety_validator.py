from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass
class SafetyCheckResult:
    ok: bool
    reason: str | None = None


class SafetyValidator:
    def validate_pre_job(
        self,
        *,
        estop_engaged: Callable[[], bool],
        active_interlocks: Callable[[], Sequence[str]],
        gps_available: Callable[[], bool],
    ) -> SafetyCheckResult:
        # E-stop must be cleared
        if estop_engaged():
            return SafetyCheckResult(ok=False, reason="E-stop engaged")
        # No active interlocks
        interlocks = list(active_interlocks() or [])
        if len(interlocks) > 0:
            return SafetyCheckResult(ok=False, reason=f"Active interlocks present: {', '.join(interlocks)}")
        # GPS available (basic check)
        if not gps_available():
            return SafetyCheckResult(ok=False, reason="GPS unavailable")
        return SafetyCheckResult(ok=True, reason=None)


__all__ = ["SafetyValidator", "SafetyCheckResult"]
