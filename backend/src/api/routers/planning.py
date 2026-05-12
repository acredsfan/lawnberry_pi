"""Schedules router — alias for /api/v2/planning/jobs persistence.

All mutations delegate to the same SQLite helpers as the /planning/jobs
endpoints in rest.py so both surfaces always reflect the same data.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from ...core.persistence import persistence

router = APIRouter(tags=["schedules"])


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class PlanningJobResponse(BaseModel):
    id: str
    name: str
    schedule: str | None = None
    zones: list[Any] = []
    priority: int = 1
    enabled: bool = True
    created_at: str | None = None
    last_run: str | None = None
    status: str = "pending"
    pattern: str | None = None
    pattern_params: dict | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_job(job_id: str) -> dict[str, Any]:
    """Return job dict or raise 404."""
    jobs = persistence.load_planning_jobs()
    for job in jobs:
        if job["id"] == job_id:
            return job
    raise HTTPException(status_code=404, detail="Schedule not found")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/schedules", response_model=list[PlanningJobResponse])
async def list_schedules():
    """List all schedules (same backing store as GET /planning/jobs)."""
    return persistence.load_planning_jobs()


@router.get("/schedules/{schedule_id}", response_model=PlanningJobResponse)
async def get_schedule(schedule_id: str):
    """Get a single schedule by ID (404 if not found)."""
    return _find_job(schedule_id)


@router.post("/schedules", response_model=PlanningJobResponse, status_code=201)
async def create_schedule(payload: dict[str, Any]):
    """Create a schedule (same body as POST /planning/jobs)."""
    job_id = str(uuid.uuid4())
    job: dict[str, Any] = {
        "id": job_id,
        "name": str(payload.get("name") or f"Schedule {job_id[:8]}"),
        "schedule": payload.get("schedule"),
        "zones": list(payload.get("zones") or []),
        "priority": int(payload.get("priority") or 1),
        "enabled": bool(payload.get("enabled", True)),
        "created_at": datetime.now(UTC).isoformat(),
        "last_run": None,
        "status": "pending",
        "pattern": str(payload.get("pattern") or "parallel"),
        "pattern_params": dict(payload.get("pattern_params") or {}),
    }
    persistence.save_planning_job(job)
    return JSONResponse(status_code=201, content=job)


@router.put("/schedules/{schedule_id}", response_model=PlanningJobResponse)
async def update_schedule(schedule_id: str, payload: dict[str, Any]):
    """Update an existing schedule (404 if not found)."""
    existing = _find_job(schedule_id)

    # Merge payload into existing; never allow id or created_at to change
    updated: dict[str, Any] = {
        **existing,
        "name": str(payload.get("name") or existing["name"]),
        "schedule": payload.get("schedule", existing.get("schedule")),
        "zones": list(payload.get("zones") or existing.get("zones") or []),
        "priority": int(payload.get("priority") or existing.get("priority") or 1),
        "enabled": bool(payload.get("enabled", existing.get("enabled", True))),
        "status": str(payload.get("status") or existing.get("status") or "pending"),
        "pattern": str(payload.get("pattern") or existing.get("pattern") or "parallel"),
        "pattern_params": dict(payload.get("pattern_params") or existing.get("pattern_params") or {}),
    }
    persistence.save_planning_job(updated)
    return updated


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: str):
    """Delete a schedule (204 No Content; 404 if not found)."""
    deleted = persistence.delete_planning_job(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return Response(status_code=204)


@router.post("/schedules/{schedule_id}/enable", response_model=PlanningJobResponse)
async def enable_schedule(schedule_id: str):
    """Set enabled=True for the schedule."""
    job = _find_job(schedule_id)
    job["enabled"] = True
    persistence.save_planning_job(job)
    return job


@router.post("/schedules/{schedule_id}/disable", response_model=PlanningJobResponse)
async def disable_schedule(schedule_id: str):
    """Set enabled=False for the schedule."""
    job = _find_job(schedule_id)
    job["enabled"] = False
    persistence.save_planning_job(job)
    return job
