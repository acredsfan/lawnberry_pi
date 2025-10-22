import asyncio
import uuid

import pytest


@pytest.mark.asyncio
async def test_scheduler_runs_job_every_second():
    """Contract: A cron-like schedule including seconds should trigger the job.

    We use a 6-field cron expression: "*/1 * * * * *" (every second).
    The scheduler must invoke the callback within ~1.5s after start.
    """
    # Lazy import to avoid import errors before implementation exists
    from backend.src.scheduler.job_scheduler import JobScheduler

    ran = asyncio.Event()

    async def job_callback(job_id: str):
        ran.set()

    scheduler = JobScheduler(tick_interval=0.1)
    try:
        job_id = await scheduler.add_job(
            name=f"test-{uuid.uuid4()}",
            schedule="*/1 * * * * *",  # every second
            callback=job_callback,
        )

        await scheduler.start()

        # Wait up to 1.5 seconds for the job to run at least once
        try:
            await asyncio.wait_for(ran.wait(), timeout=1.5)
        finally:
            await scheduler.stop()

        assert ran.is_set(), "Scheduled job did not run within expected window"
        assert isinstance(job_id, str) and len(job_id) > 0
    finally:
        # Ensure clean shutdown in case of earlier exceptions
        try:
            await scheduler.stop()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_scheduler_supports_every_syntax():
    """Contract: @every syntax should also work with seconds resolution.
    Example: "@every 1s" triggers roughly once per second.
    """
    from backend.src.scheduler.job_scheduler import JobScheduler

    counter = 0
    done = asyncio.Event()

    async def job_callback(job_id: str):
        nonlocal counter
        counter += 1
        if counter >= 2:
            done.set()

    scheduler = JobScheduler(tick_interval=0.1)
    try:
        await scheduler.add_job(
            name="every-1s",
            schedule="@every 1s",
            callback=job_callback,
        )
        await scheduler.start()

        # Wait up to 2.5 seconds for two invocations
        try:
            await asyncio.wait_for(done.wait(), timeout=2.5)
        finally:
            await scheduler.stop()

        assert counter >= 2, f"Expected >=2 executions, got {counter}"
    finally:
        try:
            await scheduler.stop()
        except Exception:
            pass
