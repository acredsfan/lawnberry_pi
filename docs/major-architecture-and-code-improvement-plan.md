# Major Architecture and Code Improvement Plan

This document records the major project changes I would prioritize after reviewing the current LawnBerry codebase. The emphasis is on changes that reduce field risk, make navigation behavior more predictable, and make future changes easier to validate on a live robotic mower.

## Executive Summary

LawnBerry has the right product boundaries: FastAPI backend, Vue frontend, hardware drivers, mission planning, safety, telemetry, and Pi operations. The main architectural issue is that several of those boundaries are not yet enforced in code. Safety-critical runtime state still flows through module globals and singletons, the navigation loop mixes mission orchestration with control and sensor fusion, and some robotics components are still scaffold-level implementations despite being wired into runtime paths.

The highest-value changes are:

1. Introduce an explicit backend runtime context and dependency graph (scoped to safety-critical paths first, not a full migration).
2. Split the navigation service into a small number of focused components — localization, mission execution, and the motor command gateway — rather than a large fan-out of micro-services.
3. Replace placeholder localization/dead-reckoning with a real pose-estimation pipeline.
4. Move manual/autonomous motor commands behind one safety-authorized command gateway, while preserving an independent firmware/hardware emergency-stop latch.
5. Consolidate persistence and configuration into typed repositories/services with single ownership per field (storage backend chosen by operator workflow, not by dogma).
6. Establish a typed API contract between backend and frontend, but defer codegen until backend boundaries stabilize.
7. Break large frontend views into feature modules and composables.
8. Build hardware simulation/replay and HIL validation around recorded sensor streams. **This must land early — replay coverage is a precondition for safely refactoring navigation, not a follow-up.**
9. Improve observability for field debugging and post-run analysis.
10. Tighten test/lint policy on a ratchet basis so quality gates do not block unrelated work.
11. Document the firmware/RoboHAT command-and-ack contract as a versioned architectural dependency.
12. Track CPU, IO, and thermal budgets as the system grows — this is a Pi-hosted mower, not a server.
13. Define an explicit rollback/bisect strategy so navigation refactors can be unwound when field regressions surface.

Section numbering below reflects topic groupings, not strict priority. The recommended execution order at the end of this document sequences work for risk reduction.

## Current Observations

- `backend/src/services/navigation_service.py` is doing too much: mission execution, heading bootstrap, waypoint pursuit, geofence response, ToF obstacle checks, dead reckoning, motor command dispatch, stiffness diagnostics, and position state.
- `backend/src/api/rest.py` still contains broad legacy API behavior, in-memory stores, global mutable state usage, and control endpoints in one large router.
- Runtime state is split across `AppState`, `backend/src/core/globals.py`, service-level singletons, router module globals, SQLite, JSON files under `data/`, and YAML/JSON config files.
- `backend/src/fusion/ekf.py` explicitly describes itself as a placeholder; `NavigationService` still has fallback dead reckoning based on a hardcoded `0.1` meter movement estimate.
- The backend has multiple API surfaces for similar domains: `backend/src/api/rest.py`, `backend/src/api/navigation.py`, `backend/src/api/mission.py`, `backend/src/api/motors.py`, and routers under `backend/src/api/routers/`.
- Several frontend files are large enough to hide state bugs: `DashboardView.vue`, `ControlView.vue`, `MissionPlannerView.vue`, `MapsView.vue`, `BoundaryEditor.vue`, and `frontend/src/services/websocket.ts`.
- Frontend API calls are mostly hand-written with `any`, so backend/frontend contract drift is likely.
- Tests exist across unit, integration, contract, and E2E layers, but some integration tests are placeholders and the robotics behavior needs replay/HIL coverage rather than only static unit coverage.

## 1. Introduce an Explicit Runtime Context

### Change

Replace most module-level runtime access with a typed `RuntimeContext` created during FastAPI lifespan startup and injected into routers/services.

### Why

The project currently uses `AppState.get_instance()`, module globals in `backend/src/core/globals.py`, service singletons such as `NavigationService.get_instance()`, and router-level globals. That makes startup order, test isolation, and safety state ownership harder to reason about.

For a mower, hidden state ownership is not just a style issue. It can produce stale sensor references, duplicated services, or safety latch mismatches after restarts.

### Scope

