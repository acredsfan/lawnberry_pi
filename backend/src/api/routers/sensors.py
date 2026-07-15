import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...core.build_info import get_build_info
from ...core.globals import _debug_overrides
from ...models.sensor_data import GpsReading
from ...services.stationary_rtk_averaging import (
    collect_live_stationary_rtk_average,
    compute_stationary_rtk_average,
)
from ...services.websocket_hub import websocket_hub

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
    tilt_detected: bool | None = None
    obstacle_detected: bool | None = None
    blade_safety_ok: bool | None = None
    safety_interlocks: list[str] = Field(default_factory=list)


class MowerStatus(BaseModel):
    position: Position | None = None
    battery_percentage: float | None = None
    power_mode: str = "UNKNOWN"
    navigation_state: str = "UNKNOWN"
    safety_status: SafetyStatus = Field(default_factory=SafetyStatus)
    blade_active: bool = False
    last_updated: datetime | None = None
    source: str = "unavailable"
    sample_age_seconds: float | None = None
    fresh: bool = False
    power_source: str | None = None
    power_sample_age_seconds: float | None = None
    power_fresh: bool = False
    reason_code: str | None = None
    build_sha: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    last_error: str | None = None
    sample_id: int | None = None
    owner_running: bool = False
    acquisition_window_samples: int = 0
    acquisition_failure_rate: float | None = None


class ToFStatusResponse(BaseModel):
    sim_mode: bool
    left: ToFProbe | None
    right: ToFProbe | None
    timestamp: str


class GPSSummary(BaseModel):
    mode: str | None = None
    initialized: bool | None = None
    running: bool | None = None
    suspended: bool = False
    last_read_age_s: float | None = None
    live: bool = False
    cached: bool | None = None
    sample_id: int | None = None
    stale_reason: str | None = None
    serial_reopen_count: int = 0
    serial_open: bool = False
    read_in_progress: bool = False
    read_lock_contention_count: int = 0
    open_attempt_count: int = 0
    last_read_error: str | None = None
    last_reading: dict[str, Any] | None = None


class RtkDiagnosticsResponse(BaseModel):
    ntrip: dict[str, Any]
    gps: dict[str, Any]
    hardware: dict[str, Any]


class StationaryRtkAverageRequest(BaseModel):
    duration_s: float = Field(default=8.0, ge=0.2, le=30.0)
    interval_s: float = Field(default=0.1, ge=0.05, le=2.0)
    min_samples: int = Field(default=5, ge=1, le=500)
    max_accuracy_m: float = Field(default=0.05, gt=0.0, le=1.0)
    max_speed_mps: float = Field(default=0.03, ge=0.0, le=1.0)
    samples: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional explicit samples for validation/replay; omitted requests read live GPS.",
    )


class StationaryRtkAverageResponse(BaseModel):
    accepted: bool
    averaged_antenna_coordinate: dict[str, float | None] | None
    rmse_m: float | None
    stddev_east_m: float | None
    stddev_north_m: float | None
    sample_count: int
    accepted_count: int
    rejected_count: int
    rejected_reasons: dict[str, int]
    rtk_status_distribution: dict[str, int]
    elapsed_s: float | None
    creates_global_offset: bool


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


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _enum_value(value: object, default: str = "UNKNOWN") -> str:
    if value is None:
        return default
    return str(getattr(value, "value", value))


