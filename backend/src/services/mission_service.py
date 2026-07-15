from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from fastapi import Depends

if TYPE_CHECKING:
    from .websocket_hub import WebSocketHub

from ..core.persistence import persistence
from ..models import NavigationMode, PathStatus, Position
from ..models.mission import (
    Mission,
    MissionLifecycleStatus,
    MissionStatus,
    MissionWaypoint,
)
from ..nav.geoutils import point_in_polygon
from ..services.navigation_service import NavigationService
from ..services.planning_service import get_planning_service

logger = logging.getLogger(__name__)

_TERMINAL_MISSION_STATUSES = {
    MissionLifecycleStatus.COMPLETED,
    MissionLifecycleStatus.ABORTED,
    MissionLifecycleStatus.FAILED,
}


def _is_emergency_active() -> bool:
    """Check emergency state via gateway if available, else direct dict read."""
    try:
        from ..main import app

        gw = getattr(getattr(app.state, "runtime", None), "command_gateway", None)
        if gw is not None:
            return gw.is_emergency_active()
    except Exception:
        pass
    try:
        from ..core import globals as _g

        return bool(_g._safety_state.get("emergency_stop_active", False))
    except Exception:
        return False


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
        websocket_hub: WebSocketHub | None = None,
        mission_repository=None,
    ):
        self.nav_service = navigation_service  # type: ignore[assignment]
        self._websocket_hub = websocket_hub
        self._mission_repo = mission_repository
        self.missions: dict[str, Mission] = {}
        self.mission_statuses: dict[str, MissionStatus] = {}
        self.mission_tasks: dict[str, asyncio.Task] = {}
        self._mission_terminal_events: dict[str, asyncio.Event] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()
        # Planning intents for lazy waypoint generation: mission_id → intent dict
        self._planning_intents: dict[str, dict] = {}

        # Observability: event store injected by set_event_store().
        self._event_store: Any | None = None
        self._obs_run_id: str = ""

    def set_event_store(self, store: Any) -> None:
        """Attach an EventStore. run_id is set per-mission at start time."""
        self._event_store = store

    def _new_run_id(self) -> str:
        import uuid
        return str(uuid.uuid4())

    def _emit_event(self, event: Any) -> None:
        if self._event_store is not None:
            try:
                self._event_store.emit(event)
            except Exception:
                pass

    def _clamp_waypoint_index(self, mission: Mission, current_waypoint_index: int | None) -> int:
        if not mission.waypoints:
            return 0
        if current_waypoint_index is None:
            return 0
        return max(0, min(int(current_waypoint_index), len(mission.waypoints) - 1))

    def _persist_mission(self, mission: Mission, *, planning_intent: dict | None = None) -> None:
        if self._mission_repo is None:
            return  # no persistence layer injected; in-memory mode only
        self._mission_repo.save_mission(
            {
                "id": mission.id,
                "name": mission.name,
                "waypoints": [waypoint.model_dump() for waypoint in mission.waypoints],
                "created_at": mission.created_at,
                "planning_intent": planning_intent,
            }
        )

    def _persist_mission_status(self, mission_id: str) -> None:
        status = self.mission_statuses.get(mission_id)
        mission = self.missions.get(mission_id)
        if status is None or mission is None:
            return

        clamped_index = self._clamp_waypoint_index(mission, status.current_waypoint_index)
        status.current_waypoint_index = clamped_index
        status.total_waypoints = len(mission.waypoints)
        status.completion_percentage = self._calculate_completion_percentage(mission, clamped_index)

        if self._mission_repo is not None:
            self._mission_repo.save_execution_state(
                {
                    "mission_id": mission_id,
                    "status": status.status.value if hasattr(status.status, "value") else status.status,
                    "current_waypoint_index": clamped_index,
                    "completion_percentage": status.completion_percentage,
                    "total_waypoints": status.total_waypoints,
                    "detail": status.detail,
                }
            )
            return
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
                    datetime.datetime.now(datetime.UTC),
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

    def _status_payload(self, mission_id: str, detail: str = "") -> dict[str, Any] | None:
        """Snapshot a status event before later lifecycle transitions can change it."""
        if self._websocket_hub is None:
            return None
        status = self.mission_statuses.get(mission_id)
        if status is None:
            return None
        return {
            "mission_id": mission_id,
            "status": status.status.value if hasattr(status.status, "value") else status.status,
            "progress_pct": status.completion_percentage,
            "detail": detail,
        }

    async def _send_status_payload(self, payload: dict[str, Any]) -> None:
        """Best-effort delivery of an already snapshotted mission status."""
        if self._websocket_hub is None:
            return
        try:
            await self._websocket_hub.broadcast_to_topic(
                "mission.status",
                payload,
            )
        except Exception as exc:
            logger.warning("Failed to broadcast mission status: %s", exc)

    async def _broadcast_status(self, mission_id: str, detail: str = "") -> None:
        """Emit mission.status event over WebSocket to all subscribers."""
        payload = self._status_payload(mission_id, detail)
        if payload is not None:
            await self._send_status_payload(payload)

    def _spawn_background(
        self,
        coroutine: Coroutine[Any, Any, None],
        *,
        name: str,
    ) -> None:
        """Retain a best-effort notification task until it finishes."""
        task = asyncio.create_task(coroutine, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(self._consume_background_result)

    @staticmethod
    def _consume_background_result(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Mission background notification failed")

    def _queue_status_broadcast(self, mission_id: str, detail: str = "") -> None:
        payload = self._status_payload(mission_id, detail)
        if payload is not None:
            self._spawn_background(
                self._send_status_payload(payload),
                name=f"mission-status:{mission_id}",
            )

    async def _broadcast_diagnostics(self, mission_id: str) -> None:
        """Emit mission.diagnostics payload over WebSocket."""
        if self._websocket_hub is None or self._event_store is None:
            return
        try:
            from collections import Counter
            events = self._event_store.load_events(run_id=self._obs_run_id)
            blocked_count = sum(1 for e in events if e["event_type"] == "safety_gate_blocked")
            pose_events = [e for e in events if e["event_type"] == "pose_updated"]
            quality_values = [e.get("pose_quality") for e in pose_events if e.get("pose_quality")]
            quality = Counter(quality_values).most_common(1)[0][0] if quality_values else None
            heading_events = [e for e in events if e["event_type"] == "heading_aligned"]
            await self._websocket_hub.broadcast_to_topic(
                "mission.diagnostics",
                {
                    "run_id": self._obs_run_id,
                    "mission_id": mission_id,
                    "blocked_command_count": blocked_count,
                    "average_pose_quality": quality,
                    "heading_alignment_samples": len(heading_events),
                    "pose_update_count": len(pose_events),
                },
            )
        except Exception as exc:
            logger.warning("Failed to broadcast mission diagnostics: %s", exc)

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
        if self._event_store is not None:
            from ..observability.events import WaypointTargetChanged
            waypoints = mission.waypoints if mission else []
            wp = waypoints[waypoint_index] if waypoint_index < len(waypoints) else None
            self._emit_event(WaypointTargetChanged(
                run_id=self._obs_run_id,
                mission_id=mission_id,
                waypoint_index=waypoint_index,
                waypoint_lat=float(wp.lat) if wp else 0.0,
                waypoint_lon=float(wp.lon) if wp else 0.0,
                distance_to_target_m=0.0,
                previous_index=waypoint_index - 1 if waypoint_index > 0 else None,
            ))

    def _load_state_from_db(self) -> tuple[list[dict], list[dict]]:
        """Load all persisted missions and execution states. Runs in executor thread."""
        if self._mission_repo is not None:
            raw_missions = self._mission_repo.list_missions()
            # Convert repo format (waypoints list) back to the format expected by recover_persisted_missions
            mission_rows = [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "waypoints_json": json.dumps(m.get("waypoints", [])),
                    "created_at": m["created_at"],
                    "planning_intent": m.get("planning_intent"),
                }
                for m in raw_missions
            ]
            state_rows = []
            for m in raw_missions:
                state = self._mission_repo.get_execution_state(m["id"])
                if state is not None:
                    state_rows.append(state)
            return mission_rows, state_rows
        with persistence.get_connection() as conn:
            mission_rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, name, waypoints_json, created_at FROM missions ORDER BY created_at"
                ).fetchall()
            ]
            state_rows = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT mission_id, status, current_waypoint_index, completion_percentage,
                           total_waypoints, detail
                    FROM mission_execution_state
                    """
                ).fetchall()
            ]
        return mission_rows, state_rows

    def _flush_changed_states(self, mission_ids: list[str]) -> None:
        """Write mission statuses for only the given IDs. Runs in executor thread."""
        for mission_id in mission_ids:
            self._persist_mission_status(mission_id)

    def _prune_old_terminal_missions(self, retention_days: int = 30) -> None:
        """Delete terminal missions older than retention_days to cap DB growth."""
        if self._mission_repo is not None:
            self._mission_repo.prune_terminal_missions(retention_days=retention_days)
            return
        with persistence.get_connection() as conn:
            conn.execute(
                """
                DELETE FROM missions
                WHERE id IN (
                    SELECT m.id FROM missions m
                    JOIN mission_execution_state mes ON m.id = mes.mission_id
                    WHERE mes.status IN ('completed', 'aborted', 'failed')
                    AND date(m.created_at) < date('now', ?)
                )
                """,
                (f"-{retention_days} days",),
            )
            conn.execute(
                "DELETE FROM mission_execution_state WHERE mission_id NOT IN (SELECT id FROM missions)"
            )
            conn.commit()

    async def recover_persisted_missions(self) -> None:
        loop = asyncio.get_running_loop()

        # Load from DB in a thread so the event loop stays unblocked.
        mission_rows, state_rows = await loop.run_in_executor(None, self._load_state_from_db)

        recovered_missions: dict[str, Mission] = {}
        persisted_states: dict[str, dict] = {}

        recovered_intents: dict[str, dict] = {}
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
            if row.get("planning_intent"):
                recovered_intents[mission.id] = row["planning_intent"]

        for row in state_rows:
            persisted_states[row["mission_id"]] = row

        self.missions = recovered_missions
        self.mission_statuses = {}
        self.mission_tasks = {}
        self._mission_terminal_events = {}
        self._planning_intents = recovered_intents

        active_like_states = {
            mission_id
            for mission_id, row in persisted_states.items()
            if row.get("status")
            in {
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

        # Only write back missions whose status actually changed.
        changed_mission_ids: list[str] = []

        for mission_id, mission in self.missions.items():
            persisted = persisted_states.get(mission_id)
            if persisted is None:
                status = self._build_status(mission_id, MissionLifecycleStatus.IDLE)
                self.mission_statuses[mission_id] = status
                changed_mission_ids.append(mission_id)
                continue

            raw_status = persisted.get("status", MissionLifecycleStatus.IDLE.value)
            try:
                lifecycle_status = MissionLifecycleStatus(raw_status)
            except ValueError:
                lifecycle_status = MissionLifecycleStatus.FAILED

            clamped_index = self._clamp_waypoint_index(
                mission, persisted.get("current_waypoint_index")
            )
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

            if lifecycle_status.value != raw_status:
                changed_mission_ids.append(mission_id)

        if changed_mission_ids:
            await loop.run_in_executor(None, self._flush_changed_states, changed_mission_ids)

        # Prune old terminal missions to prevent unbounded DB growth.
        await loop.run_in_executor(None, self._prune_old_terminal_missions)

    async def create_mission(
        self,
        name: str,
        waypoints: list[MissionWaypoint] | None = None,
        *,
        zone_id: str | None = None,
        pattern: str | None = None,
        pattern_params: dict | None = None,
    ) -> Mission:
        clean_name = (name or "").strip()
        if not clean_name:
            raise MissionValidationError("Mission name cannot be empty.")

        planning_intent: dict | None = None

        if zone_id is not None:
            # Lazy-generation path: store intent, no waypoints yet.
            planning_intent = {
                "zone_id": zone_id,
                "pattern": pattern or "parallel",
                "pattern_params": pattern_params or {},
            }
            normalized_waypoints: list[MissionWaypoint] = []
        else:
            if not waypoints:
                raise MissionValidationError("Mission must contain at least one waypoint.")
            normalized_waypoints = [
                waypoint
                if isinstance(waypoint, MissionWaypoint)
                else MissionWaypoint.model_validate(waypoint)
                for waypoint in waypoints
            ]
            # Ensure the latest zone boundaries are loaded before validating so
            # that waypoints are checked against the current geofence even on the
            # first call after startup (before any mission has executed).
            await self._refresh_nav_boundaries()
            self._validate_waypoints_in_geofence(normalized_waypoints, require_boundary=False)

        mission = Mission(
            name=clean_name,
            waypoints=normalized_waypoints,
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        self.missions[mission.id] = mission
        # Store planning intent in-memory (keyed by mission id)
        if planning_intent is not None:
            self._planning_intents[mission.id] = planning_intent
        self.mission_statuses[mission.id] = self._build_status(
            mission.id, MissionLifecycleStatus.IDLE
        )
        self._mission_terminal_events[mission.id] = asyncio.Event()
        self._persist_mission(mission, planning_intent=planning_intent)
        self._persist_mission_status(mission.id)
        return mission

    async def start_mission(
        self,
        mission_id: str,
        *,
        blade_off_diagnostic: bool = False,
        reuse_heading_alignment: bool = False,
    ):
        import os

        from .robohat_service import get_robohat_service

        if _is_emergency_active():
            raise MissionStateError("Cannot start mission while emergency stop is active.")

        mission = self._require_mission(mission_id)
        status = self._require_status(mission_id)
        if blade_off_diagnostic and any(bool(wp.blade_on) for wp in mission.waypoints):
            raise MissionStateError(
                "Blade-off diagnostic mode requires every waypoint to have blade_on=false."
            )
        if reuse_heading_alignment and not blade_off_diagnostic:
            raise MissionStateError(
                "Saved heading alignment reuse is restricted to blade-off diagnostics."
            )

        try:
            from ..main import app
            from .autonomy_readiness_service import (
                AutonomyReadinessError,
                AutonomyReadinessService,
            )

            runtime = getattr(app.state, "runtime", None)
            if runtime is not None and os.getenv("SIM_MODE", "0") != "1":
                try:
                    await AutonomyReadinessService(runtime).assert_ready(
                        require_blade=not blade_off_diagnostic
                    )
                except AutonomyReadinessError as exc:
                    codes = ", ".join(exc.report.blocking_reason_codes)
                    raise MissionStateError(f"Autonomy readiness failed: {codes}") from exc
        except MissionStateError:
            raise
        except Exception:
            logger.debug("Autonomy readiness preflight unavailable", exc_info=True)

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

        existing_task = self.mission_tasks.get(mission_id)
        if existing_task and not existing_task.done():
            raise MissionConflictError("Mission is already active.")
        if status.status == MissionLifecycleStatus.PAUSED:
            raise MissionStateError("Mission is paused. Use resume instead of start.")

        # Ensure the latest zone boundaries are loaded before any waypoint
        # validation below, so the geofence check is always against the current
        # saved zones — not stale state from a previous mission or cold start.
        await self._refresh_nav_boundaries()

        # Lazy waypoint generation: if mission has a planning intent and no waypoints yet,
        # generate waypoints NOW before changing status or spawning the nav task.
        intent = self._planning_intents.get(mission_id)
        if intent and not mission.waypoints:
            ps = get_planning_service()
            try:
                planned = await ps.plan_path_for_zone(
                    zone_id=intent["zone_id"],
                    pattern=intent.get("pattern", "parallel"),
                    params=intent.get("pattern_params") or {},
                )
            except (KeyError, NotImplementedError, ValueError, RuntimeError) as exc:
                raise MissionValidationError(
                    f"Failed to generate waypoints for zone {intent['zone_id']!r}: {exc}"
                ) from exc

            if not planned.waypoints:
                raise MissionValidationError(
                    f"Path planner returned no waypoints for zone {intent['zone_id']!r}."
                )

            # Populate the in-memory mission and re-validate against geofence.
            mission.waypoints = planned.waypoints
            self._validate_waypoints_in_geofence(
                mission.waypoints,
                require_boundary=self._live_autonomy_requires_boundary(),
            )
            # Persist updated waypoints immediately.
            self._persist_mission(mission)
        elif mission.waypoints:
            # Always re-validate explicit waypoints at start time in case the
            # boundary changed since the mission was originally created.
            self._validate_waypoints_in_geofence(
                mission.waypoints,
                require_boundary=self._live_autonomy_requires_boundary(),
            )

        self._mission_terminal_events.setdefault(mission_id, asyncio.Event()).clear()
        self.mission_statuses[mission_id] = self._build_status(
            mission.id,
            MissionLifecycleStatus.RUNNING,
            current_waypoint_index=0,
        )

        self._obs_run_id = self._new_run_id()
        # Wire navigation before its task can run and emit events.
        if hasattr(self.nav_service, "set_event_store") and self._event_store is not None:
            self.nav_service.set_event_store(
                self._event_store, self._obs_run_id, mission_id
            )
        if reuse_heading_alignment:
            task = asyncio.create_task(
                self.nav_service.execute_mission(
                    mission,
                    self,
                    reuse_heading_alignment=True,
                )
            )
        else:
            task = asyncio.create_task(self.nav_service.execute_mission(mission, self))
        self.mission_tasks[mission_id] = task
        self._persist_mission_status(mission_id)

        # Monitor task completion
        task.add_done_callback(self._mission_completed_callback(mission_id))
        from ..observability.events import MissionStateChanged
        self._emit_event(MissionStateChanged(
            run_id=self._obs_run_id,
            mission_id=mission_id,
            previous_state="idle",
            new_state="running",
            detail="Mission started",
        ))
        # RUNNING is persisted and the navigation task is owned before any
        # best-effort telemetry. Callers can now record accepted dispatches
        # without a WebSocket stall/crash window.
        self._queue_status_broadcast(mission_id, "Mission started")
        self._spawn_background(
            self._broadcast_diagnostics(mission_id),
            name=f"mission-diagnostics:{mission_id}",
        )

    def _mission_completed_callback(self, mission_id: str):
        def callback(task: asyncio.Task):
            try:
                task.result()
                status = self.mission_statuses.get(mission_id)
                if status and status.status == MissionLifecycleStatus.RUNNING:
                    status.status = MissionLifecycleStatus.COMPLETED
                    status.current_waypoint_index = (
                        max(0, status.total_waypoints - 1) if status.total_waypoints else 0
                    )
                    status.completion_percentage = 100
                    status.detail = None
                    self._persist_mission_status(mission_id)
                    self._signal_terminal_state(mission_id)
                    asyncio.ensure_future(
                        self._broadcast_status(mission_id, "Mission completed")
                    )
            except asyncio.CancelledError:
                status = self.mission_statuses.get(mission_id)
                if status is None or status.status != MissionLifecycleStatus.RUNNING:
                    return  # already handled by abort_mission or another terminal path
                status.status = MissionLifecycleStatus.ABORTED
                status.detail = "Mission execution cancelled"
                self._persist_mission_status(mission_id)
                self._signal_terminal_state(mission_id)
                asyncio.ensure_future(
                    self._broadcast_status(mission_id, getattr(status, "detail", "") or "")
                )
            except Exception as e:
                status = self.mission_statuses.get(mission_id)
                if status is None or status.status != MissionLifecycleStatus.RUNNING:
                    return  # already handled
                status.status = MissionLifecycleStatus.FAILED
                status.detail = str(e)
                self._persist_mission_status(mission_id)
                self._signal_terminal_state(mission_id)
                asyncio.ensure_future(
                    self._broadcast_status(mission_id, getattr(status, "detail", "") or "")
                )
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
            self._signal_terminal_state(mission_id)
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
        await self._broadcast_diagnostics(mission_id)
        from ..observability.events import MissionStateChanged
        self._emit_event(MissionStateChanged(
            run_id=self._obs_run_id,
            mission_id=mission_id,
            previous_state="running",
            new_state="paused",
            detail="Mission paused",
        ))

    async def resume_mission(self, mission_id: str):
        import os

        from .robohat_service import get_robohat_service

        if _is_emergency_active():
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

        await self._refresh_nav_boundaries()
        self._validate_waypoints_in_geofence(
            mission.waypoints,
            require_boundary=self._live_autonomy_requires_boundary(),
        )

        active_task = self.mission_tasks.get(mission_id)
        if active_task is None or active_task.done():
            task = asyncio.create_task(self.nav_service.execute_mission(mission, self))
            self.mission_tasks[mission_id] = task
            task.add_done_callback(self._mission_completed_callback(mission_id))
        else:
            task = active_task

        self._mission_terminal_events.setdefault(mission_id, asyncio.Event()).clear()
        status.status = MissionLifecycleStatus.RUNNING
        status.detail = None
        status.current_waypoint_index = self._clamp_waypoint_index(
            mission, status.current_waypoint_index
        )
        self.nav_service.navigation_state.current_waypoint_index = status.current_waypoint_index
        self.nav_service.navigation_state.navigation_mode = NavigationMode.AUTO
        self._persist_mission_status(mission_id)
        await self._broadcast_status(mission_id, "Mission resumed")
        await self._broadcast_diagnostics(mission_id)
        from ..observability.events import MissionStateChanged
        self._emit_event(MissionStateChanged(
            run_id=self._obs_run_id,
            mission_id=mission_id,
            previous_state="paused",
            new_state="running",
            detail="Mission resumed",
        ))

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
                detail = (
                    "Mission abort requested, but stop and emergency stop could not be confirmed"
                )

        # Establish the authoritative terminal state before cancelling the
        # execution task.  The task callback therefore cannot publish a
        # transient ABORTED state when stop/emergency delivery actually failed.
        status.status = final_status
        status.detail = detail
        self._persist_mission_status(mission_id)

        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.CancelledError:
                pass
            except TimeoutError:
                logger.warning("Mission %s task did not cancel cleanly within timeout", mission_id)
            except Exception:
                logger.debug(
                    "Mission %s task raised during abort handling", mission_id, exc_info=True
                )

        self.mission_tasks.pop(mission_id, None)
        self._signal_terminal_state(mission_id)
        await self._broadcast_status(mission_id, detail)
        await self._broadcast_diagnostics(mission_id)
        from ..observability.events import MissionStateChanged
        self._emit_event(MissionStateChanged(
            run_id=self._obs_run_id,
            mission_id=mission_id,
            previous_state="running",
            new_state=final_status.value,
            detail=detail,
        ))

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
            status.current_waypoint_index = (
                max(0, len(mission.waypoints) - 1) if mission.waypoints else 0
            )
            status.completion_percentage = 100
        elif status.current_waypoint_index is None:
            status.current_waypoint_index = 0
            status.completion_percentage = 0

        self._persist_mission_status(mission_id)
        return status

    async def wait_for_terminal_state(self, mission_id: str) -> MissionStatus:
        """Wait for a mission's authoritative terminal state.

        Waiting on this public API never awaits or cancels the private
        navigation task.  Cancelling a waiter therefore cannot bypass
        :meth:`abort_mission` and its confirmed-stop escalation path.
        """
        self._require_mission(mission_id)
        status = self._require_status(mission_id)
        if status.status in _TERMINAL_MISSION_STATUSES:
            return await self.get_mission_status(mission_id)
        if status.status == MissionLifecycleStatus.IDLE:
            raise MissionStateError("Mission has not started.")

        event = self._mission_terminal_events.setdefault(mission_id, asyncio.Event())
        # Close the status-check/event-creation race with the done callback.
        status = self._require_status(mission_id)
        if status.status in _TERMINAL_MISSION_STATUSES:
            event.set()
        await event.wait()
        return await self.get_mission_status(mission_id)

    async def list_missions(self) -> list[Mission]:
        return list(self.missions.values())

    async def update_mission(
        self,
        mission_id: str,
        *,
        name: str | None = None,
        waypoints: list[MissionWaypoint] | None = None,
    ) -> Mission:
        mission = self._require_mission(mission_id)
        status = self._require_status(mission_id)
        if status.status in (MissionLifecycleStatus.RUNNING, MissionLifecycleStatus.PAUSED):
            raise MissionConflictError("Cannot edit a running or paused mission.")
        if waypoints is not None:
            self._validate_waypoints_in_geofence(waypoints, require_boundary=False)
        if name is not None:
            mission.name = name
        if waypoints is not None:
            mission.waypoints = waypoints
        self.mission_statuses[mission_id] = self._build_status(
            mission_id,
            status.status,
            current_waypoint_index=status.current_waypoint_index,
            detail=status.detail,
        )
        self._persist_mission(mission)
        if self._websocket_hub is not None:
            try:
                await self._websocket_hub.broadcast_to_topic(
                    "mission.updated",
                    {
                        "mission_id": mission_id,
                        "name": mission.name,
                        "waypoint_count": len(mission.waypoints),
                    },
                )
            except Exception as exc:
                logger.warning("Failed to broadcast mission.updated: %s", exc)
        return mission

    async def delete_all_missions(self) -> dict:
        """Delete all missions that are not running or paused.

        Returns a dict with shape:
          {"deleted": int, "skipped": list[dict]}
        where each skipped item is {"id": str, "name": str, "reason": str}.
        Running and paused missions are skipped (not deleted); all others are deleted.
        """
        to_delete: list[str] = []
        skipped: list[dict] = []
        for mid, st in list(self.mission_statuses.items()):
            if st.status in (MissionLifecycleStatus.RUNNING, MissionLifecycleStatus.PAUSED):
                mission = self.missions.get(mid)
                skipped.append({
                    "id": mid,
                    "name": mission.name if mission else mid,
                    "reason": st.status.value,
                })
            else:
                to_delete.append(mid)
        # Include missions present in self.missions but not in self.mission_statuses
        for mid in list(self.missions.keys()):
            if mid not in self.mission_statuses and mid not in to_delete:
                to_delete.append(mid)

        if to_delete:
            if self._mission_repo is not None:
                self._mission_repo.delete_missions_bulk(to_delete)
            else:
                with persistence.get_connection() as conn:
                    placeholders = ",".join("?" * len(to_delete))
                    conn.execute(
                        f"DELETE FROM missions WHERE id IN ({placeholders})", to_delete
                    )
                    conn.commit()
            for mid in to_delete:
                self.missions.pop(mid, None)
                self.mission_statuses.pop(mid, None)
                self.mission_tasks.pop(mid, None)
                self._mission_terminal_events.pop(mid, None)
                if self._websocket_hub is not None:
                    try:
                        await self._websocket_hub.broadcast_to_topic(
                            "mission.deleted", {"mission_id": mid}
                        )
                    except Exception as exc:
                        logger.warning("Failed to broadcast mission.deleted: %s", exc)

        return {"deleted": len(to_delete), "skipped": skipped}

    async def delete_mission(self, mission_id: str) -> None:
        self._require_mission(mission_id)
        status = self._require_status(mission_id)
        if status.status in (MissionLifecycleStatus.RUNNING, MissionLifecycleStatus.PAUSED):
            raise MissionConflictError("Cannot delete a running or paused mission.")
        task = self.mission_tasks.get(mission_id)
        if task is not None and not task.done():
            # Terminal mission with stale asyncio task — cancel and proceed
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, TimeoutError):
                pass
        if self._mission_repo is not None:
            self._mission_repo.delete_mission(mission_id)
        else:
            with persistence.get_connection() as conn:
                conn.execute("DELETE FROM mission_execution_state WHERE mission_id = ?", (mission_id,))
                conn.execute("DELETE FROM missions WHERE id = ?", (mission_id,))
                conn.commit()
        self.missions.pop(mission_id, None)
        self.mission_statuses.pop(mission_id, None)
        self.mission_tasks.pop(mission_id, None)
        self._mission_terminal_events.pop(mission_id, None)
        if self._websocket_hub is not None:
            try:
                await self._websocket_hub.broadcast_to_topic(
                    "mission.deleted",
                    {"mission_id": mission_id},
                )
            except Exception as exc:
                logger.warning("Failed to broadcast mission.deleted: %s", exc)

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

    def _signal_terminal_state(self, mission_id: str) -> None:
        status = self.mission_statuses.get(mission_id)
        if status is None or status.status not in _TERMINAL_MISSION_STATUSES:
            return
        self._mission_terminal_events.setdefault(mission_id, asyncio.Event()).set()

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
            completion_percentage=self._calculate_completion_percentage(
                mission, current_waypoint_index
            ),
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

    async def _refresh_nav_boundaries(self) -> None:
        """Load the latest zone boundaries into NavigationService before validating.

        ``_validate_waypoints_in_geofence`` reads
        ``nav_service.navigation_state.safety_boundaries``, which is only
        populated by ``_load_boundaries_from_zones()`` inside
        ``execute_mission``.  Calling this helper first ensures validation
        uses current saved zones, not stale (or empty) state from a previous
        run or cold start.

        The SQLite read is offloaded to a thread so it does not block the
        asyncio event loop and trigger the safety watchdog.
        """
        try:
            await asyncio.to_thread(self.nav_service._load_boundaries_from_zones)
        except Exception as exc:
            logger.warning("Could not refresh navigation boundaries before validation: %s", exc)

    def _live_autonomy_requires_boundary(self) -> bool:
        return os.getenv("SIM_MODE", "0") != "1"

    def _validate_waypoints_in_geofence(
        self,
        waypoints: list[MissionWaypoint],
        *,
        require_boundary: bool,
    ) -> None:
        if not waypoints:
            raise MissionValidationError("Mission must contain at least one waypoint.")

        snapshot = None
        if hasattr(self.nav_service, "get_operating_area_snapshot"):
            try:
                snapshot = self.nav_service.get_operating_area_snapshot()
            except Exception as exc:
                if require_boundary:
                    raise MissionValidationError(f"SAFE_BOUNDARY_REQUIRED: {exc}") from exc

        if snapshot is not None and getattr(snapshot, "valid", False):
            points = [
                Position(latitude=waypoint.lat, longitude=waypoint.lon)
                for waypoint in waypoints
            ]
            current = getattr(self.nav_service.navigation_state, "current_position", None)
            path_points = ([current] if current is not None else []) + points
            margin = float(getattr(self.nav_service, "coverage_endpoint_clearance_m", 0.25))
            for index, point in enumerate(points, start=1):
                if not snapshot.contains_footprint(point, margin):
                    raise MissionValidationError(
                        f"PATH_EXITS_SAFE_AREA: waypoint {index} is outside free space"
                    )
            if len(path_points) >= 2:
                for index in range(len(path_points) - 1):
                    if not snapshot.segment_is_safe(path_points[index], path_points[index + 1], margin):
                        raise MissionValidationError(
                            f"PATH_EXITS_SAFE_AREA: leg {index + 1} leaves safe free space"
                        )
            return

        if require_boundary:
            reason = getattr(snapshot, "validity_state", "SAFE_BOUNDARY_REQUIRED")
            raise MissionValidationError(f"{reason}: valid generated safe boundary is required")

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
_mission_service_instance: MissionService | None = None


def get_mission_service(
    nav_service: NavigationService = Depends(NavigationService.get_instance),
    websocket_hub: WebSocketHub | None = None,
    mission_repository=None,
) -> MissionService:
    global _mission_service_instance
    if _mission_service_instance is None:
        _mission_service_instance = MissionService(
            navigation_service=nav_service,
            websocket_hub=websocket_hub,
            mission_repository=mission_repository,
        )
    else:
        if websocket_hub is not None and _mission_service_instance._websocket_hub is None:
            # Allow the hub to be injected after first construction (lifespan priming)
            _mission_service_instance._websocket_hub = websocket_hub
        if mission_repository is not None and _mission_service_instance._mission_repo is None:
            # Allow the repository to be injected after first construction (lifespan priming)
            _mission_service_instance._mission_repo = mission_repository
    return _mission_service_instance
