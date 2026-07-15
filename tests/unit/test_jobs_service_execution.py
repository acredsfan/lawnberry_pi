from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backend.src.core.persistence import PersistenceLayer
from backend.src.models import NavigationMode
from backend.src.models.job import Job, JobStatus, JobType
from backend.src.models.mission import (
    Mission,
    MissionLifecycleStatus,
    MissionStatus,
    MissionWaypoint,
)
from backend.src.services import jobs_service as jobs_service_module
from backend.src.services.jobs_service import JobsService
from backend.src.services.mission_service import MissionService


class _AllowQualification:
    def assert_current(self) -> None:
        return None


class _FakeMissionService:
    def __init__(
        self,
        *,
        start_error: Exception | None = None,
        abort_status: MissionLifecycleStatus = MissionLifecycleStatus.ABORTED,
        transient_aborted_on_abort: bool = False,
    ) -> None:
        self.start_error = start_error
        self.abort_status = abort_status
        self.transient_aborted_on_abort = transient_aborted_on_abort
        self.missions: dict[str, Mission] = {}
        self.mission_statuses: dict[str, MissionStatus] = {}
        self._terminal_events: dict[str, asyncio.Event] = {}
        self.create_calls: list[dict[str, Any]] = []
        self.start_calls: list[str] = []
        self.pause_calls: list[str] = []
        self.resume_calls: list[str] = []
        self.abort_calls: list[str] = []
        self.delete_calls: list[str] = []

    async def list_missions(self) -> list[Mission]:
        return list(self.missions.values())

    async def create_mission(self, **kwargs: Any) -> Mission:
        self.create_calls.append(kwargs)
        mission_id = f"mission-{len(self.missions) + 1}"
        mission = Mission(
            id=mission_id,
            name=kwargs["name"],
            waypoints=[],
            created_at=datetime.now(UTC).isoformat(),
        )
        self.missions[mission_id] = mission
        self.mission_statuses[mission_id] = MissionStatus(
            mission_id=mission_id,
            status=MissionLifecycleStatus.IDLE,
        )
        self._terminal_events[mission_id] = asyncio.Event()
        return mission

    async def start_mission(self, mission_id: str) -> None:
        self.start_calls.append(mission_id)
        if self.start_error is not None:
            raise self.start_error
        self.mission_statuses[mission_id].status = MissionLifecycleStatus.RUNNING

    async def wait_for_terminal_state(self, mission_id: str) -> MissionStatus:
        await self._terminal_events[mission_id].wait()
        return self.mission_statuses[mission_id]

    async def get_mission_status(self, mission_id: str) -> MissionStatus:
        return self.mission_statuses[mission_id]

    async def pause_mission(self, mission_id: str) -> None:
        self.pause_calls.append(mission_id)
        self.mission_statuses[mission_id].status = MissionLifecycleStatus.PAUSED

    async def resume_mission(self, mission_id: str) -> None:
        self.resume_calls.append(mission_id)
        self.mission_statuses[mission_id].status = MissionLifecycleStatus.RUNNING

    async def abort_mission(self, mission_id: str) -> None:
        self.abort_calls.append(mission_id)
        status = self.mission_statuses[mission_id]
        if self.transient_aborted_on_abort:
            status.status = MissionLifecycleStatus.ABORTED
            status.detail = "transient cancellation callback state"
            await asyncio.sleep(0)
        status.status = self.abort_status
        status.detail = (
            "stop and emergency stop could not be confirmed"
            if self.abort_status == MissionLifecycleStatus.FAILED
            else "Mission aborted by operator"
        )
        self._terminal_events[mission_id].set()

    async def delete_mission(self, mission_id: str) -> None:
        self.delete_calls.append(mission_id)
        self.missions.pop(mission_id, None)
        self.mission_statuses.pop(mission_id, None)
        self._terminal_events.pop(mission_id, None)

    def finish(
        self,
        mission_id: str,
        status: MissionLifecycleStatus,
        *,
        detail: str | None = None,
        completion_percentage: float = 0.0,
    ) -> None:
        mission_status = self.mission_statuses[mission_id]
        mission_status.status = status
        mission_status.detail = detail
        mission_status.completion_percentage = completion_percentage
        self._terminal_events[mission_id].set()


