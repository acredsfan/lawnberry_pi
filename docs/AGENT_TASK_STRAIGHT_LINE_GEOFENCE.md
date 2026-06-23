# Agent Task: Make LawnBerry Track Straight Mission Legs and Enforce a Fail-Closed Yard Geofence

## Repository

`https://github.com/acredsfan/lawnberry_pi`

This task is based on the current `main` branch inspected on **2026-06-23**. Reinspect the current branch before editing because line numbers may have moved.

Read and follow these repository instructions first:

1. `AGENTS.md`
2. `docs/developer-toolkit.md`
3. `.github/copilot-instructions.md`
4. `docs/diagnostics-replay.md`
5. Relevant navigation, planning, boundary, and safety documentation

Check `git status --short` before editing and preserve unrelated user changes. Keep the implementation focused. Do not replace the navigation stack wholesale or change documented motor/IMU wiring conventions.

## Assignment

Implement and verify the smallest complete solution that makes all of these execution paths behave correctly:

1. Explicit waypoints created in the Mission Planner and started through `/api/v2/missions/{id}/start`.
2. Automatically generated parallel mowing missions created from a zone, including scheduled jobs.
3. Any legacy `/api/v2/control/start` behavior that currently claims autonomous navigation is running.

The mower must:

- Track the **planned line segment** from waypoint to waypoint instead of merely holding a compass bearing.
- Recover toward the line after lateral displacement, unequal motor output, wheel slip, or an off-line start.
- Never intentionally travel directly through an exclusion zone or outside a concave operating polygon while connecting two valid endpoints.
- Fail closed whenever a valid, user-confirmed safe yard boundary or sufficiently accurate localization is unavailable.
- Stop before crossing the safe boundary rather than waiting until GPS reports that it is already outside.
- Keep the blade off during bootstrap, transit, turns, holds, faults, and any unverified motion.

Do not stop after writing a plan. Implement the code, tests, documentation, and verification evidence.

---

## Safety invariant

No software-only system can promise physical containment despite hardware failure, GNSS error, momentum, wheel slip, or actuator faults. The software requirement is therefore:

> **No nonzero autonomous drive or blade command may be authorized unless the software can demonstrate, from fresh localization and a valid operating-area snapshot, that the mower's current footprint and predicted stopping envelope remain inside free space. Any uncertainty must result in a stop, not a permissive fallback.**

This invariant must exist at the final motor-command authorization layer, not only in mission planning or the UI.

---

## Confirmed defects in the current implementation

Treat these as root causes to fix, not symptoms to work around.

### 1. Stanley cross-track correction is effectively disabled in production

Relevant files:

- `backend/src/services/navigation_service.py`
- `backend/src/services/mission_executor.py`
- `backend/src/services/localization_service.py`
- `backend/src/nav/waypoint_geometry.py`

`_NavStateLocalizationAdapter` exposes position, heading, dead-reckoning state, and GPS-fix time, but it does not expose the velocity, IMU-valid/heading-source, or pose-quality fields that `MissionExecutor` attempts to discover through `.state`.

The executor consequently sees:

- no localization state,
- velocity of `0.0`, and
- a GPS-only leg.

Its low-speed GPS-smoothing condition then bypasses `cross_track_error()` and `stanley_steer()`, leaving heading-only steering. Heading hold can drive parallel to the requested path while retaining a lateral offset.

### 2. Boundary handling fails open

Relevant files:

- `backend/src/services/navigation_service.py`
- `backend/src/services/mission_service.py`

Current behavior permits autonomous execution when:

- no safe boundary exists,
- the `MapRepository` is unavailable,
- boundary loading raises an exception, or
- no mowing-area zones are found.

`_validate_waypoints_in_geofence()` returns successfully when boundaries are empty. This must be reversed for live autonomous motion.

### 3. Loading the generated safe boundary discards exclusions

`NavigationService._load_boundaries_from_zones()` returns immediately after loading `mowing_boundary_safe.json` and explicitly sets `no_go_zones = []`. The outer safe boundary and internal exclusions are separate concepts and must be loaded together.

### 4. Code assumes the first boundary polygon is authoritative

