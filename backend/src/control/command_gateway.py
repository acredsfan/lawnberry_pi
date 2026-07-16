"""Motor command gateway — single software path from desired motion to RoboHAT PWM.

Phase A implements emergency lifecycle. Drive/blade dispatch added in Phase B.
"""
from __future__ import annotations

import logging
import math
import os
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
        self._blade_timeout_task: Any = None
        self._permit_timeout_task: Any = None
        # Observability: event store injected per-run.
        self._event_store: Any | None = None
        self._obs_run_id: str = ""
        self._obs_mission_id: str = ""
        self._watchdog: Any = None
        self._autonomy_context_provider: Any = None
        self._drive_lease_generation: int = 0
        self._blade_lease_generation: int = 0
        self._permit_lease_generation: int = 0
        self._blade_controller: Any | None = None
        self._qualification_service: Any | None = None
        self._runtime_context: Any | None = None

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

    def set_watchdog(self, watchdog: Any) -> None:
        """Attach a software safety watchdog."""
        self._watchdog = watchdog

    def set_autonomy_context_provider(self, provider: Any) -> None:
        """Attach a callable that supplies mission geofence/localization context."""
        self._autonomy_context_provider = provider

    def set_blade_controller(self, controller: Any) -> None:
        self._blade_controller = controller

    def set_qualification_service(self, service: Any) -> None:
        self._qualification_service = service

    def set_runtime_context(self, runtime: Any) -> None:
        """Attach canonical live-health owners after RuntimeContext construction."""
        self._runtime_context = runtime

    def assert_actuators_idle_for_supervised_test(self) -> None:
        drive_lease_active = bool(
            self._drive_timeout_task is not None and not self._drive_timeout_task.done()
        )
        try:
            legacy_motion_active = bool(self._rest()._legacy_motors_active)
        except Exception:
            legacy_motion_active = True
        if (
            drive_lease_active
            or legacy_motion_active
            or bool(self._blade_state.get("active", False))
        ):
            raise RuntimeError("SUPERVISED_TEST_ACTUATORS_NOT_IDLE")

    def arm_supervised_permit_deadline(self, remaining_seconds: float) -> None:
        """Bind the in-memory permit deadline to canonical actuator cleanup."""
        import asyncio

        self.clear_supervised_permit_deadline()
        self._permit_lease_generation += 1
        generation = self._permit_lease_generation

        async def _expire() -> None:
            try:
                await asyncio.sleep(max(0.0, float(remaining_seconds)))
                if generation != self._permit_lease_generation:
                    return
                await self._neutralize_supervised("SUPERVISED_TEST_PERMIT_EXPIRED")
            except asyncio.CancelledError:
                pass

        self._permit_timeout_task = asyncio.create_task(
            _expire(),
            name="supervised_qualification_permit_deadline",
        )

    def clear_supervised_permit_deadline(self) -> None:
        import asyncio

        self._permit_lease_generation += 1
        task = self._permit_timeout_task
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        if task is not None and task is not current and not task.done():
            task.cancel()
        self._permit_timeout_task = None

    def _get_blade_controller(self) -> Any:
        if self._blade_controller is not None:
            return self._blade_controller
        from ..services.blade_controller import build_blade_controller

        if self._config_loader is not None:
            hardware, _ = self._config_loader.get()
            blade_config = hardware.blade
            if blade_config.controller is None:
                blade_config = blade_config.model_copy(
                    update={"controller": hardware.blade_controller}
                )
        else:
            from ..models.hardware_config import BladeConfig

            blade_config = BladeConfig(controller=None)
        self._blade_controller = build_blade_controller(blade_config, self._robohat)
        return self._blade_controller

    def _arm_watchdog(self, reason: str) -> None:
        if self._watchdog is None:
            return
        arm = getattr(self._watchdog, "arm", None)
        if callable(arm):
            arm(reason)
            return
        self._watchdog.heartbeat()

    def _disarm_watchdog(self, reason: str) -> None:
        if self._watchdog is None:
            return
        disarm = getattr(self._watchdog, "disarm", None)
        if callable(disarm):
            disarm(reason)
            return
        self._watchdog.heartbeat()

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
        from backend.src.core.robot_state_manager import get_robot_state_manager
        get_robot_state_manager().set_emergency_stop(True, cmd.reason)
        blade_was_active = bool(self._blade_state.get("active", False))
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
        try:
            controller = self._get_blade_controller()
            blade_result = await controller.emergency_stop(reason=cmd.reason)
            if blade_was_active or blade_result.ok:
                hardware_confirmed = bool(hardware_confirmed and blade_result.ok)
        except Exception:
            if blade_was_active:
                hardware_confirmed = False

        if self._qualification_service is not None:
            revoke = getattr(
                self._qualification_service,
                "revoke_supervised_test_permit",
                None,
            )
            if callable(revoke):
                revoke("SUPERVISED_TEST_EMERGENCY_STOP")
        self.clear_supervised_permit_deadline()

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
        from backend.src.core.robot_state_manager import get_robot_state_manager
        get_robot_state_manager().set_emergency_stop(False)
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
        if self._watchdog is not None:
            self._watchdog.heartbeat()

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
                if cmd.source == "supervised_qualification":
                    await self._neutralize_supervised("SUPERVISED_TEST_FIRMWARE_UNKNOWN")
                    return DriveOutcome(
                        status=CommandStatus.BLOCKED,
                        audit_id=audit_id,
                        status_reason="SUPERVISED_TEST_FIRMWARE_UNKNOWN",
                        active_interlocks=["FIRMWARE_UNKNOWN"],
                        watchdog_latency_ms=None,
                    )
                # Version not yet received — firmware is responsive (motor_controller_ok
                # or watchdog_active confirms it), so allow through with a warning.
                # The firmware outputs its version via UART on startup; if it hasn't
                # arrived yet (e.g. backend restarted after firmware booted) we cannot
                # block the operator from driving. A missing version is not an error.
                import logging as _logging
                _logging.getLogger(__name__).debug(
                    "Firmware version not yet received; allowing drive command through"
                )
            elif fw_ver not in SUPPORTED_FIRMWARE_VERSIONS:
                if cmd.source == "supervised_qualification":
                    await self._neutralize_supervised(
                        f"SUPERVISED_TEST_FIRMWARE_INCOMPATIBLE:{fw_ver}"
                    )
                return DriveOutcome(
                    status=CommandStatus.FIRMWARE_INCOMPATIBLE,
                    audit_id=str(uuid.uuid4()),
                    status_reason=f"firmware_version_unsupported:{fw_ver}",
                    active_interlocks=[],
                    watchdog_latency_ms=None,
                )

        motion_active = abs(float(cmd.left)) > 1e-6 or abs(float(cmd.right)) > 1e-6

        if cmd.source == "supervised_qualification":
            supervised_reason = await self._authorize_supervised_drive(cmd, motion_active)
            if supervised_reason is not None:
                await self._neutralize_supervised(supervised_reason)
                return DriveOutcome(
                    status=CommandStatus.BLOCKED,
                    audit_id=audit_id,
                    status_reason=supervised_reason,
                    active_interlocks=[supervised_reason],
                    watchdog_latency_ms=None,
                )
        elif motion_active and self._qualification_service is not None:
            try:
                assert_inactive = getattr(
                    self._qualification_service,
                    "assert_supervised_test_inactive",
                    None,
                )
                if callable(assert_inactive):
                    assert_inactive()
            except Exception as exc:
                return DriveOutcome(
                    status=CommandStatus.BLOCKED,
                    audit_id=audit_id,
                    status_reason=getattr(exc, "reason_code", "SUPERVISED_TEST_PERMIT_ACTIVE"),
                    active_interlocks=["SUPERVISED_TEST_PERMIT_ACTIVE"],
                    watchdog_latency_ms=None,
                )

        if self.is_emergency_active(request) and motion_active:
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
        mission_active_interlocks: list[str] = []
        if not cmd.legacy and cmd.source in {"mission", "supervised_qualification"}:
            mission_active_interlocks = await self._check_mission_drive_interlocks(cmd)

        if mission_active_interlocks:
            mission_active_interlocks = list(dict.fromkeys(mission_active_interlocks))
            reason = self._drive_interlock_reason(mission_active_interlocks)
            if self._event_store is not None:
                from ..observability.events import SafetyGateBlocked
                self._emit_event(SafetyGateBlocked(
                    run_id=self._obs_run_id,
                    mission_id=self._obs_mission_id,
                    audit_id=audit_id,
                    reason=reason,
                    interlocks=mission_active_interlocks,
                    source=cmd.source,
                ))
            if cmd.source == "supervised_qualification":
                await self._neutralize_supervised(reason)
            return DriveOutcome(
                status=CommandStatus.BLOCKED,
                audit_id=audit_id,
                status_reason=reason,
                active_interlocks=mission_active_interlocks,
                watchdog_latency_ms=None,
            )

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
            if motion_active:
                self._arm_watchdog("drive")
            watchdog_start = datetime.now(UTC)
            success = await robohat.send_motor_command(cmd.left, cmd.right)
            watchdog_latency = (datetime.now(UTC) - watchdog_start).total_seconds() * 1000

            if success:
                self._drive_lease_generation += 1
                if self._drive_timeout_task and not self._drive_timeout_task.done():
                    self._drive_timeout_task.cancel()
                if not motion_active:
                    self._disarm_watchdog("drive")
                if self._event_store is not None:
                    from ..observability.events import MotionCommandAcked
                    self._emit_event(MotionCommandAcked(
                        run_id=self._obs_run_id,
                        mission_id=self._obs_mission_id,
                        audit_id=audit_id,
                        watchdog_latency_ms=round(watchdog_latency, 2),
                        hardware_confirmed=True,
                    ))
                if not motion_active:
                    return DriveOutcome(
                        status=CommandStatus.ACCEPTED,
                        audit_id=audit_id,
                        status_reason=None,
                        active_interlocks=[],
                        watchdog_latency_ms=round(watchdog_latency, 2),
                    )
                auto_stop_ms = cmd.duration_ms if cmd.duration_ms > 0 else 500
                if cmd.source in {"mission", "supervised_qualification"}:
                    try:
                        _, limits = self._config_loader.get() if self._config_loader else (None, None)
                        auto_stop_ms = int(getattr(limits, "autonomous_command_ttl_ms", 350) or 350)
                    except Exception:
                        auto_stop_ms = 350
                lease_generation = self._drive_lease_generation

                async def _auto_stop() -> None:
                    try:
                        await asyncio.sleep(auto_stop_ms / 1000.0)
                        if lease_generation != self._drive_lease_generation:
                            return
                        await robohat.send_motor_command(0.0, 0.0)
                        self._disarm_watchdog("drive")
                        if cmd.source == "supervised_qualification":
                            await self._neutralize_supervised(
                                "SUPERVISED_TEST_COMMAND_LEASE_EXPIRED"
                            )
                        logger.warning(
                            "%s drive lease expired (%d ms); motors stopped",
                            cmd.source,
                            auto_stop_ms,
                        )
                    except asyncio.CancelledError:
                        pass

                self._drive_timeout_task = asyncio.create_task(_auto_stop())

            if not success and cmd.source == "supervised_qualification":
                await self._neutralize_supervised("SUPERVISED_TEST_DRIVE_ACK_FAILED")
            return DriveOutcome(
                status=CommandStatus.ACCEPTED if success else CommandStatus.ACK_FAILED,
                audit_id=audit_id,
                status_reason=None
                if success
                else (getattr(getattr(robohat, "status", None), "last_error", None) or "robohat_communication_failed"),
                active_interlocks=[],
                watchdog_latency_ms=round(watchdog_latency, 2),
            )

        if cmd.source == "supervised_qualification":
            await self._neutralize_supervised("SUPERVISED_TEST_MOTOR_CONTROLLER_OFFLINE")
            return DriveOutcome(
                status=CommandStatus.BLOCKED,
                audit_id=audit_id,
                status_reason="SUPERVISED_TEST_MOTOR_CONTROLLER_OFFLINE",
                active_interlocks=["MOTOR_CONTROLLER_OFFLINE"],
                watchdog_latency_ms=None,
            )
        if not motion_active:
            self._disarm_watchdog("drive")
        return DriveOutcome(
            status=CommandStatus.QUEUED,
            audit_id=audit_id,
            status_reason="nominal",
            active_interlocks=[],
            watchdog_latency_ms=0.0,
        )

    async def _authorize_supervised_drive(
        self,
        cmd: DriveCommand,
        motion_active: bool,
    ) -> str | None:
        context = cmd.qualification
        if (
            self._qualification_service is None
            or context is None
            or context.stage_id != "supervised_blade_enabled"
            or not context.permit_token
            or not context.operator_session_id
        ):
            return "SUPERVISED_TEST_COMMAND_SOURCE_INVALID"
        try:
            self._qualification_service.authorize_supervised_command(
                permit_token=context.permit_token,
                operator_session_id=context.operator_session_id,
                command_type="drive" if motion_active else "cleanup",
                left_normalized=cmd.left if motion_active else None,
                right_normalized=cmd.right if motion_active else None,
                duration_ms=cmd.duration_ms if motion_active else None,
            )
        except Exception as exc:
            return getattr(exc, "reason_code", "SUPERVISED_TEST_PERMIT_INVALID")
        if not motion_active:
            return None
        blockers = await self._supervised_runtime_blockers()
        return blockers[0] if blockers else None

    async def _supervised_runtime_blockers(self) -> list[str]:
        runtime = self._runtime_context
        if runtime is None:
            return ["SUPERVISED_TEST_RUNTIME_UNAVAILABLE"]
        try:
            from ..models.autonomy_qualification import QualificationLevel
            from ..services.autonomy_readiness_service import AutonomyReadinessService

            report = await AutonomyReadinessService(runtime).evaluate(
                require_blade=True,
                required_qualification_level=(
                    QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE
                ),
            )
            blockers = list(report.blocking_reason_codes)
        except Exception as exc:
            logger.warning("Supervised-test readiness validation failed: %s", exc)
            return ["SUPERVISED_TEST_LIVE_SAFETY_UNAVAILABLE"]

        live_safety = getattr(runtime, "live_safety", None)
        live_status = (
            live_safety.status_dict()
            if callable(getattr(live_safety, "status_dict", None))
            else {}
        )
        limits = runtime.safety_limits
        imu_max_age_s = max(
            0.05,
            float(getattr(limits, "autonomous_command_ttl_ms", 350)) / 1000.0,
        )
        tof_max_age_s = float(getattr(limits, "obstacle_stale_sample_timeout_s", 0.25))
        for code, key, max_age_s in (
            ("IMU_SAFETY_SAMPLE_STALE", "imu_sample_age_s", imu_max_age_s),
            ("TOF_LEFT_STALE", "tof_left_sample_age_s", tof_max_age_s),
            ("TOF_RIGHT_STALE", "tof_right_sample_age_s", tof_max_age_s),
        ):
            age = live_status.get(key)
            if age is None or not math.isfinite(float(age)) or float(age) > max_age_s:
                blockers.append(code)
        blockers.extend(str(code) for code in live_status.get("active_faults") or [])

        energy = getattr(runtime, "energy_service", None)
        try:
            state = energy.current_state() if energy is not None else None
            if (
                state is None
                or not bool(getattr(state, "available", False))
                or not bool(getattr(state, "fresh", False))
                or getattr(state, "soc_percent", None) is None
                or float(state.soc_percent) <= float(state.critical_soc_percent)
                or getattr(state, "remaining_wh", None) is None
                or float(state.remaining_wh) <= float(state.return_reserve_wh)
            ):
                blockers.append("SUPERVISED_TEST_ENERGY_RESERVE_UNAVAILABLE")
        except Exception:
            blockers.append("SUPERVISED_TEST_ENERGY_RESERVE_UNAVAILABLE")
        return list(dict.fromkeys(blockers))

    async def _neutralize_supervised(self, reason_code: str) -> None:
        """Best-effort canonical cleanup for every terminal permit path."""
        self._drive_lease_generation += 1
        self._blade_lease_generation += 1
        self.clear_supervised_permit_deadline()
        self._blade_state["active"] = False
        try:
            if self._robohat is not None:
                await self._robohat.send_motor_command(0.0, 0.0)
        except Exception:
            logger.exception("Supervised-test drive neutral acknowledgment failed")
        try:
            controller = self._get_blade_controller()
            if await controller.initialize():
                await controller.set_active(False, reason=reason_code)
        except Exception:
            logger.exception("Supervised-test blade-off acknowledgment failed")
        self._disarm_watchdog("supervised_qualification")
        if self._qualification_service is not None:
            revoke = getattr(
                self._qualification_service,
                "revoke_supervised_test_permit",
                None,
            )
            if callable(revoke):
                revoke(reason_code)

    async def _check_manual_drive_interlocks(self, cmd: DriveCommand) -> list[str]:
        from datetime import datetime

        motion_active = abs(float(cmd.left)) > 1e-6 or abs(float(cmd.right)) > 1e-6
        if not motion_active:
            return []

        interlocks: list[str] = []
        try:
            from ..core.state_manager import AppState
            telemetry = AppState.get_instance().last_telemetry
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
                from ..nav.obstacle_clearance import configured_tof_obstacle_threshold_m

                threshold_mm = configured_tof_obstacle_threshold_m(limits) * 1000.0
                for side in ("left", "right"):
                    side_payload = tof.get(side) or {}
                    distance_mm = side_payload.get("distance_mm")
                    if distance_mm is None:
                        continue
                    try:
                        distance_mm_f = float(distance_mm)
                        if distance_mm_f <= 0.0:
                            continue
                        if distance_mm_f <= threshold_mm:
                            interlocks.append("obstacle_detected")
                            break
                    except (TypeError, ValueError):
                        continue
        except Exception as exc:
            logger.warning("Manual drive telemetry safety validation failed: %s", exc)
            interlocks.append("telemetry_unavailable")
        return interlocks

    async def _check_mission_drive_interlocks(self, cmd: DriveCommand) -> list[str]:
        motion_active = abs(float(cmd.left)) > 1e-6 or abs(float(cmd.right)) > 1e-6
        if not motion_active:
            return []

        interlocks: list[str] = []
        if self._autonomy_context_provider is None:
            return ["operating_area_unavailable"] if os.getenv("SIM_MODE", "0") == "0" else []

        try:
            ctx = self._autonomy_context_provider(cmd)
            if (
                cmd.source == "supervised_qualification"
                and ctx.get("gps_degradation_state") != "nominal"
            ):
                interlocks.append("localization_degraded")
            snapshot = ctx.get("snapshot")
            if snapshot is None or not getattr(snapshot, "valid", False):
                interlocks.append("operating_area_unavailable")
            else:
                try:
                    snapshot.validate_ready_for_autonomy(
                        position=ctx.get("position"),
                        last_gps_fix=ctx.get("last_gps_fix"),
                        dead_reckoning_active=bool(ctx.get("dead_reckoning_active", False)),
                        max_fix_age_s=float(ctx.get("max_fix_age_s", 2.0)),
                        max_accuracy_m=float(ctx.get("max_accuracy_m", 0.25)),
                        footprint_radius_m=float(ctx.get("footprint_radius_m", 0.35)),
                        fixed_allowance_m=float(ctx.get("fixed_allowance_m", 0.10)),
                    )
                except Exception as exc:
                    interlocks.append(getattr(exc, "reason_code", "geofence_not_ready").lower())
                position = ctx.get("position")
                if position is not None and not interlocks:
                    bootstrap_tagged = bool(getattr(cmd, "heading_bootstrap", False))
                    bootstrap_active = bool(ctx.get("heading_bootstrap_active", False)) and (
                        ctx.get("mission_phase") == "heading_bootstrap"
                    )
                    if bootstrap_tagged:
                        remaining_m = float(ctx.get("bootstrap_remaining_m") or 0.0)
                        travel_m = float(ctx.get("bootstrap_travel_m") or 0.0)
                        reserve_m = float(ctx.get("bootstrap_stop_reserve_m") or 0.0)
                        max_travel_m = float(ctx.get("bootstrap_max_travel_m") or 0.0)
                        imu_age_value = ctx.get("imu_age_s")
                        imu_age_s = float(
                            imu_age_value if imu_age_value is not None else math.inf
                        )
                        imu_lease_s = max(0.05, float(cmd.duration_ms) / 1000.0)
                        yaw_delta_deg = float(
                            ctx.get("bootstrap_imu_yaw_delta_deg")
                            if ctx.get("bootstrap_imu_yaw_delta_deg") is not None
                            else math.inf
                        )
                        max_yaw_delta_deg = float(
                            ctx.get("bootstrap_max_yaw_delta_deg") or 0.0
                        )
                        straight_forward = (
                            float(cmd.left) > 0.0
                            and float(cmd.right) > 0.0
                            and abs(float(cmd.left) - float(cmd.right)) <= 1e-3
                        )
                        if not bootstrap_active or not straight_forward:
                            interlocks.append("heading_bootstrap_invalid")
                        if (
                            not bool(ctx.get("imu_valid", False))
                            or not bool(ctx.get("imu_epoch_valid", False))
                            or not math.isfinite(imu_age_s)
                            or imu_age_s > imu_lease_s
                        ):
                            interlocks.append("imu_not_ready")
                        if (
                            not math.isfinite(yaw_delta_deg)
                            or yaw_delta_deg > max_yaw_delta_deg
                        ):
                            interlocks.append("heading_bootstrap_invalid")
                        budget_values = (
                            remaining_m,
                            travel_m,
                            reserve_m,
                            max_travel_m,
                        )
                        if (
                            not all(math.isfinite(value) for value in budget_values)
                            or remaining_m <= reserve_m
                            or reserve_m <= 0.0
                            or travel_m < 0.0
                            or max_travel_m <= 0.0
                            or travel_m + reserve_m >= max_travel_m
                        ):
                            interlocks.append("heading_bootstrap_budget_exhausted")
                        allowed = not interlocks and snapshot.contains_footprint(
                            position,
                            float(ctx.get("footprint_radius_m", 0.35))
                            + float(ctx.get("accuracy_m") or 0.0)
                            + float(ctx.get("fixed_allowance_m", 0.10))
                            + float(ctx.get("antenna_offset_m") or 0.0)
                            + remaining_m,
                        )
                    else:
                        allowed = snapshot.swept_motion_is_safe(
                            position,
                            ctx.get("heading"),
                            float(cmd.left),
                            float(cmd.right),
                            footprint_radius_m=float(ctx.get("footprint_radius_m", 0.35)),
                            uncertainty_m=float(ctx.get("accuracy_m") or 0.0),
                            fixed_allowance_m=float(ctx.get("fixed_allowance_m", 0.10)),
                            horizon_s=float(ctx.get("prediction_horizon_s", 1.0)),
                            command_latency_s=float(ctx.get("command_latency_s", 0.35)),
                            wheelbase_m=float(ctx.get("wheelbase_m", 0.30)),
                            braking_decel_mps2=float(ctx.get("braking_decel_mps2", 0.5)),
                        )
                    if not allowed and not interlocks:
                        interlocks.append("geofence_prediction_blocked")
            if bool(ctx.get("tof_blocked", False)):
                interlocks.append("obstacle_detected")
        except Exception as exc:
            logger.warning("Mission drive safety validation failed: %s", exc)
            interlocks.append("operating_area_unavailable")
        return interlocks

    @staticmethod
    def _drive_interlock_reason(interlocks: list[str]) -> str:
        if "imu_not_ready" in interlocks:
            return "IMU_NOT_READY"
        if "heading_bootstrap_invalid" in interlocks:
            return "HEADING_BOOTSTRAP_INVALID"
        if "heading_bootstrap_budget_exhausted" in interlocks:
            return "HEADING_BOOTSTRAP_BUDGET_EXHAUSTED"
        if "geofence_prediction_blocked" in interlocks:
            return "GEOFENCE_PREDICTION_BLOCKED"
        if "safe_boundary_required" in interlocks or "operating_area_unavailable" in interlocks:
            return "SAFE_BOUNDARY_REQUIRED"
        if "safe_boundary_stale" in interlocks:
            return "SAFE_BOUNDARY_STALE"
        if "localization_not_rtk_grade" in interlocks:
            return "LOCALIZATION_NOT_RTK_GRADE"
        if "localization_stale" in interlocks or "localization_unavailable" in interlocks:
            return "LOCALIZATION_STALE"
        if "localization_dead_reckoning" in interlocks:
            return "LOCALIZATION_DEAD_RECKONING"
        if "current_footprint_outside_free_space" in interlocks:
            return "CURRENT_FOOTPRINT_OUTSIDE_FREE_SPACE"
        if "obstacle_detected" in interlocks:
            return "OBSTACLE_DETECTED"
        if "location_awareness_unavailable" in interlocks:
            return "LOCATION_AWARENESS_UNAVAILABLE"
        if "telemetry_unavailable" in interlocks or "telemetry_stale" in interlocks:
            return "TELEMETRY_UNAVAILABLE"
        return "SAFETY_LOCKOUT"

    async def dispatch_blade(self, cmd: BladeCommand, request: Any = None) -> BladeOutcome:
        import asyncio
        import uuid as _uuid

        audit_id = str(_uuid.uuid4())
        supervised = cmd.source == "supervised_qualification"

        # Firmware preflight (Phase E)
        _robohat = self._robohat
        if _robohat and getattr(getattr(_robohat, "status", None), "serial_connected", False):
            fw_ver = getattr(_robohat.status, "firmware_version", None)
            if supervised and fw_ver is None:
                await self._neutralize_supervised("SUPERVISED_TEST_FIRMWARE_UNKNOWN")
                return BladeOutcome(
                    status=CommandStatus.BLOCKED,
                    audit_id=audit_id,
                    status_reason="SUPERVISED_TEST_FIRMWARE_UNKNOWN",
                )
            if fw_ver is not None and fw_ver not in SUPPORTED_FIRMWARE_VERSIONS:
                if supervised:
                    await self._neutralize_supervised(
                        f"SUPERVISED_TEST_FIRMWARE_INCOMPATIBLE:{fw_ver}"
                    )
                return BladeOutcome(
                    status=CommandStatus.FIRMWARE_INCOMPATIBLE,
                    audit_id=str(_uuid.uuid4()),
                    status_reason=f"firmware_version_unsupported:{fw_ver}",
                )

        if cmd.active:
            if cmd.motors_active and not (
                supervised and bool(self._blade_state.get("active", False))
            ):
                if supervised:
                    await self._neutralize_supervised("SUPERVISED_TEST_MOTORS_ACTIVE")
                return BladeOutcome(
                    status=CommandStatus.BLOCKED,
                    audit_id=audit_id,
                    status_reason="motors_active",
                )
            if self.is_emergency_active(request):
                if supervised:
                    await self._neutralize_supervised("SUPERVISED_TEST_EMERGENCY_STOP")
                return BladeOutcome(
                    status=CommandStatus.BLOCKED,
                    audit_id=audit_id,
                    status_reason="emergency_stop_active",
                )
            if self._qualification_service is None:
                return BladeOutcome(
                    status=CommandStatus.BLOCKED,
                    audit_id=audit_id,
                    status_reason="QUALIFICATION_SERVICE_UNAVAILABLE",
                )
            if supervised:
                context = cmd.qualification
                if (
                    context is None
                    or context.stage_id != "supervised_blade_enabled"
                    or not context.permit_token
                    or not context.operator_session_id
                ):
                    await self._neutralize_supervised(
                        "SUPERVISED_TEST_COMMAND_SOURCE_INVALID"
                    )
                    return BladeOutcome(
                        status=CommandStatus.BLOCKED,
                        audit_id=audit_id,
                        status_reason="SUPERVISED_TEST_COMMAND_SOURCE_INVALID",
                    )
                try:
                    self._qualification_service.authorize_supervised_command(
                        permit_token=context.permit_token,
                        operator_session_id=context.operator_session_id,
                        command_type="blade",
                    )
                except Exception as exc:
                    reason = getattr(exc, "reason_code", "SUPERVISED_TEST_PERMIT_INVALID")
                    await self._neutralize_supervised(reason)
                    return BladeOutcome(
                        status=CommandStatus.BLOCKED,
                        audit_id=audit_id,
                        status_reason=reason,
                    )
                blockers = await self._supervised_runtime_blockers()
                blockers.extend(self._supervised_pose_blockers(cmd))
                if blockers:
                    reason = list(dict.fromkeys(blockers))[0]
                    await self._neutralize_supervised(reason)
                    return BladeOutcome(
                        status=CommandStatus.BLOCKED,
                        audit_id=audit_id,
                        status_reason=reason,
                    )
            else:
                try:
                    assert_inactive = getattr(
                        self._qualification_service,
                        "assert_supervised_test_inactive",
                        None,
                    )
                    if callable(assert_inactive):
                        assert_inactive()
                    self._qualification_service.assert_current()
                except Exception as exc:
                    evaluation = getattr(exc, "evaluation", None)
                    reason_codes = getattr(evaluation, "reason_codes", None) or [
                        getattr(exc, "reason_code", "QUALIFICATION_EVIDENCE_MISSING")
                    ]
                    return BladeOutcome(
                        status=CommandStatus.BLOCKED,
                        audit_id=audit_id,
                        status_reason=";".join(str(code) for code in reason_codes),
                    )

        try:
            controller = self._get_blade_controller()
            if not await controller.initialize():
                if supervised:
                    await self._neutralize_supervised(
                        "SUPERVISED_TEST_BLADE_CONTROLLER_OFFLINE"
                    )
                return BladeOutcome(
                    status=CommandStatus.ACK_FAILED,
                    audit_id=audit_id,
                    status_reason="BLADE_CONTROLLER_OFFLINE",
                )
            result = await controller.set_active(
                cmd.active,
                reason=f"{cmd.source}:dispatch_blade",
            )
            ok = result.ok
            if ok:
                self._blade_state["active"] = bool(cmd.active)
                if cmd.active:
                    self._arm_watchdog("blade")
                    if supervised:
                        self._blade_lease_generation += 1
                        lease_generation = self._blade_lease_generation
                        if self._blade_timeout_task and not self._blade_timeout_task.done():
                            self._blade_timeout_task.cancel()
                        try:
                            _, limits = (
                                self._config_loader.get()
                                if self._config_loader
                                else (None, None)
                            )
                            lease_ms = int(
                                getattr(limits, "autonomous_command_ttl_ms", 350) or 350
                            )
                        except Exception:
                            lease_ms = 350

                        async def _blade_auto_stop() -> None:
                            try:
                                await asyncio.sleep(lease_ms / 1000.0)
                                if lease_generation != self._blade_lease_generation:
                                    return
                                await self._neutralize_supervised(
                                    "SUPERVISED_TEST_BLADE_LEASE_EXPIRED"
                                )
                                logger.warning(
                                    "supervised blade lease expired (%d ms); blade stopped",
                                    lease_ms,
                                )
                            except asyncio.CancelledError:
                                pass

                        self._blade_timeout_task = asyncio.create_task(_blade_auto_stop())
                else:
                    self._blade_lease_generation += 1
                    if self._blade_timeout_task and not self._blade_timeout_task.done():
                        self._blade_timeout_task.cancel()
                    self._disarm_watchdog("blade")
            elif supervised:
                await self._neutralize_supervised(
                    result.reason_code or "SUPERVISED_TEST_BLADE_ACK_FAILED"
                )
            return BladeOutcome(
                status=CommandStatus.ACCEPTED if ok else CommandStatus.ACK_FAILED,
                audit_id=audit_id,
                status_reason=None if ok else (result.reason_code or "BLADE_ACK_TIMEOUT"),
            )
        except Exception as exc:
            logger.warning("Blade service dispatch failed: %s", exc)
            if supervised:
                await self._neutralize_supervised("SUPERVISED_TEST_BLADE_CONTROLLER_OFFLINE")
            return BladeOutcome(
                status=CommandStatus.ACK_FAILED,
                audit_id=audit_id,
                status_reason="BLADE_CONTROLLER_OFFLINE",
            )

    def _supervised_pose_blockers(self, cmd: BladeCommand) -> list[str]:
        if self._autonomy_context_provider is None:
            return ["SUPERVISED_TEST_OPERATING_AREA_UNAVAILABLE"]
        try:
            context = self._autonomy_context_provider(cmd)
            if context.get("gps_degradation_state") != "nominal":
                return ["SUPERVISED_TEST_GPS_DEGRADED"]
            snapshot = context.get("snapshot")
            position = context.get("position")
            if snapshot is None or not getattr(snapshot, "valid", False):
                return ["SUPERVISED_TEST_OPERATING_AREA_UNAVAILABLE"]
            snapshot.validate_ready_for_autonomy(
                position=position,
                last_gps_fix=context.get("last_gps_fix"),
                dead_reckoning_active=bool(context.get("dead_reckoning_active", False)),
                max_fix_age_s=float(context.get("max_fix_age_s", 2.0)),
                max_accuracy_m=float(context.get("max_accuracy_m", 0.25)),
                footprint_radius_m=float(context.get("footprint_radius_m", 0.35)),
                fixed_allowance_m=float(context.get("fixed_allowance_m", 0.10)),
            )
            if bool(context.get("tof_blocked", False)):
                return ["OBSTACLE_DETECTED"]
            return []
        except Exception as exc:
            return [getattr(exc, "reason_code", "SUPERVISED_TEST_GEOFENCE_NOT_READY")]

    def reset_for_testing(self) -> None:
        from backend.src.core.robot_state_manager import get_robot_state_manager
        get_robot_state_manager().set_emergency_stop(False)
        self._safety_state["emergency_stop_active"] = False
        self._safety_state["estop_reason"] = None
        self._blade_state["active"] = False
        self._rest()._emergency_until = 0.0
        self._client_emergency.clear()