@pytest.fixture(autouse=True)
def _isolated_persistence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "backend.src.core.persistence.persistence",
        PersistenceLayer(str(tmp_path / "jobs.db")),
    )


class _BlockingWebSocketHub:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def broadcast_to_topic(self, _topic: str, _payload: dict[str, Any]) -> None:
        self.entered.set()
        await self.release.wait()


def test_scheduler_starts_only_after_all_admission_dependencies_are_wired():
    """The lifespan must not race due jobs against partially injected services."""
    source = Path("backend/src/main.py").read_text(encoding="utf-8")
    scheduler_start = source.index("await _jobs_service_singleton.start_scheduler()")

    assert source.index("_jobs_service_singleton.set_qualification_service") < scheduler_start
    assert source.index("_jobs_service_singleton.set_mission_service") < scheduler_start
    assert source.index("_jobs_service_singleton.set_websocket_hub") < scheduler_start
    assert source.index("await _power_manager.start()") < scheduler_start
    assert source.index("if power_manager_ready:") < scheduler_start


def test_scheduler_stops_before_power_and_motion_dependencies():
    """Shutdown must quiesce due jobs while mission dependencies still exist."""
    source = Path("backend/src/main.py").read_text(encoding="utf-8")
    scheduler_stop = source.index("await _jobs_service_singleton.shutdown()")

    assert scheduler_stop < source.index("await app.state.live_safety.stop()")
    assert scheduler_stop < source.index("await app.state.power_manager.stop()")
    assert scheduler_stop < source.index("await sensor_manager.shutdown()")
    assert scheduler_stop < source.index("await camera_service.shutdown()")


def _make_service(
    monkeypatch: pytest.MonkeyPatch,
    mission_service: _FakeMissionService,
) -> JobsService:
    monkeypatch.setattr(
        jobs_service_module,
        "get_safety_state",
        lambda: {"emergency_stop_active": False},
    )
    service = JobsService()
    service.set_mission_service(mission_service)  # type: ignore[arg-type]
    service.set_qualification_service(_AllowQualification())
    return service


def _create_mow_job(service: JobsService, *, job_type: JobType = JobType.SCHEDULED_MOW) -> Job:
    return service.create_job(
        "Back yard",
        job_type=job_type,
        zones=["zone-back"],
        cutting_pattern="parallel",
        parameters={"angle": 20},
    )


async def _wait_for_mission_link(job: Job) -> None:
    for _ in range(20):
        if job.mission_id is not None:
            return
        await asyncio.sleep(0)
    raise AssertionError("job did not link a mission")


async def _wait_for_mission_id(job: Job, mission_id: str) -> None:
    for _ in range(50):
        if job.mission_id == mission_id:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"job did not link mission {mission_id}; current={job.mission_id}")


async def _wait_for_job_task(service: JobsService, job_id: str) -> None:
    task = service._job_tasks[job_id]
    await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
    await asyncio.sleep(0)


async def _wait_for_job_status(job: Job, status: JobStatus) -> None:
    for _ in range(50):
        if job.status == status:
            await asyncio.sleep(0)
            return
        await asyncio.sleep(0)
    raise AssertionError(f"job did not reach {status.value}; current={job.status}")


@pytest.mark.asyncio
async def test_start_job_runs_real_mission_and_projects_completion(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)

    assert service.start_job(job.id) is True
    await _wait_for_mission_link(job)

    assert job.status == JobStatus.RUNNING
    assert job.last_run is not None
    assert job.mission_id == "mission-1"
    assert mission_service.create_calls == [
        {
            "name": "Job: Back yard",
            "zone_id": "zone-back",
            "pattern": "parallel",
            "pattern_params": {"angle": 20},
        }
    ]
    assert mission_service.start_calls == [job.mission_id]

    # Advancing the event loop cannot synthesize completion; only mission truth can.
    await asyncio.sleep(0)
    assert job.status == JobStatus.RUNNING

    mission_service.finish(
        job.mission_id,
        MissionLifecycleStatus.COMPLETED,
        completion_percentage=100.0,
    )
    await _wait_for_job_task(service, job.id)

    assert job.status == JobStatus.COMPLETED
    assert job.completed_at is not None
    assert job.result_message == f"Mission {job.mission_id} completed successfully"
    assert job.error_message is None
    assert job.progress is not None
    assert job.progress.percentage_complete == 100.0


