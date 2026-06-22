"""Power History API Router.

Provides endpoints for querying the mower's power telemetry history with
activity tagging (idle, mowing, manual, charging, etc.).

Endpoints
---------
GET /api/v2/power/history        — time-bucketed history (default 24 h, 1-min buckets)
GET /api/v2/power/history/raw    — raw un-bucketed samples (default last 1 h)
GET /api/v2/power/activity-tags  — list of valid activity tag constants
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ...services.power_history_service import (
    ACTIVITY_CHARGING,
    ACTIVITY_ESTOP,
    ACTIVITY_IDLE,
    ACTIVITY_MANUAL,
    ACTIVITY_MOWING,
    ACTIVITY_PAUSED,
    ACTIVITY_RETURNING,
    ACTIVITY_UNKNOWN,
    get_power_history_service,
)

router = APIRouter(prefix="/api/v2/power", tags=["power"])


@router.get("/history")
async def get_power_history(
    hours: float = Query(24.0, ge=0.1, le=168.0, description="Look-back window in hours (max 7 days)"),
    resolution: float = Query(1.0, ge=0.1, le=60.0, description="Bucket width in minutes"),
    activity: str | None = Query(None, description="Filter to a single activity tag"),
) -> dict[str, Any]:
    """Return time-bucketed power history.

    Each row represents the average values within a *resolution*-minute bucket.
    Use ``activity`` to filter to a specific activity (e.g. ``mowing``).
    """
    svc = get_power_history_service()
    if svc is None:
        return {"data": [], "message": "Power history service not initialised"}
    rows = svc.query_history(
        hours=hours,
        resolution_minutes=resolution,
        activity_filter=activity,
    )
    return {
        "data": rows,
        "hours": hours,
        "resolution_minutes": resolution,
        "count": len(rows),
    }


@router.get("/history/raw")
async def get_power_history_raw(
    hours: float = Query(1.0, ge=0.01, le=24.0, description="Look-back window in hours"),
    limit: int = Query(3600, ge=1, le=10000, description="Maximum rows returned"),
) -> dict[str, Any]:
    """Return raw (un-bucketed) power samples for the last *hours* hours."""
    svc = get_power_history_service()
    if svc is None:
        return {"data": [], "message": "Power history service not initialised"}
    rows = svc.query_raw(hours=hours, limit=limit)
    return {"data": rows, "hours": hours, "count": len(rows)}


@router.get("/activity-tags")
async def get_activity_tags() -> dict[str, Any]:
    """Return the list of valid activity tag values and their meanings."""
    return {
        "tags": [
            {"value": ACTIVITY_IDLE, "label": "Idle", "color": "#6b7280"},
            {"value": ACTIVITY_MOWING, "label": "Mowing", "color": "#16a34a"},
            {"value": ACTIVITY_MANUAL, "label": "Manual Drive", "color": "#2563eb"},
            {"value": ACTIVITY_RETURNING, "label": "Returning Home", "color": "#d97706"},
            {"value": ACTIVITY_PAUSED, "label": "Paused", "color": "#9333ea"},
            {"value": ACTIVITY_CHARGING, "label": "Charging", "color": "#0891b2"},
            {"value": ACTIVITY_ESTOP, "label": "Emergency Stop", "color": "#dc2626"},
            {"value": ACTIVITY_UNKNOWN, "label": "Unknown", "color": "#9ca3af"},
        ]
    }