Several paths use `safety_boundaries[0]`. This is unsafe when multiple boundary or mow zones exist. The active yard envelope and selected mow zone must be explicit and deterministic.

### 5. Only waypoint coordinates are validated

Endpoints can both lie inside a concave polygon while the straight segment between them exits the polygon. Likewise, endpoints can lie outside an exclusion while their connecting segment crosses it. Validate complete legs and their safety envelope, not just points.

### 6. Runtime geofence enforcement is reactive

The sensor pump latches an emergency only after the reported center position is outside the polygon. It does not account for:

- mower footprint,
- GPS uncertainty,
- fix age,
- stopping distance,
- command latency,
- current heading and wheel command, or
- predicted motion.

### 7. Coverage planning can connect separated scanline segments directly

`backend/src/nav/coverage_planner.py` appends clipped scanline endpoints into one continuous point list. When an exclusion or concavity splits a row, consecutive points can create an unsafe direct connector across excluded or exterior space.

### 8. Heading bootstrap can travel too far in an unknown direction

The current bootstrap is time-bounded but not tightly distance-bounded. At the configured speed it could travel several metres before timing out. Before true heading is known, the code cannot assume that direction is safe near an edge or exclusion.

### 9. Mission navigation bypasses the stated command gateway

`_NavGatewayAdapter` calls `NavigationService.set_speed()`, which sends commands directly to `RoboHATService`. Autonomous commands therefore bypass `MotorCommandGateway`, where final safety authorization should occur.

### 10. Mission blade intent is not executed safely

`MissionWaypoint.blade_on` is stored and generated but is not consumed by `MissionExecutor`. Generated coverage currently marks every waypoint alike, which is also insufficient for distinguishing mow legs from blade-off transit and turns.

### 11. `/api/v2/control/start` can report success without an executor

`start_autonomous_navigation()` changes navigation state but does not start a waypoint control task or send drive commands. It must either delegate to the real mission executor or return a clear not-supported/not-ready response. It must never claim motion is running when no execution loop exists.

---

## Required implementation

The exact class names may vary, but preserve these responsibilities and invariants.

## A. Create one authoritative operating-area service

Introduce a focused geometry/service layer, for example:

- `backend/src/services/operating_area_service.py`, or
- `backend/src/nav/operating_area.py`

It should produce an immutable `OperatingAreaSnapshot` containing at least:

- Valid user-confirmed outer yard boundary.
- Generated inward safe boundary used for the mower center.
- All active no-go/exclusion polygons.
- Free-space geometry: safe outer polygon minus inflated exclusions.
- Boundary source, creation time, configured buffer, revision/hash, and validity state.
- A deterministic selected mow zone when the mission was created from `zone_id`.

Use local metric ENU/UTM geometry with Shapely; do not perform metre-scale buffering directly in latitude/longitude degrees.

### Boundary source rules

- The imported parcel boundary is never authoritative for autonomous motion.
- Live autonomous motion requires a user-confirmed boundary and a valid generated safe boundary.
- Store a stable hash/revision of the confirmed boundary in the generated safe-boundary payload.
- Reject startup if the safe boundary is missing, invalid, collapsed, or was generated from a different confirmed-boundary revision.
- A raw map-zone fallback may remain available for simulation or explicit operator diagnostics, but it must not silently enable live autonomous motion.
- `zone_kind` is authoritative. Preserve legacy `exclusion_zone` compatibility only at the storage/API boundary.
- Load exclusions even when the generated safe outer boundary exists.
- Do not use `safety_boundaries[0]` as an implicit selection rule.

### Geometry API

Provide pure, testable operations such as:

- `contains_center(position)`
- `contains_footprint(position, uncertainty_m)`
- `distance_to_boundary(position)`
- `segment_is_safe(start, end, margin_m)`
- `path_is_safe(points, margin_m)`
- `swept_motion_is_safe(pose, left_speed, right_speed, ...)`
- `validate_ready_for_autonomy()`

Use `covers`/buffered geometry deliberately so boundary semantics are explicit and tested.

## B. Centralize safety configuration

Do not scatter new constants through services. Add typed fields to the existing safety configuration model and YAML configuration where appropriate. At minimum provide configurable values for:

