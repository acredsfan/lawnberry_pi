"""Motor command gateway — single software path from desired motion to RoboHAT PWM.

Phase A implements emergency lifecycle. Drive/blade dispatch added in Phase B.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from ..core.http_util import client_key
from .commands import (
    BladeCommand,
    BladeOutcome,
    CommandStatus,
    DriveCommand,
    DriveOutcome,
    EmergencyClear,
    EmergencyOutcome,
    EmergencyTrigger,
)

logger = logging.getLogger(__name__)


class MotorCommandGateway:
    def __init__(
        self,
        safety_state: dict,
        blade_state: dict,
        client_emergency: dict,
        robohat: Any,
        persistence: Any,
        websocket_hub: Any = None,
        config_loader: Any = None,
        _rest_module: Any = None,
    ) -> None:
        self._safety_state = safety_state
        self._blade_state = blade_state
        self._client_emergency = client_emergency
        self._robohat = robohat
        self._persistence = persistence
        self._websocket_hub = websocket_hub
        self._config_loader = config_loader
        self.__rest_module = _rest_module
        self._drive_timeout_task: Any = None

    def _rest(self) -> Any:
        if self.__rest_module is not None:
            return self.__rest_module
        import backend.src.api.rest as _rest
        return _rest

    def is_emergency_active(self, request: Any = None) -> bool:
        try:
            if bool(self._safety_state.get("emergency_stop_active", False)):
                return True
            if time.time() < self._rest()._emergency_until:
                return True
        except Exception:
            return True
        if request is None:
            return False
        try:
            key = client_key(request)
            exp = self._client_emergency.get(key)
            if exp is None:
                return False
            if time.time() < exp:
                return True
            self._client_emergency.pop(key, None)
        except Exception:
            pass
        return False

    async def trigger_emergency(self, cmd: EmergencyTrigger) -> EmergencyOutcome:
        audit_id = str(uuid.uuid4())
        self._safety_state["emergency_stop_active"] = True
        self._safety_state["estop_reason"] = cmd.reason
        self._blade_state["active"] = False
        rest = self._rest()
        rest._emergency_until = time.time() + 0.2
        try:
            rest._legacy_motors_active = False
        except Exception:
            pass
        try:
            if cmd.request is not None:
                self._client_emergency[client_key(cmd.request)] = time.time() + 0.3
        except Exception:
            pass

        hardware_confirmed = True
        robohat = self._robohat
        if robohat and getattr(getattr(robohat, "status", None), "serial_connected", False):
            try:
                hardware_confirmed = await robohat.emergency_stop()
            except Exception:
                hardware_confirmed = False

        return EmergencyOutcome(
            status=CommandStatus.EMERGENCY_LATCHED,
            audit_id=audit_id,
            hardware_confirmed=hardware_confirmed,
        )

    async def clear_emergency(self, cmd: EmergencyClear) -> EmergencyOutcome:
        audit_id = str(uuid.uuid4())
        if not cmd.confirmed:
            return EmergencyOutcome(
                status=CommandStatus.BLOCKED,
                audit_id=audit_id,
                hardware_confirmed=False,
            )
        if not self._safety_state.get("emergency_stop_active", False):
            return EmergencyOutcome(
                status=CommandStatus.ACCEPTED,
                audit_id=audit_id,
                hardware_confirmed=True,
                idempotent=True,
            )
        self._safety_state["emergency_stop_active"] = False
        self._safety_state["estop_reason"] = None
        self._blade_state["active"] = False
        self._rest()._emergency_until = 0.0
        self._client_emergency.clear()

        hardware_confirmed = True
        robohat = self._robohat
        if robohat and getattr(getattr(robohat, "status", None), "serial_connected", False):
            try:
                hardware_confirmed = await robohat.clear_emergency()
            except Exception:
                hardware_confirmed = False

        return EmergencyOutcome(
            status=CommandStatus.ACCEPTED,
            audit_id=audit_id,
            hardware_confirmed=hardware_confirmed,
        )

    async def dispatch_drive(self, cmd: DriveCommand, request: Any = None) -> DriveOutcome:
        raise NotImplementedError("dispatch_drive implemented in Phase B")

    async def dispatch_blade(self, cmd: BladeCommand, request: Any = None) -> BladeOutcome:
        raise NotImplementedError("dispatch_blade implemented in Phase B")

    def reset_for_testing(self) -> None:
        self._safety_state["emergency_stop_active"] = False
        self._safety_state["estop_reason"] = None
        self._blade_state["active"] = False
        self._rest()._emergency_until = 0.0
        self._client_emergency.clear()
