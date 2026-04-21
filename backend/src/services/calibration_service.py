"""IMU calibration orchestration helpers.

Provides a high-level routine that gently moves the mower through the
orientations the BNO085 expects during its calibration sequence. The routine
is safe to call in SIM_MODE (returns a simulated success) and guards against
concurrent executions so operators cannot stack conflicting calibration runs.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .robohat_service import get_robohat_service

logger = logging.getLogger(__name__)


class CalibrationInProgressError(RuntimeError):
    """Raised when a calibration attempt is already running."""


class DriveControllerUnavailableError(RuntimeError):
    """Raised when no drive controller is available for calibration."""


_CALIBRATION_STATE_TO_SCORE = {
    "fully_calibrated": 3,
    "calibrated": 3,
    "calibrating": 2,
    # "rvc_active": BNO085 is streaming in UART/RVC mode; calibration level is
    # not exposed by the protocol but the sensor is running correctly.
    "rvc_active": 2,
    "partial": 2,
    "unknown": 1,
    "uncalibrated": 0,
    None: 0,
}


def _compute_gps_heading_validation(
    pre: Dict[str, Any], post: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Compare GPS trajectory bearing to raw IMU yaw from forward-sweep snapshots.

    Returns a dict with the GPS bearing, raw IMU yaw, and the suggested
    ``imu_yaw_offset_degrees`` value (= gps_bearing + raw_yaw) that would
    make the navigation heading match the GPS heading.  Returns None if GPS
    data is unavailable or the trajectory was too short for a reliable bearing.
    """
    pre_lat = pre.get("gps_lat")
    pre_lon = pre.get("gps_lon")
    post_lat = post.get("gps_lat")
    post_lon = post.get("gps_lon")
    imu_raw_yaw = post.get("yaw")

    if not all(v is not None for v in [pre_lat, pre_lon, post_lat, post_lon, imu_raw_yaw]):
        return None

    # Compute straight-line distance between GPS snapshots
    lat1 = math.radians(float(pre_lat))
    lat2 = math.radians(float(post_lat))
    dlon = math.radians(float(post_lon) - float(pre_lon))
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    dist_m = 2 * 6_371_000 * math.asin(math.sqrt(a))

    if dist_m < 0.3:
        return {
            "reliable": False,
            "distance_m": round(dist_m, 3),
            "note": "GPS trajectory too short for heading validation (< 0.3 m moved)",
        }

    # Compute haversine bearing (true compass, 0 = North, 90 = East)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    gps_bearing = (math.degrees(math.atan2(x, y)) + 360) % 360

    # Suggested total yaw offset:
    # heading formula:  adjusted = (-raw_yaw + offset) % 360
    # for adjusted == gps_bearing:  offset = gps_bearing + raw_yaw (mod 360)
    suggested_offset = (gps_bearing + float(imu_raw_yaw)) % 360

    return {
        "reliable": True,
        "distance_m": round(dist_m, 3),
        "gps_bearing_degrees": round(gps_bearing, 1),
        "imu_raw_yaw_degrees": round(float(imu_raw_yaw), 1),
        "suggested_imu_yaw_offset_degrees": round(suggested_offset, 1),
        "note": (
            f"Set imu.yaw_offset_degrees={round(suggested_offset, 1)} in config/hardware.yaml "
            f"for correct persistent heading (based on {round(dist_m, 2)} m GPS trajectory). "
            f"Runtime session alignment will converge automatically while driving."
        ),
    }



