"""Dashboard API endpoints."""
from fastapi import APIRouter
from typing import Dict, Any, List
from datetime import datetime

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/state")
async def get_dashboard_state() -> Dict[str, Any]:
    """Get current dashboard state with mower status and KPIs."""
    return {
        "mower_status": "idle",
        "battery_level": 85.0,
        "battery_voltage": 12.8,
        "current_job": None,
        "safety_alerts": [],
        "last_updated": datetime.utcnow().isoformat(),
        "position": {"lat": 0.0, "lon": 0.0},
        "coverage_percent": 0.0,
        "runtime_today": 0,
        "next_scheduled_job": None
    }


@router.get("/alerts")
async def get_dashboard_alerts() -> Dict[str, Any]:
    """Get current safety and system alerts."""
    return {
        "safety_alerts": [],
        "system_alerts": [],
        "maintenance_alerts": [],
        "last_updated": datetime.utcnow().isoformat()
    }