from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import TYPE_CHECKING, Dict, List

from fastapi import Depends

if TYPE_CHECKING:
    from .websocket_hub import WebSocketHub

from ..core.persistence import persistence
from ..models import NavigationMode, PathStatus
from ..models.mission import (
    Mission,
    MissionLifecycleStatus,
    MissionStatus,
    MissionWaypoint,
)
from ..nav.geoutils import point_in_polygon
from ..services.navigation_service import NavigationService


logger = logging.getLogger(__name__)


class MissionError(Exception):
    """Base mission domain error."""


class MissionValidationError(MissionError):
    """Raised when a mission payload or state is invalid."""


class MissionNotFoundError(MissionError):
    """Raised when a mission cannot be found."""


class MissionConflictError(MissionError):
    """Raised when an operation conflicts with the current mission execution."""


class MissionStateError(MissionError):
    """Raised when an operation is not valid for the current mission lifecycle state."""


class MissionService:
    def __init__(
        self,
        navigation_service: NavigationService | None = None,
        websocket_hub: "WebSocketHub | None" = None,
    ):
        self.nav_service = navigation_service  # type: ignore[assignment]
        self._websocket_hub = websocket_hub
        self.missions: Dict[str, Mission] = {}
        self.mission_statuses: Dict[str, MissionStatus] = {}
        self.mission_tasks: Dict[str, asyncio.Task] = {}

    def _clamp_waypoint_index(self, mission: Mission, current_waypoint_index: int | None) -> int:
        if not mission.waypoints:
            return 0
        if current_waypoint_index is None:
            return 0
        return max(0, min(int(current_waypoint_index), len(mission.waypoints) - 1))

    def _persist_mission(self, mission: Mission) -> None:
        with persistence.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO missions (id, name, waypoints_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    mission.id,
                    mission.name,
                    json.dumps([waypoint.model_dump() for waypoint in mission.waypoints]),
                    mission.created_at,
                ),
            )
            conn.commit()

    def _persist_mission_status(self, mission_id: str) -> None:
        status = self.mission_statuses.get(mission_id)
        mission = self.missions.get(mission_id)
        if status is None or mission is None:
            return

        clamped_index = self._clamp_waypoint_index(mission, status.current_waypoint_index)
        status.current_waypoint_index = clamped_index
        status.total_waypoints = len(mission.waypoints)
        status.completion_percentage = self._calculate_completion_percentage(mission, clamped_index)

        with persistence.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO mission_execution_state (
                    mission_id,
                    status,
                    current_waypoint_index,
                    completion_percentage,
                    total_waypoints,
                    detail,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    status.status.value if hasattr(status.status, "value") else status.status,
                    clamped_index,
                    status.completion_percentage,
                    status.total_waypoints,
                    status.detail,
                    datetime.datetime.now(datetime.timezone.utc),
                ),
            )
            conn.commit()

    def _sync_status_with_navigation(self, mission_id: str) -> None:
        mission = self.missions.get(mission_id)
        status = self.mission_statuses.get(mission_id)
        if mission is None or status is None:
            return

        nav_state = self.nav_service.navigation_state
        if nav_state.planned_path:
            status.current_waypoint_index = self._clamp_waypoint_index(
                mission,
                nav_state.current_waypoint_index,
            )
            status.completion_percentage = self._calculate_completion_percentage(
                mission,
                status.current_waypoint_index,
            )
        elif status.current_waypoint_index is None:
            status.current_waypoint_index = 0
            status.completion_percentage = 0.0

        self._persist_mission_status(mission_id)

    async def _broadcast_status(self, mission_id: str, detail: str = "") -> None:
        """Emit mission.status event over WebSocket to all subscribers."""
        if self._websocket_hub is None:
            return
        status = self.mission_statuses.get(mission_id)
        if status is None:
            return
        try:
            await self._websocket_hub.broadcast_to_topic(
                "mission.status",
                {
                    "mission_id": mission_id,
                    "status": status.status.value if hasattr(status.status, "value") else status.status,
                    "progress_pct": status.completion_percentage,
                    "detail": detail,
                },
            )
        except Exception as exc:
            logger.warning("Failed to broadcast mission status: %s", exc)

    async def update_waypoint_progress(self, mission_id: str, waypoint_index: int) -> None:
        """Update waypoint progress in mission status (MissionStatusReader protocol method).

        Called by NavigationService after each waypoint is reached, passing the
        current waypoint index directly so this method has no back-reference to
        NavigationService.
        """
        mission = self.missions.get(mission_id)
        status = self.mission_statuses.get(mission_id)
        if mission is None or status is None:
            return
        status.current_waypoint_index = self._clamp_waypoint_index(mission, waypoint_index)
        status.completion_percentage = self._calculate_completion_percentage(
            mission, status.current_waypoint_index
        )
        self._persist_mission_status(mission_id)

    async def recover_persisted_missions(self) -> None:
        recovered_missions: Dict[str, Mission] = {}
        persisted_states: Dict[str, dict] = {}

        with persistence.get_connection() as conn:
            mission_rows = conn.execute(
                "SELECT id, name, waypoints_json, created_at FROM missions ORDER BY created_at"
            ).fetchall()
            state_rows = conn.execute(
                """
                SELECT mission_id, status, current_waypoint_index, completion_percentage,
                       total_waypoints, detail
                FROM mission_execution_state
                """
            ).fetchall()

        for row in mission_rows:
            mission = Mission.model_validate(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "waypoints": json.loads(row["waypoints_json"]),
                    "created_at": row["created_at"],
                }
            )
            recovered_missions[mission.id] = mission

        for row in state_rows:
            persisted_states[row["mission_id"]] = dict(row)

        self.missions = recovered_missions
        self.mission_statuses = {}
        self.mission_tasks = {}

        active_like_states = {
            mission_id
            for mission_id, row in persisted_states.items()
            if row.get("status") in {
                MissionLifecycleStatus.RUNNING.value,
                MissionLifecycleStatus.PAUSED.value,
            }
        }

        stop_confirmed = True
        emergency_ok = False
        if active_like_states:
            stop_confirmed = await self.nav_service.stop_navigation()
            if not stop_confirmed:
                emergency_ok = await self.nav_service.emergency_stop()

        self.nav_service.navigation_state.navigation_mode = NavigationMode.IDLE
        self.nav_service.navigation_state.target_velocity = 0.0
        self.nav_service.navigation_state.velocity = 0.0
        self.nav_service.navigation_state.planned_path = []
        self.nav_service.navigation_state.current_waypoint_index = 0
        self.nav_service.navigation_state.path_status = PathStatus.INTERRUPTED

        for mission_id, mission in self.missions.items():
            persisted = persisted_states.get(mission_id)
            if persisted is None:
                status = self._build_status(mission_id, MissionLifecycleStatus.IDLE)
                self.mission_statuses[mission_id] = status
                self._persist_mission_status(mission_id)
                continue

            raw_status = persisted.get("status", MissionLifecycleStatus.IDLE.value)
            try:
                lifecycle_status = MissionLifecycleStatus(raw_status)
            except ValueError:
                lifecycle_status = MissionLifecycleStatus.FAILED

            clamped_index = self._clamp_waypoint_index(mission, persisted.get("current_waypoint_index"))
            detail = persisted.get("detail")

            if lifecycle_status == MissionLifecycleStatus.RUNNING:
                if stop_confirmed:
                    lifecycle_status = MissionLifecycleStatus.PAUSED
                    detail = "Recovered after backend restart; explicit operator resume required"
                else:
                    lifecycle_status = MissionLifecycleStatus.FAILED
                    detail = (
                        "Recovered after backend restart but stop could not be confirmed; emergency stop activated"
                        if emergency_ok
                        else "Recovered after backend restart but neither stop nor emergency stop could be confirmed"
                    )
            elif lifecycle_status == MissionLifecycleStatus.PAUSED and not stop_confirmed:
                lifecycle_status = MissionLifecycleStatus.FAILED
                detail = (
                    "Recovered paused mission but stop could not be confirmed; emergency stop activated"
                    if emergency_ok
                    else "Recovered paused mission but neither stop nor emergency stop could be confirmed"
                )

            status = MissionStatus(
                mission_id=mission_id,
                status=lifecycle_status,
                current_waypoint_index=clamped_index,
                completion_percentage=self._calculate_completion_percentage(mission, clamped_index),
                total_waypoints=len(mission.waypoints),
                detail=detail,
            )
            self.mission_statuses[mission_id] = status
            self._persist_mission_status(mission_id)

    async def create_mission(self, name: str, waypoints: List[MissionWaypoint]) -> Mission:
        clean_name = (name or "").strip()
        if not clean_name:
            raise MissionValidationError("Mission name cannot be empty.")
        if not waypoints:
            raise MissionValidationError("Mission must contain at least one waypoint.")
        normalized_waypoints = [
            waypoint if isinstance(waypoint, MissionWaypoint) else MissionWaypoint.model_validate(waypoint)
            for waypoint in waypoints
        ]
        self._validate_waypoints_in_geofence(normalized_waypoints)

        mission = Mission(
            name=clean_name,
            waypoints=normalized_waypoints,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        self.missions[mission.id] = mission
        self.mission_statuses[mission.id] = self._build_status(mission.id, MissionLifecycleStatus.IDLE)
        self._persist_mission(mission)
        self._persist_mission_status(mission.id)
        return mission

    async def start_mission(self, mission_id: str):
        import os
        from ..api import rest as rest_api
        from .robohat_service import get_robohat_service

        if rest_api._safety_state.get("emergency_stop_active", False):
            raise MissionStateError("Cannot start mission while emergency stop is active.")

        # Pre-flight: verify motor controller is available (skip in simulation)
        # Only block when a robohat service IS registered but currently disconnected.
        # None means no service configured (dev / test without hardware) — allow.
        if os.getenv("SIM_MODE", "0") != "1":
            robohat = get_robohat_service()
            if robohat is not None and (not robohat.running or not robohat.status.serial_connected):
                detail = f" ({robohat.status.last_error})" if robohat.status.last_error else ""
                raise MissionStateError(
                    f"Cannot start mission: motor controller is not connected{detail}. "
                    "Check USB cable and RoboHAT firmware."
                )

        mission = self._require_mission(mission_id)
        status = self._require_status(mission_id)
        existing_task = self.mission_tasks.get(mission_id)
        if existing_task and not existing_task.done():
            raise MissionConflictError("Mission is already active.")
        if status.status == MissionLifecycleStatus.PAUSED:
            raise MissionStateError("Mission is paused. Use resume instead of start.")

        self.mission_statuses[mission_id] = self._build_status(
            mission.id,
            MissionLifecycleStatus.RUNNING,
            current_waypoint_index=0,
        )

        task = asyncio.create_task(self.nav_service.execute_mission(mission, self))
        self.mission_tasks[mission_id] = task
        self._persist_mission_status(mission_id)

        # Monitor task completion
        task.add_done_callback(self._mission_completed_callback(mission_id))
        await self._broadcast_status(mission_id, "Mission started")

    def _mission_completed_callback(self, mission_id: str):
        def callback(task: asyncio.Task):
            try:
                task.result()
                status = self.mission_statuses.get(mission_id)
                if status and status.status == MissionLifecycleStatus.RUNNING:
                    status.status = MissionLifecycleStatus.COMPLETED
                    status.current_waypoint_index = max(0, status.total_waypoints - 1) if status.total_waypoints else 0
                    status.completion_percentage = 100
                    status.detail = None
                    self._persist_mission_status(mission_id)
            except asyncio.CancelledError:
                status = self.mission_statuses.get(mission_id)
                if status:
                    status.status = MissionLifecycleStatus.ABORTED
                    status.detail = "Mission execution cancelled"
                    self._persist_mission_status(mission_id)
            except Exception as e:
                status = self.mission_statuses.get(mission_id)
                if status:
                    status.status = MissionLifecycleStatus.FAILED
                    status.detail = str(e)
                    self._persist_mission_status(mission_id)
                logger.exception("Mission %s failed", mission_id)
            finally:
                self.mission_tasks.pop(mission_id, None)
        return callback


    async def pause_mission(self, mission_id: str):
        status = self._require_status(mission_id)
        if status.status != MissionLifecycleStatus.RUNNING:
            raise MissionStateError("Mission is not running.")
        if mission_id not in self.mission_tasks or self.mission_tasks[mission_id].done():
            raise MissionConflictError("Mission execution task is not active.")

        stop_confirmed = False
        delay = 0.1
        for attempt in range(1, 4):
            try:
                await self.nav_service.set_speed(0.0, 0.0)
                stop_confirmed = True
                break
            except Exception:
                logger.warning(
                    "Mission pause stop command could not be delivered (attempt %d/3)",
                    attempt,
                    exc_info=True,
                )
                if attempt < 3:
                    await asyncio.sleep(delay)
                    delay *= 2

        if not stop_confirmed:
            emergency_ok = await self.nav_service.emergency_stop()
            status.status = MissionLifecycleStatus.FAILED
            status.detail = (
                "Pause requested but stop command failed; emergency stop activated"
                if emergency_ok
                else "Pause requested but neither stop nor emergency stop could be confirmed"
            )
            self._persist_mission_status(mission_id)
            await self._broadcast_status(mission_id, status.detail)
            return

        status.status = MissionLifecycleStatus.PAUSED
        status.detail = None
        status.current_waypoint_index = self._clamp_waypoint_index(
            self._require_mission(mission_id),
            self.nav_service.navigation_state.current_waypoint_index,
        )
        self.nav_service.navigation_state.navigation_mode = NavigationMode.PAUSED
        self._persist_mission_status(mission_id)
        await self._broadcast_status(mission_id, "Mission paused")


    async def resume_mission(self, mission_id: str):
        import os
        from ..api import rest as rest_api
        from .robohat_service import get_robohat_service

        if rest_api._safety_state.get("emergency_stop_active", False):
            raise MissionStateError("Cannot resume mission while emergency stop is active.")

        # Pre-flight: verify motor controller is available (skip in simulation)
        # Only block when a robohat service IS registered but currently disconnected.
        # None means no service configured (dev / test without hardware) — allow.
        if os.getenv("SIM_MODE", "0") != "1":
            robohat = get_robohat_service()
            if robohat is not None and (not robohat.running or not robohat.status.serial_connected):
                detail = f" ({robohat.status.last_error})" if robohat.status.last_error else ""
                raise MissionStateError(
                    f"Cannot resume mission: motor controller is not connected{detail}. "
                    "Check USB cable and RoboHAT firmware."
                )

        mission = self._require_mission(mission_id)
        status = self._require_status(mission_id)
        if status.status != MissionLifecycleStatus.PAUSED:
            raise MissionStateError("Mission is not paused.")

        active_task = self.mission_tasks.get(mission_id)
        if active_task is None or active_task.done():
            task = asyncio.create_task(self.nav_service.execute_mission(mission, self))
            self.mission_tasks[mission_id] = task
            task.add_done_callback(self._mission_completed_callback(mission_id))
        else:
            task = active_task

        status.status = MissionLifecycleStatus.RUNNING
        status.detail = None
        status.current_waypoint_index = self._clamp_waypoint_index(mission, status.current_waypoint_index)
        self.nav_service.navigation_state.current_waypoint_index = status.current_waypoint_index
        self.nav_service.navigation_state.navigation_mode = NavigationMode.AUTO
        self._persist_mission_status(mission_id)
        await self._broadcast_status(mission_id, "Mission resumed")


    async def abort_mission(self, mission_id: str):
        self._require_mission(mission_id)
        status = self._require_status(mission_id)
        final_status = MissionLifecycleStatus.ABORTED
        detail = "Mission aborted by operator"
        task = self.mission_tasks.get(mission_id)

        stop_confirmed = await self.nav_service.stop_navigation()
        if not stop_confirmed:
            emergency_ok = await self.nav_service.emergency_stop()
            if emergency_ok:
                detail = "Mission aborted by operator after stop failure; emergency stop activated"
            else:
                final_status = MissionLifecycleStatus.FAILED
                detail = "Mission abort requested, but stop and emergency stop could not be confirmed"

        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                logger.warning("Mission %s task did not cancel cleanly within timeout", mission_id)
            except Exception:
                logger.debug("Mission %s task raised during abort handling", mission_id, exc_info=True)

        self.mission_tasks.pop(mission_id, None)
        status.status = final_status
        status.detail = detail
        self._persist_mission_status(mission_id)
        await self._broadcast_status(mission_id, detail)

    async def get_mission_status(self, mission_id: str) -> MissionStatus:
        mission = self._require_mission(mission_id)
        status = self._require_status(mission_id)
        status.total_waypoints = len(mission.waypoints)

        if status.status in {MissionLifecycleStatus.RUNNING, MissionLifecycleStatus.PAUSED}:
            nav_state = self.nav_service.navigation_state
            if nav_state.planned_path:
                max_index = max(0, len(mission.waypoints) - 1)
                status.current_waypoint_index = min(nav_state.current_waypoint_index, max_index)
            else:
                status.current_waypoint_index = self._clamp_waypoint_index(
                    mission,
                    status.current_waypoint_index,
                )
            status.completion_percentage = self._calculate_completion_percentage(
                mission,
                status.current_waypoint_index,
            )
        elif status.status == MissionLifecycleStatus.COMPLETED:
            status.current_waypoint_index = max(0, len(mission.waypoints) - 1) if mission.waypoints else 0
            status.completion_percentage = 100
        elif status.current_waypoint_index is None:
            status.current_waypoint_index = 0
            status.completion_percentage = 0

        self._persist_mission_status(mission_id)
        return status

    async def list_missions(self) -> List[Mission]:
        return list(self.missions.values())

    def _require_mission(self, mission_id: str) -> Mission:
        mission = self.missions.get(mission_id)
        if mission is None:
            raise MissionNotFoundError("Mission not found.")
        return mission

    def _require_status(self, mission_id: str) -> MissionStatus:
        status = self.mission_statuses.get(mission_id)
        if status is None:
            raise MissionNotFoundError("Mission not found.")
        return status

    def _build_status(
        self,
        mission_id: str,
        status: MissionLifecycleStatus,
        current_waypoint_index: int | None = 0,
        detail: str | None = None,
    ) -> MissionStatus:
        mission = self.missions.get(mission_id)
        total_waypoints = len(mission.waypoints) if mission else 0
        return MissionStatus(
            mission_id=mission_id,
            status=status,
            current_waypoint_index=current_waypoint_index,
            completion_percentage=self._calculate_completion_percentage(mission, current_waypoint_index),
            total_waypoints=total_waypoints,
            detail=detail,
        )

    def _calculate_completion_percentage(
        self,
        mission: Mission | None,
        current_waypoint_index: int | None,
    ) -> float:
        if mission is None or not mission.waypoints:
            return 0.0
        if current_waypoint_index is None:
            return 0.0
        bounded_index = max(0, min(current_waypoint_index, len(mission.waypoints)))
        return round((bounded_index / len(mission.waypoints)) * 100, 2)

    def _validate_waypoints_in_geofence(self, waypoints: List[MissionWaypoint]) -> None:
        boundaries = getattr(self.nav_service.navigation_state, "safety_boundaries", None) or []
        if not boundaries:
            return

        outer_boundary = boundaries[0]
        if len(outer_boundary) < 3:
            raise MissionValidationError("Configured safety boundary is invalid.")

        polygon = [(point.latitude, point.longitude) for point in outer_boundary]
        invalid_indices = [
            str(index + 1)
            for index, waypoint in enumerate(waypoints)
            if not point_in_polygon(waypoint.lat, waypoint.lon, polygon)
        ]
        if invalid_indices:
            joined = ", ".join(invalid_indices)
            raise MissionValidationError(
                f"Waypoint(s) {joined} fall outside the configured safety boundary."
            )

# Dependency injection
_mission_service_instance: "MissionService | None" = None


def get_mission_service(
    nav_service: NavigationService = Depends(NavigationService.get_instance),
    websocket_hub: "WebSocketHub | None" = None,
) -> "MissionService":
    global _mission_service_instance
    if _mission_service_instance is None:
        _mission_service_instance = MissionService(
            navigation_service=nav_service,
            websocket_hub=websocket_hub,
        )
    elif websocket_hub is not None and _mission_service_instance._websocket_hub is None:
        # Allow the hub to be injected after first construction (lifespan priming)
        _mission_service_instance._websocket_hub = websocket_hub
    return _mission_service_instance