class IMUCalibrationService:
    """Coordinate IMU calibration manoeuvres and telemetry sampling."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_result: Optional[Dict[str, Any]] = None

    async def run(self, sensor_manager=None) -> Dict[str, Any]:
        """Execute the calibration routine and return a status payload."""
        if self._lock.locked():
            raise CalibrationInProgressError("Calibration already in progress")

        async with self._lock:
            result = await self._execute(sensor_manager)
            self._last_result = result
            return result

    async def _execute(self, sensor_manager=None) -> Dict[str, Any]:
        # Short-circuit in simulation to avoid hardware requirements.
        if os.getenv("SIM_MODE", "0") == "1":
            await asyncio.sleep(0.5)
            ts = datetime.now(timezone.utc).isoformat()
            return {
                "status": "simulated",
                "calibration_status": "fully_calibrated",
                "calibration_score": 3,
                "steps": [],
                "timestamp": ts,
                "notes": "SIM_MODE enabled; returning canned calibration result.",
            }

        robohat = get_robohat_service()
        if robohat is None or not robohat.running or not getattr(robohat.status, "serial_connected", False):
            raise DriveControllerUnavailableError("RoboHAT drive controller is offline")

        from .sensor_manager import SensorManager  # local import to avoid circular deps

        manager = sensor_manager
        if manager is None:
            manager = SensorManager()
            await manager.initialize()

        sequence = [
            {
                "name": "spin_clockwise",
                "description": "Rotate clockwise to excite gyro heading",
                "duration": 4.0,
                "left_speed": 0.35,
                "right_speed": -0.35,
            },
            {
                "name": "spin_counter_clockwise",
                "description": "Rotate counter-clockwise",
                "duration": 4.0,
                "left_speed": -0.35,
                "right_speed": 0.35,
            },
            {
                "name": "forward_sweep",
                "description": "Drive forward slowly to settle accelerometer",
                "duration": 2.5,
                "left_speed": 0.4,
                "right_speed": 0.4,
            },
            {
                "name": "reverse_sweep",
                "description": "Drive backwards gently",
                "duration": 2.5,
                "left_speed": -0.35,
                "right_speed": -0.35,
            },
        ]

        step_results: List[Dict[str, Any]] = []
        start_ts = datetime.now(timezone.utc)

        async def _capture_snapshot() -> Optional[Dict[str, Any]]:
            try:
                snapshot = await manager.read_all_sensors()  # type: ignore[union-attr]
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.debug("Failed to read sensors during calibration: %s", exc)
                return None
            imu = getattr(snapshot, "imu", None)
            gps = getattr(snapshot, "gps", None)
            if imu is None:
                return None
            return {
                "roll": getattr(imu, "roll", None),
                "pitch": getattr(imu, "pitch", None),
                "yaw": getattr(imu, "yaw", None),
                "calibration_status": getattr(imu, "calibration_status", None),
                "calibration_score": _CALIBRATION_STATE_TO_SCORE.get(
                    getattr(imu, "calibration_status", None), 0
                ),
                "gps_lat": getattr(gps, "latitude", None),
                "gps_lon": getattr(gps, "longitude", None),
                "gps_speed": getattr(gps, "speed", None),
            }

        try:
            for step in sequence:
                # For forward_sweep: capture GPS position before driving for heading validation
                pre_sweep_snapshot: Optional[Dict[str, Any]] = None
                if step["name"] == "forward_sweep":
                    pre_sweep_snapshot = await _capture_snapshot()

                accepted = await robohat.send_motor_command(step["left_speed"], step["right_speed"])
                logger.info("IMU calibration step %s accepted=%s", step["name"], accepted)
                await asyncio.sleep(step["duration"])
                sample = await _capture_snapshot()

                step_result: Dict[str, Any] = {
                    "name": step["name"],
                    "description": step["description"],
                    "duration_s": step["duration"],
                    "command_accepted": accepted,
                    "sensor_snapshot": sample,
                }

                # GPS heading validation: compare GPS trajectory bearing to raw IMU yaw
                if pre_sweep_snapshot and sample and step["name"] == "forward_sweep":
                    gps_val = _compute_gps_heading_validation(pre_sweep_snapshot, sample)
                    if gps_val:
                        step_result["gps_heading_validation"] = gps_val
                        logger.info(
                            "Calibration GPS heading validation: %s",
                            gps_val.get("note", gps_val),
                        )

                step_results.append(step_result)
        finally:
            # Always bring the mower to a stop at the end of the sequence.
            try:
                await robohat.send_motor_command(0.0, 0.0)
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.warning("Failed to send final stop command after calibration: %s", exc)

        await asyncio.sleep(0.75)
        final_snapshot = await _capture_snapshot()
        final_status = None
        final_score = 0
        if final_snapshot:
            final_status = final_snapshot.get("calibration_status")
            final_score = int(final_snapshot.get("calibration_score") or 0)

        # Extract GPS heading validation from forward_sweep (if available)
        gps_heading_info: Optional[Dict[str, Any]] = None
        for sr in step_results:
            if sr["name"] == "forward_sweep" and "gps_heading_validation" in sr:
                gps_heading_info = sr["gps_heading_validation"]
                break

        result = {
            "status": "completed" if final_score >= 2 else "pending",
            "calibration_status": final_status,
            "calibration_score": final_score,
            "steps": step_results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "started_at": start_ts.isoformat(),
            "gps_heading_validation": gps_heading_info,
            "notes": None if final_score >= 2 else "Continue moving mower gently until status improves.",
        }
        return result

    def last_result(self) -> Optional[Dict[str, Any]]:
        """Return the most recent result, if one exists."""
        return self._last_result

    def is_running(self) -> bool:
        """Return True if a calibration routine is currently executing."""
        return self._lock.locked()


imu_calibration_service = IMUCalibrationService()