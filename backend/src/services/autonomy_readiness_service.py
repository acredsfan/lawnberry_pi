from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..hardware.pin_registry import build_pin_allocation_report
from ..hardware.platform_profile import PlatformKind, detect_platform_profile
from ..models.hardware_config import BladeControllerType, HardwareConfig
from .autonomy_qualification_service import AutonomyQualificationError


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    ok: bool
    severity: str
    message: str
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "ok": self.ok,
            "severity": self.severity,
            "message": self.message,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class AutonomyReadinessReport:
    ready: bool
    generated_at: str
    checks: list[ReadinessCheck] = field(default_factory=list)
    pin_report: dict[str, Any] | None = None
    blade: dict[str, Any] | None = None

    @property
    def blocking_reason_codes(self) -> list[str]:
        return [check.code for check in self.checks if not check.ok and check.severity == "blocker"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "generated_at": self.generated_at,
            "blocking_reason_codes": self.blocking_reason_codes,
            "checks": [check.to_dict() for check in self.checks],
            "pin_report": self.pin_report,
            "blade": self.blade,
        }


class AutonomyReadinessError(RuntimeError):
    def __init__(self, report: AutonomyReadinessReport):
        super().__init__(", ".join(report.blocking_reason_codes) or "AUTONOMY_NOT_READY")
        self.report = report