Migrate only the routers/services where test isolation and ownership confusion are causing real pain. Initial migration targets:

- navigation
- safety
- motor command / RoboHAT
- telemetry

Routers without test-isolation problems (auth, settings, maps, debug surfaces) stay on `AppState` until they have a concrete reason to move. **Full removal of `AppState` is not a goal of this phase.** A long-lived shim that legacy routers continue to consume is acceptable, and arguably preferable to forcing a churn-heavy migration on a single-developer project.

### Implementation

- Add `backend/src/core/runtime.py` with a typed `RuntimeContext` dataclass:
  - `config_loader`
  - `hardware_config`
  - `safety_limits`
  - `sensor_manager`
  - `navigation`
  - `mission_service`
  - `safety_state`
  - `robohat`
  - `websocket_hub`
  - `persistence`
- Build the context in `backend/src/main.py` lifespan startup.
- Store it on `app.state.runtime`.
- Add a FastAPI dependency such as `get_runtime(request: Request) -> RuntimeContext`.
- Convert in-scope routers incrementally from globals/singletons to `Depends(get_runtime)`.
- Keep `AppState` available indefinitely for legacy routers; remove it only when all consumers have migrated. Do not block phase completion on full removal.

### Acceptance Criteria

- Tests can create an isolated `RuntimeContext` for safety-critical paths without resetting module globals.
- `NavigationService.get_instance()` is no longer used by new code in scope.
- Safety state has one authoritative owner.
- Backend startup logs a concise inventory of the runtime context services.

## 2. Split Navigation Into Focused Components

### Change

Refactor `NavigationService` into separate modules with narrow responsibilities.

### Why

Navigation is the most safety-critical subsystem and is currently a high-change monolith. The heading issues and position-offset work are examples of why this matters: localization, heading alignment, mission execution, motor command behavior, and telemetry formatting all interact inside or around the same service.

### Proposed Components

Aim for **three** top-level components, with sub-responsibilities living inside them. Earlier drafts of this plan proposed six (`LocalizationService`, `HeadingAlignmentService`, `WaypointController`, `MissionExecutor`, `SafetyGate`, `MotorCommandGateway`); that decomposition introduces too many seams up front, splits tightly-coupled state (heading bootstrap shares state with localization), and elevates small pure functions (waypoint geometry) to service status.

- `LocalizationService`
  - Owns current pose, antenna offset, GPS/IMU/encoder fusion, GPS age/accuracy policy, pose quality, **and mission-start heading bootstrap** (GPS COG resolution + IMU yaw/session alignment).
- `MissionExecutor`
  - Owns mission lifecycle traversal, pause/resume/abort checks, waypoint progress, **waypoint-to-motion conversion** (bearing/distance helpers as pure functions), and failure detail.
- `MotorCommandGateway` (see §4)
  - Owns safety gating (geofence, obstacle, stale-position, emergency, authorization), final authorized command dispatch to RoboHAT, and acknowledgement verification.

Only split a sub-responsibility into its own service when it outgrows its host or develops an independent lifecycle — not before.

### Implementation

- Start by extracting pure helpers from `NavigationService` without behavior changes:
  - heading delta/wrap helpers
  - GPS COG resolution
  - antenna offset application
  - waypoint bearing/distance command calculation
- Add unit tests for each extracted component.
- Move mission execution into `MissionExecutor` once the pure pieces are covered.
- Make `NavigationService` a façade during migration, then retire it or keep it as a thin orchestrator.

### Acceptance Criteria

- No single navigation file exceeds roughly 500 lines.
- Mission execution can be tested with fake localization and fake motor gateway.
- Localization can be tested with recorded GPS/IMU/encoder sequences without mission state.
- Geofence and obstacle gating can be tested without constructing a full navigation service.

## 3. Replace Placeholder Localization With a Real Pose Pipeline

### Change

Promote localization to a first-class subsystem that fuses GPS, IMU, encoder odometry, and pose quality. Replace the scaffold EKF and hardcoded dead-reckoning fallback with a real local-frame estimator.

### Why

The mower’s behavior depends heavily on sub-meter position and stable heading. The code currently has:

- `backend/src/fusion/ekf.py` describing itself as placeholder scaffolding.
- dead reckoning in `NavigationService` that estimates a fixed `0.1` meters per update when GPS is missing.
- encoder utilities in `backend/src/nav/odometry.py` that are not yet fully wired into the navigation state.

