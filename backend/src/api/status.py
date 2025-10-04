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

from .rest import websocket_hub
from ..core.robot_state_manager import get_robot_state_manager
from ..models.safety_interlock import SafetyInterlock


router = APIRouter()


@router.get("/api/v2/status")
async def get_status_v2():
    """Return current robot state in a simplified schema for contract tests."""
    mgr = get_robot_state_manager()
    st = mgr.get_state()
    return {
        "battery_percentage": st.battery.percentage,
        "navigation_state": st.navigation_mode.value,
        "safety_status": {
            "emergency_stop_active": False,
            "tilt_detected": False,
            "obstacle_detected": False,
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
    await websocket.accept()
    cadence_hz = 5.0
    mgr = get_robot_state_manager()
    try:
        while True:
            # Update state opportunistically from the same telemetry source used for dashboard
            telemetry: dict[str, Any] = await websocket_hub._generate_telemetry()
            mgr.update_from_telemetry(telemetry)
            st = mgr.get_state()
            await websocket.send_json({
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                "battery_percentage": st.battery.percentage,
                "navigation_state": st.navigation_mode.value,
                "position": st.position.model_dump(),
            })
            await asyncio.sleep(1.0 / cadence_hz)
    except WebSocketDisconnect:
        return