class AutonomyReadinessService:
    def __init__(self, runtime: Any):
        self._runtime = runtime

    async def evaluate(self, *, require_blade: bool = True) -> AutonomyReadinessReport:
        hardware: HardwareConfig = self._runtime.hardware_config
        checks: list[ReadinessCheck] = []
        platform = detect_platform_profile()
        pin_report = build_pin_allocation_report(hardware, platform)

        if not platform.supported:
            checks.append(
                ReadinessCheck(
                    code="UNSUPPORTED_PLATFORM",
                    ok=False,
                    severity="blocker",
                    message=f"Unsupported or unknown Raspberry Pi platform: {platform.model}",
                    remediation="Run on Raspberry Pi 5/4B or set an explicit validated test profile.",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    code="SUPPORTED_PLATFORM",
                    ok=True,
                    severity="info",
                    message=f"Detected {platform.model}",
                )
            )

        if pin_report.conflicts:
            checks.append(
                ReadinessCheck(
                    code="HARDWARE_PIN_CONFLICT",
                    ok=False,
                    severity="blocker",
                    message="Configured GPIO allocations conflict.",
                    remediation="Use the Pi 5 profile as wired or rewire Pi 4B IBT-4 blade to GPIO 26/27.",
                )
            )

        controller = hardware.blade.controller or hardware.blade_controller
        blade_health: dict[str, Any] | None = None
        if require_blade:
            qualification = getattr(self._runtime, "qualification_service", None)
            if qualification is None:
                checks.append(
                    ReadinessCheck(
                        code="QUALIFICATION_SERVICE_UNAVAILABLE",
                        ok=False,
                        severity="blocker",
                        message="Autonomy qualification service is not available.",
                        remediation="Restart backend and verify RuntimeContext wiring.",
                    )
                )
            else:
                try:
                    evaluation = qualification.assert_current()
                    checks.append(
                        ReadinessCheck(
                            code="QUALIFICATION_EVIDENCE_CURRENT",
                            ok=True,
                            severity="info",
                            message=(
                                "Current commit, hardware configuration, limits, runtime, "
                                "and firmware have passing qualification evidence."
                            ),
                        )
                    )
                    blade_health = blade_health or {}
                    blade_health["qualification_record_id"] = (
                        evaluation.record.record_id if evaluation.record else None
                    )
                except AutonomyQualificationError as exc:
                    for code in exc.evaluation.reason_codes:
                        checks.append(
                            ReadinessCheck(
                                code=code,
                                ok=False,
                                severity="blocker",
                                message=f"Qualification evidence blocker: {code}",
                                remediation=exc.evaluation.remediation.get(code),
                            )
                        )

            if controller is None:
                checks.append(
                    ReadinessCheck(
                        code="BLADE_CONTROLLER_OFFLINE",
                        ok=False,
                        severity="blocker",
                        message="No blade controller backend is configured.",
                    )
                )
            elif not hardware.blade.allow_autonomous:
                checks.append(
                    ReadinessCheck(
                        code="BLADE_BACKEND_NOT_AUTONOMY_APPROVED",
                        ok=False,
                        severity="blocker",
                        message="Configured blade backend is not approved for autonomous mowing.",
                        remediation="Set blade.allow_autonomous only after wiring and E-stop validation.",
                    )
                )

        if (
            require_blade
            and controller == BladeControllerType.IBT_4
            and platform.kind is PlatformKind.UNKNOWN
        ):
            checks.append(
                ReadinessCheck(
                    code="UNSUPPORTED_PLATFORM",
                    ok=False,
                    severity="blocker",
                    message="Pi GPIO blade control requires a known Raspberry Pi pin profile.",
                )
            )

        gateway = getattr(self._runtime, "command_gateway", None)
        if require_blade and gateway is not None:
            try:
                blade_controller = gateway._get_blade_controller()
                if await blade_controller.initialize():
                    health = await blade_controller.health()
                    qualification_record_id = (
                        blade_health.get("qualification_record_id")
                        if blade_health is not None
                        else None
                    )
                    blade_health = health.to_dict()
                    if qualification_record_id is not None:
                        blade_health["qualification_record_id"] = qualification_record_id
                    if not health.online:
                        checks.append(
                            ReadinessCheck(
                                code=health.reason_code or "BLADE_CONTROLLER_OFFLINE",
                                ok=False,
                                severity="blocker",
                                message="Blade controller is not online.",
                            )
                        )
                else:
                    checks.append(
                        ReadinessCheck(
                            code="BLADE_CONTROLLER_OFFLINE",
                            ok=False,
                            severity="blocker",
                            message="Blade controller failed to initialize.",
                        )
                    )
            except Exception:
                checks.append(
                    ReadinessCheck(
                        code="BLADE_CONTROLLER_OFFLINE",
                        ok=False,
                        severity="blocker",
                        message="Blade controller health check failed.",
                    )
                )

        robohat = getattr(self._runtime, "robohat", None)
        if getattr(hardware, "motor_controller", None) is not None and robohat is not None:
            status = getattr(robohat, "status", None)
            if not bool(getattr(status, "serial_connected", False)):
                checks.append(
                    ReadinessCheck(
                        code="MOTOR_CONTROLLER_OFFLINE",
                        ok=False,
                        severity="blocker",
                        message="RoboHAT motor controller is not connected.",
                    )
                )

        safety_state = getattr(self._runtime, "safety_state", {}) or {}
        if safety_state.get("emergency_stop_active"):
            checks.append(
                ReadinessCheck(
                    code="ACTIVE_SAFETY_INTERLOCK",
                    ok=False,
                    severity="blocker",
                    message="Emergency stop is active.",
                )
            )

        live_safety = getattr(self._runtime, "live_safety", None)
        if require_blade:
            if live_safety is None:
                checks.append(
                    ReadinessCheck(
                        code="LIVE_SAFETY_LOOP_HEALTHY",
                        ok=False,
                        severity="blocker",
                        message="Live safety coordinator is not available.",
                    )
                )
            else:
                status = (
                    live_safety.status_dict()
                    if callable(getattr(live_safety, "status_dict", None))
                    else {}
                )
                if not bool(status.get("running")):
                    checks.append(
                        ReadinessCheck(
                            code="LIVE_SAFETY_LOOP_HEALTHY",
                            ok=False,
                            severity="blocker",
                            message="Live safety coordinator is not running.",
                        )
                    )
                else:
                    checks.append(
                        ReadinessCheck(
                            code="LIVE_SAFETY_LOOP_HEALTHY",
                            ok=True,
                            severity="info",
                            message="Live safety coordinator is running.",
                        )
                    )

                fast_age = status.get("fast_loop_age_s")
                if fast_age is None or float(fast_age) > 1.0:
                    checks.append(
                        ReadinessCheck(
                            code="LIVE_SAFETY_LOOP_HEALTHY",
                            ok=False,
                            severity="blocker",
                            message="Live safety fast loop has not produced a recent tick.",
                        )
                    )
                for code, key in (
                    ("IMU_SAFETY_SAMPLE_FRESH", "imu_sample_age_s"),
                    ("TOF_LEFT_SAFETY_SAMPLE_FRESH", "tof_left_sample_age_s"),
                    ("TOF_RIGHT_SAFETY_SAMPLE_FRESH", "tof_right_sample_age_s"),
                ):
                    age = status.get(key)
                    if age is None or float(age) > 1.0:
                        checks.append(
                            ReadinessCheck(
                                code=code,
                                ok=False,
                                severity="blocker",
                                message=f"{code} is stale or unavailable.",
                            )
                        )

        ready = not any(not check.ok and check.severity == "blocker" for check in checks)
        return AutonomyReadinessReport(
            ready=ready,
            generated_at=datetime.now(UTC).isoformat(),
            checks=checks,
            pin_report=pin_report.to_dict(),
            blade=blade_health,
        )

    async def assert_ready(self, *, require_blade: bool = True) -> AutonomyReadinessReport:
        report = await self.evaluate(require_blade=require_blade)
        if not report.ready:
            raise AutonomyReadinessError(report)
        return report