This is a root cause category for inefficient waypoint pursuit and map/position confusion.

### Implementation

- Define a local ENU frame anchored at mission start or home position.
- Convert GPS lat/lon into local meters at the localization boundary.
- Track a `Pose2D` model:
  - `x_m`
  - `y_m`
  - `heading_deg`
  - `velocity_mps`
  - `angular_velocity_dps`
  - covariance or quality fields
  - source timestamps
- Use GPS as a position measurement, IMU as heading/angular-rate input, and wheel encoders as odometry input.
- Keep GPS COG as a movement vector, not a continuous heading truth source.
- Emit explicit quality states:
  - `rtk_fixed`
  - `gps_float`
  - `gps_degraded`
  - `dead_reckoning`
  - `stale`
- Add replay tests from captured telemetry logs.

### Acceptance Criteria

- Navigation consumes `Pose2D`, not raw GPS dictionaries.
- Dead-reckoning distance is derived from encoders or commanded velocity with elapsed time, never a fixed constant.
- Pose quality is visible in telemetry and Mission Planner.
- A recorded straight-line movement replay reproduces course and distance within expected tolerances.

## 4. Create One Motor Command Gateway

### Change

Route all motion and blade commands through a single safety-authorized command gateway.

### Why

Manual drive, mission drive, emergency stop, blade control, RoboHAT commands, and legacy control state are spread across services and routers. This makes it harder to prove that every path respects the same safety policy and acknowledgement rules.

### Implementation

- Add `backend/src/control/command_gateway.py`.
- Define typed commands:
  - `DriveCommand(left, right, source, duration_ms)`
  - `BladeCommand(active, source)`
  - `EmergencyStopCommand(reason, source)`
- Define typed outcomes:
  - `accepted`
  - `blocked`
  - `timed_out`
  - `ack_failed`
  - `emergency_latched`
- Gateway responsibilities:
  - apply safety gates
  - send command to RoboHAT
  - require firmware acknowledgement
  - update command audit logs
  - emit telemetry/control events
- Convert manual-control endpoints and mission navigation to use the gateway.

### Estop Boundary

The gateway is the authoritative **software** path for stop. It is not a substitute for a hardware-level latch.

- Firmware (RoboHAT) must retain an independent emergency-stop path: a watchdog that halts motors if the Pi process hangs, crashes, or stops sending heartbeats.
- The hardware estop button must reach the firmware/motor controller through a path that does not depend on the gateway process being healthy.
- "Emergency stop cannot be bypassed by any route" applies to in-process software flows. The system as a whole has more stop paths than the gateway, and that is a feature, not a redundancy to remove.
- Document the firmware-side latch behavior in §11 (Firmware/RoboHAT Contract).

### Acceptance Criteria

- There is one **software** code path from "desired motion" to RoboHAT PWM.
- In-process emergency stop cannot be bypassed by any software route.
- A firmware-side stop latch operates independently of the gateway process and is exercised by HIL tests.
- Mission and manual drive share the same obstacle, stale telemetry, and controller-ready checks unless explicitly overridden by a documented policy.
- Command outcomes are testable without serial hardware.

## 5. Consolidate Configuration and Persistence

### Change

Create typed services/repositories for config and runtime persistence instead of mixing YAML, JSON files, SQLite tables, and in-memory route state ad hoc.

### Why

Current state/config sources include `config/hardware.yaml`, `config/limits.yaml`, `config/default.json`, `config/maps_settings.json`, `data/settings.json`, `data/ui_settings.json`, `data/imu_alignment.json`, SQLite tables, router globals, and `core/globals.py`. Some of this is reasonable, but the ownership boundary is unclear.

### Implementation

- Define a configuration ownership map. The invariant is **single owner per field**, not single backend per category. Storage choice should follow operator workflow:
  - hardware facts: YAML with optional local overlay
  - frontend-mutated operator settings: SQLite (mutated through repository APIs)
  - operator/calibration tunables that benefit from manual editing during field bring-up: human-editable JSON, with a single documented owner
  - secrets: env or secrets manager only
  - volatile runtime state: runtime context only
  - mission/map persisted domain data: SQLite repositories
- Add repository classes:
  - `MapRepository`
  - `MissionRepository`
  - `SettingsRepository`
  - `CalibrationRepository`
  - `TelemetryRepository`
