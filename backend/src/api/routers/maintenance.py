from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, Field, ConfigDict
from typing import Any
import time
import logging
from datetime import datetime, timezone

from ...services.hw_selftest import run_selftest
from ...services.timezone_service import detect_system_timezone
from ...core.persistence import persistence
from ...services.websocket_hub import websocket_hub
from ...services.calibration_service import (
    imu_calibration_service,
    CalibrationInProgressError,
    DriveControllerUnavailableError,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_app_start_time = time.time()

# ------------------------ Models ------------------------

class IMUCalibrationResultPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: str = Field(..., description="High-level outcome for the calibration run.")
    calibration_status: str | None = Field(default=None, description="Raw status reported by the IMU.")
    calibration_score: int = Field(default=0, ge=0, le=3, description="Normalized score from 0-3.")
    steps: list[dict[str, Any]] = Field(default_factory=list, description="Diagnostic step snapshots captured during calibration.")
    timestamp: str = Field(..., description="Completion timestamp (ISO 8601).")
    started_at: str | None = Field(default=None, description="Timestamp when the calibration routine began.")
    notes: str | None = Field(default=None, description="Additional guidance for the operator.")


class IMUCalibrationStatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    in_progress: bool = Field(..., description="True when a calibration routine is currently executing.")
    last_result: IMUCalibrationResultPayload | None = Field(
        default=None,
        description="Most recent calibration summary if available.",
    )

class TimezoneResponse(BaseModel):
    timezone: str
    source: str

# ------------------------ Hardware Self-Test ------------------------

@router.get("/system/selftest")
def system_selftest():
    """Run on-device hardware self-test.

    Safe to run on systems without hardware; returns a structured report.
    """
    report = run_selftest()
    return report

# ------------------------ Health Endpoints ------------------------

@router.get("/health/liveness")
def health_liveness():
    """Basic liveness for systemd: process is up and serving requests."""
    uptime = max(0.0, time.time() - _app_start_time)
    return {
        "status": "ok",
        "service": "lawnberry-backend",
        "uptime_seconds": uptime,
    }

@router.get("/health/readiness")
def health_readiness():
    """Readiness: verify core dependencies are reachable (DB, app state)."""
    db_ok = False
    try:
        with persistence.get_connection() as conn:
            conn.execute("SELECT 1")
            db_ok = True
    except Exception:
        db_ok = False

    telemetry_state = "running" if getattr(websocket_hub, "_telemetry_task", None) else "idle"

    ready = db_ok  # minimal: DB reachable => ready
    return {
        "status": "ready" if ready else "not-ready",
        "components": {
            "database": {"ok": db_ok},
            "telemetry": {"state": telemetry_state},
        },
        "ready": ready,
    }

# -------------------- System Timezone --------------------

@router.get("/system/timezone", response_model=TimezoneResponse)
def get_system_timezone() -> TimezoneResponse:
    """Return the mower's default timezone.

    Strategy: prefer the Raspberry Pi's configured timezone. If unavailable,
    fall back to UTC. A GPS-derived timezone may be added in future.
    """
    info = detect_system_timezone()
    return TimezoneResponse(timezone=info.timezone, source=info.source)

# -------------------- IMU Calibration --------------------

@router.post("/maintenance/imu/calibrate", response_model=IMUCalibrationResultPayload)
async def post_calibrate_imu(request: Request) -> IMUCalibrationResultPayload:
    """Execute the IMU calibration routine and return the resulting summary."""
    hub = getattr(request.app.state, "websocket_hub", websocket_hub)

    if hub._calibration_lock.locked() or imu_calibration_service.is_running():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="IMU calibration already in progress")

    async with hub._calibration_lock:
        try:
            sensor_manager = await hub._ensure_sensor_manager()
        except Exception as exc:
            logger.exception("Failed to prepare SensorManager for calibration: %s", exc)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to initialize sensors for calibration",
            ) from exc

        try:
            result = await imu_calibration_service.run(sensor_manager)
        except CalibrationInProgressError:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="IMU calibration already in progress")
        except DriveControllerUnavailableError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.exception("IMU calibration routine failed: %s", exc)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="IMU calibration failed to complete",
            ) from exc

    return IMUCalibrationResultPayload.model_validate(result)


@router.get("/maintenance/imu/calibrate", response_model=IMUCalibrationStatusResponse)
async def get_calibration_status(request: Request) -> IMUCalibrationStatusResponse:
    """Return current calibration activity state and the most recent result."""
    hub = getattr(request.app.state, "websocket_hub", websocket_hub)

    in_progress = imu_calibration_service.is_running() or hub._calibration_lock.locked()
    last = imu_calibration_service.last_result()
    result_model = IMUCalibrationResultPayload.model_validate(last) if last else None

    return IMUCalibrationStatusResponse(in_progress=in_progress, last_result=result_model)