- Maximum autonomous GPS accuracy; default should require RTK-grade accuracy, no worse than `0.25 m`.
- Maximum autonomous GPS-fix age; default approximately `2.0 s`.
- Mower footprint radius or half-width.
- Differential-drive wheelbase if it is not already canonical elsewhere.
- Fixed geofence safety allowance.
- Prediction horizon and command TTL.
- Assumed braking/deceleration capability or conservative stopping-distance parameters.
- Bootstrap speed and maximum bootstrap travel distance.
- Coverage endpoint/turn clearance.
- Maximum operational cross-track error before a controlled stop or recovery.

Avoid duplicate wheelbase, footprint, or GPS thresholds in multiple modules. Validate values with Pydantic.

## C. Fix the localization contract and activate line tracking

Define an explicit typed protocol for the executor's localization dependency. It must expose, without introspecting an optional `.state` attribute:

- `current_position`
- `heading`
- `velocity`
- `heading_source` or `imu_valid`
- `pose_quality`
- `dead_reckoning_active`
- `last_gps_fix`
- current accuracy/uncertainty

Update `_NavStateLocalizationAdapter`, `LocalizationService`, and/or runtime wiring so production supplies real values. Mirror localization velocity and quality into `NavigationState` if that remains the compatibility facade.

Requirements for `MissionExecutor`:

- Use the planned segment bearing and signed cross-track error on every normal tracking tick with valid pose data.
- Do not silently disable cross-track correction merely because the measured velocity is below `0.3 m/s`; `stanley_steer()` already has a velocity floor. Adjust gain/smoothing by pose quality if needed.
- Keep the first leg anchored to the actual accepted starting position.
- Keep later legs anchored to the planned previous waypoint so lateral arrival error is corrected on the next planned line.
- Retain tank-turn hysteresis for large heading errors.
- Preserve existing motor-direction conventions and verify both manual and mission directions after routing commands through the gateway.
- Expose current path bearing, CTE, steering command, velocity, heading source, and safety clearance in `nav_debug`.

Do not solve this by merely increasing steering gain. The production data path must actually feed the existing controller.

## D. Add along-track progress and overshoot handling

Distance-to-waypoint alone is insufficient.

For every leg, calculate projection/along-track progress in the same local metric frame. Implement explicit behavior:

- Normal arrival when inside the effective arrival radius.
- If the mower crosses the target's perpendicular plane while within a bounded lateral tolerance, accept the waypoint without driving indefinitely away from it.
- If it passes the target with excessive CTE, stop and enter a bounded recovery/replan path; do not keep the original constant bearing indefinitely.
- Abort safely if bounded recovery fails.

Add unit tests for all three cases.

## E. Route every autonomous command through `MotorCommandGateway`

Inject the existing command gateway into the navigation/mission execution path. `NavigationService.set_speed()` must not be the live mission path directly to `RoboHATService`.

Dispatch mission commands using a typed `DriveCommand` with:

- `source="mission"`,
- a short TTL compatible with the control-loop cadence, and
- normalized/clamped wheel outputs.

The gateway must become the final authorization point for autonomous motion. Add autonomous interlocks separate from manual-session checks.

Before accepting any nonzero mission drive command, verify:

1. No emergency or safety interlock is active.
2. Hardware telemetry is live.
3. A valid operating-area snapshot exists.
4. The GPS fix is fresh and within the configured autonomous accuracy threshold.
5. Dead reckoning is not being used as authority for boundary containment.
6. The current footprint is inside free space.
7. The predicted swept footprint and stopping envelope remain inside free space.
8. No active ToF/obstacle stop condition blocks the command.
9. The active boundary revision still matches the mission's validated revision.

Zero-speed and blade-off commands must remain deliverable during fault conditions.

### Predictive geofence guard

Implement this as a pure/testable calculation where possible:

- Convert the current pose and differential wheel command to a short-horizon trajectory.
- Include command latency and conservative stopping distance.
- Buffer the trajectory by mower footprint plus localization uncertainty and fixed allowance.
- Require the complete swept envelope to be covered by free space.
- Tank turns must validate the stationary rotational footprint.
- Commands directed toward an edge must be blocked early enough to stop inside the safe boundary.
- An outward unsafe command should stop/latch a geofence safety fault; an inward command from the same near-edge pose may be allowed only if the current footprint is still valid.