- Move route-level in-memory stores into repositories or explicitly mark them simulation-only.
- Add a startup config report that lists loaded files, overlays, and effective values excluding secrets.

### Acceptance Criteria

- Every persisted field has a single owner.
- Routes do not own persistent state.
- Local overrides are documented and visible in health diagnostics.
- Tests can run against temporary repositories without touching real `data/`.

## 6. Normalize the API Surface and Generate Frontend Types

### Change

Stabilize `/api/v2` as the canonical API and generate TypeScript types/client code from FastAPI OpenAPI.

### Why

The backend has overlapping routers and legacy routes. The frontend uses hand-written API calls with many `any` payloads. That increases drift risk and makes safety/status payload changes harder to verify.

### Sequencing

Defer codegen until backend boundaries from §1, §2, and §4 stabilize. Generating frontend types while the backend is mid-refactor produces high-churn regenerations and merge conflicts on every backend type rename. The endpoint inventory and deprecation labelling can start immediately; codegen wiring should wait until Phase 3.

### Implementation

- Inventory current endpoints and label each as:
  - canonical `/api/v2`
  - compatibility
  - deprecated
  - simulation/debug only
- Add deprecation headers to compatibility endpoints.
- Generate an OpenAPI schema in CI.
- Generate frontend TypeScript types using an OpenAPI TypeScript tool.
- Replace hand-written `any` payloads in `frontend/src/services/api.ts` with generated request/response types.
- Move endpoint-specific functions into domain clients:
  - `missionClient`
  - `controlClient`
  - `telemetryClient`
  - `settingsClient`
  - `mapsClient`

### Acceptance Criteria

- New frontend code does not use untyped API payloads.
- Contract tests fail when backend payloads drift from frontend expectations.
- Legacy endpoints have a documented removal plan.

## 7. Decompose Large Frontend Views

### Change

Split large Vue views into feature components and composables.

### Why

Files like `DashboardView.vue`, `ControlView.vue`, `MapsView.vue`, `PlanningView.vue`, and `BoundaryEditor.vue` are large enough that state, UI, and side effects are coupled. This makes map/telemetry/debugging issues more expensive to isolate.

### Implementation

- For `MissionPlannerView.vue`:
  - extract `useMowerTelemetry()`
  - extract `useMissionMapSettings()`
  - extract `MissionControls.vue`
  - extract `MissionStatusPanel.vue`
- For `ControlView.vue`:
  - extract camera panel, lockout panel, joystick authorization, and command history.
- For `DashboardView.vue`:
  - extract telemetry cards and system health cards.
- For `BoundaryEditor.vue`:
  - separate geometry editing, map provider management, and persistence.
- Use typed store models shared from generated API types.

### Acceptance Criteria

- Major views are orchestration shells under roughly 400 lines.
- WebSocket subscription setup lives in composables with cleanup tests.
- Mission/map telemetry handling can be unit-tested without mounting a full page.

## 8. Build Sensor Replay and HIL Validation

### Change

Add a repeatable validation workflow that replays real GPS/IMU/encoder/command logs through localization and navigation code.

### Why

The hardest bugs in this project are field behavior bugs: heading, map position, waypoint efficiency, obstacle gating, and command timing. Unit tests are necessary but not sufficient. The project needs a way to reproduce yard runs without physically rerunning every scenario.

### Implementation

- Add a telemetry capture format for:
  - GPS raw and corrected position
  - IMU raw yaw and adjusted heading
  - encoder ticks or wheel velocity
  - motor commands and acknowledgements
  - mission waypoint target
  - safety/obstacle state
- Add `scripts/replay_navigation.py`:
  - loads captured telemetry JSONL/SQLite rows
  - runs localization and waypoint logic offline
  - emits pose, heading error, cross-track error, and command decisions
- Add golden replay fixtures under `tests/fixtures/navigation/`.
- Add HIL smoke tests for:
  - startup sensor discovery
  - emergency stop latch
  - manual drive command acknowledgement
  - GPS/IMU mission bootstrap

### Acceptance Criteria

- A failed yard run can become a replay fixture.
- Heading and position fixes can be validated before deploying to the mower.
- HIL tests are opt-in and clearly separated from CI-safe tests.

## 9. Improve Observability and Field Diagnostics

### Change

