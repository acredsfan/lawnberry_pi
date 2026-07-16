from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..hardware.pin_registry import build_pin_allocation_report
from ..hardware.platform_profile import PlatformKind, detect_platform_profile
from ..models.autonomy_qualification import QualificationLevel
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
    snapshot: dict[str, Any] = field(default_factory=dict)

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
            "snapshot": self.snapshot,
        }


class AutonomyReadinessError(RuntimeError):
    def __init__(self, report: AutonomyReadinessReport):
        super().__init__(", ".join(report.blocking_reason_codes) or "AUTONOMY_NOT_READY")
        self.report = report


class AutonomyReadinessService:
    def __init__(self, runtime: Any):
        self._runtime = runtime

    async def evaluate(
        self,
        *,
        require_blade: bool = True,
        mission: Any | None = None,
        required_qualification_level: QualificationLevel = (
            QualificationLevel.FULL_BLADE_AUTONOMY
        ),
    ) -> AutonomyReadinessReport:
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
                    if (
                        required_qualification_level
                        == QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE
                    ):
                        evaluation = qualification.assert_prerequisite_current()
                    else:
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

                owner_running = bool(status.get("tof_acquisition_owner_running"))
                checks.append(
                    ReadinessCheck(
                        code="TOF_ACQUISITION_OWNER_HEALTHY",
                        ok=owner_running,
                        severity="info" if owner_running else "blocker",
                        message=(
                            "Single ToF acquisition owner is running."
                            if owner_running
                            else "Single ToF acquisition owner is not running."
                        ),
                    )
                )
                for side in ("left", "right"):
                    failure_rate = status.get(f"tof_{side}_failure_rate")
                    window_samples = int(status.get(f"tof_{side}_window_samples") or 0)
                    healthy = bool(
                        failure_rate is not None
                        and window_samples >= 5
                        and float(failure_rate) <= 0.25
                    )
                    checks.append(
                        ReadinessCheck(
                            code=f"TOF_{side.upper()}_ACQUISITION_RELIABLE",
                            ok=healthy,
                            severity="info" if healthy else "blocker",
                            message=(
                                f"ToF {side} acquisition failure rate is within limits."
                                if healthy
                                else f"ToF {side} acquisition lacks five samples or exceeds 25% failures."
                            ),
                        )
                    )

        snapshot: dict[str, Any] = {}
        if mission is not None:
            snapshot = await self._evaluate_mission_snapshot(checks, mission)

        ready = not any(not check.ok and check.severity == "blocker" for check in checks)
        return AutonomyReadinessReport(
            ready=ready,
            generated_at=datetime.now(UTC).isoformat(),
            checks=checks,
            pin_report=pin_report.to_dict(),
            blade=blade_health,
            snapshot=snapshot,
        )

    async def assert_ready(
        self,
        *,
        require_blade: bool = True,
        mission: Any | None = None,
    ) -> AutonomyReadinessReport:
        report = await self.evaluate(require_blade=require_blade, mission=mission)
        if not report.ready:
            raise AutonomyReadinessError(report)
        return report

    async def _evaluate_mission_snapshot(
        self,
        checks: list[ReadinessCheck],
        mission: Any,
    ) -> dict[str, Any]:
        """Capture every live fact used to admit one mission.

        Evaluation errors become explicit blockers.  This method never supplies
        fallback values that could be mistaken for live hardware truth.
        """
        snapshot: dict[str, Any] = {"mission_id": getattr(mission, "id", None)}

        def record(
            code: str,
            ok: bool,
            message: str,
            *,
            remediation: str | None = None,
        ) -> None:
            checks.append(
                ReadinessCheck(
                    code=code,
                    ok=ok,
                    severity="info" if ok else "blocker",
                    message=message,
                    remediation=remediation,
                )
            )

        navigation = getattr(self._runtime, "navigation", None)
        localization = getattr(self._runtime, "localization", None)
        pose = None
        if localization is None or not callable(getattr(localization, "canonical_pose", None)):
            record(
                "LOCALIZATION_UNAVAILABLE",
                False,
                "Canonical LocalizationService pose is unavailable.",
            )
            snapshot["localization"] = {"available": False}
        else:
            try:
                pose = localization.canonical_pose()
                pose_payload = pose.to_dict() if hasattr(pose, "to_dict") else pose.model_dump(mode="json")
                snapshot["localization"] = pose_payload
                rtk_fixed = str(getattr(pose, "rtk_status", "")).upper() == "RTK_FIXED"
                max_age = float(getattr(navigation, "autonomous_max_gps_fix_age_s", 2.0))
                max_accuracy = float(
                    getattr(navigation, "autonomous_max_gps_accuracy_m", 0.25)
                )
                pose_ready = bool(
                    getattr(pose, "body_center", None) is not None
                    and getattr(pose, "gps_fix_age_s", None) is not None
                    and float(pose.gps_fix_age_s) <= max_age
                    and getattr(pose, "accuracy_m", None) is not None
                    and float(pose.accuracy_m) <= max_accuracy
                    and not bool(getattr(pose, "dead_reckoning_active", False))
                    and not bool(getattr(pose, "cached", False))
                    and rtk_fixed
                )
                record(
                    "LOCALIZATION_RTK_READY",
                    pose_ready,
                    "Canonical pose is fresh, uncached, RTK fixed, and within accuracy limits."
                    if pose_ready
                    else "Canonical pose is not fresh RTK-fixed live localization.",
                )
                heading_ready = bool(
                    getattr(pose, "heading_deg", None) is not None
                    and getattr(pose, "heading_source", None) not in {None, "unavailable"}
                    and bool(getattr(localization, "imu_valid", False))
                )
                record(
                    "HEADING_READY",
                    heading_ready,
                    "Live IMU-backed heading is ready."
                    if heading_ready
                    else "Live IMU-backed heading is unavailable.",
                )
            except Exception as exc:
                snapshot["localization"] = {"error": type(exc).__name__}
                record(
                    "LOCALIZATION_EVALUATION_FAILED",
                    False,
                    "Canonical localization evaluation failed closed.",
                )

        area = None
        if navigation is None or not callable(
            getattr(navigation, "get_operating_area_snapshot", None)
        ):
            record("SAFE_BOUNDARY_REQUIRED", False, "Operating-area service is unavailable.")
            snapshot["operating_area"] = {"available": False}
        else:
            try:
                area = navigation.get_operating_area_snapshot()
                area_payload = {
                    "valid": bool(getattr(area, "valid", False)),
                    "validity_state": getattr(area, "validity_state", None),
                    "revision": getattr(area, "revision_hash", None),
                    "source": getattr(area, "source", None),
                }
                snapshot["operating_area"] = area_payload
                area_ready = bool(area_payload["valid"])
                record(
                    "OPERATING_AREA_READY",
                    area_ready,
                    "Versioned operating area is valid."
                    if area_ready
                    else "Versioned operating area is invalid or missing.",
                )
                positions = []
                if pose is not None and getattr(pose, "body_center", None) is not None:
                    positions.append(pose.body_center)
                from ..models import Position

                positions.extend(
                    Position(latitude=float(waypoint.lat), longitude=float(waypoint.lon))
                    for waypoint in getattr(mission, "waypoints", [])
                )
                margin = float(getattr(navigation, "coverage_endpoint_clearance_m", 0.25))
                path_ready = bool(
                    area_ready
                    and len(positions) >= 2
                    and area.path_is_safe(positions, margin_m=margin)
                )
                snapshot["path"] = {
                    "waypoint_count": len(getattr(mission, "waypoints", [])),
                    "margin_m": margin,
                    "safe": path_ready,
                }
                record(
                    "MISSION_PATH_SAFE",
                    path_ready,
                    "The complete mission path is inside free space."
                    if path_ready
                    else "The complete current-to-mission path is not proven safe.",
                )
            except Exception as exc:
                snapshot["operating_area"] = {"error": type(exc).__name__}
                record(
                    "OPERATING_AREA_EVALUATION_FAILED",
                    False,
                    "Operating-area evaluation failed closed.",
                )

        nav_state = getattr(navigation, "navigation_state", None)
        obstacle_active = bool(getattr(nav_state, "obstacle_avoidance_active", False))
        obstacle_count = len(getattr(nav_state, "obstacle_map", []) or [])
        snapshot["obstacles"] = {"active": obstacle_active, "mapped_count": obstacle_count}
        record(
            "OBSTACLE_PATH_CLEAR",
            not obstacle_active,
            "No active obstacle is blocking admission."
            if not obstacle_active
            else "An active obstacle blocks mission admission.",
        )

        mission_service = getattr(self._runtime, "mission_service", None)
        conflicts = []
        for mission_id, status in getattr(mission_service, "mission_statuses", {}).items():
            status_value = getattr(getattr(status, "status", None), "value", getattr(status, "status", None))
            if mission_id != getattr(mission, "id", None) and status_value in {"running", "paused"}:
                conflicts.append(mission_id)
        snapshot["mission_conflicts"] = conflicts
        record(
            "NO_MISSION_CONFLICT",
            not conflicts,
            "No other mission is active."
            if not conflicts
            else "Another running or paused mission blocks admission.",
        )

        weather = getattr(self._runtime, "weather_service", None) or getattr(
            navigation, "weather", None
        )
        if weather is None:
            snapshot["weather"] = {"available": False}
            record("WEATHER_STATE_UNAVAILABLE", False, "Weather safety service is unavailable.")
        else:
            try:
                body_center = getattr(pose, "body_center", None) if pose is not None else None
                current = await weather.get_current_async(
                    latitude=getattr(body_center, "latitude", None),
                    longitude=getattr(body_center, "longitude", None),
                )
                advice = weather.get_planning_advice(current)
                snapshot["weather"] = {"current": current, "advice": advice}
                weather_ready = advice.get("advice") == "proceed"
                record(
                    "WEATHER_SAFE_TO_MOW",
                    weather_ready,
                    "Weather inputs permit mowing."
                    if weather_ready
                    else "Weather inputs do not positively permit mowing.",
                )
            except Exception as exc:
                snapshot["weather"] = {"error": type(exc).__name__}
                record("WEATHER_EVALUATION_FAILED", False, "Weather evaluation failed closed.")

        energy = getattr(self._runtime, "energy_service", None)
        if energy is None or not callable(getattr(energy, "admission_snapshot", None)):
            snapshot["energy"] = {"available": False}
            record("ENERGY_STATE_UNAVAILABLE", False, "Canonical energy service is unavailable.")
        else:
            try:
                energy_snapshot = energy.admission_snapshot(mission=mission)
                snapshot["energy"] = energy_snapshot
                record(
                    "ENERGY_RESERVE_READY",
                    bool(energy_snapshot.get("admitted")),
                    "Energy reserve covers the mission and return reserve."
                    if energy_snapshot.get("admitted")
                    else "Energy reserve does not cover the mission and return reserve.",
                )
            except Exception as exc:
                snapshot["energy"] = {"error": type(exc).__name__}
                record("ENERGY_EVALUATION_FAILED", False, "Energy evaluation failed closed.")

        return snapshot
