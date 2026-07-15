# Planning Subsystem

Last updated: 2026-05-12

## Overview

The planning subsystem lets operators define mowing zones, configure recurring
schedules, and automatically generate coverage paths without writing explicit
waypoints.  It was built incrementally across Tasks T1–T12 of the Phase 3 plan.

---

## Components

### Zones (`MapRepository`)

Zones are persistent GeoJSON-style polygons stored in SQLite by `MapRepository` in the
`map_zones` table.  All zone data is read from this table — it is the single source of
truth for spatial data and is **not** embedded in the map configuration envelope
(`map_config`).

The `zone_kind` column distinguishes zone roles:

| `zone_kind` | Planning role |
|---|---|
| `boundary` | Outer operating boundary; defines the gross mow area |
| `exclusion` | Obstacle / no-go; subtracted from coverage paths automatically |
| `mow` | Explicit mow polygon; path planner constrains scanlines to this area |

`PlanningService` queries `MapRepository` and filters rows by `zone_kind` to separate
the boundary polygon from exclusions and explicit mow zones before invoking the coverage
planner.

The legacy `exclusion_zone` boolean column is still present for backward compatibility
but `zone_kind` is authoritative.  New code must write and read `zone_kind`.

- API surface: `GET/POST?bulk=true /api/v2/map/zones` (bulk) and
  `GET/POST/PUT/DELETE /api/v2/map/zones/{zone_id}` (per-zone CRUD).
- Zone mutations broadcast a `planning.zone.changed` WebSocket event.
- See `docs/map-storage.md` for the full table schema, audit log format, and
  deprecated endpoint behaviour.

### Schedules / Jobs (unified SQLite backing store)

`/api/v2/planning/jobs` and `/api/v2/schedules` share the same SQLite table
(`planning_jobs`).  A "job" and a "schedule" are the same record; the two
surface names are aliases.

Key fields:

| Field | Type | Description |
|---|---|---|
| `id` | UUID string | Primary key |
| `name` | string | Human-readable label |
| `schedule` | `"HH:MM"` string | Local time to run (24-hour) |
| `timezone` | IANA tz name | e.g. `"America/New_York"`. Defaults to `"UTC"`. Used by `_calculate_next_run` to convert the local fire time to UTC. |
| `days_of_week` | list[int] | 0=Mon … 6=Sun; empty means every day |
| `zones` | list[string] | Zone IDs to mow (first element used as `zone_id`) |
| `pattern` | string | Coverage pattern (`"parallel"`) |
| `pattern_params` | dict | Pattern-specific parameters (see below) |
| `enabled` | bool | Whether the scheduler will fire this job |
| `last_run` | ISO-8601 string | Timestamp when `MissionService` last accepted the linked mission start; not proof of mission completion |

Timezone semantics: `_calculate_next_run` (in `JobsService`) builds a
`datetime` for the next fire time in the job's local timezone using
`zoneinfo.ZoneInfo`.  Invalid IANA names are rejected at validation time with a
400 error.

### `PlanningService`

Module-level singleton (`backend/src/services/planning_service.py`).
Injected with a `MapRepository` reference during app lifespan.

**Public API:**

```python
async def plan_path_for_zone(
    self,
    zone_id: str,
    pattern: str,    # "parallel" | raises NotImplementedError for spiral/random
    params: dict,    # spacing_m, angle_deg, speed_ms, blade_on, speed_pct
) -> PlannedPath
```

`PlannedPath` contains `waypoints: list[MissionWaypoint]`, `length_m`, and
`est_duration_s`.

Internally calls `plan_coverage()` from `backend/src/nav/coverage_planner.py`
which implements an arbitrary-angle boustrophedon (serpentine) algorithm without
Shapely.

When an operating-area snapshot is available, generated coverage points are
validated as connected segments before a mission is accepted. If a direct
connector would leave free space or cross an exclusion, planning fails instead
of silently creating an unsafe transit. The waypoint `blade_on` flag remains a
compatibility field and represents the requested blade state for motion into
that waypoint until an explicit leg/action model is added.

**Patterns:**

| Pattern | Status | Notes |
|---|---|---|
| `parallel` | Implemented | Serpentine scanlines at configurable angle and spacing |
| `spiral` | Not implemented | Raises `NotImplementedError` (501 from the API) |
| `random` | Not implemented | Raises `NotImplementedError` (501 from the API) |

**Default params:**