If the current footprint is already outside free space, immediately command drive stop, command blade off, latch the emergency/safety state, and fail the mission.

## F. Make GPS degradation fail safe

During autonomous execution:

- A stale fix, accuracy beyond the autonomous threshold, missing position, or unbounded dead-reckoning state must stop motion.
- Do not continue a live mission under the current broad `5 m` waypoint accuracy allowance.
- A short stopped grace period for RTK recovery is acceptable, but automatic movement must not resume without reauthorization.
- Require operator resume after a geofence/localization safety stop unless the repository already has an established, tested safety-state recovery contract.
- Blade off must precede or accompany the drive stop.

## G. Make heading bootstrap boundary-safe

The bootstrap must be blade-off and distance-bounded.

Required behavior:

- Verify a valid operating area and fresh RTK-grade position before motion.
- Verify sufficient free-space clearance for an initially unknown travel direction. A conservative radial-clearance check is acceptable.
- Use a low configured speed.
- Stop after the configured maximum distance, even if the time deadline has not elapsed.
- Stop immediately if the predictive geofence guard or localization gate fails.
- Abort the mission if heading cannot be aligned within both the time and distance budget.
- Do not first check containment only after completing the bootstrap drive.

A bootstrap near a boundary or exclusion must be rejected while stopped, with a clear remediation message telling the operator to reposition the mower farther inside the safe area.

## H. Validate full mission paths before start and resume

At mission start and resume, validate against the current immutable operating-area snapshot:

- Current mower footprint and required bootstrap clearance.
- Every waypoint.
- Every direct leg, including the initial mower-position-to-first-waypoint leg.
- Every leg's configured safety margin.
- Exclusions/no-go zones.
- Active boundary revision.
- GPS quality and hardware readiness.

If the boundary or exclusions change during a mission, stop and invalidate the current path. Require revalidation/replanning before movement resumes.

Return explicit API errors such as:

- `SAFE_BOUNDARY_REQUIRED`
- `SAFE_BOUNDARY_STALE`
- `PATH_EXITS_SAFE_AREA`
- `PATH_CROSSES_EXCLUSION`
- `INSUFFICIENT_BOOTSTRAP_CLEARANCE`
- `LOCALIZATION_NOT_RTK_GRADE`
- `GEOFENCE_PREDICTION_BLOCKED`

Do not replace these with generic 500 responses.

## I. Fix coverage generation and transit routing

Create an explicit distinction between mowing and transit legs.

Recommended model:

- A leg/segment has a start, end, action (`mow` or `transit`), requested speed, and blade state.
- Maintain backward API compatibility with existing waypoint payloads where practical.
- Document whether waypoint `blade_on` applies to the incoming or outgoing leg if retaining the boolean.

For generated coverage:

1. Build the coverage area from the selected mow zone intersected with the safe yard area, minus inflated exclusions.
2. Generate stripe segments inside a further endpoint/turn margin.
3. Treat each clipped stripe portion as a distinct mow segment.
4. Before connecting segment endpoints, test whether the direct connector is inside free space.
5. If not, route a blade-off transit using the existing A* planner or another bounded in-repository path planner.
6. Validate the routed connector before accepting it.
7. If no route exists, fail planning instead of connecting through unsafe space.
8. Simplify transit paths only when the simplified line remains inside free space.

All transitions, turns, obstacle routes, approach-to-first-stripe travel, pause/resume holds, and return/recovery movement must be blade off unless explicitly proven to be a mowing leg.

## J. Implement mission blade sequencing through the gateway

Use `MotorCommandGateway.dispatch_blade()` with `source="mission"`.

Required behavior:

- Blade off before bootstrap.
- Blade off while traveling to the first mowing segment.
- Blade on only immediately before an authorized mow leg.
- Blade off before turns and transit legs.
- Blade off on pause, abort, completion, GPS degradation, obstacle stop, geofence block, motor-command failure, or any exception.
- If blade-off delivery cannot be confirmed, latch emergency and fail the mission.
- Never infer blade state only from a UI value; use acknowledged service state.

