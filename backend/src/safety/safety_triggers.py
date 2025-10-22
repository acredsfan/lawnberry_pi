"""Safety triggers (T051): tilt, obstacle, low battery, high temp.

Centralizes safety interlock activation based on sensor thresholds. Updates the
canonical RobotState via RobotStateManager and exposes helpers to
trigger/clear interlocks. SIM_MODE-safe and lightweight.
"""
from __future__ import annotations

import time
import uuid

from ..core.robot_state_manager import get_robot_state_manager
from ..models.safety_interlock import (
    InterlockState,
    InterlockType,
    SafetyInterlock,
)


_event_handler: callable | None = None


def set_safety_event_handler(handler: callable | None) -> None:
    global _event_handler
    _event_handler = handler


class SafetyTriggerManager:
    def __init__(self) -> None:
        self._active: dict[InterlockType, SafetyInterlock] = {}

    def _now_us(self) -> int:
        return int(time.time() * 1_000_000)

    def _activate(
        self, itype: InterlockType, description: str, value: float | None = None
    ) -> SafetyInterlock:
        existing = self._active.get(itype)
        if existing and existing.state == InterlockState.ACTIVE:
            return existing
        interlock = SafetyInterlock(
            interlock_id=str(uuid.uuid4()),
            interlock_type=itype,
            triggered_at_us=self._now_us(),
            state=InterlockState.ACTIVE,
            trigger_value=value,
            description=description,
        )
        self._active[itype] = interlock
        self._sync_robot_state()
        # Notify event bridge
        try:
            if _event_handler is not None:
                _event_handler("activate", interlock)
        except Exception:
            pass
        return interlock

    def _clear(self, itype: InterlockType) -> None:
        inter = self._active.get(itype)
        if inter and inter.state == InterlockState.ACTIVE:
            inter.state = InterlockState.CLEARED_PENDING_ACK
            inter.cleared_at_us = self._now_us()
            self._sync_robot_state()
            try:
                if _event_handler is not None:
                    _event_handler("clear", inter)
            except Exception:
                pass

    def _sync_robot_state(self) -> None:
        mgr = get_robot_state_manager()
        st = mgr.get_state()
        # Keep only ACTIVE or CLEARED_PENDING_ACK interlocks
        st.active_interlocks = [
            il for il in self._active.values() if il.state != InterlockState.ACKNOWLEDGED
        ]
        st.touch()

    # Public trigger helpers
    def trigger_tilt(
        self, roll_deg: float, pitch_deg: float, threshold_deg: float
    ) -> bool:
        if max(abs(roll_deg), abs(pitch_deg)) >= threshold_deg:
            self._activate(
                InterlockType.TILT_DETECTED,
                "Tilt threshold exceeded",
                max(abs(roll_deg), abs(pitch_deg)),
            )
            return True
        return False

    def clear_tilt(self) -> None:
        self._clear(InterlockType.TILT_DETECTED)

    def trigger_obstacle(self, distance_m: float, threshold_m: float) -> bool:
        if distance_m <= threshold_m:
            self._activate(InterlockType.OBSTACLE_DETECTED, "Obstacle detected by ToF", distance_m)
            return True
        return False

    def clear_obstacle(self) -> None:
        self._clear(InterlockType.OBSTACLE_DETECTED)

    def trigger_low_battery(self, voltage_v: float, threshold_v: float) -> bool:
        if voltage_v <= threshold_v:
            self._activate(InterlockType.LOW_BATTERY, "Battery voltage below threshold", voltage_v)
            return True
        return False

    def clear_low_battery(self) -> None:
        self._clear(InterlockType.LOW_BATTERY)

    def trigger_high_temp(self, temp_c: float, threshold_c: float) -> bool:
        if temp_c >= threshold_c:
            self._activate(InterlockType.HIGH_TEMPERATURE, "High temperature detected", temp_c)
            return True
        return False

    def clear_high_temp(self) -> None:
        self._clear(InterlockType.HIGH_TEMPERATURE)

    def list_active(self) -> list[SafetyInterlock]:
        return list(self._active.values())


_manager: SafetyTriggerManager | None = None


def get_safety_trigger_manager() -> SafetyTriggerManager:
    global _manager
    if _manager is None:
        _manager = SafetyTriggerManager()
    return _manager


__all__ = ["SafetyTriggerManager", "get_safety_trigger_manager", "set_safety_event_handler"]