@router.get("/dashboard/status", response_model=MowerStatus)
async def dashboard_status(request: Request) -> MowerStatus:
    """Return a read-only snapshot without inventing missing mower state."""

    runtime = getattr(request.app.state, "runtime", None)
    hub = getattr(runtime, "websocket_hub", None) if runtime is not None else websocket_hub
    try:
        telemetry = await hub.get_cached_telemetry()
    except Exception:
        telemetry = {"source": "unavailable"}

    sample = telemetry.get("sample") if isinstance(telemetry.get("sample"), dict) else {}
    source = str(sample.get("source") or telemetry.get("source") or "unavailable")
    sample_age = sample.get("age_seconds")
    try:
        sample_age = float(sample_age) if sample_age is not None else None
    except (TypeError, ValueError):
        sample_age = None
    fresh = bool(sample.get("fresh", False)) and source != "unavailable"

    position_payload = (
        telemetry.get("position") if isinstance(telemetry.get("position"), dict) else {}
    )
    position_values = {
        key: position_payload.get(key)
        for key in ("latitude", "longitude", "altitude", "accuracy", "gps_mode")
    }
    position = Position(**position_values) if any(v is not None for v in position_values.values()) else None

    navigation_state = "UNKNOWN"
    safety_state: dict[str, Any] = {}
    blade_state: dict[str, Any] = {}
    energy_state = None
    if runtime is not None:
        navigation = getattr(runtime, "navigation", None)
        navigation_state = _enum_value(
            getattr(getattr(navigation, "navigation_state", None), "navigation_mode", None)
        )
        safety_state = getattr(runtime, "safety_state", {}) or {}
        blade_state = getattr(runtime, "blade_state", {}) or {}
        energy_service = getattr(runtime, "energy_service", None)
        if energy_service is not None:
            try:
                energy_state = energy_service.current_state()
            except Exception:
                logger.exception("Canonical energy state unavailable for dashboard status")

    active_interlocks: list[str] = []
    try:
        from ...core.robot_state_manager import get_robot_state_manager

        robot_state = get_robot_state_manager().get_state()
        active_interlocks = [
            _enum_value(getattr(item, "interlock_type", item), default="unknown")
            for item in robot_state.active_interlocks
        ]
    except Exception:
        pass

    obstacle_detected = "obstacle_detected" in active_interlocks if fresh else None
    tilt_detected = "tilt_detected" in active_interlocks if fresh else None
    emergency_active = bool(safety_state.get("emergency_stop_active", False))
    blade_safety_ok = not emergency_active and not active_interlocks if fresh else None

    battery_percentage = getattr(energy_state, "soc_percent", None)
    power_available = bool(getattr(energy_state, "available", False))
    charging = bool(getattr(energy_state, "charging_confirmed", False))
    power_mode = "CHARGING" if charging else "NORMAL" if power_available else "UNKNOWN"
    observed_at = _parse_timestamp(sample.get("observed_at"))

    return MowerStatus(
        position=position,
        battery_percentage=battery_percentage,
        power_mode=power_mode,
        navigation_state=navigation_state,
        safety_status=SafetyStatus(
            emergency_stop_active=emergency_active,
            tilt_detected=tilt_detected,
            obstacle_detected=obstacle_detected,
            blade_safety_ok=blade_safety_ok,
            safety_interlocks=active_interlocks,
        ),
        blade_active=bool(blade_state.get("active", False)),
        last_updated=observed_at,
        source=source,
        sample_age_seconds=sample_age,
        fresh=fresh,
        power_source=getattr(energy_state, "source", None),
        power_sample_age_seconds=getattr(energy_state, "sample_age_seconds", None),
        power_fresh=bool(getattr(energy_state, "fresh", False)),
        reason_code=getattr(energy_state, "reason_code", "POWER_SERVICE_UNAVAILABLE"),
        build_sha=get_build_info().get("short_sha"),
    )