Add structured, correlation-friendly runtime events for navigation, localization, control, safety, and mission state.

### Why

The system has logs and telemetry, but field debugging still requires manually inferring relationships between GPS, heading, mission state, and motor commands. The mower needs post-run diagnostics that answer: “Why did it move that way?”

### Implementation

- Add structured event models:
  - `PoseUpdated`
  - `HeadingAligned`
  - `WaypointTargetChanged`
  - `MotionCommandIssued`
  - `MotionCommandAcked`
  - `SafetyGateBlocked`
  - `MissionStateChanged`
- Persist key events with mission/run IDs.
- Add a run summary endpoint:
  - total distance
  - average pose quality
  - heading alignment samples
  - blocked command count
  - waypoint inefficiency/cross-track metrics
- Add frontend diagnostics panels for current mission run.

### Acceptance Criteria

- Every motion command has a traceable source, safety decision, hardware acknowledgement, and resulting pose update.
- Mission Planner can show position correction metadata and pose quality.
- Logs can be bundled by mission/run ID.

## 10. Tighten Test and Lint Policy

### Change

Make validation stricter but staged so the project can continue moving.

### Why

The codebase already has tests, but current lint output includes pre-existing issues in some files, and placeholder integration tests are explicitly skipped. Without a staged policy, every change risks either ignoring quality gates or getting blocked by unrelated debt.

### Implementation

- Define “ratchet” validation:
  - changed files must pass `ruff --select F,I` immediately
  - new/modified backend modules should pass full configured ruff rules
  - gradually expand full lint coverage by directory
- Add a `make validate-changed` or script equivalent.
- Mark placeholder tests with explicit issue IDs or remove them.
- Require replay tests for navigation/heading changes.
- Require API contract tests for payload changes.

### Acceptance Criteria

- Validation failures are attributable to the current change.
- New modules meet stricter standards than legacy modules.
- Placeholder tests do not silently create false confidence.

## 11. Document the Firmware/RoboHAT Contract

### Change

Treat the firmware-side command and acknowledgement protocol as a versioned architectural dependency, not implementation detail.

### Why

§4 routes all motion commands through a gateway that "requires firmware acknowledgement." The ack format, timeout, retry policy, and version compatibility define gateway correctness. Firmware behavior changes can silently invalidate gateway assumptions, and the hardware estop latch (introduced in §4) is firmware-side behavior that the rest of the system depends on.

### Implementation

- Document the command/ack protocol explicitly: command bytes, expected ack format, ack timeout budget, retry policy on ack timeout.
- Add a firmware version field readable from the Pi at startup; surface it in health/diagnostics.
- Refuse gateway dispatch with a clear telemetry event if firmware version is unknown or incompatible.
- Document hardware-level emergency stop latch behavior independently of software (which signals trigger latch, how it is cleared, what the Pi observes during a latched state).
- Treat firmware as a versioned dependency: protocol changes require updating documented contract and gateway tests in the same change.

### Acceptance Criteria

- Firmware version is logged at startup and surfaced in `/health`.
- Gateway tests include a simulated firmware-version mismatch and a simulated ack timeout.
- Hardware estop latch behavior is documented separately from software estop and exercised by HIL.

## 12. Power, Thermal, and Runtime Budget

### Change

Track CPU, IO, and thermal cost of architecture changes and event persistence.

### Why

This is a Pi-hosted mower running off a battery in summer heat. Adding event persistence (§9), structured logging, replay capture (§8), and additional service layers (§1, §2) all have measurable runtime cost. Without an explicit budget, the system can drift toward thermal throttling, SD-card write exhaustion, or excess battery draw during field operation, and these regressions are easy to miss in dev because they only manifest under sustained load.

### Implementation

- Capture baseline measurements before refactor begins:
  - CPU per service under nominal mission load
  - SD card write rate during a typical mission
  - Pi CPU temperature curve during a sustained run
  - approximate idle and active battery draw
- Add a per-phase regression check:
  - mission CPU budget
  - log volume budget (bytes/minute)
  - SD write rate budget
- Make event persistence (§9) configurable: full vs. summary modes, with summary as the default for unattended runs.
- Prefer in-memory ring buffers with periodic flush over per-event sync writes.

### Acceptance Criteria

