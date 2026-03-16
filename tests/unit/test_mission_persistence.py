import asyncio

import pytest

import backend.src.services.mission_service as mission_service_module
from backend.src.core.persistence import PersistenceLayer
from backend.src.models import NavigationMode
from backend.src.models.mission import MissionLifecycleStatus, MissionWaypoint
from backend.src.services.mission_service import MissionService


class DummyNavigationService:
    def __init__(self):
        self.navigation_state = type(
            "NavState",
            (),
            {
                "navigation_mode": NavigationMode.IDLE,
                "planned_path": [],
                "current_waypoint_index": 0,
                "safety_boundaries": [],
                "target_velocity": 0.0,
                "velocity": 0.0,
                "path_status": None,
            },
        )()
        self.stop_calls = 0
        self.emergency_calls = 0
        self.stop_navigation_results: list[bool] = []
        self._mission_gate: asyncio.Event | None = None

    async def execute_mission(self, mission):
        if self._mission_gate is not None:
            await self._mission_gate.wait()
        return None

    async def stop_navigation(self):
        self.stop_calls += 1
        self.navigation_state.navigation_mode = NavigationMode.IDLE
        if self.stop_navigation_results:
            return self.stop_navigation_results.pop(0)
        return True

    async def emergency_stop(self):
        self.emergency_calls += 1
        self.navigation_state.navigation_mode = NavigationMode.EMERGENCY_STOP
        return True

    async def set_speed(self, left_speed: float, right_speed: float):
        return None


@pytest.fixture(autouse=True)
def reset_singletons(tmp_path, monkeypatch):
    original_service = mission_service_module._mission_service_instance
    original_persistence = mission_service_module.persistence
    mission_service_module._mission_service_instance = None
    mission_service_module.persistence = PersistenceLayer(db_path=str(tmp_path / "lawnberry.db"))
    yield
    mission_service_module._mission_service_instance = original_service
    mission_service_module.persistence = original_persistence


@pytest.mark.asyncio
async def test_mission_metadata_survives_restart():
    service = MissionService(DummyNavigationService())
    mission = await service.create_mission(
        "Persistent mission",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    restarted = MissionService(DummyNavigationService())
    await restarted.recover_persisted_missions()

    assert mission.id in restarted.missions
    assert restarted.missions[mission.id].name == "Persistent mission"
    assert restarted.mission_statuses[mission.id].status == MissionLifecycleStatus.IDLE


@pytest.mark.asyncio
async def test_running_mission_recovers_as_paused_after_restart():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Recover running",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    await service.start_mission(mission.id)
    await asyncio.sleep(0)
    task = service.mission_tasks[mission.id]

    with mission_service_module.persistence.get_connection() as conn:
        conn.execute(
            """
            UPDATE mission_execution_state
            SET status = ?, current_waypoint_index = ?, completion_percentage = ?, total_waypoints = ?, detail = ?
            WHERE mission_id = ?
            """,
            (MissionLifecycleStatus.RUNNING.value, 0, 0.0, 1, None, mission.id),
        )
        conn.commit()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    with mission_service_module.persistence.get_connection() as conn:
        conn.execute(
            """
            UPDATE mission_execution_state
            SET status = ?, current_waypoint_index = ?, completion_percentage = ?, total_waypoints = ?, detail = ?
            WHERE mission_id = ?
            """,
            (MissionLifecycleStatus.RUNNING.value, 0, 0.0, 1, None, mission.id),
        )
        conn.commit()

    restarted_nav = DummyNavigationService()
    restarted = MissionService(restarted_nav)
    await restarted.recover_persisted_missions()

    recovered_status = restarted.mission_statuses[mission.id]
    assert restarted_nav.stop_calls == 1
    assert recovered_status.status == MissionLifecycleStatus.PAUSED
    assert "explicit operator resume required" in (recovered_status.detail or "")


@pytest.mark.asyncio
async def test_recovered_paused_mission_resumes_with_new_task():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Recover paused",
        [
            MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50),
            MissionWaypoint(lat=0.2, lon=0.2, blade_on=False, speed=50),
        ],
    )

    service.mission_statuses[mission.id].status = MissionLifecycleStatus.PAUSED
    service.mission_statuses[mission.id].current_waypoint_index = 1
    service._persist_mission_status(mission.id)

    restarted_nav = DummyNavigationService()
    restarted_nav._mission_gate = asyncio.Event()
    restarted = MissionService(restarted_nav)
    await restarted.recover_persisted_missions()
    await restarted.resume_mission(mission.id)

    assert restarted.mission_statuses[mission.id].status == MissionLifecycleStatus.RUNNING
    assert restarted_nav.navigation_state.current_waypoint_index == 1
    assert mission.id in restarted.mission_tasks

    restarted_nav._mission_gate.set()
    await asyncio.wait_for(restarted.mission_tasks[mission.id], timeout=1.0)


@pytest.mark.asyncio
async def test_recovered_paused_status_preserves_waypoint_index_before_resume():
    service = MissionService(DummyNavigationService())
    mission = await service.create_mission(
        "Paused status preserved",
        [
            MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50),
            MissionWaypoint(lat=0.2, lon=0.2, blade_on=False, speed=50),
        ],
    )

    service.mission_statuses[mission.id].status = MissionLifecycleStatus.PAUSED
    service.mission_statuses[mission.id].current_waypoint_index = 1
    service._persist_mission_status(mission.id)

    restarted = MissionService(DummyNavigationService())
    await restarted.recover_persisted_missions()

    recovered_status = await restarted.get_mission_status(mission.id)

    assert recovered_status.status == MissionLifecycleStatus.PAUSED
    assert recovered_status.current_waypoint_index == 1


@pytest.mark.asyncio
async def test_recovery_clamps_invalid_waypoint_index():
    service = MissionService(DummyNavigationService())
    mission = await service.create_mission(
        "Clamp index",
        [
            MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50),
            MissionWaypoint(lat=0.2, lon=0.2, blade_on=False, speed=50),
        ],
    )

    with mission_service_module.persistence.get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO mission_execution_state (
                mission_id, status, current_waypoint_index, completion_percentage, total_waypoints, detail, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (mission.id, MissionLifecycleStatus.PAUSED.value, 99, 0.0, 2, None),
        )
        conn.commit()

    restarted = MissionService(DummyNavigationService())
    await restarted.recover_persisted_missions()

    assert restarted.mission_statuses[mission.id].current_waypoint_index == 1


@pytest.mark.asyncio
async def test_recovery_escalates_to_failed_when_stop_cannot_be_confirmed():
    service = MissionService(DummyNavigationService())
    mission = await service.create_mission(
        "Unsafe recovery",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )
    service.mission_statuses[mission.id].status = MissionLifecycleStatus.PAUSED
    service._persist_mission_status(mission.id)

    restarted_nav = DummyNavigationService()
    restarted_nav.stop_navigation_results = [False]
    restarted = MissionService(restarted_nav)
    await restarted.recover_persisted_missions()

    recovered_status = restarted.mission_statuses[mission.id]
    assert restarted_nav.stop_calls == 1
    assert restarted_nav.emergency_calls == 1
    assert recovered_status.status == MissionLifecycleStatus.FAILED
    assert "emergency stop activated" in (recovered_status.detail or "")