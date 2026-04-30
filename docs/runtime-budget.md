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
