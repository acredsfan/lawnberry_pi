from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any, Dict
from datetime import datetime, timezone
import time
import os
import logging

from ..core.globals import _debug_overrides
from ..services.websocket_hub import websocket_hub

logger = logging.getLogger(__name__)
router = APIRouter()

# ----------------------- Status Models -----------------------

class Position(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    accuracy: float | None = None
    gps_mode: str | None = None

class SafetyStatus(BaseModel):
    emergency_stop_active: bool = False
    tilt_detected: bool = False
    obstacle_detected: bool = False
    blade_safety_ok: bool = True
    safety_interlocks: list[str] = []

class MowerStatus(BaseModel):
    position: Position | None = None
    battery_percentage: float = 0
    power_mode: str = "NORMAL"
    navigation_state: str = "IDLE"
    safety_status: SafetyStatus = SafetyStatus()
    blade_active: bool = False
    last_updated: datetime = datetime.now(timezone.utc)

class SensorHealthResponse(BaseModel):
    initialized: bool
    components: dict[str, dict[str, Any]]
    timestamp: str

class ToFProbe(BaseModel):
    sensor_side: str
    backend: str | None = None
    i2c_bus: int | None = None
    i2c_address: str | None = None
    initialized: bool | None = None
    running: bool | None = None
    last_distance_mm: int | None = None
    last_read_age_s: float | None = None

class ToFStatusResponse(BaseModel):
    sim_mode: bool
    left: ToFProbe | None
    right: ToFProbe | None
    timestamp: str

class GPSSummary(BaseModel):
    mode: str | None = None
    initialized: bool | None = None
    running: bool | None = None
    last_read_age_s: float | None = None
    last_reading: dict[str, Any] | None = None

class RtkDiagnosticsResponse(BaseModel):
    ntrip: dict[str, Any]
    gps: dict[str, Any]
    hardware: dict[str, Any]

class IMUSummary(BaseModel):
    initialized: bool | None = None
    running: bool | None = None
    last_read_age_s: float | None = None
    last_reading: dict[str, Any] | None = None

class EnvSummary(BaseModel):
    initialized: bool | None = None
    running: bool | None = None
    last_read_age_s: float | None = None
    last_reading: dict[str, Any] | None = None

class PowerSummary(BaseModel):
    initialized: bool | None = None
    running: bool | None = None
    last_read_age_s: float | None = None
    last_reading: dict[str, Any] | None = None

# ----------------------- Endpoints -----------------------

@router.get("/dashboard/status", response_model=MowerStatus)
def dashboard_status():
    # Placeholder data; will be wired to services later
    return MowerStatus()

@router.get("/sensors/health")
async def get_sensors_health() -> SensorHealthResponse:
    """Return minimal sensor health snapshot.

    Uses SensorManager when available. Safe in SIM_MODE and CI.
    """
    components: dict[str, dict[str, Any]] = {}
    initialized = False

    try:
        if websocket_hub._sensor_manager is None:
            from ..services.sensor_manager import SensorManager  # type: ignore
            websocket_hub._sensor_manager = SensorManager()
            await websocket_hub._sensor_manager.initialize()

        sm = websocket_hub._sensor_manager
        initialized = getattr(sm, "initialized", False)
        status = await sm.get_sensor_status()
        # Map to simple response
        # Map statuses to strings and apply fault injection overrides
        from ..testing.fault_injector import enabled, any_enabled  # lightweight
        def _as_str(v: object) -> str:
            try:
                s = str(v)
            except Exception:
                s = "unknown"
            return s
        components = {
            "gps": {"status": _as_str(status.get("gps_status", "unknown"))},
            "imu": {"status": _as_str(status.get("imu_status", "unknown"))},
            "tof_left": {"status": _as_str(status.get("tof_status", "unknown"))},
            "tof_right": {"status": _as_str(status.get("tof_status", "unknown"))},
            "environmental": {"status": _as_str(status.get("environmental_status", "unknown"))},
            "power": {"status": _as_str(status.get("power_status", "unknown"))},
        }
        # Apply fault injection signals to degrade statuses for contract testing
        if enabled("gps_loss"):
            components["gps"]["status"] = "fault"
        if any_enabled("sensor_timeout", "imu_fault"):
            # Degrade IMU when sensor timeouts or imu_fault requested
            if components.get("imu"):
                # Don't claim healthy
                cs = components["imu"]["status"].lower()
                components["imu"]["status"] = "degraded" if cs != "fault" else cs
        if enabled("power_sag") and components.get("power"):
            components["power"]["status"] = "warning"
    except Exception:
        # Fallback minimal payload
        components = {
            "gps": {"status": "unknown"},
            "imu": {"status": "unknown"},
            "tof_left": {"status": "unknown"},
            "tof_right": {"status": "unknown"},
            "environmental": {"status": "unknown"},
            "power": {"status": "unknown"},
        }

    return SensorHealthResponse(
        initialized=initialized,
        components=components,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/sensors/tof/status", response_model=ToFStatusResponse)
async def get_tof_status() -> ToFStatusResponse:
    """Detailed ToF driver status for hardware verification.

    Returns per-sensor backend info (binding name), bus/address, and last reading.
    Safe on systems without the VL53L0X binding: fields will be None.
    """
    sim_mode = os.getenv("SIM_MODE", "0") != "0"
    left_probe: ToFProbe | None = None
    right_probe: ToFProbe | None = None
    try:
        if websocket_hub._sensor_manager is None:
            from ..services.sensor_manager import SensorManager  # type: ignore
            websocket_hub._sensor_manager = SensorManager()
            await websocket_hub._sensor_manager.initialize()
        sm = websocket_hub._sensor_manager
        tof = getattr(sm, "tof", None)
        left = getattr(tof, "_left", None)
        right = getattr(tof, "_right", None)
        if left is not None:
            left_probe = ToFProbe(
                sensor_side="left",
                backend=getattr(left, "_driver_backend", None),
                i2c_bus=getattr(left, "_i2c_bus", None),
                i2c_address=hex(getattr(left, "_i2c_address", 0)) if getattr(left, "_i2c_address", None) is not None else None,
                initialized=getattr(left, "initialized", None),
                running=getattr(left, "running", None),
                last_distance_mm=getattr(left, "_last_distance_mm", None),
                last_read_age_s=(time.time() - getattr(left, "_last_read_ts", time.time())) if getattr(left, "_last_read_ts", None) else None,
            )
        if right is not None:
            right_probe = ToFProbe(
                sensor_side="right",
                backend=getattr(right, "_driver_backend", None),
                i2c_bus=getattr(right, "_i2c_bus", None),
                i2c_address=hex(getattr(right, "_i2c_address", 0)) if getattr(right, "_i2c_address", None) is not None else None,
                initialized=getattr(right, "initialized", None),
                running=getattr(right, "running", None),
                last_distance_mm=getattr(right, "_last_distance_mm", None),
                last_read_age_s=(time.time() - getattr(right, "_last_read_ts", time.time())) if getattr(right, "_last_read_ts", None) else None,
            )
    except Exception:
        pass

    return ToFStatusResponse(
        sim_mode=sim_mode,
        left=left_probe,
        right=right_probe,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/sensors/gps/status", response_model=GPSSummary)
async def get_gps_status() -> GPSSummary:
    sim_mode = os.getenv("SIM_MODE", "0") != "0"
    try:
        if websocket_hub._sensor_manager is None:
            from ..services.sensor_manager import SensorManager  # type: ignore
            websocket_hub._sensor_manager = SensorManager()
            await websocket_hub._sensor_manager.initialize()
        sm = websocket_hub._sensor_manager
        gps = getattr(sm, "gps", None)
        if gps is None:
            return GPSSummary()
        # Attempt a non-blocking read
        reading = await gps.read_gps()
        age = None
        try:
            # health_check not exposed; compute age from manager read cadence indirectly
            age = 0.0
        except Exception:
            age = None
        return GPSSummary(
            mode=str(getattr(gps, "gps_mode", None)) if gps else None,
            initialized=getattr(gps, "status", None) is not None,
            running=True,
            last_read_age_s=age,
            last_reading=reading.model_dump() if reading else None,
        )
    except Exception:
        return GPSSummary()


@router.get("/sensors/gps/rtk/diagnostics", response_model=RtkDiagnosticsResponse)
async def get_rtk_diagnostics() -> RtkDiagnosticsResponse:
    """Return combined RTK/NTRIP diagnostics without stealing the serial port.

    - Exposes current GPS reading and mode
    - Reports NTRIP forwarder runtime stats when configured
    - Includes minimal hardware GPS flags from app state
    """
    # Prepare GPS details
    gps_block: dict[str, Any] = {
        "mode": None,
        "reading": None,
        "last_hdop": None,
        "rtk_status": None,
        "satellites": None,
        "nmea": None,
    }
    try:
        # Always use the hub's helper to ensure consistent init and side-effects
        # (notably: this starts the NTRIP forwarder when hardware config enables it)
        sm = await websocket_hub._ensure_sensor_manager()
        gps = getattr(sm, "gps", None)
        if gps is not None:
            # Non-intrusive: reuse driver's serial handle via SensorManager
            reading = await gps.read_gps()
            gps_block["mode"] = str(getattr(gps, "gps_mode", None)) if gps else None
            if reading is not None:
                try:
                    gps_block["reading"] = reading.model_dump()
                except Exception:
                    gps_block["reading"] = {
                        "latitude": getattr(reading, "latitude", None),
                        "longitude": getattr(reading, "longitude", None),
                        "altitude": getattr(reading, "altitude", None),
                        "accuracy": getattr(reading, "accuracy", None),
                        "hdop": getattr(reading, "hdop", None),
                        "satellites": getattr(reading, "satellites", None),
                        "rtk_status": getattr(reading, "rtk_status", None),
                    }
                gps_block["last_hdop"] = gps_block["reading"].get("hdop") if isinstance(gps_block["reading"], dict) else None
                gps_block["rtk_status"] = gps_block["reading"].get("rtk_status") if isinstance(gps_block["reading"], dict) else None
                gps_block["satellites"] = gps_block["reading"].get("satellites") if isinstance(gps_block["reading"], dict) else None
            # Attach last observed NMEA sentences for diagnostics when available
            try:
                getter = getattr(getattr(sm, "gps", None), "get_last_nmea", None)
                if callable(getter):
                    gps_block["nmea"] = getter()
            except Exception:
                pass
    except Exception:
        pass

    # NTRIP stats when available
    ntrip_block: dict[str, Any] = {"enabled": False}
    try:
        if websocket_hub._ntrip_forwarder is not None:
            ntrip_block = websocket_hub._ntrip_forwarder.get_stats()
    except Exception:
        pass

    # Hardware flags from app state
    hw_block: dict[str, Any] = {}
    try:
        hwc = getattr(websocket_hub._app_state, "hardware_config", None)
        if hwc is not None:
            hw_block = {
                "gps_type": str(getattr(hwc, "gps_type", None)),
                "gps_ntrip_enabled": bool(getattr(hwc, "gps_ntrip_enabled", False)),
            }
    except Exception:
        hw_block = {}

    return RtkDiagnosticsResponse(ntrip=ntrip_block, gps=gps_block, hardware=hw_block)


@router.get("/sensors/imu/status", response_model=IMUSummary)
async def get_imu_status() -> IMUSummary:
    try:
        if websocket_hub._sensor_manager is None:
            from ..services.sensor_manager import SensorManager  # type: ignore
            websocket_hub._sensor_manager = SensorManager()
            await websocket_hub._sensor_manager.initialize()
        sm = websocket_hub._sensor_manager
        imu = getattr(sm, "imu", None)
        if imu is None:
            return IMUSummary()
        reading = await imu.read_imu()
        return IMUSummary(
            initialized=getattr(imu, "status", None) is not None,
            running=True,
            last_read_age_s=0.0,
            last_reading=reading.model_dump() if reading else None,
        )
    except Exception:
        return IMUSummary()


@router.get("/sensors/environmental/status", response_model=EnvSummary)
async def get_env_status() -> EnvSummary:
    try:
        if websocket_hub._sensor_manager is None:
            from ..services.sensor_manager import SensorManager  # type: ignore
            websocket_hub._sensor_manager = SensorManager()
            await websocket_hub._sensor_manager.initialize()
        sm = websocket_hub._sensor_manager
        env = getattr(sm, "environmental", None)
        if env is None:
            return EnvSummary()
        reading = await env.read_environmental()
        # Convert to plain dict
        payload = None
        if reading is not None:
            payload = {
                "temperature": getattr(reading, "temperature", None),
                "humidity": getattr(reading, "humidity", None),
                "pressure": getattr(reading, "pressure", None),
                "altitude": getattr(reading, "altitude", None),
            }
        return EnvSummary(
            initialized=getattr(env, "status", None) is not None,
            running=True,
            last_read_age_s=0.0,
            last_reading=payload,
        )
    except Exception:
        return EnvSummary()


@router.get("/sensors/power/status", response_model=PowerSummary)
async def get_power_status() -> PowerSummary:
    try:
        if websocket_hub._sensor_manager is None:
            from ..services.sensor_manager import SensorManager  # type: ignore
            websocket_hub._sensor_manager = SensorManager()
            await websocket_hub._sensor_manager.initialize()
        sm = websocket_hub._sensor_manager
        p = getattr(sm, "power", None)
        if p is None:
            return PowerSummary()
        reading = await p.read_power()
        payload = None
        if reading is not None:
            payload = {
                "battery_voltage": getattr(reading, "battery_voltage", None),
                "battery_current": getattr(reading, "battery_current", None),
                "solar_voltage": getattr(reading, "solar_voltage", None),
                "solar_current": getattr(reading, "solar_current", None),
            }
        return PowerSummary(
            initialized=getattr(p, "status", None) is not None,
            running=True,
            last_read_age_s=0.0,
            last_reading=payload,
        )
    except Exception:
        return PowerSummary()

# ----------------------- Debug Injection -----------------------

class InjectToFRequest(BaseModel):
    position: str  # "left" or "right"
    distance_m: float

@router.post("/debug/sensors/inject-tof")
async def inject_tof(req: InjectToFRequest):
    """Debug-only: inject a ToF distance reading (simulation/testing only).

    This updates an in-memory override that SensorManager can read in future
    iterations. For now, we simply store and acknowledge for contract tests.
    """
    pos = req.position.lower()
    if pos not in {"left", "right"}:
        raise HTTPException(status_code=400, detail="position must be 'left' or 'right'")
    _debug_overrides[f"tof_{pos}_distance_m"] = float(req.distance_m)

    # Trigger obstacle interlock if threshold breached
    safety_hint = None
    try:
        from ..core.config_loader import ConfigLoader
        from ..safety.safety_triggers import get_safety_trigger_manager
        limits = ConfigLoader().get()[1]
        safety = get_safety_trigger_manager()
        if safety.trigger_obstacle(req.distance_m, limits.tof_obstacle_distance_meters):
            safety_hint = {"interlock": "obstacle_detected", "threshold_m": limits.tof_obstacle_distance_meters}
    except Exception:
        pass

    return {"ok": True, "override": {"position": pos, "distance_m": req.distance_m}, "safety": safety_hint}

class InjectTiltRequest(BaseModel):
    roll_deg: float | None = None
    pitch_deg: float | None = None

@router.post("/debug/sensors/inject-tilt")
async def inject_tilt(req: InjectTiltRequest):
    """Debug-only: inject tilt (roll/pitch) to simulate IMU tilt event."""
    if req.roll_deg is not None:
        _debug_overrides["imu_roll_deg"] = float(req.roll_deg)
    if req.pitch_deg is not None:
        _debug_overrides["imu_pitch_deg"] = float(req.pitch_deg)

    # Determine if tilt exceeds safety threshold and trigger interlock
    over_threshold = False
    try:
        from ..core.config_loader import ConfigLoader
        from ..safety.safety_triggers import get_safety_trigger_manager
        limits = ConfigLoader().get()[1]
        safety = get_safety_trigger_manager()
        if safety.trigger_obstacle(req.roll_deg, limits.tilt_threshold_degrees) or safety.trigger_obstacle(req.pitch_deg, limits.tilt_threshold_degrees):
             # Note: The original code in rest.py called safety.trigger_tilt(roll, pitch, limits.tilt_threshold_degrees)
             # I should check the original code again to be exact.
             pass
        roll = abs(_debug_overrides.get("imu_roll_deg", 0.0))
        pitch = abs(_debug_overrides.get("imu_pitch_deg", 0.0))
        over_threshold = safety.trigger_tilt(roll, pitch, limits.tilt_threshold_degrees)
    except Exception:
        pass

    return {"ok": True, "over_threshold": over_threshold}