@router.get("/sensors/health")
async def get_sensors_health() -> SensorHealthResponse:
    """Return minimal sensor health snapshot.

    Uses SensorManager when available. Safe in SIM_MODE and CI.
    """
    components: dict[str, dict[str, Any]] = {}
    initialized = False

    try:
        sm = await websocket_hub._ensure_sensor_manager()
        initialized = getattr(sm, "initialized", False)
        status = await sm.get_sensor_status()
        # Map to simple response
        # Map statuses to strings and apply fault injection overrides
        from ...testing.fault_injector import any_enabled, enabled  # lightweight

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
        timestamp=datetime.now(UTC).isoformat(),
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
        sm = await websocket_hub._ensure_sensor_manager()
        tof = getattr(sm, "tof", None)
        left = getattr(tof, "_left", None)
        right = getattr(tof, "_right", None)
        health = tof.health_snapshot() if callable(getattr(tof, "health_snapshot", None)) else {}
        owner_running = bool(health.get("owner_running"))
        if left is not None:
            left_health = health.get("left", {})
            left_probe = ToFProbe(
                sensor_side="left",
                backend=getattr(left, "_driver_backend", None),
                i2c_bus=getattr(left, "_i2c_bus", None),
                i2c_address=hex(getattr(left, "_i2c_address", 0))
                if getattr(left, "_i2c_address", None) is not None
                else None,
                initialized=getattr(left, "initialized", None),
                running=getattr(left, "running", None),
                last_distance_mm=getattr(left, "_last_distance_mm", None),
                last_read_age_s=left_health.get("sample_age_s"),
                last_error=left_health.get("last_error"),
                sample_id=left_health.get("sample_id"),
                owner_running=owner_running,
                acquisition_window_samples=int(left_health.get("window_samples") or 0),
                acquisition_failure_rate=left_health.get("failure_rate"),
            )
        if right is not None:
            right_health = health.get("right", {})
            right_probe = ToFProbe(
                sensor_side="right",
                backend=getattr(right, "_driver_backend", None),
                i2c_bus=getattr(right, "_i2c_bus", None),
                i2c_address=hex(getattr(right, "_i2c_address", 0))
                if getattr(right, "_i2c_address", None) is not None
                else None,
                initialized=getattr(right, "initialized", None),
                running=getattr(right, "running", None),
                last_distance_mm=getattr(right, "_last_distance_mm", None),
                last_read_age_s=right_health.get("sample_age_s"),
                last_error=right_health.get("last_error"),
                sample_id=right_health.get("sample_id"),
                owner_running=owner_running,
                acquisition_window_samples=int(right_health.get("window_samples") or 0),
                acquisition_failure_rate=right_health.get("failure_rate"),
            )
    except Exception:
        pass

    return ToFStatusResponse(
        sim_mode=sim_mode,
        left=left_probe,
        right=right_probe,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/sensors/gps/status", response_model=GPSSummary)
async def get_gps_status() -> GPSSummary:
    try:
        sm = await websocket_hub._ensure_sensor_manager()
        gps = getattr(sm, "gps", None)
        if gps is None:
            return GPSSummary(stale_reason="gps_unavailable")

        # This endpoint is intentionally read-only. The sensor manager's polling
        # loop is the sole GPS reader; an operator status refresh must not compete
        # for or reset the serial stream.
        reading = getattr(gps, "last_reading", None)
        driver = getattr(gps, "_driver", None)
        health: dict[str, Any] = {}
        if driver is not None and hasattr(driver, "health_check"):
            health = await driver.health_check()

        age = health.get("last_read_age_s")
        if age is None and reading is not None and reading.timestamp is not None:
            age = max(0.0, (datetime.now(UTC) - reading.timestamp).total_seconds())
        cached = bool(reading.cached) if reading is not None else None
        running = bool(health.get("running", getattr(gps, "status", None) is not None))
        suspended = bool(health.get("suspended", False))
        live = bool(health.get("live", False) and reading is not None and not cached)
        if reading is None:
            stale_reason = "no_sample"
        elif not running:
            stale_reason = "driver_not_running"
        elif suspended:
            stale_reason = "driver_suspended"
        elif cached:
            stale_reason = "cached_sample"
        elif not live:
            stale_reason = "stale_sample"
        else:
            stale_reason = None
        gps_mode = getattr(gps, "gps_mode", None)
        return GPSSummary(
            mode=getattr(gps_mode, "value", str(gps_mode) if gps_mode is not None else None),
            initialized=bool(
                health.get("initialized", getattr(gps, "status", None) is not None)
            ),
            running=running,
            suspended=suspended,
            last_read_age_s=age,
            live=live,
            cached=cached,
            sample_id=getattr(reading, "sample_id", None),
            stale_reason=stale_reason,
            serial_reopen_count=int(health.get("serial_reopen_count", 0)),
            serial_open=bool(health.get("serial_open", False)),
            read_in_progress=bool(health.get("read_in_progress", False)),
            read_lock_contention_count=int(
                health.get("read_lock_contention_count", 0)
            ),
            open_attempt_count=int(health.get("open_attempt_count", 0)),
            last_read_error=health.get("last_read_error"),
            last_reading=reading.model_dump() if reading else None,
        )
    except Exception:
        logger.exception("GPS status collection failed")
        return GPSSummary(stale_reason="status_error")


@router.post("/sensors/gps/stationary-average", response_model=StationaryRtkAverageResponse)
async def collect_stationary_rtk_average(
    request: StationaryRtkAverageRequest,
) -> StationaryRtkAverageResponse:
    """Average fresh stationary RTK-fixed antenna samples without writing offsets."""
    readings: list[GpsReading] = []
    if request.samples is not None:
        readings = [GpsReading.model_validate(sample) for sample in request.samples]
    else:
        try:
            sm = await websocket_hub._ensure_sensor_manager()
            gps = getattr(sm, "gps", None)
            if gps is None:
                raise RuntimeError("GPS is not available")
            result = await collect_live_stationary_rtk_average(
                gps,
                duration_s=request.duration_s,
                interval_s=request.interval_s,
                min_samples=request.min_samples,
                max_accuracy_m=request.max_accuracy_m,
                max_speed_mps=request.max_speed_mps,
            )
            return StationaryRtkAverageResponse.model_validate(result.to_dict())
        except Exception as exc:
            logger.exception("Stationary RTK averaging failed to collect GPS samples: %s", exc)
            raise HTTPException(status_code=503, detail="GPS samples unavailable") from exc

    result = compute_stationary_rtk_average(
        readings,
        min_samples=request.min_samples,
        max_accuracy_m=request.max_accuracy_m,
        max_speed_mps=request.max_speed_mps,
    )
    return StationaryRtkAverageResponse.model_validate(result.to_dict())


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
                gps_block["last_hdop"] = (
                    gps_block["reading"].get("hdop")
                    if isinstance(gps_block["reading"], dict)
                    else None
                )
                gps_block["rtk_status"] = (
                    gps_block["reading"].get("rtk_status")
                    if isinstance(gps_block["reading"], dict)
                    else None
                )
                gps_block["satellites"] = (
                    gps_block["reading"].get("satellites")
                    if isinstance(gps_block["reading"], dict)
                    else None
                )
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
        sm = await websocket_hub._ensure_sensor_manager()
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
        sm = await websocket_hub._ensure_sensor_manager()
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
        sm = await websocket_hub._ensure_sensor_manager()
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
        from ..core.config_loader import get_config_loader
        from ..safety.safety_triggers import get_safety_trigger_manager

        limits = get_config_loader().get()[1]
        safety = get_safety_trigger_manager()
        if safety.trigger_obstacle(req.distance_m, limits.tof_obstacle_distance_meters):
            safety_hint = {
                "interlock": "obstacle_detected",
                "threshold_m": limits.tof_obstacle_distance_meters,
            }
    except Exception:
        pass

    return {
        "ok": True,
        "override": {"position": pos, "distance_m": req.distance_m},
        "safety": safety_hint,
    }


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
        from ..core.config_loader import get_config_loader
        from ..safety.safety_triggers import get_safety_trigger_manager

        limits = get_config_loader().get()[1]
        safety = get_safety_trigger_manager()
        roll = abs(_debug_overrides.get("imu_roll_deg", 0.0))
        pitch = abs(_debug_overrides.get("imu_pitch_deg", 0.0))
        over_threshold = safety.trigger_tilt(roll, pitch, limits.tilt_threshold_degrees)
    except Exception:
        pass

    return {"ok": True, "over_threshold": over_threshold}
