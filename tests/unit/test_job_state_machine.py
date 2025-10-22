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