@pytest.mark.asyncio
async def test_multi_zone_job_runs_ordered_child_missions(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    job = service.create_job(
        "Both yards",
        zones=["zone-front", "zone-back"],
        parameters={"angle": 10},
    )

    assert service.start_job(job.id) is True
    await _wait_for_mission_id(job, "mission-1")
    mission_service.finish(
        "mission-1",
        MissionLifecycleStatus.COMPLETED,
        completion_percentage=100.0,
    )
    await _wait_for_mission_id(job, "mission-2")

    assert job.status == JobStatus.RUNNING
    assert job.progress is not None
    assert job.progress.zones_completed == ["zone-front"]
    assert job.progress.percentage_complete == 50.0
    assert [call["zone_id"] for call in mission_service.create_calls] == [
        "zone-front",
        "zone-back",
    ]

    mission_service.finish(
        "mission-2",
        MissionLifecycleStatus.COMPLETED,
        completion_percentage=100.0,
    )
    await _wait_for_job_task(service, job.id)

    assert job.status == JobStatus.COMPLETED
    assert job.progress.zones_completed == ["zone-front", "zone-back"]
    assert job.progress.percentage_complete == 100.0


@pytest.mark.asyncio
async def test_restart_reconciles_occurrence_and_resumes_terminal_projection(monkeypatch):
    from backend.src.core.persistence import persistence

    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    job = {
        "id": "persisted-recovery-job",
        "name": "Recovery job",
        "schedule": "",
        "zones": ["zone-front"],
        "pattern": "parallel",
        "pattern_params": {},
        "created_at": datetime.now(UTC).isoformat(),
        "status": "running",
    }
    persistence.save_planning_job(job)
    occurrence, _created = persistence.claim_planning_job_occurrence(
        occurrence_id="occurrence-recovery",
        job_id=job["id"],
        scheduled_for=job["created_at"],
    )
    mission = await mission_service.create_mission(name="Recovery child")
    await mission_service.start_mission(mission.id)
    await mission_service.pause_mission(mission.id)
    persistence.update_planning_job_occurrence(
        occurrence["occurrence_id"],
        status="running",
        mission_ids=[mission.id],
        active_mission_id=mission.id,
        started_at=job["created_at"],
    )

    await service._recover_planning_occurrences()

    recovered = persistence.load_latest_planning_job_occurrence(job["id"])
    assert recovered is not None
    assert recovered["status"] == "paused"
    await service.control_persisted_planning_job(job["id"], "resume")
    mission_service.finish(
        mission.id,
        MissionLifecycleStatus.COMPLETED,
        completion_percentage=100.0,
    )
    await asyncio.wait_for(
        service._planning_occurrence_tasks[occurrence["occurrence_id"]],
        timeout=1.0,
    )

    terminal = persistence.load_latest_planning_job_occurrence(job["id"])
    assert terminal is not None
    assert terminal["status"] == "completed"
    assert terminal["zones_completed"] == ["zone-front"]


@pytest.mark.asyncio
async def test_start_rejection_fails_job_without_recording_last_run(monkeypatch):
    mission_service = _FakeMissionService(start_error=RuntimeError("Navigation not ready"))
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)

    assert service.start_job(job.id) is True
    await _wait_for_job_task(service, job.id)

    assert job.status == JobStatus.FAILED
    assert job.last_run is None
    assert job.mission_id is None
    assert mission_service.delete_calls == ["mission-1"]
    assert "Navigation not ready" in (job.error_message or "")
    assert job.result_message is None


@pytest.mark.asyncio
async def test_failed_mission_projects_failure_detail(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)

    assert service.start_job(job.id) is True
    await _wait_for_mission_link(job)
    mission_service.finish(
        job.mission_id,
        MissionLifecycleStatus.FAILED,
        detail="wheel encoder fault",
        completion_percentage=35.0,
    )
    await _wait_for_job_task(service, job.id)

    assert job.status == JobStatus.FAILED
    assert job.last_run is not None
    assert job.error_message == "wheel encoder fault"
    assert job.progress is not None
    assert job.progress.percentage_complete == 35.0


