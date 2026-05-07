"""Motor command gateway — single software path from desired motion to RoboHAT PWM.

Phase A implements emergency lifecycle. Drive/blade dispatch added in Phase B.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC
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

SUPPORTED_FIRMWARE_VERSIONS: frozenset[str] = frozenset({"1.0.0", "1.1.0", "1.2.0", "1.2.1", "1.3.0", "10.0.0"})

ACK_TIMEOUT_S: float = 0.35
ACK_RETRY_COUNT: int = 0


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
        # Observability: event store injected per-run.
        self._event_store: Any | None = None
        self._obs_run_id: str = ""
        self._obs_mission_id: str = ""

    def _rest(self) -> Any:
        if self.__rest_module is not None:
            return self.__rest_module
        import backend.src.api.rest as _rest
        return _rest

    def set_event_store(self, store: Any, run_id: str, mission_id: str) -> None:
        """Attach an EventStore. run_id/mission_id overwritten per mission start."""
        self._event_store = store
        self._obs_run_id = run_id
        self._obs_mission_id = mission_id

    def _emit_event(self, event: Any) -> None:
        if self._event_store is not None:
            try:
                self._event_store.emit(event)
            except Exception:
                pass

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
        import asyncio
        import os
        import uuid as _uuid
        from datetime import datetime

        audit_id = str(_uuid.uuid4())

        # Firmware preflight (Phase E)
        _robohat = self._robohat
        if _robohat and getattr(getattr(_robohat, "status", None), "serial_connected", False):
            fw_ver = getattr(_robohat.status, "firmware_version", None)
            if fw_ver is None:
                return DriveOutcome(
                    status=CommandStatus.FIRMWARE_UNKNOWN,
                    audit_id=str(uuid.uuid4()),
                    status_reason="firmware_version_not_received",
                    active_interlocks=[],
                    watchdog_latency_ms=None,
                )
            if fw_ver not in SUPPORTED_FIRMWARE_VERSIONS:
                return DriveOutcome(
                    status=CommandStatus.FIRMWARE_INCOMPATIBLE,
                    audit_id=str(uuid.uuid4()),
                    status_reason=f"firmware_version_unsupported:{fw_ver}",
                    active_interlocks=[],
                    watchdog_latency_ms=None,
                )

        if self.is_emergency_active(request):
            if self._event_store is not None:
                from ..observability.events import SafetyGateBlocked
                self._emit_event(SafetyGateBlocked(
                    run_id=self._obs_run_id,
                    mission_id=self._obs_mission_id,
                    audit_id=audit_id,
                    reason="emergency_stop_active",
                    interlocks=["emergency_stop_active"],
                    source=cmd.source,
                ))
            return DriveOutcome(
                status=CommandStatus.BLOCKED,
                audit_id=audit_id,
                status_reason="emergency_stop_active",
                active_interlocks=[],
                watchdog_latency_ms=None,
            )

        manual_active_interlocks: list[str] = []
        if (
            not cmd.legacy
            and cmd.source == "manual"
            and os.getenv("SIM_MODE", "0") == "0"
            and self._robohat
            and getattr(getattr(self._robohat, "status", None), "serial_connected", False)
        ):
            manual_active_interlocks = await self._check_manual_drive_interlocks(cmd)

        if manual_active_interlocks:
            manual_active_interlocks = list(dict.fromkeys(manual_active_interlocks))
            if self._event_store is not None:
                from ..observability.events import SafetyGateBlocked
                self._emit_event(SafetyGateBlocked(
                    run_id=self._obs_run_id,
                    mission_id=self._obs_mission_id,
                    audit_id=audit_id,
                    reason=self._drive_interlock_reason(manual_active_interlocks),
                    interlocks=manual_active_interlocks,
                    source=cmd.source,
                ))
            return DriveOutcome(
                status=CommandStatus.BLOCKED,
                audit_id=audit_id,
                status_reason=self._drive_interlock_reason(manual_active_interlocks),
                active_interlocks=manual_active_interlocks,
                watchdog_latency_ms=None,
            )

        # Emit MotionCommandIssued: all safety gates cleared, command proceeds to dispatch.
        if self._event_store is not None:
            from ..observability.events import MotionCommandIssued
            self._emit_event(MotionCommandIssued(
                run_id=self._obs_run_id,
                mission_id=self._obs_mission_id,
                audit_id=audit_id,
                left=cmd.left,
                right=cmd.right,
                source=cmd.source,
                duration_ms=cmd.duration_ms,
            ))

        robohat = self._robohat
        if robohat and getattr(getattr(robohat, "status", None), "serial_connected", False):
            watchdog_start = datetime.now(UTC)
            success = await robohat.send_motor_command(cmd.left, cmd.right)
            watchdog_latency = (datetime.now(UTC) - watchdog_start).total_seconds() * 1000

            if success:
                if self._event_store is not None:
                    from ..observability.events import MotionCommandAcked
                    self._emit_event(MotionCommandAcked(
                        run_id=self._obs_run_id,
                        mission_id=self._obs_mission_id,
                        audit_id=audit_id,
                        watchdog_latency_ms=round(watchdog_latency, 2),
                        hardware_confirmed=True,
                    ))
                auto_stop_ms = cmd.duration_ms if cmd.duration_ms > 0 else 500
                if self._drive_timeout_task and not self._drive_timeout_task.done():
                    self._drive_timeout_task.cancel()

                async def _auto_stop() -> None:
                    try:
                        await asyncio.sleep(auto_stop_ms / 1000.0)
                        await robohat.send_motor_command(0.0, 0.0)
                        logger.warning(
                            "Manual drive duration expired (%d ms); motors stopped", auto_stop_ms
                        )
                    except asyncio.CancelledError:
                        pass

                self._drive_timeout_task = asyncio.create_task(_auto_stop())

            return DriveOutcome(
                status=CommandStatus.ACCEPTED if success else CommandStatus.ACK_FAILED,
                audit_id=audit_id,
                status_reason=None
                if success
                else (getattr(getattr(robohat, "status", None), "last_error", None) or "robohat_communication_failed"),
                active_interlocks=[],
                watchdog_latency_ms=round(watchdog_latency, 2),
            )

        return DriveOutcome(
            status=CommandStatus.QUEUED,
            audit_id=audit_id,
            status_reason="nominal",
            active_interlocks=[],
            watchdog_latency_ms=0.0,
        )

    async def _check_manual_drive_interlocks(self, cmd: DriveCommand) -> list[str]:
        from datetime import datetime

        interlocks: list[str] = []
        try:
            telemetry = await self._websocket_hub.get_cached_telemetry()
            source = telemetry.get("source")
            if source != "hardware":
                interlocks.append("telemetry_unavailable")
                return interlocks

            snapshot_timestamp = telemetry.get("timestamp")
            try:
                snapshot_at = datetime.fromisoformat(str(snapshot_timestamp))
                if snapshot_at.tzinfo is None:
                    snapshot_at = snapshot_at.replace(tzinfo=UTC)
                if (datetime.now(UTC) - snapshot_at).total_seconds() > 2.5:
                    interlocks.append("telemetry_stale")
            except Exception:
                interlocks.append("telemetry_stale")

            position = telemetry.get("position") or {}
            lat = position.get("latitude")
            lon = position.get("longitude")
            acc = position.get("accuracy")
            if lat is None or lon is None or acc is None:
                interlocks.append("location_awareness_unavailable")
            else:
                try:
                    from ..services.navigation_service import NavigationService

                    max_acc = NavigationService.get_instance().max_waypoint_accuracy_m
                    if float(acc) > float(max_acc):
                        interlocks.append("location_awareness_unavailable")
                except Exception:
                    interlocks.append("location_awareness_unavailable")

            if not interlocks or "location_awareness_unavailable" not in interlocks:
                loader = self._config_loader
                if loader is None:
                    from ..core.config_loader import ConfigLoader

                    loader = ConfigLoader()
                _, limits = loader.get()
                tof = telemetry.get("tof") or {}
                threshold_mm = float(limits.tof_obstacle_distance_meters) * 1000.0
                for side in ("left", "right"):
                    side_payload = tof.get(side) or {}
                    distance_mm = side_payload.get("distance_mm")
                    if distance_mm is None:
                        continue
                    try:
                        if float(distance_mm) <= threshold_mm:
                            interlocks.append("obstacle_detected")
                            break
                    except (TypeError, ValueError):
                        continue
        except Exception as exc:
            logger.warning("Manual drive telemetry safety validation failed: %s", exc)
            interlocks.append("telemetry_unavailable")
        return interlocks

    @staticmethod
    def _drive_interlock_reason(interlocks: list[str]) -> str:
        if "obstacle_detected" in interlocks:
            return "OBSTACLE_DETECTED"
        if "location_awareness_unavailable" in interlocks:
            return "LOCATION_AWARENESS_UNAVAILABLE"
        if "telemetry_unavailable" in interlocks or "telemetry_stale" in interlocks:
            return "TELEMETRY_UNAVAILABLE"
        return "SAFETY_LOCKOUT"

    async def dispatch_blade(self, cmd: BladeCommand, request: Any = None) -> BladeOutcome:
        import uuid as _uuid

        audit_id = str(_uuid.uuid4())

        # Firmware preflight (Phase E)
        _robohat = self._robohat
        if _robohat and getattr(getattr(_robohat, "status", None), "serial_connected", False):
            fw_ver = getattr(_robohat.status, "firmware_version", None)
            if fw_ver is None:
                return BladeOutcome(
                    status=CommandStatus.FIRMWARE_UNKNOWN,
                    audit_id=str(_uuid.uuid4()),
                    status_reason="firmware_version_not_received",
                )
            if fw_ver not in SUPPORTED_FIRMWARE_VERSIONS:
                return BladeOutcome(
                    status=CommandStatus.FIRMWARE_INCOMPATIBLE,
                    audit_id=str(_uuid.uuid4()),
                    status_reason=f"firmware_version_unsupported:{fw_ver}",
                )

        if cmd.active:
            if cmd.motors_active:
                return BladeOutcome(
                    status=CommandStatus.BLOCKED,
                    audit_id=audit_id,
                    status_reason="motors_active",
                )
            if self.is_emergency_active(request):
                return BladeOutcome(
                    status=CommandStatus.BLOCKED,
                    audit_id=audit_id,
                    status_reason="emergency_stop_active",
                )

        try:
            from ..services.blade_service import get_blade_service

            bs = get_blade_service()
            await bs.initialize()
            ok = await bs.set_active(cmd.active)
            return BladeOutcome(
                status=CommandStatus.ACCEPTED if ok else CommandStatus.ACK_FAILED,
                audit_id=audit_id,
                status_reason=None if ok else "blade_service_rejected",
            )
        except Exception as exc:
            logger.warning("Blade service dispatch failed: %s", exc)
            return BladeOutcome(
                status=CommandStatus.ACK_FAILED,
                audit_id=audit_id,
                status_reason="blade_service_unavailable",
            )

    def reset_for_testing(self) -> None:
        self._safety_state["emergency_stop_active"] = False
        self._safety_state["estop_reason"] = None
        self._blade_state["active"] = False
        self._rest()._emergency_until = 0.0
        self._client_emergency.clear()
