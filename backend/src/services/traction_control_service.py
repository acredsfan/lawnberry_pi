"""
TractionControlService for LawnBerry Pi v2
Detects motor slipping and traction loss, applies dynamic compensation.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TractionControlState:
    """Track traction control metrics and history."""
    
    # Current wheel speeds (from encoders)
    left_rpm: float = 0.0
    right_rpm: float = 0.0
    
    # Motor command history for comparison
    left_commanded: float = 0.0
    right_commanded: float = 0.0
    
    # Traction loss tracking
    is_left_slipping: bool = False
    is_right_slipping: bool = False
    slip_samples: int = 0
    slip_start_time: float | None = None
    
    # Boost compensation (Stage 1: increase motor power)
    left_boost: float = 0.0
    right_boost: float = 0.0
    max_boost: float = 0.3  # Max 30% boost
    boost_ramp_rate: float = 0.05  # Increase by 5% per control cycle
    
    # Counter-rotation compensation (Stage 2: tank-turn pivot if boost fails)
    counter_rotation_active: bool = False
    counter_rotation_start_time: float | None = None
    counter_rotation_threshold_s: float = 8.0  # Activate after 8s of max boost
    
    # Diagnostics
    last_update: float = 0.0
    total_slip_events: int = 0
    max_boost_timeout_count: int = 0


class TractionControlService:
    """
    Detects and compensates for motor traction loss.
    
    Uses encoder feedback to detect when commanded wheel speeds don't match
    actual motor speeds, indicating slipping or stalled motor. Applies dynamic
    boost to slipping wheels to regain traction.
    
    Safety constraints:
    - Never boost total motor command above max_speed
    - Resets boost if slipping stops
    - Logs all slip events for diagnostics
    """
    
    def __init__(self, 
                 slip_threshold: float = 5.0,  # RPM threshold to declare slipping
                 min_speed_for_detection: float = 0.2,  # Don't test when creeping
                 slip_sample_required: int = 3,  # Require 3 cycles to confirm slip
                 slip_timeout_s: float = 5.0,  # Give up after 5s of max boost
                 counter_rotation_threshold_s: float = 8.0,  # Activate Stage 2 after this long
                 boost_ramp_rate: float = 0.05):  # Increase by 5% per control cycle
        """
        Initialize traction control.
        
        Args:
            slip_threshold: RPM delta that triggers slip detection
            min_speed_for_detection: Ignore slip when commanded speed is very low
            slip_sample_required: Consecutive samples needed to confirm slip
            slip_timeout_s: Time before giving up on slip recovery
            counter_rotation_threshold_s: Time before activating Stage 2 counter-rotation
            boost_ramp_rate: Rate at which to increase motor boost (per cycle)
        """
        self.slip_threshold = slip_threshold
        self.min_speed_for_detection = min_speed_for_detection
        self.slip_sample_required = slip_sample_required
        self.slip_timeout_s = slip_timeout_s
        self.boost_ramp_rate = boost_ramp_rate
        
        self.state = TractionControlState()
        self.state.counter_rotation_threshold_s = counter_rotation_threshold_s
        self.enabled = True
    
    def update_motor_feedback(self, left_rpm: float, right_rpm: float) -> None:
        """Update actual motor speeds from encoders."""
        self.state.left_rpm = left_rpm  # Keep sign for direction
        self.state.right_rpm = right_rpm
        self.state.last_update = time.monotonic()
    
    def record_motor_command(self, left_speed: float, right_speed: float) -> None:
        """Record the motor command sent (for slip detection)."""
        self.state.left_commanded = left_speed
        self.state.right_commanded = right_speed
    
    def detect_slip(self) -> tuple[bool, bool]:
        """
        Detect if either wheel is slipping.
        
        Slip is detected when the commanded wheel speed is significantly higher
        than actual wheel speed (from encoders). This indicates either:
        - Motor stalled or not running (0 RPM)
        - Low traction (wheel spinning in place)
        - Mechanical failure
        
        Returns:
            (is_left_slipping, is_right_slipping)
        """
        if not self.enabled:
            return (False, False)
        
        # Don't test at very low speeds (creeping)
        avg_cmd = (abs(self.state.left_commanded) + abs(self.state.right_commanded)) / 2.0
        if avg_cmd < self.min_speed_for_detection:
            return (False, False)
        
        # Calculate speed mismatch (expected vs actual)
        # For slip detection, we compare:
        # - Expected speed: |commanded_value| * 100 (rough RPM scale)
        # - Actual speed: |encoder_rpm| (actual motor speed)
        # If expected >> actual, wheel is slipping
        
        left_speed_magnitude = abs(self.state.left_rpm)
        right_speed_magnitude = abs(self.state.right_rpm)
        left_cmd_magnitude = abs(self.state.left_commanded) * 100.0  # Scale to RPM-like units
        right_cmd_magnitude = abs(self.state.right_commanded) * 100.0
        
        # Slip when command >> actual (large mismatch = wheel spinning in place)
        left_slipping = (left_cmd_magnitude > self.slip_threshold and 
                        (left_cmd_magnitude - left_speed_magnitude) > self.slip_threshold)
        right_slipping = (right_cmd_magnitude > self.slip_threshold and 
                         (right_cmd_magnitude - right_speed_magnitude) > self.slip_threshold)
        
        return (left_slipping, right_slipping)
    
    def compute_boost(self) -> tuple[float, float]:
        """
        Compute motor boost to apply to compensate for slipping.
        
        Two-stage approach:
        Stage 1 (0-8s): Increase motor power on slipping wheel(s)
        Stage 2 (8s+): If Stage 1 fails to recover traction, activate counter-rotation
                       (spin opposite wheel backward) to create a tank-turn pivot
        
        Returns:
            (left_boost, right_boost) to add to motor commands
        """
        if not self.enabled:
            return (0.0, 0.0)
        
        left_slip, right_slip = self.detect_slip()
        
        # Update slip tracking
        if left_slip or right_slip:
            if self.state.slip_samples == 0:
                self.state.slip_start_time = time.monotonic()
            self.state.slip_samples += 1
        else:
            # Slip cleared
            if self.state.slip_samples >= self.slip_sample_required:
                logger.info(
                    "Traction recovered after %d samples; clearing boost",
                    self.state.slip_samples
                )
                self.state.total_slip_events += 1
            self.state.slip_samples = 0
            self.state.slip_start_time = None
            self.state.left_boost = 0.0
            self.state.right_boost = 0.0
            self.state.counter_rotation_active = False
            self.state.counter_rotation_start_time = None
            return (0.0, 0.0)
        
        # Need N consecutive samples to confirm slip
        if self.state.slip_samples < self.slip_sample_required:
            return (self.state.left_boost, self.state.right_boost)
        
        # Slip confirmed — Stage 1: apply power boost first
        if self.state.slip_samples == self.slip_sample_required:
            logger.warning(
                "Traction loss detected: left_rpm=%.1f right_rpm=%.1f | "
                "left_slip=%s right_slip=%s — Stage 1: applying power boost",
                self.state.left_rpm, self.state.right_rpm,
                left_slip, right_slip
            )
        
        # Stage 1: Ramp up boost gradually (first 8 seconds)
        if left_slip:
            self.state.left_boost = min(
                self.state.max_boost,
                self.state.left_boost + self.boost_ramp_rate
            )
        
        if right_slip:
            self.state.right_boost = min(
                self.state.max_boost,
                self.state.right_boost + self.boost_ramp_rate
            )
        
        # Check if boost has maxed out
        is_boost_maxed = ((self.state.left_boost >= self.state.max_boost - 0.01 or 
                          self.state.right_boost >= self.state.max_boost - 0.01) and
                         self.state.slip_start_time is not None)
        
        if is_boost_maxed:
            elapsed = time.monotonic() - self.state.slip_start_time
            
            # Stage 2 threshold reached: activate counter-rotation if boost alone isn't working
            if (elapsed > self.state.counter_rotation_threshold_s and 
                not self.state.counter_rotation_active):
                logger.warning(
                    "Stage 1 boost maxed for %.1f s without recovery — "
                    "activating Stage 2: counter-rotation pivot",
                    elapsed
                )
                self.state.counter_rotation_active = True
                self.state.counter_rotation_start_time = time.monotonic()
                self.state.max_boost_timeout_count += 1
            
            # Stage 2: Check if counter-rotation has been active too long (give up)
            if self.state.counter_rotation_active and self.state.counter_rotation_start_time:
                counter_elapsed = time.monotonic() - self.state.counter_rotation_start_time
                if counter_elapsed > self.slip_timeout_s:
                    logger.error(
                        "Traction loss persisted %.1f s despite boost + counter-rotation; "
                        "likely mechanical issue or stalled motor — raising error",
                        elapsed
                    )
                    self.state.slip_samples = 0
                    self.state.slip_start_time = None
                    self.state.counter_rotation_active = False
                    raise RuntimeError(
                        f"Motor traction loss: slip persisted {elapsed:.1f}s "
                        "despite boost and counter-rotation — possible stalled motor or mechanical failure"
                    )
        
        return (self.state.left_boost, self.state.right_boost)
    
    def apply_boost_to_command(self, 
                               left_speed: float, 
                               right_speed: float,
                               max_speed: float = 1.0) -> tuple[float, float]:
        """
        Apply traction control boost to motor commands.
        
        Stage 1: Apply power boost to slipping wheel(s)
        Stage 2: If boost fails after 8s, apply counter-rotation (tank-turn pivot)
        
        Args:
            left_speed: Commanded left motor speed (-1.0 to 1.0)
            right_speed: Commanded right motor speed (-1.0 to 1.0)
            max_speed: Maximum allowable motor speed (safety limit)
        
        Returns:
            (boosted_left_speed, boosted_right_speed) clamped to [-max_speed, max_speed]
        """
        self.record_motor_command(left_speed, right_speed)
        
        left_boost, right_boost = self.compute_boost()
        
        # Stage 1: Apply boost with direction preservation
        boosted_left = left_speed + (left_boost if left_speed >= 0 else -left_boost)
        boosted_right = right_speed + (right_boost if right_speed >= 0 else -right_boost)
        
        # Stage 2: If counter-rotation is active, apply tank-turn pivot
        # This means spinning one wheel forward while spinning the other backward
        if self.state.counter_rotation_active:
            left_slip, right_slip = self.detect_slip()
            
            # If left wheel is slipping, spin right wheel backward
            if left_slip and not right_slip:
                logger.debug("Counter-rotation: left slipping — reversing right wheel")
                boosted_right = -max_speed * 0.6  # Reverse at 60% power
            # If right wheel is slipping, spin left wheel backward
            elif right_slip and not left_slip:
                logger.debug("Counter-rotation: right slipping — reversing left wheel")
                boosted_left = -max_speed * 0.6  # Reverse at 60% power
            # If both are slipping, apply mild counter-rotation
            elif left_slip and right_slip:
                logger.debug("Counter-rotation: both slipping — applying mild pivot")
                boosted_left = min(max_speed, boosted_left * 1.2)
                boosted_right = -max_speed * 0.3  # Slight reverse on opposite wheel
        
        # Clamp to max speed
        boosted_left = max(-max_speed, min(max_speed, boosted_left))
        boosted_right = max(-max_speed, min(max_speed, boosted_right))
        
        return (boosted_left, boosted_right)
    
    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information about traction control state."""
        return {
            "enabled": self.enabled,
            "left_rpm": round(self.state.left_rpm, 2),
            "right_rpm": round(self.state.right_rpm, 2),
            "left_commanded": round(self.state.left_commanded, 3),
            "right_commanded": round(self.state.right_commanded, 3),
            "left_slipping": self.state.is_left_slipping,
            "right_slipping": self.state.is_right_slipping,
            "left_boost": round(self.state.left_boost, 3),
            "right_boost": round(self.state.right_boost, 3),
            "slip_samples": self.state.slip_samples,
            "slip_duration_s": (
                time.monotonic() - self.state.slip_start_time
                if self.state.slip_start_time else 0.0
            ),
            "counter_rotation_active": self.state.counter_rotation_active,
            "max_boost_timeout_count": self.state.max_boost_timeout_count,
            "total_slip_events": self.state.total_slip_events,
        }


# Global singleton instance
_instance: TractionControlService | None = None


def get_traction_control_service() -> TractionControlService:
    """Get or create the global traction control service instance."""
    global _instance
    if _instance is None:
        _instance = TractionControlService()
    return _instance
