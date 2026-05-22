"""Robot State Manager

Maintains canonical RobotState and provides methods to update from
subsystem inputs. Minimal implementation for Phase 1 (T023).
"""

from __future__ import annotations

import datetime
import threading
from typing import Any

from ..models.robot_state import BatteryState, Orientation, Position, RobotState
from .message_bus import MessageBus  # noqa: F401 (future integration)


class RobotStateManager:
    def __init__(self):
        self._state: RobotState = RobotState()
        self._lock = threading.Lock()

    def get_state(self) -> RobotState:
        with self._lock:
            return self._state

    def set_emergency_stop(self, active: bool, reason: str | None = None) -> None:
        """Consolidate emergency stop state thread-safely across all global state systems."""
        with self._lock:
            from ..models.robot_state import NavigationMode
            if active:
                self._state.navigation_mode = NavigationMode.EMERGENCY_STOP
            else:
                if self._state.navigation_mode == NavigationMode.EMERGENCY_STOP:
                    self._state.navigation_mode = NavigationMode.IDLE

            # Synchronize to backend.src.core.globals
            try:
                import backend.src.core.globals as _g
                _g._safety_state["emergency_stop_active"] = active
                _g._safety_state["estop_reason"] = reason
                if not active:
                    _g._emergency_until = 0.0
            except Exception:
                pass

            # Synchronize to AppState
            try:
                from backend.src.core.state_manager import AppState
                AppState.get_instance().safety_state["emergency_stop_active"] = active
                AppState.get_instance().safety_state["estop_reason"] = reason
            except Exception:
                pass

    def update_from_telemetry(self, telemetry: dict[str, Any]) -> RobotState:
        """Update state from a generic telemetry dict (hardware or simulated)."""
        with self._lock:
            st = self._state
            pos = telemetry.get("position") or {}
            batt = telemetry.get("battery") or {}
            imu = telemetry.get("imu") or {}

            # Position
            st.position = Position(
                latitude=pos.get("latitude"),
                longitude=pos.get("longitude"),
                altitude_m=pos.get("altitude"),
                accuracy_m=pos.get("accuracy"),
            )

            # Battery
            st.battery = BatteryState(
                percentage=batt.get("percentage"),
                voltage_v=batt.get("voltage"),
            )

            # Orientation
            st.orientation = Orientation(
                roll_deg=imu.get("roll"),
                pitch_deg=imu.get("pitch"),
                yaw_deg=imu.get("yaw"),
            )

            # Simple derived heading/velocity (unknown by default)
            st.heading_deg = st.heading_deg
            st.velocity_mps = st.velocity_mps

            st.last_updated = datetime.datetime.now(datetime.UTC)
            return st


# Simple module-level singleton for convenience
_manager: RobotStateManager | None = None


def get_robot_state_manager() -> RobotStateManager:
    global _manager
    if _manager is None:
        _manager = RobotStateManager()
    return _manager
