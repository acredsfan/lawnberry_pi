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


@pytest.mark.asyncio
async def test_job_task_exception_logged(caplog):
    """Exceptions from _execute_job must be logged, not silently discarded."""
    import logging
    import asyncio
    from backend.src.services.jobs_service import JobsService, JobStatus
    from backend.src.models.job import Job, JobType, JobPriority
    from datetime import datetime, timezone

    svc = JobsService()

    async def _raise(_job):
        raise ValueError("test job failure")

    svc._execute_job = _raise  # monkey-patch to force unhandled exception

    job = Job(
        id="j1",
        name="bad",
        job_type=JobType.SCHEDULED_MOW,
        status=JobStatus.PENDING,
        priority=JobPriority.NORMAL,
        zones=[],
        created_at=datetime.now(timezone.utc),
    )
    svc.jobs["j1"] = job

    with caplog.at_level(logging.ERROR, logger="backend.src.services.jobs_service"):
        svc.start_job("j1")
        await asyncio.sleep(0.2)

    all_messages = " ".join(r.message for r in caplog.records)
    assert "test job failure" in all_messages or "Unhandled" in all_messages, \
        f"Expected error log for failed job task; caplog: {all_messages}"
