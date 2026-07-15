"""Mission-owned GPS degradation policy.

The state machine is deliberately side-effect free: it classifies fresh
localization samples and exposes the motion cap/terminal decision.  The
mission executor owns stopping and termination, while MotorCommandGateway's
navigation adapter applies the cap as a final defence-in-depth boundary.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum


class GPSDegradationState(str, Enum):
    NOMINAL = "nominal"
    HOLD = "hold"
    DEAD_RECKONING = "dead_reckoning"
    RECOVERING = "recovering"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class GPSDegradationConfig:
    max_accuracy_m: float = 0.25
    max_fix_age_s: float = 2.0
    hold_grace_s: float = 2.0
    max_degraded_s: float = 15.0
    recovery_samples: int = 5
    degraded_speed_cap_mps: float = 0.20

    def __post_init__(self) -> None:
        if self.max_accuracy_m <= 0 or self.max_fix_age_s <= 0:
            raise ValueError("GPS quality thresholds must be positive")
        if self.hold_grace_s < 0 or self.max_degraded_s <= self.hold_grace_s:
            raise ValueError("GPS degraded timeout must exceed the hold grace period")
        if self.recovery_samples < 1 or self.degraded_speed_cap_mps < 0:
            raise ValueError("GPS recovery samples and speed cap are invalid")


@dataclass(frozen=True)
class GPSDegradationSnapshot:
    state: GPSDegradationState
    reason: str | None
    degraded_for_s: float
    recovery_samples: int
    speed_cap_mps: float | None

    @property
    def terminal(self) -> bool:
        return self.state is GPSDegradationState.TERMINAL

    @property
    def motion_held(self) -> bool:
        return self.state in {
            GPSDegradationState.HOLD,
            GPSDegradationState.RECOVERING,
            GPSDegradationState.TERMINAL,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "degraded_for_s": self.degraded_for_s,
            "recovery_samples": self.recovery_samples,
            "speed_cap_mps": self.speed_cap_mps,
            "terminal": self.terminal,
            "motion_held": self.motion_held,
        }


class GPSDegradationStateMachine:
    """Classify GPS loss with bounded degradation and hysteretic recovery."""

    def __init__(self, config: GPSDegradationConfig | None = None) -> None:
        self.config = config or GPSDegradationConfig()
        self._state = GPSDegradationState.NOMINAL
        self._reason: str | None = None
        self._degraded_at: float | None = None
        self._recovery_samples = 0

    def configure(self, config: GPSDegradationConfig) -> None:
        self.config = config

    def start_mission(self) -> GPSDegradationSnapshot:
        self._state = GPSDegradationState.NOMINAL
        self._reason = None
        self._degraded_at = None
        self._recovery_samples = 0
        return self.snapshot()

    def end_mission(self) -> GPSDegradationSnapshot:
        return self.start_mission()

    def update(
        self,
        *,
        position_available: bool,
        fix_age_s: float | None,
        accuracy_m: float | None,
        dead_reckoning_active: bool,
        now_monotonic: float | None = None,
    ) -> GPSDegradationSnapshot:
        now = time.monotonic() if now_monotonic is None else float(now_monotonic)
        healthy, reason = self._quality(
            position_available=position_available,
            fix_age_s=fix_age_s,
            accuracy_m=accuracy_m,
            dead_reckoning_active=dead_reckoning_active,
        )

        if self._state is GPSDegradationState.TERMINAL:
            return self.snapshot(now)

        if healthy:
            if self._state is GPSDegradationState.NOMINAL:
                self._reason = None
                return self.snapshot(now)
            if self._state is not GPSDegradationState.RECOVERING:
                self._state = GPSDegradationState.RECOVERING
                self._recovery_samples = 1
            else:
                self._recovery_samples += 1
            self._reason = "GPS_RECOVERY_CONFIRMING"
            if self._recovery_samples >= self.config.recovery_samples:
                self._state = GPSDegradationState.NOMINAL
                self._reason = None
                self._degraded_at = None
                self._recovery_samples = 0
            return self.snapshot(now)

        self._reason = reason
        self._recovery_samples = 0
        if self._degraded_at is None:
            self._degraded_at = now
        degraded_for = max(0.0, now - self._degraded_at)
        if degraded_for >= self.config.max_degraded_s:
            self._state = GPSDegradationState.TERMINAL
        elif degraded_for >= self.config.hold_grace_s:
            self._state = GPSDegradationState.DEAD_RECKONING
        else:
            self._state = GPSDegradationState.HOLD
        return self.snapshot(now)

    def snapshot(self, now_monotonic: float | None = None) -> GPSDegradationSnapshot:
        now = time.monotonic() if now_monotonic is None else float(now_monotonic)
        degraded_for = (
            max(0.0, now - self._degraded_at) if self._degraded_at is not None else 0.0
        )
        speed_cap = (
            self.config.degraded_speed_cap_mps
            if self._state is not GPSDegradationState.NOMINAL
            else None
        )
        return GPSDegradationSnapshot(
            state=self._state,
            reason=self._reason,
            degraded_for_s=degraded_for,
            recovery_samples=self._recovery_samples,
            speed_cap_mps=speed_cap,
        )

    def _quality(
        self,
        *,
        position_available: bool,
        fix_age_s: float | None,
        accuracy_m: float | None,
        dead_reckoning_active: bool,
    ) -> tuple[bool, str | None]:
        if not position_available:
            return False, "GPS_POSITION_UNAVAILABLE"
        if dead_reckoning_active:
            return False, "GPS_DEAD_RECKONING_ACTIVE"
        if fix_age_s is None or fix_age_s > self.config.max_fix_age_s:
            return False, "GPS_FIX_STALE"
        if accuracy_m is None or accuracy_m > self.config.max_accuracy_m:
            return False, "GPS_ACCURACY_INSUFFICIENT"
        return True, None


__all__ = [
    "GPSDegradationConfig",
    "GPSDegradationSnapshot",
    "GPSDegradationState",
    "GPSDegradationStateMachine",
]
