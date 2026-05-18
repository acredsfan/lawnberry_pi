# Waypoint Reliability — Design Spec

**Date:** 2026-05-18
**Status:** Approved, pending implementation plan

---

## Problem

A field test on 2026-05-18 showed the mower driving through waypoint 1 without triggering arrival detection. Log analysis identified five compounding failure modes:

| # | Failure | Root Cause |
|---|---------|-----------|
| 1 | Mower drove through waypoint at boosted speed | 119° heading error at leg start → Stall Escape A fired with boost throttle while mower was still turning |
| 2 | Arrival check never triggered | `_position_is_verified()` returns False when `accuracy=None`; loop `continue`s, skipping the distance check entirely |
| 3 | 0.5m tolerance unachievable with consumer GPS | Standard outdoor GPS CEP is 1–3m; the mower can be physically at the waypoint while GPS reports it 1.2m away |
| 4 | No speed reduction near waypoint | Full cruise speed (0.5 m/s) into a 0.5m zone = ~1 detection tick; one GPS lag = slip-through |
| 5 | Bootstrap heading committed from single GPS COG sample | One multipath-affected reading can produce a 90°+ heading error that persists the entire mission |

Together these produced the observed overshoot: the mower entered Stall Escape A boost mode (extra throttle while turning) at mission start, drove through the waypoint zone at elevated speed, and the position-verification gate suppressed the distance check at the critical moment.

---

## Goal

Make waypoint arrival detection reliable in outdoor residential GPS conditions so that:
- Geometric mowing patterns (parallel stripes, spirals) have clean edges with no missed corners
- A single GPS noise event cannot cause a waypoint to be skipped entirely
- The mower rotates to the correct heading before moving forward, preventing overshoot at leg start

---

## Fix 1 — Pre-rotation gate

**Files:** `backend/src/services/mission_executor.py`

### Behavior

Add a `_pre_rotating: bool` flag to `go_to_waypoint()`. It activates when `go_to_waypoint` is first called for a waypoint leg if the initial **absolute** heading error (`abs(heading_error(current_hdg, bearing_to_target))`) exceeds **45°**. While active, the forward speed component passed to `compute_blend_speeds` is clamped to **0.05 m/s** (essentially stationary — enough to keep blend-mode heading differential active but not enough to translate the mower).

Deactivation condition: absolute heading error drops below **20°**. Normal speed selection (cruise speed / decel taper) resumes immediately.

The gate does not fire if the initial heading error is ≤ 45° — legs that are already roughly aligned proceed without any added latency.

### Stall-escape interaction

Stall Escape A arms when `raw_abs_err > 20°` for several seconds. Pre-rotation resolves heading error within those seconds, clearing the condition before Stage B escalation. As an explicit safety guard, the stall-escape timer is reset when `_pre_rotating` clears, so the timer doesn't inherit accumulated pre-rotation time.

### Speed precedence

When pre-rotation and decel taper are both active (short legs < 4.5m), the pre-rotation cap (0.05 m/s) wins over `min_approach_speed` (0.15 m/s).

### Tests

- Unit: leg starting at 119° heading error does not advance mower position > 0.15m until heading error < 20°
- Unit: leg starting at 30° heading error does not activate pre-rotation flag

---

## Fix 2 — Waypoint tolerance widened to 1.5m

**Files:** `backend/src/models/system_configuration.py`, `backend/src/services/navigation_service.py`, `backend/src/services/mission_executor.py`, `backend/src/models/mission.py`

### Behavior

Change the `waypoint_tolerance` default from `0.5m` to `1.5m` in all three service/config locations. No logic changes.

Consumer-grade GPS (u-blox M8/M9) has a CEP of 1.0–2.5m outdoors. 0.5m is inside the noise floor. 1.5m provides reliable detection while keeping pattern geometry tight enough for residential stripe mowing.

### Per-waypoint override

Add an optional `arrival_threshold_m: float | None = None` field to `MissionWaypoint`. When set, `go_to_waypoint` uses it in place of `self.waypoint_tolerance`. This allows critical boundary waypoints (e.g., last point before a garden bed) to use a tighter tolerance (e.g., 0.8m) while interior waypoints remain at 1.5m.

All existing missions that omit the field continue to work unchanged (None → fall through to `self.waypoint_tolerance`).

### Tests

- Update all existing arrival-check unit tests from 0.5m to 1.5m
- Unit: per-waypoint override of 0.8m is used when field is set
- Unit: per-waypoint field of None falls back to executor default

---

## Fix 3 — Deceleration taper

**Files:** `backend/src/services/mission_executor.py`

### Behavior

When `distance_to_target < decel_start_distance` (= 3 × `waypoint_tolerance`, so **4.5m** at 1.5m default), replace flat `cruise_speed` with:

```
approach_speed = max(min_approach_speed, cruise_speed × (distance / decel_start_distance))
```

Constants:
- `min_approach_speed = 0.15 m/s` — slow enough for reliable detection, fast enough to avoid GPS-stall escape arm
- `decel_start_distance = 3 × waypoint_tolerance` (derived, not hardcoded)

