import asyncio
import pytest


@pytest.mark.asyncio
async def test_weather_postponement_defers_job(monkeypatch):
    """Contract: Jobs must be postponed when weather is unsuitable (FR-036).

    We inject a weather predicate that returns unsuitable and assert the
    scheduler does not execute the job within the window.
    """
    from backend.src.scheduler.job_scheduler import JobScheduler

    ran = asyncio.Event()

    async def job_callback(job_id: str):
        ran.set()

    # Weather predicate: always unsuitable
    def weather_unsuitable() -> bool:
        return False  # returns False for 'suitable'; here we invert in scheduler call

    scheduler = JobScheduler(tick_interval=0.1)

    try:
        await scheduler.add_job(
            name="weather-test",
            schedule="*/1 * * * * *",  # every second
            callback=job_callback,
        )
        # Start with weather gating: suitable=False should postpone
        await scheduler.start(weather_suitable=lambda: False)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ran.wait(), timeout=1.6)

    finally:
        try:
            await scheduler.stop()
        except Exception:
            pass
