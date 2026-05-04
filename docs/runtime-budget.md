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

---

## §12 Event Persistence IO Budget

This section tracks the write rate of the `mission_events` table introduced in
the §9 observability plan (`docs/superpowers/plans/2026-05-01-09-observability-events.md`).

### Persistence modes

Controlled by the `LAWNBERRY_PERSISTENCE_MODE` environment variable (default: `summary`).

| Mode | Events persisted | Approx writes/minute at 1 Hz nav | Approx bytes/minute |
|------|-----------------|----------------------------------|---------------------|
| `summary` | `mission_state_changed`, `safety_gate_blocked` | ≤2 (lifecycle events only) | ≤500 B/min |
| `full` | All 7 event types | ~60–120 (pose + commands) | ~18–36 KB/min |

**Default is `summary`.** Use `full` only for debugging sessions; do not leave `full`
enabled on a deployed Pi running unattended multi-hour missions.

### IO budget thresholds

- `summary` mode: **≤2 KB/minute** write ceiling (lifecycle events + safety blocks only).
- `full` mode: **≤50 KB/minute** write ceiling (development/debug only; not enforced in CI).
- Navigation tick metric (existing): unchanged from prior §12 entry above.

### How to set persistence mode

```bash
# Summary mode (default, field-safe):
export LAWNBERRY_PERSISTENCE_MODE=summary

# Full mode (debug sessions only):
export LAWNBERRY_PERSISTENCE_MODE=full
```

In `config/environment` or systemd unit `Environment=` stanza, set:

```
LAWNBERRY_PERSISTENCE_MODE=summary
```

### Measuring write rate

After a 5-minute mission with `LAWNBERRY_PERSISTENCE_MODE=full`:

```bash
# Check mission_events row count and approximate table size
sqlite3 data/lawnberry.db "
  SELECT COUNT(*) as rows, event_type FROM mission_events GROUP BY event_type;
"
sqlite3 data/lawnberry.db ".dbinfo" | grep "page size\|pages"
```

Divide total rows by elapsed minutes to validate the bytes/minute estimate.
Append a measurement row to the table below when first measured on real hardware.

### Baseline history

| Date | Mode | Run duration (min) | Events written | KB/min | Notes |
|------|------|--------------------|---------------|--------|-------|
| _TBD — first capture pending yard run with §9 deployed_ | | | | | |