Do not enable the physical blade as part of automated agent validation.

## K. Correct `/api/v2/control/start`

Choose one clear behavior:

- Delegate it to a real selected mission and the same `MissionService`/`MissionExecutor`, or
- Return a clear conflict/not-supported response directing callers to the mission start endpoint.

It must not return `running` merely because `navigation_mode` and `path_status` were changed.

---

## Required automated tests

Do not weaken, skip, or xfail safety tests. Add focused pure unit tests plus integration/contract coverage.

### 1. Production-adapter line-tracking regression

Using the real `_NavStateLocalizationAdapter` or its replacement:

- Confirm velocity, heading source/IMU validity, quality, and accuracy reach `MissionExecutor`.
- Start `0.30 m` to one side of a straight `10 m` leg with RTK-fixed quality.
- Confirm CTE is non-null.
- Confirm steering is toward the line.
- Confirm simulated CTE decreases below `0.10 m` rather than remaining parallel.

### 2. Deterministic closed-loop differential-drive simulation

Add a small test-only simulator, not production portability code. Test at least:

- Initial lateral offset.
- Approximately 10% left/right drive bias.
- Small heading disturbance.
- RTK-fixed measurement noise.
- Waypoint arrival and overshoot.

Software acceptance targets:

- The controller converges rather than diverges.
- Steady-state/RMS CTE after acquisition is no worse than `0.10 m` in the deterministic RTK-fixed scenario.
- The leg completes without an infinite loop.
- No unsafe command is issued after a simulated localization or geofence fault.

### 3. Geofence readiness tests

Verify mission start is blocked when:

- confirmed boundary is missing,
- generated safe boundary is missing,
- generated boundary hash/revision is stale,
- polygon is invalid,
- buffer collapses the polygon,
- current position is outside,
- GPS is stale or insufficiently accurate, or
- bootstrap clearance is insufficient.

### 4. Full-segment geometry tests

Include:

- Concave polygon with both endpoints inside but the segment outside.
- Segment crossing an exclusion with both endpoints outside the exclusion.
- Segment tangent to the configured safety margin.
- Multiple mow zones with deterministic active-zone selection.
- Safe outer boundary plus exclusions loaded simultaneously.

### 5. Predictive runtime guard tests

At the same near-edge pose:

- Outward command is rejected before crossing.
- Inward command is allowed only when the current footprint remains valid.
- High-speed command is rejected sooner than low-speed command because of stopping distance.
- Tank turn is rejected if the footprint sweep is unsafe.
- Stale GPS, degraded accuracy, or dead reckoning blocks nonzero mission commands.
- Zero-speed and blade-off commands remain accepted.

### 6. Coverage planner tests

For convex, concave, and exclusion-containing polygons:

- Every mow segment lies in free space.
- Every transit segment lies in free space.
- No segment crosses an exclusion.
- Transit and turns are blade off.
- Mow stripes are blade on.
- Planning fails cleanly when disconnected free-space regions cannot be safely connected.

### 7. Boundary mutation test

Change the boundary/exclusion revision during a running simulated mission. Verify drive stops, blade turns off, and the mission cannot resume until the path is revalidated.

### 8. API contract tests

Verify useful non-500 responses and stable reason codes for all preflight failures. Verify `/control/start` cannot claim a nonexistent executor is running.

### Suggested test locations

Use existing conventions; likely files include:

- `tests/unit/test_mission_executor.py`
- `tests/unit/test_waypoint_geometry.py`
- `tests/unit/test_navigation_service_facade.py`
- `tests/unit/test_navigation_safe_boundary.py`
- `tests/integration/test_nav_geofence_from_map_repo.py`
- New focused tests such as:
  - `tests/unit/test_operating_area.py`
  - `tests/unit/test_predictive_geofence_guard.py`
  - `tests/integration/test_mission_line_tracking.py`
  - `tests/integration/test_safe_coverage_execution.py`
  - `tests/contract/test_mission_safety_preflight.py`

---

## Validation commands

Run targeted tests first, then the broad non-hardware suite according to `AGENTS.md`:

