"""Restart-safe, blade-off boundary point verification."""

from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from ..control.commands import BladeCommand, CommandStatus
from ..models import NavigationMode, Position
from ..models.mission import MissionLifecycleStatus, MissionWaypoint
from ..nav.geoutils import haversine_m
from ..nav.localization_helpers import apply_antenna_offset
from .boundary_paths import BOUNDARY_VERIFICATION_SESSION, boundary_file
from .geofence_buffer import boundary_revision_hash
from .parcel_boundary import BoundaryValidationError, normalize_boundary_to_lat_lng
from .stationary_rtk_averaging import collect_live_stationary_rtk_average


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _position_payload(position: Position) -> dict[str, float]:
    return {
        "latitude": float(position.latitude),
        "longitude": float(position.longitude),
    }


def _serialized_mutation(method):
    """Serialize operator mutations so one click can create at most one leg."""

    @wraps(method)
    async def wrapper(self, *args, **kwargs):
        async with self._mutation_lock:
            return await method(self, *args, **kwargs)

    return wrapper


class BoundaryVerificationService:
    """Coordinates operator-paced verification through canonical mission owners."""

    def __init__(
        self,
        *,
        rtk_min_samples: int = 5,
        rtk_duration_s: float = 8.0,
        rtk_interval_s: float = 0.1,
    ) -> None:
        self._rtk_min_samples = max(1, int(rtk_min_samples))
        self._rtk_duration_s = max(0.1, float(rtk_duration_s))
        self._rtk_interval_s = max(0.01, float(rtk_interval_s))
        self._mutation_lock = asyncio.Lock()

    def _read(self) -> dict[str, Any] | None:
        path = boundary_file(BOUNDARY_VERIFICATION_SESSION)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BoundaryValidationError(
                "Boundary verification session is unreadable; cancel and restart it"
            ) from exc

    def _write(self, session: dict[str, Any]) -> dict[str, Any]:
        path = boundary_file(BOUNDARY_VERIFICATION_SESSION)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(session, indent=2), encoding="utf-8")
        tmp.replace(path)
        return session

    @staticmethod
    def _idle_status() -> dict[str, Any]:
        return {
            "status": "idle",
            "points": [],
            "target_index": None,
            "active_mission_id": None,
        }

    async def status(self, runtime: Any | None = None) -> dict[str, Any]:
        """Read and reconcile without racing an in-flight operator mutation."""
        async with self._mutation_lock:
            return await self._status_unlocked(runtime)

    async def _status_unlocked(self, runtime: Any | None = None) -> dict[str, Any]:
        session = self._read()
        if session is None:
            return self._idle_status()
        if runtime is not None:
            session = await self._reconcile_mission(session, runtime)
        return session

    @_serialized_mutation
    async def start(
        self,
        points: list[dict[str, float]],
        runtime: Any,
        *,
        operator_confirmed: bool,
        blade_physically_disabled: bool,
        route_clear_confirmed: bool,
        heading_bootstrap_confirmed: bool,
        physical_intervention: str,
    ) -> dict[str, Any]:
        if not all(
            (
                operator_confirmed,
                blade_physically_disabled,
                route_clear_confirmed,
                heading_bootstrap_confirmed,
            )
        ) or not physical_intervention.strip():
            raise BoundaryValidationError(
                "All physical safety acknowledgements are required before verification"
            )

        existing = await self._status_unlocked(runtime)
        if existing.get("status") == "active":
            raise BoundaryValidationError(
                "A boundary verification session is already active; cancel it first"
            )

        normalized = normalize_boundary_to_lat_lng(points, order="latlng")
        snapshot = runtime.navigation.get_operating_area_snapshot()
        if not snapshot.valid:
            raise BoundaryValidationError(
                f"A current generated safe boundary is required: {snapshot.validity_state}"
            )
        revision = boundary_revision_hash(normalized)
        if snapshot.revision_hash != revision:
            raise BoundaryValidationError(
                "Verification points do not match the boundary used to generate the safe area"
            )

        footprint_m = float(getattr(runtime.navigation, "mower_footprint_radius_m", 0.35))
        fixed_allowance_m = float(
            getattr(runtime.navigation, "geofence_safety_allowance_m", 0.10)
        )
        rtk_allowance_m = 0.05
        verification_margin_m = 0.05
        standoff_m = (
            footprint_m + fixed_allowance_m + rtk_allowance_m + verification_margin_m
        )

        session_points: list[dict[str, Any]] = []
        for index, point in enumerate(normalized):
            reference = Position(
                latitude=float(point["latitude"]),
                longitude=float(point["longitude"]),
            )
            approach = snapshot.safe_approach_position(reference, standoff_m)
            session_points.append(
                {
                    "index": index,
                    "reference": _position_payload(reference),
                    "approach": _position_payload(approach),
                    "status": "pending",
                    "mission_id": None,
                    "mission_lifecycle": None,
                    "error": None,
                    "evidence": None,
                }
            )

        session = {
            "session_id": str(uuid.uuid4()),
            "status": "active",
            "created_at": _now(),
            "updated_at": _now(),
            "target_index": None,
            "active_mission_id": None,
            "operating_area_revision": revision,
            "safe_boundary_buffer_m": float(snapshot.buffer_meters),
            "verification_standoff_m": standoff_m,
            "clearance_model": {
                "mower_footprint_radius_m": footprint_m,
                "fixed_geofence_allowance_m": fixed_allowance_m,
                "stationary_rtk_accuracy_allowance_m": rtk_allowance_m,
                "verification_margin_m": verification_margin_m,
            },
            "physical_acknowledgement": {
                "operator_confirmed": True,
                "blade_physically_disabled": True,
                "route_clear_confirmed": True,
                "heading_bootstrap_confirmed": True,
                "physical_intervention": physical_intervention.strip(),
                "acknowledged_at": _now(),
            },
            "points": session_points,
        }
        return self._write(session)

    @_serialized_mutation
    async def next_point(self, runtime: Any) -> dict[str, Any]:
        session = await self._status_unlocked(runtime)
        if session.get("status") != "active":
            raise BoundaryValidationError("No active boundary verification session")
        if session.get("target_index") is not None:
            raise BoundaryValidationError(
                "Finish, reject, or cancel the current verification point first"
            )

        points = session.get("points") or []
        target = next(
            (
                point
                for point in points
                if point.get("status")
                in {"pending", "rejected", "failed", "interrupted"}
            ),
            None,
        )
        if target is None:
            session["status"] = "complete"
            session["updated_at"] = _now()
            return self._write(session)

        reuse_heading_alignment = bool(
            runtime.navigation.has_reusable_heading_alignment()
        )
        await self._preflight(
            runtime,
            session,
            require_live_heading=reuse_heading_alignment,
        )
        await self._ensure_safe_idle(runtime)
        if not reuse_heading_alignment:
            acknowledged = bool(
                (session.get("physical_acknowledgement") or {}).get(
                    "heading_bootstrap_confirmed"
                )
            )
            if not acknowledged:
                raise BoundaryValidationError(
                    "Restart verification and acknowledge the bounded heading bootstrap"
                )
            runtime.navigation.assert_heading_bootstrap_ready()

        approach = target["approach"]
        waypoint = MissionWaypoint(
            lat=float(approach["latitude"]),
            lon=float(approach["longitude"]),
            blade_on=False,
            speed=20,
            arrival_threshold_m=0.15,
        )
        mission = await runtime.mission_service.create_mission(
            f"Boundary verification point {int(target['index']) + 1}",
            [waypoint],
        )
        target["status"] = "starting"
        target["mission_id"] = mission.id
        target["mission_lifecycle"] = MissionLifecycleStatus.IDLE.value
        target["mission_phase"] = "admitting"
        target["heading_bootstrap_required"] = not reuse_heading_alignment
        target["error"] = None
        session["target_index"] = target["index"]
        session["active_mission_id"] = mission.id
        session["updated_at"] = _now()
        self._write(session)

        try:
            await runtime.mission_service.start_mission(
                mission.id,
                blade_off_diagnostic=True,
                reuse_heading_alignment=reuse_heading_alignment,
            )
        except Exception as exc:
            try:
                await runtime.mission_service.abort_mission(mission.id)
            except Exception:
                pass
            target["status"] = "failed"
            target["error"] = str(exc)
            session["target_index"] = None
            session["active_mission_id"] = None
            session["updated_at"] = _now()
            self._write(session)
            await self._ensure_safe_idle(runtime, raise_on_failure=False)
            raise BoundaryValidationError(f"Verification mission failed to start: {exc}") from exc

        # Let the new task run once, then return the observed lifecycle/phase.
        # This prevents a fast admission failure from being reported as idle.
        await asyncio.sleep(0)
        return await self._reconcile_mission(session, runtime)

    @_serialized_mutation
    async def confirm_point(self, runtime: Any) -> dict[str, Any]:
        session = await self._status_unlocked(runtime)
        target = self._current_point(session)
        if target is None or target.get("status") != "arrived":
            raise BoundaryValidationError(
                "A verification point must be arrived and stopped before confirmation"
            )

        cleanup = await self._ensure_safe_idle(runtime)
        gps = getattr(runtime.sensor_manager, "gps", None)
        if gps is None:
            raise BoundaryValidationError("GPS owner is unavailable")
        result = await collect_live_stationary_rtk_average(
            gps,
            duration_s=self._rtk_duration_s,
            interval_s=self._rtk_interval_s,
            min_samples=self._rtk_min_samples,
            max_accuracy_m=0.05,
            max_speed_mps=0.03,
        )
        if not result.accepted or result.averaged_antenna_coordinate is None:
            reasons = ", ".join(
                f"{key}={value}" for key, value in sorted(result.rejected_reasons.items())
            ) or "not enough unique samples"
            raise BoundaryValidationError(
                f"Stationary live RTK evidence was not accepted: {reasons}"
            )

        heading = getattr(runtime.navigation.navigation_state, "heading", None)
        if not isinstance(heading, (int, float)):
            raise BoundaryValidationError("A live mower heading is required for antenna correction")
        antenna = result.averaged_antenna_coordinate
        hardware = runtime.hardware_config
        center_lat, center_lon = apply_antenna_offset(
            gps_lat=float(antenna["latitude"]),
            gps_lon=float(antenna["longitude"]),
            forward_m=float(getattr(hardware, "gps_antenna_offset_forward_m", 0.0)),
            right_m=float(getattr(hardware, "gps_antenna_offset_right_m", 0.0)),
            heading_deg=float(heading),
        )
        center = {"latitude": center_lat, "longitude": center_lon}
        approach = target["approach"]
        reference = target["reference"]
        target["evidence"] = {
            "captured_at": _now(),
            "drive_stopped": cleanup["drive_stopped"],
            "blade_off_confirmed": cleanup["blade_off_confirmed"],
            "heading_deg": float(heading),
            "averaged_antenna_coordinate": antenna,
            "body_center_coordinate": center,
            "approach_target_residual_m": haversine_m(
                center_lat,
                center_lon,
                float(approach["latitude"]),
                float(approach["longitude"]),
            ),
            "verified_reference_distance_m": haversine_m(
                center_lat,
                center_lon,
                float(reference["latitude"]),
                float(reference["longitude"]),
            ),
            "stationary_rtk": result.to_dict(),
        }
        target["status"] = "confirmed"
        target["error"] = None
        session["target_index"] = None
        session["active_mission_id"] = None
        session["updated_at"] = _now()
        if all(point.get("status") == "confirmed" for point in session.get("points") or []):
            session["status"] = "complete"
        return self._write(session)

    @_serialized_mutation
    async def reject_point(self, runtime: Any) -> dict[str, Any]:
        session = await self._status_unlocked(runtime)
        target = self._current_point(session)
        if target is None or target.get("status") not in {"starting", "traveling", "arrived"}:
            raise BoundaryValidationError("No active or arrived verification point to reject")
        try:
            await self._abort_active_mission(session, runtime)
        finally:
            await self._ensure_safe_idle(runtime, raise_on_failure=False)
        target["status"] = "rejected"
        target["error"] = None
        session["target_index"] = None
        session["active_mission_id"] = None
        session["updated_at"] = _now()
        return self._write(session)

    @_serialized_mutation
    async def cancel(self, runtime: Any) -> dict[str, Any]:
        session = await self._status_unlocked(runtime)
        try:
            await self._abort_active_mission(session, runtime)
        finally:
            cleanup = await self._ensure_safe_idle(runtime, raise_on_failure=False)
        session["status"] = "cancelled"
        session["target_index"] = None
        session["active_mission_id"] = None
        session["cleanup"] = {**cleanup, "at": _now()}
        session["updated_at"] = _now()
        return self._write(session)

    async def _preflight(
        self,
        runtime: Any,
        session: dict[str, Any],
        *,
        require_live_heading: bool = True,
    ) -> None:
        nav = runtime.navigation
        state = nav.navigation_state
        mode = getattr(state.navigation_mode, "value", state.navigation_mode)
        if mode != NavigationMode.IDLE.value:
            raise BoundaryValidationError("Mower navigation must be idle before starting a leg")
        if bool((getattr(runtime, "safety_state", {}) or {}).get("emergency_stop_active")):
            raise BoundaryValidationError("Emergency stop is active")
        if bool(getattr(state, "obstacle_avoidance_active", False)):
            raise BoundaryValidationError("Front ToF reports an obstacle inside stopping clearance")
        self._assert_live_imu(runtime)
        if require_live_heading and not isinstance(
            getattr(state, "heading", None), (int, float)
        ):
            raise BoundaryValidationError(
                "No live heading is available; run the center-yard heading bootstrap first"
            )

        snapshot = nav.get_operating_area_snapshot()
        if not snapshot.valid or snapshot.revision_hash != session.get("operating_area_revision"):
            raise BoundaryValidationError("Safe boundary changed; restart verification")
        try:
            snapshot.validate_ready_for_autonomy(
                position=state.current_position,
                last_gps_fix=state.last_gps_fix,
                dead_reckoning_active=state.dead_reckoning_active,
                max_fix_age_s=float(getattr(nav, "autonomous_max_gps_fix_age_s", 2.0)),
                max_accuracy_m=float(getattr(nav, "autonomous_max_gps_accuracy_m", 0.25)),
                footprint_radius_m=float(getattr(nav, "mower_footprint_radius_m", 0.35)),
                fixed_allowance_m=float(getattr(nav, "geofence_safety_allowance_m", 0.10)),
            )
        except Exception as exc:
            reason = getattr(exc, "reason_code", type(exc).__name__)
            detail = getattr(exc, "detail", str(exc))
            raise BoundaryValidationError(f"{reason}: {detail}") from exc

        gps = getattr(runtime.sensor_manager, "gps", None)
        reading = getattr(gps, "last_reading", None) if gps is not None else None
        if reading is None:
            raise BoundaryValidationError("Live GPS sample is unavailable")
        age_s = (datetime.now(UTC) - reading.timestamp).total_seconds()
        if bool(getattr(reading, "cached", False)) or age_s > 2.0:
            raise BoundaryValidationError("GPS sample is cached or stale; wait for live acquisition")
        if str(getattr(reading, "rtk_status", "")).upper() != "RTK_FIXED":
            raise BoundaryValidationError("RTK fixed status is required")
        if reading.accuracy is None or float(reading.accuracy) > 0.05:
            raise BoundaryValidationError("GPS accuracy must be 0.05 m or better")

    @staticmethod
    def _assert_live_imu(runtime: Any) -> None:
        state = runtime.navigation.navigation_state
        if not bool(getattr(state, "imu_valid", False)):
            raise BoundaryValidationError("IMU_NOT_READY: a valid live IMU sample is required")
        imu = getattr(runtime.sensor_manager, "imu", None)
        reading = getattr(imu, "last_reading", None) if imu is not None else None
        if reading is None:
            raise BoundaryValidationError("IMU_NOT_READY: live IMU owner has no sample")
        yaw = getattr(reading, "yaw", None)
        if not isinstance(yaw, (int, float)) or not math.isfinite(float(yaw)):
            raise BoundaryValidationError("IMU_NOT_READY: live IMU yaw is unavailable")
        timestamp = getattr(reading, "timestamp", None)
        if not isinstance(timestamp, datetime):
            raise BoundaryValidationError("IMU_NOT_READY: IMU sample timestamp is unavailable")
        observed_at = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
        age_s = (datetime.now(UTC) - observed_at).total_seconds()
        if age_s < -1.0 or age_s > 2.0:
            raise BoundaryValidationError("IMU_NOT_READY: IMU sample is stale")
        if str(getattr(reading, "calibration_status", "")).lower() == "uncalibrated":
            raise BoundaryValidationError("IMU_NOT_READY: IMU is uncalibrated")
        if bool(getattr(reading, "cached", False)):
            raise BoundaryValidationError("IMU_NOT_READY: IMU sample is cached")
        received_mono = getattr(reading, "monotonic_received_s", None)
        if not isinstance(received_mono, (int, float)) or not math.isfinite(
            float(received_mono)
        ):
            raise BoundaryValidationError("IMU_NOT_READY: IMU receipt marker is unavailable")
        max_age_s = max(
            0.05,
            float(getattr(runtime.navigation, "autonomous_command_ttl_ms", 350)) / 1000.0,
        )
        if not 0.0 <= time.monotonic() - float(received_mono) <= max_age_s:
            raise BoundaryValidationError("IMU_NOT_READY: IMU sample is stale")
        imu_epoch_id = getattr(reading, "imu_epoch_id", None)
        repository = getattr(runtime, "calibration_repository", None)
        if (
            not isinstance(imu_epoch_id, str)
            or not imu_epoch_id.strip()
            or repository is None
            or getattr(repository, "imu_epoch_id", None) != imu_epoch_id.strip()
        ):
            raise BoundaryValidationError(
                "IMU_NOT_READY: IMU reset generation is not bound to calibration evidence"
            )

    async def _reconcile_mission(
        self,
        session: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any]:
        mission_id = session.get("active_mission_id")
        target = self._current_point(session)
        if mission_id is None or target is None:
            return session
        try:
            status = await runtime.mission_service.get_mission_status(mission_id)
            lifecycle = getattr(status.status, "value", str(status.status))
            detail = getattr(status, "detail", None)
        except Exception as exc:
            lifecycle = "missing"
            detail = str(exc)
        changed = target.get("mission_lifecycle") != lifecycle
        target["mission_lifecycle"] = lifecycle
        mission_phase = target.get("mission_phase")
        if lifecycle == MissionLifecycleStatus.RUNNING.value:
            phase_reader = getattr(runtime.navigation, "get_mission_execution_phase", None)
            if callable(phase_reader):
                mission_phase = phase_reader(mission_id)
            if mission_phase is not None and target.get("mission_phase") != mission_phase:
                target["mission_phase"] = mission_phase
                changed = True
        if (
            lifecycle == MissionLifecycleStatus.RUNNING.value
            and mission_phase == "waypoint"
            and target.get("status") == "starting"
        ):
            changed = True
            target["status"] = "traveling"
        elif lifecycle == MissionLifecycleStatus.COMPLETED.value:
            changed = changed or target.get("status") != "arrived"
            target["status"] = "arrived"
            target["arrived_at"] = target.get("arrived_at") or _now()
            session["active_mission_id"] = None
        elif lifecycle in {
            MissionLifecycleStatus.FAILED.value,
            MissionLifecycleStatus.ABORTED.value,
            MissionLifecycleStatus.PAUSED.value,
            "missing",
        }:
            changed = True
            target["status"] = (
                "failed" if lifecycle == MissionLifecycleStatus.FAILED.value else "interrupted"
            )
            target["error"] = detail or f"Mission ended as {lifecycle}"
            session["target_index"] = None
            session["active_mission_id"] = None
        elif (
            lifecycle == MissionLifecycleStatus.IDLE.value
            and target.get("status") == "starting"
        ):
            changed = True
            target["status"] = "interrupted"
            target["error"] = "Mission was created but not started before restart"
            session["target_index"] = None
            session["active_mission_id"] = None
        if changed:
            session["updated_at"] = _now()
            self._write(session)
        return session

    @staticmethod
    def _current_point(session: dict[str, Any]) -> dict[str, Any] | None:
        target_index = session.get("target_index")
        if target_index is None:
            return None
        return next(
            (
                point
                for point in session.get("points") or []
                if point.get("index") == target_index
            ),
            None,
        )

    async def _abort_active_mission(self, session: dict[str, Any], runtime: Any) -> None:
        mission_id = session.get("active_mission_id")
        if mission_id is None:
            return
        try:
            await runtime.mission_service.abort_mission(mission_id)
        except Exception:
            # Cleanup below still issues canonical zero/blade-off commands.
            pass

    @staticmethod
    async def _ensure_safe_idle(
        runtime: Any,
        *,
        raise_on_failure: bool = True,
    ) -> dict[str, bool]:
        try:
            drive_stopped = bool(await runtime.navigation.stop_navigation())
        except Exception:
            drive_stopped = False

        blade_off_confirmed = not bool(
            (getattr(runtime, "blade_state", {}) or {}).get("active", False)
        )
        gateway = getattr(runtime, "command_gateway", None)
        if gateway is not None:
            try:
                outcome = await gateway.dispatch_blade(
                    BladeCommand(active=False, source="mission")
                )
                blade_off_confirmed = outcome.status == CommandStatus.ACCEPTED
            except Exception:
                blade_off_confirmed = False

        if raise_on_failure and not (drive_stopped and blade_off_confirmed):
            raise BoundaryValidationError(
                "Could not confirm zero drive and blade-off state; verification is blocked"
            )
        return {
            "drive_stopped": drive_stopped,
            "blade_off_confirmed": blade_off_confirmed,
        }


boundary_verification_service = BoundaryVerificationService()


__all__ = ["BoundaryVerificationService", "boundary_verification_service"]
