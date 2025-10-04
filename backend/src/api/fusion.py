from __future__ import annotations

import os
import time
from typing import Any, Dict

from fastapi import APIRouter

from ..fusion.ekf import SimpleEKF
from ..fusion.sensor_health import SensorHealthMonitor
from ..core.simulation import is_simulation_mode


router = APIRouter()


_ekf = SimpleEKF()
_health = SensorHealthMonitor()


@router.get("/api/v2/fusion/state")
async def get_fused_state() -> Dict[str, Any]:
    """Return a fused navigation state (SIM_MODE-friendly scaffold).

    In SIM_MODE, advance the model slightly each call to emulate motion and set
    stable quality metrics. This keeps CI safe and enables placeholder tests.
    """
    sim = is_simulation_mode() or os.environ.get("SIM_MODE") == "1"
    if sim:
        # Simulate slow forward motion with gentle turn
        state = _ekf.step(v_mps=0.0, omega_dps=5.0)
        # Provide a simple GPS/IMU update occasionally to keep state bounded
        if int(time.time()) % 5 == 0:
            _ekf.update_gps_xy(0.0, 0.0, alpha=0.05)
            _ekf.update_heading(90.0, alpha=0.05)
    else:
        state = _ekf.get_state()

    qualities = _health.get_snapshot()
    quality_label = "good" if sum(qualities.values()) / max(len(qualities), 1) > 0.7 else "degraded"
    return {
        "position": {"x": state.x, "y": state.y},
        "heading": state.heading_deg,
        "timestamp": state.timestamp_s,
        "quality": quality_label,
        "sources": ["gps", "imu", "odometry"],
        "sensor_quality": qualities,
    }
