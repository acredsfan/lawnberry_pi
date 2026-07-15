import pytest

from backend.src.models.scheduled_job import JobState, ScheduledJob


def test_job_state_machine_happy_path_transitions():
    from backend.src.scheduler.job_state_machine import JobStateMachine

    job = ScheduledJob(
        job_id="j1",
        name="demo",
        cron_schedule="@every 1s",
        state=JobState.IDLE,
    )
    fsm = JobStateMachine(job)

    # IDLE -> SCHEDULED
    fsm.schedule()
    assert job.state == JobState.SCHEDULED

    # SCHEDULED -> RUNNING
    fsm.start()
    assert job.state == JobState.RUNNING
    assert isinstance(job.last_run_time_us, int) and job.last_run_time_us > 0

    # RUNNING -> PAUSED
    fsm.pause()
    assert job.state == JobState.PAUSED

    # PAUSED -> RUNNING
    fsm.resume()
    assert job.state == JobState.RUNNING

    # RUNNING -> COMPLETED
    fsm.complete()
    assert job.state == JobState.COMPLETED


def test_job_state_machine_invalid_transition_raises():
    from backend.src.scheduler.job_state_machine import JobStateMachine

    job = ScheduledJob(
        job_id="j2",
        name="demo2",
        cron_schedule="@every 1s",
        state=JobState.COMPLETED,
    )
    fsm = JobStateMachine(job)

    with pytest.raises(ValueError) as exc_info:
        fsm.start()

    assert "COMPLETED -> RUNNING" in str(exc_info.value)


def test_job_state_machine_fail_records_reason():
    from backend.src.scheduler.job_state_machine import JobStateMachine

    job = ScheduledJob(
        job_id="j3",
        name="demo3",
        cron_schedule="@every 1s",
        state=JobState.RUNNING,
    )
    fsm = JobStateMachine(job)
    fsm.fail("low battery")
    assert job.state == JobState.FAILED
    assert job.error_message == "low battery"


def test_v41_jobs_service_preserves_synchronous_compatibility_adapters():
    """V41: legacy bool methods remain sync and expose explicit async operations."""
    import inspect

    from backend.src.services.jobs_service import JobsService

    service = JobsService()

    assert not inspect.iscoroutinefunction(service.start_job)
    assert not inspect.iscoroutinefunction(service.delete_job)
    assert not inspect.iscoroutinefunction(service.pause_job)
    assert not inspect.iscoroutinefunction(service.resume_job)
    assert not inspect.iscoroutinefunction(service.cancel_job)
    assert inspect.iscoroutinefunction(service.delete_job_async)
    assert inspect.iscoroutinefunction(service.pause_job_async)
    assert inspect.iscoroutinefunction(service.resume_job_async)
    assert inspect.iscoroutinefunction(service.cancel_job_async)


def test_v41_sync_adapters_keep_safe_immediate_operations_without_a_loop():
    """Safe legacy operations remain immediate; mission starts still need a loop."""
    from backend.src.models.job import JobStatus, JobType
    from backend.src.services.jobs_service import JobsService

    service = JobsService()
    start_job = service.create_job("start", job_type=JobType.SCHEDULED_MOW, zones=["zone"])
    cancel_job = service.create_job("cancel", job_type=JobType.SCHEDULED_MOW, zones=["zone"])
    delete_job = service.create_job("delete", job_type=JobType.SCHEDULED_MOW, zones=["zone"])

    assert service.start_job(start_job.id) is False
    assert start_job.status == JobStatus.PENDING
    assert service.cancel_job(cancel_job.id) is True
    assert cancel_job.status == JobStatus.CANCELLED
    assert service.delete_job(delete_job.id) is True
    assert service.get_job(delete_job.id) is None


@pytest.mark.asyncio
async def test_job_task_exception_is_logged(caplog):
    """Unexpected wrapper failures remain observable through the done callback."""
    import asyncio
    import logging

    from backend.src.models.job import JobType
    from backend.src.services.jobs_service import JobsService

    service = JobsService()

    async def _raise(_job):
        raise ValueError("test job failure")

    service._execute_job = _raise  # type: ignore[method-assign]
    job = service.create_job("bad", job_type=JobType.SCHEDULED_MOW, zones=["zone"])

    with caplog.at_level(logging.ERROR, logger="backend.src.services.jobs_service"):
        assert service.start_job(job.id) is True
        task = service._job_tasks[job.id]
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    assert "test job failure" in " ".join(record.message for record in caplog.records)
