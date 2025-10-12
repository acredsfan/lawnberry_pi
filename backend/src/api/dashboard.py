"""Dashboard API (FR-045)

Exposes key performance indicators for the frontend dashboard. Designed to be
resilient on CI and in SIM_MODE by returning sensible defaults when live
services are unavailable.
"""

import datetime as dt
from typing import Any, Tuple

from fastapi import APIRouter, Request

from ..models.operational_data import OperationalData
from ..models import SensorData
from ..services.sensor_manager import SensorManager  # type: ignore

router = APIRouter()


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


async def _ensure_sensor_snapshot(request: Request) -> Tuple[SensorManager | None, SensorData | None]:
    """Return an initialized SensorManager and its latest SensorData snapshot."""
    sensor_manager: SensorManager | None = None

    hub = getattr(request.app.state, "websocket_hub", None)
    if hub and getattr(hub, "_sensor_manager", None):
        sensor_manager = hub._sensor_manager  # type: ignore[attr-defined]
    elif getattr(request.app.state, "sensor_manager", None):
        sensor_manager = request.app.state.sensor_manager  # type: ignore[attr-defined]

    if sensor_manager is None:
        try:
            sensor_manager = SensorManager()
            request.app.state.sensor_manager = sensor_manager
        except Exception:
            return None, None

    if not getattr(sensor_manager, "initialized", False):
        try:
            ready = await sensor_manager.initialize()
        except Exception:
            return sensor_manager, None
        if not ready:
            return sensor_manager, None

    try:
        snapshot = await sensor_manager.read_all_sensors()
    except Exception:
        snapshot = None

    return sensor_manager, snapshot

def _estimate_soc_from_voltage(voltage: float | None) -> float:
    if voltage is None:
        return 0.0
    try:
        value = float(voltage)
    except (TypeError, ValueError):
        return 0.0

    min_v = 11.5
    max_v = 13.0
    if value <= min_v:
        return 0.0
    if value >= max_v:
        return 100.0

    ratio = (value - min_v) / (max_v - min_v)
    return round(ratio * 100.0, 1)


def _battery_block(sensor_data: SensorData | None, sm: SensorManager | None) -> dict[str, Any]:
    pct = 0.0
    volt = 0.0
    curr = 0.0
    health = "unknown"
    power_reading = None
    if sensor_data and sensor_data.power:
        power_reading = sensor_data.power
    elif sm and sm.power and sm.power.last_reading:
        power_reading = sm.power.last_reading

    if power_reading:
        pr = power_reading
        if sm is not None:
            try:
                pct = sm._estimate_battery_soc(pr.battery_voltage) or 0.0
            except Exception:
                pct = _estimate_soc_from_voltage(pr.battery_voltage)
        else:
            pct = _estimate_soc_from_voltage(pr.battery_voltage)
        volt = pr.battery_voltage or 0.0
        curr = pr.battery_current or 0.0
        health = "healthy" if volt > 11.0 else ("warning" if volt > 10.0 else "critical")
    return {
        "percentage": pct,
        "voltage": volt,
        "current": curr,
        "health": health,
    }


def _has_live_data(snapshot: SensorData | None) -> bool:
    if snapshot is None:
        return False
    if snapshot.power and snapshot.power.battery_voltage is not None:
        return True
    if snapshot.gps and snapshot.gps.latitude is not None and snapshot.gps.longitude is not None:
        return True
    if snapshot.imu and any(
        getattr(snapshot.imu, axis) is not None for axis in ("roll", "pitch", "yaw", "gyro_z")
    ):
        return True
    if snapshot.environmental and snapshot.environmental.temperature is not None:
        return True
    if snapshot.tof_left and snapshot.tof_left.distance is not None:
        return True
    if snapshot.tof_right and snapshot.tof_right.distance is not None:
        return True
    return False


def _coverage_block(op: OperationalData | None) -> dict[str, Any]:
    if not op:
        return {"area_covered_sqm": 0.0, "efficiency_percent": 0.0}
    # Summarize quickly from cumulative stats if available
    area = op.total_area_covered_sqm
    metrics = op.get_current_performance_metrics()
    eff = metrics.coverage_efficiency_percent if metrics else 0.0
    return {"area_covered_sqm": area, "efficiency_percent": eff}


def _safety_block(op: OperationalData | None) -> dict[str, Any]:
    if not op:
        return {"interlocks_active": 0, "emergency_stops": 0}
    # Count emergency events in last 24h
    emg_events = []
    if op.events:
        first_type = op.events[0].event_type
        for e in op.get_events_by_type(event_type=first_type, hours_back=24):
            if getattr(e, "severity", "").lower() in {"emergency"}:
                emg_events.append(e)
    # Interlocks active would come from safety service; expose 0 as default
    return {"interlocks_active": 0, "emergency_stops": len(emg_events)}


def _uptime_block(op: OperationalData | None) -> dict[str, Any]:
    since = _now_iso()
    pct = 100.0
    if op:
        since = op.collection_start.isoformat()
        pct = op.calculate_uptime_percent(hours_back=24)
    return {"since": since, "uptime_percent_24h": pct}


@router.get("/api/v2/dashboard/metrics")
async def get_dashboard_metrics(request: Request) -> dict[str, Any]:
    # Operational data may be tracked elsewhere; provide a small ephemeral instance
    op_data = getattr(request.app.state, "operational_data", None)
    if op_data is None:
        try:
            op_data = OperationalData()  # in-memory scratch for basic KPIs
            request.app.state.operational_data = op_data
        except Exception:
            op_data = None

    sm, sensor_snapshot = await _ensure_sensor_snapshot(request)
    telemetry_source = "hardware" if _has_live_data(sensor_snapshot) else ("initializing" if sm else "unavailable")

    return {
        "battery": _battery_block(sensor_snapshot, sm),
        "coverage": _coverage_block(op_data),
        "safety": _safety_block(op_data),
        "uptime": _uptime_block(op_data),
        "telemetry_source": telemetry_source,
        "timestamp": _now_iso(),
    }
