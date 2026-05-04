"""§12 per-phase budget regression check.

Reads the navigation_tick_duration metric from the /metrics endpoint after
running N simulated navigation ticks and asserts avg_ms is within budget.

The threshold (NAV_TICK_BUDGET_AVG_MS) is the value documented in
docs/runtime-budget.md §12 threshold. Fail CI if a change exceeds this
threshold without a justification note in the PR.

This test runs in SIM_MODE=1 via TestClient (no hardware required). Navigation
ticks are driven through the singleton NavigationService that is wired into the
app lifespan — the same path used in production, measured by the same
`navigation_tick_duration` timer that feeds the /metrics endpoint.

Mark skip with pytest.mark.skip(reason="...") + a justification comment
if temporarily exceeding budget during an architecture change phase.
"""
import asyncio
import os

import pytest

# Navigation tick average budget from docs/runtime-budget.md §12 threshold.
# Current budget: 15 ms average per tick on Pi 5 with SIM_MODE=1.
# Tighten this once >=3 real-hardware baseline rows exist in the table.
NAV_TICK_BUDGET_AVG_MS = 15.0

os.environ.setdefault("SIM_MODE", "1")


@pytest.fixture(scope="module")
def client_with_ticks():
    """Return a TestClient after running 10 navigation ticks to populate the timer.

    Uses the app's real lifespan so that NavigationService.get_instance() is the
    same singleton recorded in app.state.runtime.navigation. Ticks are run via
    asyncio so the async update_navigation_state coroutine is awaited correctly.
    """
    from backend.src.main import app
    from backend.src.core.runtime import get_runtime
    from backend.src.core.observability import observability
    from backend.src.models.sensor_data import GpsReading, SensorData
    from fastapi.testclient import TestClient

    # Reset metrics so only ticks from this fixture appear in the budget check.
    observability.reset_events_for_testing()

    with TestClient(app) as client:
        real_runtime = app.state.runtime
        app.dependency_overrides[get_runtime] = lambda: real_runtime

        # Use the nav singleton that lifespan wired into the runtime so the
        # recorded timer flows to the shared observability.metrics instance.
        nav = real_runtime.navigation

        sensor_data = SensorData(
            gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=0.5)
        )

        for _ in range(10):
            asyncio.get_event_loop().run_until_complete(
                nav.update_navigation_state(sensor_data)
            )

        try:
            yield client
        finally:
            app.dependency_overrides.pop(get_runtime, None)


def test_navigation_tick_avg_ms_within_budget(client_with_ticks):
    """avg_ms of navigation_tick_duration must stay below NAV_TICK_BUDGET_AVG_MS."""
    import re

    resp = client_with_ticks.get("/metrics")
    assert resp.status_code == 200
    body = resp.text

    match = re.search(
        r"lawnberry_timer_navigation_tick_duration_avg_ms\s+([\d.]+)", body
    )
    assert match, (
        "navigation_tick_duration_avg_ms not found in /metrics output.\n"
        f"Metrics body:\n{body[:2000]}"
    )
    avg_ms = float(match.group(1))
    assert avg_ms < NAV_TICK_BUDGET_AVG_MS, (
        f"Navigation tick avg_ms={avg_ms:.2f} exceeds budget of "
        f"{NAV_TICK_BUDGET_AVG_MS} ms. "
        "If this is justified by an architecture change, document it in "
        "docs/runtime-budget.md and raise the threshold with a PR justification comment."
    )


def test_navigation_tick_metric_present(client_with_ticks):
    """All four navigation_tick sub-series are present in /metrics."""
    resp = client_with_ticks.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    for suffix in ("_count", "_avg_ms", "_min_ms", "_max_ms"):
        assert f"lawnberry_timer_navigation_tick_duration{suffix}" in body, (
            f"Missing metric suffix: navigation_tick_duration{suffix}"
        )


def test_navigation_tick_count_at_least_ten(client_with_ticks):
    """After 10 ticks the count metric must be >= 10."""
    import re

    resp = client_with_ticks.get("/metrics")
    assert resp.status_code == 200
    body = resp.text

    match = re.search(
        r"lawnberry_timer_navigation_tick_duration_count\s+([\d.]+)", body
    )
    assert match, "navigation_tick_duration_count not found in /metrics output."
    count = int(float(match.group(1)))
    assert count >= 10, (
        f"Expected at least 10 recorded ticks, got {count}. "
        "The timer is not being populated by update_navigation_state()."
    )
