"""Integration tests: JobsService is wired into RuntimeContext + lifespan.

Tests verify that:
  - jobs_service is attached to app.state.runtime after lifespan startup
  - the scheduler is running (scheduler_running=True) after startup
  - the scheduler is stopped (_scheduler_task is None) after lifespan teardown
"""
from __future__ import annotations


def test_scheduler_running_after_lifespan_startup():
    """Within a TestClient context, jobs_service is non-None and scheduler_running is True."""
    from fastapi.testclient import TestClient

    from backend.src.main import app

    with TestClient(app) as _client:
        runtime = getattr(app.state, "runtime", None)
        assert runtime is not None, "lifespan did not assign app.state.runtime"

        jobs_svc = getattr(runtime, "jobs_service", None)
        assert jobs_svc is not None, (
            "runtime.jobs_service should not be None after lifespan startup"
        )
        assert jobs_svc.scheduler_running is True, (
            "JobsService.scheduler_running should be True after lifespan startup"
        )


def test_scheduler_stopped_after_shutdown():
    """After the TestClient context exits, the scheduler is fully stopped."""
    from fastapi.testclient import TestClient

    from backend.src.main import app
    from backend.src.services.jobs_service import jobs_service as module_singleton

    with TestClient(app) as _client:
        runtime = getattr(app.state, "runtime", None)
        assert runtime is not None

    # After lifespan teardown, scheduler_running must be False and
    # _scheduler_task must be cleaned up (None).
    assert module_singleton.scheduler_running is False, (
        "JobsService.scheduler_running should be False after lifespan shutdown"
    )
    assert module_singleton._scheduler_task is None, (
        "JobsService._scheduler_task should be None after lifespan shutdown"
    )
