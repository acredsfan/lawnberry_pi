import asyncio
import datetime
import logging
from typing import Dict, List

from fastapi import Depends

from ..models import NavigationMode
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
    def __init__(self, navigation_service: NavigationService):
        self.nav_service = navigation_service
        self.missions: Dict[str, Mission] = {}
        self.mission_statuses: Dict[str, MissionStatus] = {}
        self.mission_tasks: Dict[str, asyncio.Task] = {}

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
        return mission

    async def start_mission(self, mission_id: str):
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

        task = asyncio.create_task(self.nav_service.execute_mission(mission))
        self.mission_tasks[mission_id] = task

        # Monitor task completion
        task.add_done_callback(self._mission_completed_callback(mission_id))

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
            except asyncio.CancelledError:
                status = self.mission_statuses.get(mission_id)
                if status:
                    status.status = MissionLifecycleStatus.ABORTED
                    status.detail = "Mission execution cancelled"
            except Exception as e:
                status = self.mission_statuses.get(mission_id)
                if status:
                    status.status = MissionLifecycleStatus.FAILED
                    status.detail = str(e)
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

        status.status = MissionLifecycleStatus.PAUSED
        status.detail = None
        self.nav_service.navigation_state.navigation_mode = NavigationMode.PAUSED
        try:
            await self.nav_service.set_speed(0.0, 0.0)
        except Exception:
            logger.debug("Mission pause stop command could not be delivered", exc_info=True)


    async def resume_mission(self, mission_id: str):
        self._require_mission(mission_id)
        status = self._require_status(mission_id)
        if status.status != MissionLifecycleStatus.PAUSED:
            raise MissionStateError("Mission is not paused.")

        active_task = self.mission_tasks.get(mission_id)
        if active_task is None or active_task.done():
            raise MissionConflictError("Mission task is not active; restart the mission instead.")

        status.status = MissionLifecycleStatus.RUNNING
        status.detail = None
        self.nav_service.navigation_state.navigation_mode = NavigationMode.AUTO


    async def abort_mission(self, mission_id: str):
        self._require_mission(mission_id)
        status = self._require_status(mission_id)
        status.status = MissionLifecycleStatus.ABORTED
        status.detail = "Mission aborted by operator"
        task = self.mission_tasks.pop(mission_id, None)
        if task and not task.done():
            task.cancel()
        await self.nav_service.stop_navigation()

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
                status.current_waypoint_index = 0
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
_mission_service_instance = None

def get_mission_service(nav_service: NavigationService = Depends(NavigationService.get_instance)) -> "MissionService":
    global _mission_service_instance
    if _mission_service_instance is None:
        _mission_service_instance = MissionService(nav_service)
    return _mission_service_instance