At 0.15 m/s and 5 Hz, the mower travels 0.03m per tick — 50 detection ticks within the 1.5m arrival zone. Zero chance of slip-through.

### Interaction with pre-rotation

When both gates are active, `min(pre_rotation_cap, approach_speed)` applies. Pre-rotation cap (0.05 m/s) always dominates until heading is settled, then taper takes over cleanly.

### Interaction with GPS stall escape

GPS stall escape arms after 8s without 0.15m movement. At `min_approach_speed` (0.15 m/s) the mower covers 0.15m in 1s — well within the 8s window.

### Tests

- Unit: speed output at `distance = decel_start_distance` equals `cruise_speed`
- Unit: speed output at `distance = 0.5 × decel_start_distance` equals `cruise_speed × 0.5`
- Unit: speed output at `distance = waypoint_tolerance` equals `min_approach_speed`
- Integration: mower does not overshoot a simulated 1.5m arrival zone when starting from 10m at cruise speed

---

## Fix 4 — Position-verification fallback

**Files:** `backend/src/services/mission_executor.py`

### Behavior

Split the current binary `_position_is_verified()` path into three tiers at the arrival check site:

| Tier | Condition | Arrival behavior |
|------|-----------|-----------------|
| **Full confidence** | position exists, not dead-reckoning, fix age < 2.0s, accuracy within threshold | Check distance vs `waypoint_tolerance` (1.5m) — unchanged |
| **Degraded confidence** | position exists, fix age < 5.0s, but `accuracy=None` or marginally stale | Check distance vs `2 × waypoint_tolerance` (3.0m); log `WARNING: waypoint arrival in degraded GPS mode` |
| **No confidence** | dead-reckoning active or position `None` | Issue stop command, hold — unchanged |

`accuracy=None` and dead-reckoning are very different conditions. `accuracy=None` means a GPS metadata field is unpopulated (common on some u-blox firmware configs). Dead-reckoning means the fix is genuinely lost. The original code treated them identically, causing silent skip of arrival detection for minutes.

### `_position_is_verified` refactor

The existing method returns a single bool. It is replaced by `_position_confidence() -> Literal["full", "degraded", "none"]`. The existing `_position_is_verified()` method is kept as a shim (`return self._position_confidence() == "full"`) for any callers outside `go_to_waypoint`.

### Tests

- Unit: `_position_confidence()` returns `"degraded"` when `accuracy=None` and fix age = 3s
- Unit: `_position_confidence()` returns `"none"` during dead-reckoning
- Unit: `_position_confidence()` returns `"full"` under nominal conditions
- Unit: arrival check uses 3.0m zone in degraded mode, 1.5m in full mode

---

## Fix 5 — Bootstrap multi-sample

**Files:** `backend/src/services/localization_service.py`

### Behavior

Replace the single-sample GPS COG snap with a consistency-gated commit:

1. During bootstrap, each tick where the mower is moving straight (existing gate), append the computed COG to a circular buffer (max 5 readings).
2. Commit when `len(buffer) >= 3` **and** `max(buffer) - min(buffer) < 15°`. Snap delta = mean of buffer.
3. **Fallback**: if the bootstrap drive completes without 3 consistent readings (e.g., GPS multipath throughout), commit the mean of whatever readings exist. Bootstrap always completes — it never hangs. A `WARNING: bootstrap heading uncertain (spread=Xdeg, samples=N)` is logged.
4. After committing, if the heading error on the first waypoint leg exceeds 30°, log `WARNING: bootstrap heading uncertain — first-leg error exceeds 30°` to aid field debugging.

`reset_for_mission()` flushes the COG buffer so each mission starts clean.

### Why 3 / 15°

3 samples = 0.6s additional bootstrap drive at 5 Hz. Negligible on a residential lawn. 15° spread filters GPS multipath spikes (brief reflections off buildings) without requiring perfect conditions.

### Tests

- Unit: COG sequence [210°, 355°, 212°, 211°, 213°] — 355° spike rejected; commitment on readings 3–5 with mean ≈ 211.5°
- Unit: COG sequence with persistent 30°+ spread triggers fallback; WARNING is logged; bootstrap completes
- Unit: `reset_for_mission()` flushes buffer; second mission starts with empty buffer

---

## Summary of changes

| Fix | Files touched | Config change | Logic change |
|-----|--------------|---------------|--------------|
| Pre-rotation gate | `mission_executor.py` | No | Yes — speed clamp on leg entry |
| Tolerance 1.5m + per-waypoint field | `system_configuration.py`, `navigation_service.py`, `mission_executor.py`, `mission.py` | Yes | Minor — None fallback |
| Decel taper | `mission_executor.py` | No | Yes — speed formula near waypoint |
| Position-confidence tiers | `mission_executor.py` | No | Yes — `_position_confidence()` replaces bool |
| Bootstrap multi-sample | `localization_service.py` | No | Yes — buffer + consistency gate |

---

## Out of scope

- State-machine refactor of `go_to_waypoint` (Approach B) — deferred to a future session once this behavior is solid
- Automatic `LAWNBERRY_CAPTURE_PATH` injection into systemd service — operational change, separate PR
- Spiral / checkerboard mission pattern generation — future feature work
