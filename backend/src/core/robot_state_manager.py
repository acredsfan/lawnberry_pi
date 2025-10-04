"""Robot State Manager

Maintains canonical RobotState and provides methods to update from
subsystem inputs. Minimal implementation for Phase 1 (T023).
"""
from __future__ import annotations

import datetime
from typing import Any

from ..models.robot_state import BatteryState, Orientation, Position, RobotState
from .message_bus import MessageBus  # noqa: F401 (future integration)


class RobotStateManager:
    def __init__(self):
        self._state: RobotState = RobotState()

    def get_state(self) -> RobotState:
        return self._state

    def update_from_telemetry(self, telemetry: dict[str, Any]) -> RobotState:
        """Update state from a generic telemetry dict (hardware or simulated)."""
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
