# Navigation Tick Baseline Metric Implementation Plan (§12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument `NavigationService.update_navigation_state` to record per-call wall time as a timer metric so we have a baseline runtime number we can regression-test against once the §3 real-pose pipeline lands. Implements the first deliverable of §12 in `docs/major-architecture-and-code-improvement-plan.md` ("CPU per service under nominal mission load") for the navigation service.

**Architecture:** The codebase already has an `observability` singleton in `backend/src/core/observability.py` that exposes `MetricsCollector.record_timer(name, duration_ms)`. The `/metrics` endpoint at `backend/src/api/metrics.py` already serializes timers as `lawnberry_timer_<name>_count`, `_avg_ms`, `_min_ms`, `_max_ms`. Therefore this PR is purely additive: wrap the body of `update_navigation_state` in a `time.perf_counter()` measurement and record the duration under the timer name `navigation_tick_duration`. No new abstractions, no new endpoints, no new dependencies. The metric becomes a visible Prometheus-compatible series the moment the navigation tick fires.

**Tech Stack:** Python 3.11, existing `observability.metrics.record_timer` API, pytest, pytest-asyncio. No new dependencies.

**Out of scope for this plan:**

- CPU-time measurement (`psutil.Process().cpu_times()`) — wall time is what the handoff explicitly asked for; CPU time is a follow-up if/when we hit Pi thermal issues.
- Recording metrics for `go_to_waypoint` (the 5 Hz mission control loop) — separate concern; the handoff says "navigation tick", which is the periodic `update_navigation_state` called from telemetry.
- Adding histograms, percentiles, or per-component decomposition — `record_timer` already exposes count/avg/min/max which is enough for a baseline.
- Wiring a per-phase budget regression check (the plan §12 second deliverable) — that needs the baseline number first; comes in a follow-up PR.
- Event-persistence IO budget (§9) — separate change.
- Backfilling timers for other services (telemetry, robohat, blade) — out of scope.

---

## File Structure

**Created:**

- `docs/runtime-budget.md` — short operator/dev doc explaining what the metric measures, where to read it, and how to capture a baseline. ≤80 lines.
- `tests/contract/test_navigation_tick_metric.py` — contract test that the timer surfaces on `/metrics` after a tick. ≤40 lines.

**Modified:**

- `backend/src/services/navigation_service.py:1162` — wrap the body of `update_navigation_state` in a `time.perf_counter()` measurement and call `observability.metrics.record_timer("navigation_tick_duration", duration_ms)` in a `finally` block.
- `tests/unit/test_navigation_service.py` — add one unit test asserting the timer increments after a tick.

---

## Task 1: Instrument `update_navigation_state` with the timer

**Files:**

- Modify: `backend/src/services/navigation_service.py:1162`
- Test: `tests/unit/test_navigation_service.py`

- [ ] **Step 1: Write the failing unit test**

Append to `tests/unit/test_navigation_service.py` (after the existing imports add `from backend.src.core.observability import observability` if not already present):

```python
@pytest.mark.asyncio
async def test_update_navigation_state_records_tick_duration_metric():
    observability.reset_events_for_testing()
    nav = NavigationService()

    await nav.update_navigation_state(
        SensorData(gps=GpsReading(latitude=1.0, longitude=1.0, accuracy=0.5))
    )

    snapshot = observability.get_metrics_snapshot()
    timer = snapshot["timers"].get("navigation_tick_duration")
    assert timer is not None, "navigation_tick_duration timer should be recorded"
    assert timer["count"] == 1
    assert timer["avg"] >= 0.0
    assert timer["min"] >= 0.0
    assert timer["max"] >= timer["min"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SIM_MODE=1 uv run pytest tests/unit/test_navigation_service.py::test_update_navigation_state_records_tick_duration_metric -v`
