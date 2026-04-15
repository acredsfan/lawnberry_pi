"""GPS calibration and position offset endpoints."""
from __future__ import annotations

import math
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gps", tags=["gps"])


class GpsCalibrateRequest(BaseModel):
    """Map position where the mower is actually located (clicked by the operator)."""
    latitude: float = Field(..., description="True latitude of mower as seen on the map")
    longitude: float = Field(..., description="True longitude of mower as seen on the map")


class GpsCalibrateResponse(BaseModel):
    status: str
    offset_lat_m: float
    offset_lon_m: float
    message: str


class GpsOffsetResponse(BaseModel):
    offset_lat_m: float
    offset_lon_m: float


@router.post("/calibrate", response_model=GpsCalibrateResponse)
async def calibrate_gps_position(body: GpsCalibrateRequest, request: Request):
    """Set the GPS position calibration offset.

    The operator parks the mower at a clearly visible location, then clicks
    *that spot* on the satellite imagery map.  This endpoint computes the
    difference between the current (possibly already-offset) GPS reading and
    the clicked position, and saves the total offset to hardware.yaml so the
    displayed position aligns with the imagery.

    The offset is applied in the sensor layer so both the map display *and*
    autonomous navigation use the corrected coordinates.
    """
    from ...core.config_loader import ConfigLoader
    from ...services.websocket_hub import websocket_hub

    # Retrieve current GPS position from the latest telemetry snapshot.
    current_lat: Optional[float] = None
    current_lon: Optional[float] = None

    try:
        snapshot = await websocket_hub.get_last_telemetry(max_age_s=5.0)
        pos = snapshot.get("position") or {}
        current_lat = pos.get("latitude") or pos.get("lat")
        current_lon = pos.get("longitude") or pos.get("lon")
    except Exception:
        pass

    if current_lat is None or current_lon is None:
        # Try the sensor manager directly via app state
        sensor_manager = getattr(getattr(request, "app", None), "state", None)
        sensor_manager = getattr(sensor_manager, "sensor_manager", None) if sensor_manager else None
        if sensor_manager is not None:
            try:
                data = await sensor_manager.read_all_sensors()
                pos = (data.get("position") or data.get("gps") or {})
                current_lat = pos.get("latitude") or pos.get("lat")
                current_lon = pos.get("longitude") or pos.get("lon")
            except Exception:
                pass

    if current_lat is None or current_lon is None:
        raise HTTPException(
            status_code=503,
            detail="No GPS fix available — ensure GPS has a fix before calibrating.",
        )

    # Load existing offset.
    try:
        loader = ConfigLoader()
        hw, _ = loader.get()
        old_lat_m = hw.gps_position_offset_lat_m
        old_lon_m = hw.gps_position_offset_lon_m
    except Exception:
        old_lat_m = 0.0
        old_lon_m = 0.0
        loader = ConfigLoader()

    # Compute the raw (pre-offset) GPS position.
    raw_lat = current_lat - old_lat_m / 111111.0
    raw_lon = current_lon - old_lon_m / (111111.0 * math.cos(math.radians(raw_lat)))

    # New offset = clicked position − raw GPS position.
    new_lat_m = (body.latitude - raw_lat) * 111111.0
    new_lon_m = (body.longitude - raw_lon) * (111111.0 * math.cos(math.radians(raw_lat)))

    try:
        loader.update_gps_offset(new_lat_m, new_lon_m)
    except Exception as exc:
        logger.exception("Failed to write GPS calibration offset: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to save offset: {exc}")

    logger.info(
        "GPS calibration applied: lat_m=%.3f lon_m=%.3f (prev lat_m=%.3f lon_m=%.3f)",
        new_lat_m, new_lon_m, old_lat_m, old_lon_m,
    )
    return GpsCalibrateResponse(
        status="ok",
        offset_lat_m=round(new_lat_m, 3),
        offset_lon_m=round(new_lon_m, 3),
        message=(
            f"Offset saved: {new_lat_m:+.2f} m north, {new_lon_m:+.2f} m east. "
            "Position will update immediately."
        ),
    )


@router.get("/offset", response_model=GpsOffsetResponse)
async def get_gps_offset():
    """Return the current GPS position calibration offset."""
    from ...core.config_loader import ConfigLoader
    try:
        hw, _ = ConfigLoader().get()
        return GpsOffsetResponse(
            offset_lat_m=hw.gps_position_offset_lat_m,
            offset_lon_m=hw.gps_position_offset_lon_m,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/offset", response_model=GpsCalibrateResponse)
async def clear_gps_offset():
    """Reset the GPS position calibration offset to zero."""
    from ...core.config_loader import ConfigLoader
    try:
        loader = ConfigLoader()
        loader.update_gps_offset(0.0, 0.0)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return GpsCalibrateResponse(
        status="ok",
        offset_lat_m=0.0,
        offset_lon_m=0.0,
        message="GPS calibration offset cleared.",
    )