@pytest.mark.asyncio
async def test_pause_resume_and_cancel_delegate_to_linked_mission(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)

    assert service.start_job(job.id) is True
    await _wait_for_mission_link(job)

    assert await service.pause_job_async(job.id) is True
    assert job.status == JobStatus.PAUSED
    assert mission_service.pause_calls == [job.mission_id]

    assert await service.resume_job_async(job.id) is True
    assert job.status == JobStatus.RUNNING
    assert mission_service.resume_calls == [job.mission_id]

    assert await service.cancel_job_async(job.id) is True
    assert mission_service.abort_calls == [job.mission_id]
    assert job.status == JobStatus.CANCELLED
    assert job.result_message == "Mission aborted by operator"


@pytest.mark.asyncio
async def test_cancel_projects_authoritative_failed_abort_not_transient_aborted(monkeypatch):
    mission_service = _FakeMissionService(
        abort_status=MissionLifecycleStatus.FAILED,
        transient_aborted_on_abort=True,
    )
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)

    assert service.start_job(job.id) is True
    await _wait_for_mission_link(job)

    assert await service.cancel_job_async(job.id) is False

    assert job.status == JobStatus.FAILED
    assert job.error_message == "stop and emergency stop could not be confirmed"
    assert job.result_message is None


@pytest.mark.asyncio
async def test_sync_control_adapters_schedule_once_and_execute(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)

    assert service.start_job(job.id) is True
    await _wait_for_mission_link(job)

    assert service.pause_job(job.id) is True
    assert service.pause_job(job.id) is False
    await _wait_for_job_status(job, JobStatus.PAUSED)
    assert mission_service.pause_calls == [job.mission_id]

    assert service.resume_job(job.id) is True
    assert service.resume_job(job.id) is False
    await _wait_for_job_status(job, JobStatus.RUNNING)
    assert mission_service.resume_calls == [job.mission_id]

    assert service.cancel_job(job.id) is True
    assert service.cancel_job(job.id) is False
    await _wait_for_job_status(job, JobStatus.CANCELLED)
    assert mission_service.abort_calls == [job.mission_id]

    pending = _create_mow_job(service)
    assert service.delete_job(pending.id) is True
    assert service.delete_job(pending.id) is False
    assert service.get_job(pending.id) is None


@pytest.mark.asyncio
async def test_delete_refuses_when_linked_mission_stop_fails(monkeypatch):
    mission_service = _FakeMissionService(abort_status=MissionLifecycleStatus.FAILED)
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)

    assert service.start_job(job.id) is True
    await _wait_for_mission_link(job)

    assert await service.delete_job_async(job.id) is False
    assert service.get_job(job.id) is job
    assert job.status == JobStatus.FAILED
    assert job.error_message == "stop and emergency stop could not be confirmed"
    assert service.delete_job(job.id) is False
    assert await service.delete_job_async(job.id) is False
    assert service.get_job(job.id) is job


@pytest.mark.asyncio
async def test_delete_refuses_when_linked_mission_stop_is_unconfirmed(monkeypatch):
    mission_service = _FakeMissionService(abort_status=MissionLifecycleStatus.RUNNING)
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)

    assert service.start_job(job.id) is True
    await _wait_for_mission_link(job)

    assert await service.delete_job_async(job.id) is False
    assert service.get_job(job.id) is job
    assert job.status == JobStatus.FAILED
    assert job.error_message == "Mission ended in unexpected state running"
    assert service.delete_job(job.id) is False
    assert await service.delete_job_async(job.id) is False
    assert service.get_job(job.id) is job