```bash
SIM_MODE=1 python -m pytest tests/unit/ -x -q -m "not hardware"
SIM_MODE=1 python -m pytest tests/integration/ -x -q -m "not hardware"
SIM_MODE=1 python -m pytest tests/contract/ -x -q -m "not hardware"
SIM_MODE=1 python -m pytest tests/ -x -q -m "not hardware"
python -m ruff check backend/src tests
bash scripts/check_docs_drift.sh
```

If frontend code or generated API types change:

```bash
cd frontend
npm ci
npm run type-check
npm test
npm run build
```

Also run the navigation replay/regression workflow described in `docs/diagnostics-replay.md` when feasible.

Do not report the task complete if tests pass only because the safety path was mocked out or bypassed.

---

## Safe hardware-validation procedure to document

Prepare this procedure in the repository documentation, but do not enable the blade or perform unattended tests.

1. Bench-check manual and mission wheel direction with drive wheels safely raised.
2. Confirm E-stop, command TTL/watchdog, pause, abort, and blade-off paths.
3. Outdoors, keep the blade physically disabled and cap speed to approximately 25% for initial tests.
4. Require RTK Fixed before movement.
5. Use a temporary test boundary placed several metres inside the actual yard edge. Never use the real property edge as the first stop test.
6. Run a short straight leg from an on-line start.
7. Run a 10 m leg beginning approximately 0.30 m off-line and capture CTE, heading, steering, commands, GPS accuracy, and boundary clearance.
8. Test an outward command near the temporary inner boundary and verify the mower stops inside it.
9. Induce GPS degradation in a controlled manner and verify drive stops and blade state remains off.
10. Only after repeated blade-off success should a separately authorized, supervised mowing test be considered.

Real-world correctness may be claimed only with captured on-device evidence. Simulation alone proves software behavior, not traction, braking distance, GNSS multipath performance, or motor wiring.

---

## Documentation and telemetry requirements

Update relevant docs and `docs/code_structure_overview.md` when interfaces change.

Expose enough telemetry to diagnose a failed run:

- active boundary source and revision,
- safe-boundary buffer,
- current boundary clearance,
- GPS accuracy and fix age,
- pose quality and heading source,
- planned path bearing,
- along-track progress,
- cross-track error,
- steering command,
- left/right command,
- predicted stopping/swept-envelope clearance,
- blade state,
- last safety-block reason.

Use structured safety reason codes and existing observability/event infrastructure. Avoid high-frequency unbounded logs.

---

## Deliverables

Provide all of the following:

1. Focused production code changes.
2. Automated regression and safety tests.
3. Any configuration/schema migrations with safe defaults.
4. Updated API/types if contracts change.
5. Updated operator/developer documentation.
6. A concise completion report containing:
   - root causes fixed,
   - files changed,
   - exact validation commands and results,
   - remaining hardware-only uncertainty,
   - safe on-device test steps.

Do not leave untracked TODOs. Do not silently preserve a fail-open compatibility path. Do not mark the work complete merely because waypoints render correctly on the map.

---

## Definition of done

- [ ] Production mission execution receives real velocity, heading-source/IMU validity, pose quality, and accuracy.
- [ ] Stanley CTE correction runs during normal live mission legs.
- [ ] An off-line simulated mower converges to the planned segment.
- [ ] Waypoint overshoot cannot cause indefinite travel away from the target.
- [ ] Live autonomous start and resume fail closed without a valid, current safe boundary.
- [ ] Safe outer boundary and exclusions are active simultaneously.
- [ ] Every waypoint and complete path leg is validated.
- [ ] Coverage/transit connectors cannot cross exclusions or leave free space.
- [ ] Autonomous drive commands pass through `MotorCommandGateway`.
- [ ] Predictive footprint/stopping-envelope checks occur before nonzero motor authorization.
- [ ] Stale/degraded localization stops motion and keeps the blade off.
- [ ] Bootstrap is low-speed, blade-off, clearance-checked, and distance-bounded.
- [ ] Mission blade sequencing distinguishes mowing from transit and fails safe.
- [ ] Boundary changes invalidate a running mission safely.
- [ ] `/control/start` no longer reports false execution.
- [ ] Targeted and broad non-hardware tests pass.
- [ ] Documentation and evidence are complete.