Expected: FAIL with `AssertionError: navigation_tick_duration timer should be recorded` (the snapshot's `timers` map has no `navigation_tick_duration` key yet).

- [ ] **Step 3: Implement the timer instrumentation**

Edit `backend/src/services/navigation_service.py` around line 1162. The existing method signature is:

```python
async def update_navigation_state(self, sensor_data: SensorData) -> NavigationState:
    """Update navigation state with sensor fusion"""

    # Update position from GPS or dead reckoning
    current_position = await self._update_position(sensor_data)
    ...
    return self.navigation_state
```

Wrap the body so the duration is always recorded, even if the body raises. The minimal patch:

1. At the top of the file, ensure `from ..core.observability import observability` is imported (check existing imports first; the file already imports from `..core` for other things).
2. Refactor the public method into a thin wrapper that times an inner implementation. The simplest non-invasive pattern is:

```python
async def update_navigation_state(self, sensor_data: SensorData) -> NavigationState:
    """Update navigation state with sensor fusion."""
    start = time.perf_counter()
    try:
        return await self._update_navigation_state_impl(sensor_data)
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        observability.metrics.record_timer("navigation_tick_duration", duration_ms)

async def _update_navigation_state_impl(self, sensor_data: SensorData) -> NavigationState:
    """Original update_navigation_state body — measured by the public wrapper."""
    # ... existing body unchanged ...
```

`time` is already imported at the top of the file (`import time`). `observability` may not be — add the import alongside the other `..core` imports near the top of the file.

When renaming the body, **do not change any internal logic**. Just rename `update_navigation_state` to `_update_navigation_state_impl` and add the new public wrapper above it. Existing internal calls within the file (e.g. `self.update_navigation_state(...)` from `_run_bootstrap_and_check_geofence` at line 944) continue to use the public wrapper, which is correct — bootstrap ticks should also be measured.

- [ ] **Step 4: Run the new test to verify it passes**

Run: `SIM_MODE=1 uv run pytest tests/unit/test_navigation_service.py::test_update_navigation_state_records_tick_duration_metric -v`
Expected: PASS.

- [ ] **Step 5: Run the full navigation service test file**

Run: `SIM_MODE=1 uv run pytest tests/unit/test_navigation_service.py tests/unit/test_navigation_service_capture.py -v`
Expected: All previously-passing tests still pass. The pre-existing `xfail` marker on `test_go_to_waypoint_holds_until_fresh_gps_fix` is unchanged. No new failures.

- [ ] **Step 6: Commit**

```bash
git add backend/src/services/navigation_service.py tests/unit/test_navigation_service.py
git commit -m "feat(observability): record navigation tick wall-time as timer metric

Wrap NavigationService.update_navigation_state in a time.perf_counter()
measurement and record duration_ms via observability.metrics.record_timer
under the name navigation_tick_duration. Establishes the baseline runtime
metric required by §12 of the architecture plan."
```

---

## Task 2: Contract test that the metric surfaces on `/metrics`

**Files:**

- Create: `tests/contract/test_navigation_tick_metric.py`

- [ ] **Step 1: Write the failing contract test**

Create `tests/contract/test_navigation_tick_metric.py`:

```python
"""Contract: the navigation tick wall-time metric is exposed on /metrics."""

import pytest

from backend.src.api.metrics import metrics
from backend.src.core.observability import observability
from backend.src.models import GpsReading, SensorData
from backend.src.services.navigation_service import NavigationService


@pytest.mark.asyncio
async def test_navigation_tick_duration_appears_in_metrics_endpoint():
    observability.reset_events_for_testing()
    nav = NavigationService()
    await nav.update_navigation_state(
        SensorData(gps=GpsReading(latitude=1.0, longitude=1.0, accuracy=0.5))
    )

    body = metrics().body.decode()

    assert "lawnberry_timer_navigation_tick_duration_count 1" in body
    assert "lawnberry_timer_navigation_tick_duration_avg_ms" in body
    assert "lawnberry_timer_navigation_tick_duration_min_ms" in body
    assert "lawnberry_timer_navigation_tick_duration_max_ms" in body
```

- [ ] **Step 2: Run the test**

Run: `SIM_MODE=1 uv run pytest tests/contract/test_navigation_tick_metric.py -v`
Expected: PASS. Task 1's instrumentation already records the timer; this test just verifies the existing `/metrics` serializer renders it correctly. No production code change needed in this task — the test exists to lock the contract so future refactors of `metrics.py` don't accidentally drop the navigation tick output.

- [ ] **Step 3: Commit**

```bash
git add tests/contract/test_navigation_tick_metric.py
git commit -m "test(contract): lock navigation_tick_duration on /metrics endpoint

Verifies the timer recorded by NavigationService.update_navigation_state
surfaces on the Prometheus-compatible /metrics endpoint with the expected
lawnberry_timer_navigation_tick_duration_{count,avg_ms,min_ms,max_ms}
series names."
```

---

## Task 3: Document the runtime budget metric

**Files:**

- Create: `docs/runtime-budget.md`

- [ ] **Step 1: Write the doc**

Create `docs/runtime-budget.md` with the following content (no placeholders — this is the final text):

````markdown
# Runtime Budget — Navigation Tick

This document tracks the runtime cost of the navigation tick (`NavigationService.update_navigation_state`) so we can detect regressions as the architecture plan progresses (§3 real-pose pipeline, §1 RuntimeContext follow-ups, §9 event persistence).

The metric is the first deliverable of §12 ("Power, Thermal, and Runtime Budget") in `docs/major-architecture-and-code-improvement-plan.md`.

## What is measured

- **Series name:** `lawnberry_timer_navigation_tick_duration` (Prometheus-compatible).
- **Sub-series:** `_count` (number of ticks), `_avg_ms`, `_min_ms`, `_max_ms`.
- **Unit:** milliseconds of wall-clock time per call.
- **Scope:** entire body of `NavigationService.update_navigation_state` — pose update from GPS/dead-reckoning, heading fusion (IMU + GPS COG), obstacle detection, navigation-state mutation. Does not include `set_speed` or motor command delivery (those are outside the tick).

## How to read the current value

Run the backend and curl the metrics endpoint:

```bash
curl -s http://localhost:8000/metrics | grep navigation_tick_duration
```

Expected output shape:

```text
lawnberry_timer_navigation_tick_duration_count 1234
lawnberry_timer_navigation_tick_duration_avg_ms 4.21
lawnberry_timer_navigation_tick_duration_min_ms 0.83
lawnberry_timer_navigation_tick_duration_max_ms 18.07
```

## How to capture a baseline

A baseline pair `(avg_ms, max_ms)` should be captured on the target Pi 5 platform before each major architecture change, and committed to this doc with the date and HEAD SHA.

1. Boot the mower in `SIM_MODE=0` (real hardware) with a typical mission running.
2. Let the mission run for **at least 5 minutes** so the timer averages stabilize across waypoints, tank turns, and obstacle events.
3. Capture the metric once: `curl -s http://localhost:8000/metrics | grep navigation_tick_duration`.
4. Append a row to the baseline table below.

## Baseline history

| Date | HEAD SHA | Conditions | count | avg_ms | min_ms | max_ms | Notes |
|------|----------|------------|-------|--------|--------|--------|-------|
| _TBD — first capture pending operator yard run_ | | | | | | | Captured before §3 real-pose pipeline |

## Regression policy

- A change that increases `avg_ms` by more than 50% over the previous baseline must justify the cost in the PR description.
- A change that increases `max_ms` by more than 100% (a new tail latency spike) must include a follow-up issue or a mitigation note in the same PR.
- These thresholds are intentionally loose for the first two captured baselines while we learn the variance of the metric on real hardware. Tighten in a follow-up once we have ≥3 baseline rows.

## Related code

- Instrumentation: `backend/src/services/navigation_service.py` — the `update_navigation_state` wrapper.
- Endpoint: `backend/src/api/metrics.py` — Prometheus-compatible serializer.
- Plan reference: `docs/major-architecture-and-code-improvement-plan.md` §12.
````

- [ ] **Step 2: Verify the doc renders**

Run: `cat docs/runtime-budget.md | head -10`
Expected: file exists and shows the heading line `# Runtime Budget — Navigation Tick`. No tooling validation required (no docs lint in CI for non-spec markdown).

- [ ] **Step 3: Commit**

```bash
git add docs/runtime-budget.md
git commit -m "docs(observability): document navigation tick runtime budget metric

Adds docs/runtime-budget.md with the metric definition, how to read it
from /metrics, the procedure for capturing a baseline on real hardware,
and the regression policy. First baseline row is left as TBD pending an
operator yard run."
```

---

## Verification before PR

- [ ] **Step 1: Run the full test suite**

Run: `SIM_MODE=1 uv run pytest -q`
Expected: same pass/skip/xfail counts as the handoff baseline (600 passed, 47 skipped, 12 xfailed, 2 xpassed) **plus 2 new passes** from this PR (`test_update_navigation_state_records_tick_duration_metric` and `test_navigation_tick_duration_appears_in_metrics_endpoint`). Total: 602 passed, 47 skipped, 12 xfailed, 2 xpassed.

- [ ] **Step 2: Run lint**

Run: `uv run ruff check backend/src/services/navigation_service.py tests/unit/test_navigation_service.py tests/contract/test_navigation_tick_metric.py`
Expected: 0 errors. The repo pins `ruff==0.13.3` (per `.github/workflows/ci.yml`).

- [ ] **Step 3: Open the PR**

Push the branch and open a PR titled `feat(observability): baseline navigation tick runtime metric (§12)`. Body should reference this plan doc and the §12 section of the architecture plan, and call out that the first baseline-table row is left as TBD pending an operator yard run.
