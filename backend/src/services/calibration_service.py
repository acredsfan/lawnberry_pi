"""IMU calibration orchestration helpers.

Provides a high-level routine that gently moves the mower through the
orientations the BNO085 expects during its calibration sequence. The routine
is safe to call in SIM_MODE (returns a simulated success) and guards against
concurrent executions so operators cannot stack conflicting calibration runs.
"""
from __future__ import annotations

import asyncio
import logging
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
    "partial": 2,
    "unknown": 1,
    None: 0,
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
            }

        try:
            for step in sequence:
                accepted = await robohat.send_motor_command(step["left_speed"], step["right_speed"])
                logger.info("IMU calibration step %s accepted=%s", step["name"], accepted)
                await asyncio.sleep(step["duration"])
                sample = await _capture_snapshot()
                step_results.append(
                    {
                        "name": step["name"],
                        "description": step["description"],
                        "duration_s": step["duration"],
                        "command_accepted": accepted,
                        "sensor_snapshot": sample,
                    }
                )
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

        result = {
            "status": "completed" if final_score >= 2 else "pending",
            "calibration_status": final_status,
            "calibration_score": final_score,
            "steps": step_results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "started_at": start_ts.isoformat(),
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