from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..hardware.pin_registry import build_pin_allocation_report
from ..hardware.platform_profile import PlatformKind, detect_platform_profile
from ..models.hardware_config import BladeControllerType, HardwareConfig


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
        if require_blade:
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

        blade_health: dict[str, Any] | None = None
        gateway = getattr(self._runtime, "command_gateway", None)
        if require_blade and gateway is not None:
            try:
                blade_controller = gateway._get_blade_controller()
                if await blade_controller.initialize():
                    health = await blade_controller.health()
                    blade_health = health.to_dict()
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