@pytest.mark.asyncio
async def test_accepted_start_is_recorded_before_broadcast_and_can_be_cancelled(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    websocket_hub = _BlockingWebSocketHub()
    service.set_websocket_hub(websocket_hub)  # type: ignore[arg-type]
    job = _create_mow_job(service)

    assert service.start_job(job.id) is True
    await asyncio.wait_for(websocket_hub.entered.wait(), timeout=1.0)

    assert job.mission_id == "mission-1"
    assert job.last_run is not None
    assert job.result_message == "Mission mission-1 running"

    # Cancellation must not wait for a best-effort websocket broadcast to finish.
    assert service.cancel_job(job.id) is True
    await asyncio.wait_for(_wait_for_job_status(job, JobStatus.CANCELLED), timeout=1.0)
    assert mission_service.abort_calls == [job.mission_id]


@pytest.mark.asyncio
async def test_persisted_start_is_saved_before_broadcast(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    websocket_hub = _BlockingWebSocketHub()
    service.set_websocket_hub(websocket_hub)  # type: ignore[arg-type]
    saved_jobs: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "backend.src.core.persistence.persistence.save_planning_job",
        lambda job: saved_jobs.append(dict(job)),
    )
    job = {
        "id": "persisted-job",
        "name": "Front yard",
        "zones": ["zone-front"],
        "pattern": "parallel",
        "pattern_params": {},
        "schedule": "08:00",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "pending",
    }

    dispatch = asyncio.create_task(service._dispatch_scheduled_job(job))
    await asyncio.wait_for(websocket_hub.entered.wait(), timeout=1.0)

    assert job["last_run"] is not None
    assert "last_successful_run" not in job
    assert saved_jobs and saved_jobs[-1]["last_run"] == job["last_run"]

    websocket_hub.release.set()
    assert await asyncio.wait_for(dispatch, timeout=1.0) is not None


@pytest.mark.asyncio
async def test_timeout_aborts_mission_and_fails_job(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)
    # Assignment is intentionally sub-minute so the test exercises asyncio.timeout
    # without waiting a full production-configurable minute.
    job.timeout_minutes = 0.001  # type: ignore[assignment]

    assert service.start_job(job.id) is True
    await _wait_for_job_task(service, job.id)

    assert mission_service.abort_calls == [job.mission_id]
    assert job.status == JobStatus.FAILED
    assert "exceeded job timeout" in (job.error_message or "")


@pytest.mark.asyncio
async def test_timeout_stop_failure_remains_failed_and_observable(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)
    job.timeout_minutes = 0.001  # type: ignore[assignment]

    async def fail_abort(_mission_id: str) -> None:
        raise RuntimeError("controller did not acknowledge stop")

    mission_service.abort_mission = fail_abort  # type: ignore[method-assign]

    assert service.start_job(job.id) is True
    await _wait_for_job_task(service, job.id)

    assert job.status == JobStatus.FAILED
    assert "mission stop could not be confirmed" in (job.error_message or "")
    assert "controller did not acknowledge stop" in (job.error_message or "")
    assert service.delete_job(job.id) is False


@pytest.mark.asyncio
async def test_shutdown_aborts_active_linked_mission(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service)

    assert service.start_job(job.id) is True
    await _wait_for_mission_link(job)

    await service.shutdown()

    assert mission_service.abort_calls == [job.mission_id]
    assert job.status == JobStatus.CANCELLED
    assert service._job_tasks == {}
    assert service._running_tasks == set()


@pytest.mark.asyncio
async def test_unsupported_job_type_fails_without_creating_mission(monkeypatch):
    mission_service = _FakeMissionService()
    service = _make_service(monkeypatch, mission_service)
    job = _create_mow_job(service, job_type=JobType.RETURN_HOME)

    assert service.start_job(job.id) is True
    await _wait_for_job_task(service, job.id)

    assert job.status == JobStatus.FAILED
    assert "no MissionService executor" in (job.error_message or "")
    assert job.last_run is None
    assert job.mission_id is None
    assert mission_service.create_calls == []


class _AbortFailureNavigation:
    def __init__(self) -> None:
        self.navigation_state = SimpleNamespace(
            navigation_mode=NavigationMode.IDLE,
            planned_path=[],
            current_waypoint_index=0,
            safety_boundaries=[],
        )
        self._mission_gate = asyncio.Event()

    async def execute_mission(self, mission, mission_service=None) -> None:
        await self._mission_gate.wait()

    async def stop_navigation(self) -> bool:
        return False

    async def emergency_stop(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_mission_terminal_waiter_observes_failed_abort_when_stops_fail(monkeypatch):
    monkeypatch.setenv("SIM_MODE", "1")
    navigation = _AbortFailureNavigation()
    service = MissionService(navigation)  # type: ignore[arg-type]
    mission = await service.create_mission(
        "Abort failure",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=20)],
    )
    await service.start_mission(mission.id)
    waiter = asyncio.create_task(service.wait_for_terminal_state(mission.id))
    await asyncio.sleep(0)

    await service.abort_mission(mission.id)
    terminal = await asyncio.wait_for(waiter, timeout=1.0)

    assert terminal.status == MissionLifecycleStatus.FAILED
    assert terminal.detail == (
        "Mission abort requested, but stop and emergency stop could not be confirmed"
    )
