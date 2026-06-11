"""Guided blade-off boundary point verification."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from ..models.mission import Mission, MissionLifecycleStatus, MissionStatus, MissionWaypoint
from .boundary_paths import BOUNDARY_VERIFICATION_SESSION, boundary_file
from .parcel_boundary import BoundaryValidationError, normalize_boundary_to_lat_lng


def _now() -> str:
    return datetime.now(UTC).isoformat()


class BoundaryVerificationService:
    def __init__(self) -> None:
        self._active_task: Any | None = None
        self._active_status_reader: Any | None = None

    def _read(self) -> dict[str, Any] | None:
        path = boundary_file(BOUNDARY_VERIFICATION_SESSION)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, session: dict[str, Any]) -> dict[str, Any]:
        path = boundary_file(BOUNDARY_VERIFICATION_SESSION)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(session, indent=2), encoding="utf-8")
        tmp.replace(path)
        return session

    def status(self) -> dict[str, Any]:
        return self._read() or {"status": "idle", "points": [], "target_index": None}

    def start(self, points: list[dict[str, float]]) -> dict[str, Any]:
        normalized = normalize_boundary_to_lat_lng(points, order="latlng")
        session = {
            "session_id": str(uuid.uuid4()),
            "status": "active",
            "created_at": _now(),
            "updated_at": _now(),
            "target_index": None,
            "points": [
                {
                    "index": idx,
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                    "status": "pending",
                }
                for idx, point in enumerate(normalized)
            ],
            "active_mission_id": None,
        }
        return self._write(session)

    async def next_point(self, navigation: Any) -> dict[str, Any]:
        session = self.status()
        if session.get("status") != "active":
            raise BoundaryValidationError("No active boundary verification session")
        if self._active_task is not None and not self._active_task.done():
            raise BoundaryValidationError("Mower is already traveling to a verification point")
        points = session.get("points") or []
        target = next((p for p in points if p.get("status") in {"pending", "rejected"}), None)
        if target is None:
            session["status"] = "complete"
            session["target_index"] = None
            session["updated_at"] = _now()
            return self._write(session)
        waypoint = MissionWaypoint(
            lat=float(target["latitude"]),
            lon=float(target["longitude"]),
            blade_on=False,
            speed=20,
            arrival_threshold_m=0.25,
        )
        mission = Mission(
            id=f"boundary-verification-{session['session_id']}-{target['index']}",
            name=f"Boundary verification point {int(target['index']) + 1}",
            waypoints=[waypoint],
            created_at=_now(),
        )
        reader = _VerificationStatusReader(mission)
        self._active_status_reader = reader
        self._active_task = asyncio.create_task(navigation.go_to_waypoint(mission, waypoint, reader))
        session["active_mission_id"] = mission.id
        session["target_index"] = target["index"]
        target["status"] = "traveling"
        session["updated_at"] = _now()
        return self._write(session)

    async def confirm_point(self, navigation: Any) -> dict[str, Any]:
        session = self.status()
        target_index = session.get("target_index")
        if target_index is None:
            raise BoundaryValidationError("No active target point to confirm")
        if self._active_task is not None and not self._active_task.done():
            raise BoundaryValidationError("Mower has not completed travel to this point yet")
        if self._active_task is not None:
            self._active_task.result()
        for point in session.get("points") or []:
            if point.get("index") == target_index:
                point["status"] = "confirmed"
        session["target_index"] = None
        session["active_mission_id"] = None
        session["updated_at"] = _now()
        if all(p.get("status") == "confirmed" for p in session.get("points") or []):
            session["status"] = "complete"
        return self._write(session)

    async def reject_point(self, navigation: Any) -> dict[str, Any]:
        session = self.status()
        target_index = session.get("target_index")
        if target_index is None:
            raise BoundaryValidationError("No active target point to reject")
        await self._stop_active_task(navigation)
        for point in session.get("points") or []:
            if point.get("index") == target_index:
                point["status"] = "rejected"
        session["target_index"] = None
        session["active_mission_id"] = None
        session["updated_at"] = _now()
        return self._write(session)

    async def cancel(self, navigation: Any) -> dict[str, Any]:
        session = self.status()
        await self._stop_active_task(navigation)
        session["status"] = "cancelled"
        session["target_index"] = None
        session["active_mission_id"] = None
        session["updated_at"] = _now()
        return self._write(session)

    async def _stop_active_task(self, navigation: Any) -> None:
        if self._active_status_reader is not None:
            for status in self._active_status_reader.mission_statuses.values():
                status.status = MissionLifecycleStatus.ABORTED
        if self._active_task is not None and not self._active_task.done():
            self._active_task.cancel()
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        try:
            await navigation.stop_navigation()
        except Exception:
            try:
                await navigation.set_speed(0.0, 0.0)
            except Exception:
                pass
        self._active_task = None
        self._active_status_reader = None


class _VerificationStatusReader:
    def __init__(self, mission: Mission) -> None:
        self.mission_statuses = {
            mission.id: MissionStatus(
                mission_id=mission.id,
                status=MissionLifecycleStatus.RUNNING,
                current_waypoint_index=0,
                completion_percentage=0.0,
                total_waypoints=1,
            )
        }

    async def update_waypoint_progress(self, mission_id: str, waypoint_index: int) -> None:
        status = self.mission_statuses.get(mission_id)
        if status is None:
            return
        status.current_waypoint_index = waypoint_index
        status.completion_percentage = 100.0


boundary_verification_service = BoundaryVerificationService()
