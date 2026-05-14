"""TractionControlService — GPS-velocity-based adaptive boost for hill climbing."""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TractionControlState:
    """Underpower tracking state."""

    left_rpm: float = 0.0
    right_rpm: float = 0.0

    commanded_velocity_mps: float = 0.0
    measured_velocity_mps: float = 0.0

    underpower_start_time: float | None = None
    underpower_boost: float = 0.0
    max_boost: float = 0.30
    last_update: float = field(default_factory=time.monotonic)


class TractionControlService:
    """Detects when the mower is underpowered and boosts both wheels symmetrically.

    Compares GPS-measured velocity against commanded velocity.  When measured
    velocity falls below 50% of commanded for >2 s, applies a symmetric 15%
    boost; after 4 s of the same condition, boosts to 30%.  Boost resets when
    measured velocity recovers to >=80% of commanded.

    The boost is applied symmetrically so it does not alter heading — it simply
    increases the throttle level on both wheels equally.  This is appropriate
    for hill climbing where the mower slows under load without wheel slip.
    """

    def __init__(
        self,
        min_speed_for_detection: float = 0.25,
    ) -> None:
        self.min_speed_for_detection = min_speed_for_detection
        self.enabled = True
        self.state = TractionControlState()

    def update_motor_feedback(self, left_rpm: float, right_rpm: float) -> None:
        """Store latest encoder RPM readings (used by diagnostics and Part 3 stuck detector)."""
        self.state.left_rpm = left_rpm
        self.state.right_rpm = right_rpm
        self.state.last_update = time.monotonic()

    def update_velocity_feedback(self, commanded_mps: float, measured_mps: float) -> None:
        """Record commanded vs measured velocity each control tick.

        Starts the underpower timer when the condition first appears so that
        detect_underpower() can compute elapsed time without a separate priming call.
        """
        prev_cmd = self.state.commanded_velocity_mps
        prev_meas = self.state.measured_velocity_mps
        self.state.commanded_velocity_mps = commanded_mps
        self.state.measured_velocity_mps = measured_mps

        # Start underpower timer when condition transitions from clear to active.
        if (
            commanded_mps >= self.min_speed_for_detection
            and measured_mps < 0.5 * commanded_mps
            and self.state.underpower_start_time is None
        ):
            # Also reset if the previous reading was clear (recovery just happened)
            was_clear = (
                prev_cmd < self.min_speed_for_detection
                or prev_meas >= 0.8 * prev_cmd
            )
            if was_clear or prev_cmd == 0.0:
                self.state.underpower_start_time = time.monotonic()
                self.state.underpower_boost = 0.0

    def detect_underpower(self) -> float:
        """Return current underpower boost fraction (0.0, 0.15, or 0.30).

        Stages:
          0   — commanded < min_speed_for_detection OR measured >= 0.8 x commanded
          0.15 — measured < 0.5 x commanded for >= 2 s
          0.30 — measured < 0.5 x commanded for >= 4 s
        """
        if not self.enabled:
            return 0.0

        cmd = self.state.commanded_velocity_mps
        meas = self.state.measured_velocity_mps

        if cmd < self.min_speed_for_detection:
            self._reset_boost()
            return 0.0

        if meas >= 0.8 * cmd:
            self._reset_boost()
            return 0.0

        if meas < 0.5 * cmd:
            now = time.monotonic()
            if self.state.underpower_start_time is None:
                # Grace: timer not yet started (first detect_underpower call without
                # a preceding update_velocity_feedback underpower event)
                self.state.underpower_start_time = now
                self.state.underpower_boost = 0.0
                return 0.0

            elapsed = now - self.state.underpower_start_time
            if elapsed >= 4.0:
                self.state.underpower_boost = 0.30
            elif elapsed >= 2.0:
                self.state.underpower_boost = 0.15
            # else: still in grace period, no boost yet

        return self.state.underpower_boost

    def _reset_boost(self) -> None:
        if self.state.underpower_start_time is not None:
            logger.info(
                "Underpower boost reset: measured=%.2f commanded=%.2f boost=%.2f",
                self.state.measured_velocity_mps,
                self.state.commanded_velocity_mps,
                self.state.underpower_boost,
            )
        self.state.underpower_start_time = None
        self.state.underpower_boost = 0.0

    def apply_boost_to_command(
        self,
        left_speed: float,
        right_speed: float,
        max_speed: float = 1.0,
    ) -> tuple[float, float]:
        """Apply symmetric underpower boost to both wheel commands.

        Scales both wheels by (1 + boost) and clamps to +-max_speed.
        Symmetric scaling preserves the left/right ratio (heading intent).
        """
        boost = self.detect_underpower()
        if boost == 0.0:
            return left_speed, right_speed
        scale = 1.0 + boost
        left_boosted = max(-max_speed, min(max_speed, left_speed * scale))
        right_boosted = max(-max_speed, min(max_speed, right_speed * scale))
        if boost > 0.0:
            logger.debug(
                "Underpower boost %.0f%%: L %.2f->%.2f R %.2f->%.2f",
                boost * 100,
                left_speed,
                left_boosted,
                right_speed,
                right_boosted,
            )
        return left_boosted, right_boosted

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information."""
        return {
            "enabled": self.enabled,
            "left_rpm": round(self.state.left_rpm, 2),
            "right_rpm": round(self.state.right_rpm, 2),
            "commanded_velocity_mps": round(self.state.commanded_velocity_mps, 3),
            "measured_velocity_mps": round(self.state.measured_velocity_mps, 3),
            "underpower_boost": round(self.state.underpower_boost, 3),
            "underpower_duration_s": round(
                time.monotonic() - self.state.underpower_start_time
                if self.state.underpower_start_time is not None
                else 0.0,
                1,
            ),
        }


_instance: TractionControlService | None = None


def get_traction_control_service() -> TractionControlService:
    """Get or create the global traction control service instance."""
    global _instance
    if _instance is None:
        _instance = TractionControlService()
    return _instance
