"""Dashboard API (FR-045)

Exposes key performance indicators for the frontend dashboard. Designed to be
resilient on CI and in SIM_MODE by returning sensible defaults when live
services are unavailable.
"""

import datetime as dt
from typing import Any

from fastapi import APIRouter, Request

from ..models.operational_data import OperationalData
from ..services.sensor_manager import SensorManager  # type: ignore

router = APIRouter()


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _safe_get_sensor_manager(request: Request) -> SensorManager | None:
    # Try websocket hub cache first (rest.py pattern), else create a lightweight instance
    hub = getattr(request.app.state, "websocket_hub", None)
    if hub and getattr(hub, "_sensor_manager", None):
        return hub._sensor_manager  # type: ignore[attr-defined]
    try:
        return SensorManager()
    except Exception:
        return None


def _battery_block(sm: SensorManager | None) -> dict[str, Any]:
    pct = 0.0
    volt = 0.0
    curr = 0.0
    health = "unknown"
    if sm and sm.power and sm.power.last_reading:
        pr = sm.power.last_reading
        pct = sm._estimate_battery_soc(pr.battery_voltage) or 0.0
        volt = pr.battery_voltage or 0.0
        curr = pr.battery_current or 0.0
        health = "healthy" if volt > 11.0 else ("warning" if volt > 10.0 else "critical")
    return {
        "percentage": pct,
        "voltage": volt,
        "current": curr,
        "health": health,
    }


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

    sm = _safe_get_sensor_manager(request)

    return {
        "battery": _battery_block(sm),
        "coverage": _coverage_block(op_data),
        "safety": _safety_block(op_data),
        "uptime": _uptime_block(op_data),
        "timestamp": _now_iso(),
    }