- Baseline metrics are recorded and committed to the repo.
- Each phase records new measurements and is rejected if it exceeds budget without justification.
- Event persistence has a documented IO budget and a switch to reduce volume in the field.

## 13. Rollback and Bisect Strategy

### Change

Define how to bisect and unwind a field regression that lands during the architecture migration.

### Why

Architecture changes that touch navigation can introduce subtle field regressions that pass unit tests. Once `NavigationService` is partially extracted, the surface area for `git bisect` is fragmented and individual commits become hard to attribute when something behaves wrong in the yard. The plan as originally written treats the migration as forward-only — that is fragile for a single-developer mower where the only regression test is a yard run.

### Implementation

- Tag every phase milestone (`phase-1-runtime-context`, `phase-2-localization-extracted`, etc.) so any commit can be checked against a known-good baseline.
- Keep the legacy `NavigationService` code path runnable behind a config flag during migration. Do not delete it until the refactored path has demonstrated parity on captured replay fixtures.
- Add a "compare run" mode in the replay harness (§8) that runs both legacy and refactored localization against the same captured telemetry and reports divergence (pose, heading, command decisions).
- Document expected behavioral parity boundaries: where legacy and refactored output should match, and where intentional behavior change is permitted (with a justification).

### Acceptance Criteria

- Any Phase 2 commit can be reverted independently without unwinding §1 or §4 changes.
- The replay harness can run side-by-side legacy vs. refactored navigation on the same fixture and produce a divergence report.
- Behavioral divergence is explicit and reviewed, not surprise.

## Recommended Execution Order

### Phase 1: Stabilize Runtime Ownership and Capture Field Truth

Replay harness comes **before** navigation refactor, not after. Refactoring safety-critical navigation without replay coverage is the failure mode this plan exists to prevent.

1. Add `RuntimeContext`, scoped to navigation, safety, motor, and telemetry routers (§1).
2. Create the motor command gateway, including a firmware-version preflight check (§4, §11).
3. Add command outcome tests.
4. **Build the telemetry capture format and replay harness scaffolding** (§8) before Phase 2 begins.
5. Capture at least one full yard run as a golden replay fixture and commit it.
6. Record baseline runtime budget metrics (§12).

### Phase 2: Stabilize Navigation

1. Extract `LocalizationService` (including heading bootstrap) from `NavigationService`. Keep the legacy path runnable behind a flag (§13).
2. Replace hardcoded dead reckoning with encoder/time-based odometry (§3).
3. Validate every Phase 2 change against the replay fixtures from Phase 1 using compare-run mode (§13).
4. Add pose quality telemetry.

### Phase 3: Stabilize API and Frontend

1. Inventory and deprecate duplicate endpoints (start of phase, in parallel with Phase 2).
2. Generate frontend API types only after backend boundaries from Phases 1–2 have stabilized (§6 sequencing note).
3. Split Mission Planner and Control views into composables/components.
4. Add frontend tests for mission-map telemetry and control lockout behavior.

### Phase 4: Improve Operations and Diagnostics

1. Add mission/run event logging within the runtime budget (§9, §12).
2. Add run-summary diagnostics.
3. Add HIL smoke tests for mower-specific startup and safety behavior, including firmware-side estop latch exercise (§11).

## Non-Goals

- Do not rewrite the entire backend into a new framework.
- Do not replace FastAPI, Vue, Pinia, or SQLite unless a concrete operational limit is reached.
- Do not remove legacy endpoints until frontend usage and tests prove they are unused.
- Do not make safety behavior less conservative to simplify architecture.

## Final Recommendation

The next major engineering push should not be a new feature. It should be a staged architecture stabilization pass around runtime state, navigation/localization, and command authorization. Those areas directly affect whether the mower moves safely and predictably.

Two preconditions matter more than the refactor itself:

1. **Replay harness before navigation refactor.** Without captured-telemetry replay, navigation changes cannot be validated except by yard testing, and yard testing alone will not catch subtle pose/heading regressions before they ship.
2. **Firmware contract documented before the gateway lands.** The gateway depends on firmware ack semantics and the firmware-side estop latch. Treating those as undocumented implementation detail puts software-side safety guarantees on a foundation that can shift without notice.

Once those are in place and the gateway and localization split are done, frontend and API cleanup becomes much lower risk, and field fixes like heading or map-position corrections become easier to diagnose instead of requiring repeated patching across services.