| Key | Default | Description |
|---|---|---|
| `spacing_m` | 0.35 | Scanline spacing in metres |
| `angle_deg` | 0.0 | Scanline bearing clockwise from North |
| `speed_ms` | 0.5 | Mower travel speed (for duration estimate only) |
| `blade_on` | `True` | Blade active for every waypoint |
| `speed_pct` | 50 | Motor speed percentage 0–100 |

### `JobsService`

`backend/src/services/jobs_service.py` — wired into `RuntimeContext` and the
app lifespan (T1).  Runs an async scheduler loop that:

1. Calls `_calculate_next_run()` for each enabled job to determine whether it
   should fire.
2. Calls `MissionService.create_mission(zone_id=..., pattern=..., pattern_params=...)`
   to create a mission with a *planning intent* (no waypoints yet).
3. Calls `MissionService.start_mission(mission_id)` to trigger lazy waypoint
   generation and dispatch to the navigation stack.
4. Emits the linked mission ID in the dispatch event/log and updates `last_run`
   in SQLite only after `MissionService` accepts the start. The planning row does
   not claim mission completion; the mission record is authoritative afterward.

The in-memory compatibility `Job` path uses the same admission flow, retains its
`mission_id`, and projects terminal truth from that mission. It must not run a
parallel timed executor or infer success from elapsed time.

Multi-zone jobs: only `zones[0]` is used as the target zone.  Multi-zone
parallel dispatch is out of scope.

### `MissionService` — lazy waypoint generation (T8)

When `create_mission(zone_id=..., pattern=..., pattern_params=...)` is called:

- No waypoints are generated immediately; the mission is stored with
  `waypoints=[]` and a `planning_intent` dict in SQLite.
- On `start_mission(mission_id)`, if the mission has a `planning_intent` and
  no waypoints, `PlanningService.plan_path_for_zone` is called to generate
  waypoints before the navigation task is spawned.
- Errors from the path planner surface as 400 `MissionValidationError`.

---

## Data Flow

```
Operator or scheduler
        │
        ▼
POST /api/v2/missions/create
  { zone_id, pattern, pattern_params }
        │
        ▼
MissionService.create_mission()
  ── stores planning_intent in SQLite ──► missions table
  ── no waypoints yet ──
        │
        ▼
POST /api/v2/missions/{id}/start
        │
        ▼
MissionService.start_mission()
  ── reads planning_intent ──
  ── PlanningService.plan_path_for_zone(zone_id, pattern, params) ──
        │
        ▼
plan_coverage(boundary_polygon, exclusions, spacing_m, angle_deg)
  ── returns list[LatLng] path points ──
        │
        ▼
NavigationService.set_planned_path(waypoints)
  ── mower begins following path ──
```

---

## Out of Scope

- **Spiral / random patterns:** `PlanningService` validates and raises
  `NotImplementedError`; the mission API returns 501.
- **Shapely-based lawnmower:** The `plan_coverage_shapely` path exists in
  `coverage_planner.py` but is xfailed in the test suite (Shapely 2.x
  `__slots__` incompatibility).
- **Multi-zone jobs:** `JobsService._dispatch_scheduled_job` uses `zones[0]`
  only.  Parallel dispatch across multiple zones requires a future task.

---

## Key Service Classes

| Class | File | Role |
|---|---|---|
| `PlanningService` | `services/planning_service.py` | Coverage path generation |
| `JobsService` | `services/jobs_service.py` | Scheduler/compatibility adapter + linked mission-state projection |
| `MissionService` | `services/mission_service.py` | Mission lifecycle + lazy waypoints |
| `MapRepository` | `core/map_repository.py` | SQLite zone persistence |

---

## Tests

| File | What it covers |
|---|---|
| `tests/unit/test_coverage_planner_angle.py` | Boustrophedon at arbitrary angles |
| `tests/unit/test_planning_service.py` | PlanningService: known-zone paths, missing-zone 404, unimplemented patterns |
| `tests/unit/test_jobs_schedule_timezone.py` | Timezone-aware `_calculate_next_run`, DST, invalid tz rejection |
| `tests/integration/test_planning_jobs_persistence.py` | Jobs survive simulated app restart (SQLite) |
| `tests/integration/test_scheduled_mission_dispatch.py` | JobsService fires create + start; emits mission identity; emergency-stop skip; accepted-start `last_run` update |
| `tests/integration/test_planning_e2e.py` | End-to-end: zone → schedule → mission with planning intent |
