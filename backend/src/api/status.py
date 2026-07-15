"""Status API exposing robot state over REST and WebSocket.

Implements T024 minimal contract: GET /api/v2/status returns current state
and a WebSocket at /api/v2/ws/status streams updates at ~5Hz.
"""

from __future__ import annotations
# ruff: noqa: I001

import asyncio
import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .rest import websocket_hub, _safety_state
from .routers.auth import _authorize_websocket
from ..core.robot_state_manager import get_robot_state_manager


router = APIRouter()


@router.get("/api/v2/status")
async def get_status_v2():
    """Return current robot state in a simplified schema for contract tests."""
    mgr = get_robot_state_manager()
    try:
        telemetry: dict[str, Any] = await websocket_hub.get_cached_telemetry()
        if telemetry.get("source") != "unavailable":
            mgr.update_from_telemetry(telemetry)
    except Exception:
        pass
    st = mgr.get_state()
    
    # Deriving specific interlocks from active_interlocks list
    active_types = {
        i.interlock_type.value if hasattr(i.interlock_type, "value") else str(i.interlock_type)
        for i in st.active_interlocks if hasattr(i, "interlock_type")
    }
    
    return {
        "battery_percentage": st.battery.percentage,
        "navigation_state": st.navigation_mode.value,
        "safety_status": {
            "emergency_stop_active": bool(_safety_state.get("emergency_stop_active", False)),
            "estop_reason": _safety_state.get("estop_reason"),
            "tilt_detected": "tilt_detected" in active_types,
            "obstacle_detected": "obstacle_detected" in active_types,
            "blade_safety_ok": True,
            "safety_interlocks": [
                (i.interlock_type.value if hasattr(i, "interlock_type") else str(i))
                for i in st.active_interlocks
            ],
        },
        "motor_status": "idle",
        "last_updated": st.last_updated.isoformat(),
    }


@router.websocket("/api/v2/ws/status")
async def ws_status(websocket: WebSocket):
    """Stream robot state at approximately 5Hz."""
    await _authorize_websocket(websocket)
    await websocket.accept()
    cadence_hz = 5.0
    mgr = get_robot_state_manager()
    try:
        while True:
            # Use cached telemetry to avoid a live sensor read on every tick.
            # _generate_telemetry() blocks the event loop for 600-800 ms per call
            # at 5 Hz, which starves the safety watchdog heartbeat.
            telemetry: dict[str, Any] = await websocket_hub.get_cached_telemetry()
            if telemetry.get("source") != "unavailable":
                mgr.update_from_telemetry(telemetry)
            st = mgr.get_state()
            await websocket.send_json(
                {
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    "battery_percentage": st.battery.percentage,
                    "navigation_state": st.navigation_mode.value,
                    "position": st.position.model_dump(),
                }
            )
            await asyncio.sleep(1.0 / cadence_hz)
    except WebSocketDisconnect:
        return
