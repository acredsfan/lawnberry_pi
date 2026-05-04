"""GET /api/v2/missions/{run_id}/summary — mission run diagnostics summary."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.runtime import RuntimeContext, get_runtime

router = APIRouter()


class WaypointInefficiencyMetrics(BaseModel):
    waypoint_count: int
    average_approach_distance_m: float | None


class RunSummary(BaseModel):
    run_id: str
    mission_id: str | None
    total_distance_m: float
    average_pose_quality: str | None
    heading_alignment_samples: int
    blocked_command_count: int
    waypoint_inefficiency_metrics: WaypointInefficiencyMetrics


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _compute_summary(run_id: str, events: list[dict[str, Any]]) -> RunSummary:
    if not events:
        raise HTTPException(status_code=404, detail=f"No events found for run_id={run_id!r}")

    mission_ids = {e["mission_id"] for e in events if e.get("mission_id")}
    mission_id = next(iter(mission_ids), None)

    pose_events = [e for e in events if e["event_type"] == "pose_updated"]
    total_distance_m = 0.0
    for i in range(1, len(pose_events)):
        prev, curr = pose_events[i - 1], pose_events[i]
        try:
            total_distance_m += _haversine_m(
                float(prev["lat"]), float(prev["lon"]),
                float(curr["lat"]), float(curr["lon"]),
            )
        except (KeyError, TypeError, ValueError):
            continue

    if pose_events:
        quality_counts = Counter(e.get("pose_quality", "unknown") for e in pose_events)
        average_pose_quality: str | None = quality_counts.most_common(1)[0][0]
    else:
        average_pose_quality = None

    heading_events = [e for e in events if e["event_type"] == "heading_aligned"]
    heading_alignment_samples = sum(int(e.get("sample_count", 1)) for e in heading_events)

    blocked_events = [e for e in events if e["event_type"] == "safety_gate_blocked"]
    blocked_command_count = len(blocked_events)

    waypoint_events = [e for e in events if e["event_type"] == "waypoint_target_changed"]
    waypoint_count = len(waypoint_events)
    avg_approach: float | None = None
    if waypoint_events:
        distances = [
            float(e["distance_to_target_m"])
            for e in waypoint_events
            if e.get("distance_to_target_m") is not None
        ]
        avg_approach = sum(distances) / len(distances) if distances else None

    return RunSummary(
        run_id=run_id,
        mission_id=mission_id,
        total_distance_m=round(total_distance_m, 3),
        average_pose_quality=average_pose_quality,
        heading_alignment_samples=heading_alignment_samples,
        blocked_command_count=blocked_command_count,
        waypoint_inefficiency_metrics=WaypointInefficiencyMetrics(
            waypoint_count=waypoint_count,
            average_approach_distance_m=round(avg_approach, 3) if avg_approach is not None else None,
        ),
    )


@router.get("/api/v2/missions/{run_id}/summary", response_model=RunSummary)
async def get_run_summary(
    run_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
) -> RunSummary:
    """Return a post-run diagnostic summary for the given run_id."""
    event_store = runtime.event_store
    if event_store is None:
        raise HTTPException(status_code=503, detail="Event store not initialized")
    events = event_store.load_events(run_id=run_id)
    return _compute_summary(run_id, events)
