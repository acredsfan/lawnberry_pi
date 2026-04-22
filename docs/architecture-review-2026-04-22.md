# LawnBerry Architecture Review — 2026-04-22

## Overall Assessment

LawnBerry has a well-intentioned layered architecture with clear separation between hardware
drivers, service logic, API routing, and a reactive Vue 3 frontend. Core safety mechanisms
(E-stop, tilt, geofence, obstacle avoidance, mission recovery after restart) are all present
and reflect genuine care for autonomous mower safety. The primary risks are structural: emergency
stop state is fragmented across multiple uncoordinated dictionaries, two critical services share
a circular dependency resolved only by deferred local imports, and synchronous SQLite calls are
made from within the async event loop without WAL mode — all of which could cause subtle failures
under concurrent or edge-case operation on real hardware.

---

## Strengths

- **Mission recovery on restart** — `MissionService.recover_persisted_missions()` correctly
  transitions running missions to `paused` rather than `running`, requiring explicit operator
  resume. Failed-stop cases escalate to emergency stop. Schema v5 persists mission and waypoint
  state in SQLite.
- **Hardware abstraction and SIM_MODE** — Every hardware touch point checks
  `os.getenv("SIM_MODE")` and falls back gracefully. Sensor drivers use lazy imports so the
  entire backend starts in CI without any hardware present.
- **Navigation safety gates** — `go_to_waypoint()` runs a tight control loop with layered
  guards: E-stop check, GPS position availability timeout (30 s → emergency stop), GPS accuracy
  verification (30 s → emergency stop), geofence enforcement, obstacle hold (ToF), stall
  detection with progressive boost, and a tank-turn watchdog (30 s). Each gate stops motors
  before raising.
- **Motor command retry + grace period** — Three attempts for each motor command with 150 ms
  backoff; 20 s motor-controller reconnect grace period with firmware's own 5 s serial-timeout
  as a physical backstop.
- **Pydantic-validated config at startup** — `ConfigLoader` validates `hardware.yaml` and
  `limits.yaml` through Pydantic models on every startup, with `hardware.local.yaml` overlay
  for site-specific overrides. Safety limits are validated separately via `safety_validator.py`.
- **Heading bootstrap** — Per-mission GPS COG bootstrap drive ensures the IMU alignment is
  correct for tank-turns before the first real waypoint, with explicit disk persistence of
  the alignment offset.
- **Middleware stack** — Rate limiting, input validation, security headers, API key auth,
  correlation IDs, and sanitization are all registered in a clear, sequential order.
- **Frontend lockout UX** — The control store manages lockout state with per-reason descriptions,
  auto-clear timers, and remediation links, making safety states actionable for operators.
- **WebSocket cleanup on disconnect** — Both `ws_telemetry` and `ws_control` handlers call
  `websocket_hub.disconnect(client_id)` in a `finally` block; the hub removes the client from
  all topic subscriptions on disconnect.

---

## Risks and Weaknesses

### ARCH-001: Fragmented Emergency Stop State
- **Area**: Safety system — `backend/src/core/globals.py`, `core/state_manager.py`,
  `safety/safety_triggers.py`, `safety/estop_handler.py`
- **Severity**: Critical
- **Description**: The emergency stop condition is tracked in at least four separate locations
  that are never synchronised atomically:
  1. `globals._safety_state["emergency_stop_active"]` — the dict that `api/rest.py`,
     `api/safety.py`, and `NavigationService._global_emergency_active()` all read/write.
  2. `AppState.safety_state["emergency_stop_active"]` — a parallel singleton dict in
     `state_manager.py` that is never written by E-stop handlers.
  3. `SafetyTriggerManager._active` — maintains `SafetyInterlock` objects via
     `RobotStateManager`; not queried by the navigation service or blade control.
  4. `EstopHandler` / `MotorAuthorization.revoke()` — a third parallel gate that is not
     connected to the REST API path.
  The navigation service reads from source (1) via a deferred `from ..api import rest as
  rest_api` import; `api/safety.py` clears source (1) on the clear endpoint. These currently
  agree. But `AppState.safety_state` and `SafetyTriggerManager` are never consulted by the
  motor-command guard, so triggers fired through `safety_triggers.py` (e.g., tilt, low battery)
  do not prevent motor commands via the direct `set_speed()` path.
- **Risk**: A tilt or obstacle interlock fired through `SafetyTriggerManager` would broadcast
  to WebSocket and update `RobotStateManager`, but would not set
  `globals._safety_state["emergency_stop_active"]`. The navigation service would therefore
  continue to issue motor commands while the frontend displays an active interlock.
- **Recommendation**: Designate a single authoritative E-stop predicate — the simplest
  approach is to make `SafetyTriggerManager._activate()` also set
  `globals._safety_state["emergency_stop_active"] = True` when `itype` is `ESTOP` or any
  motion-blocking interlock. Better yet, replace the globals dict with a thread-safe
  `threading.Event` or an `asyncio.Event` that all paths read through a single
  `is_emergency_active()` helper function.

---

### ARCH-002: Circular Dependency — MissionService ↔ NavigationService
- **Area**: Service layer — `services/mission_service.py`, `services/navigation_service.py`
- **Severity**: High
- **Description**: `mission_service.py` imports `NavigationService` at **module level**
  (`from ..services.navigation_service import NavigationService`). `navigation_service.py`
  avoids a reciprocal module-level import only by using deferred function-body imports
  (`from .mission_service import get_mission_service`) inside `execute_mission()` and
  `go_to_waypoint()`. The singleton factory `get_mission_service()` silently ignores the
  `nav_service` argument on all calls after the first, because the global
  `_mission_service_instance` is set once without a lock.
- **Risk**: Import order sensitivity can cause `AttributeError` on cold start if any module
  triggers the circular resolution before the singletons are wired. The silent argument drop
  in `get_mission_service()` means the navigation service passed at startup is the only one
  ever used; if the singleton is ever cleared (e.g., in tests), a new instance is created with
  `NavigationService.get_instance()` as the default dependency, which may differ from the
  runtime instance.
- **Recommendation**: Break the cycle by introducing a narrow `MissionStatusReader` protocol
  that `NavigationService` depends on, rather than importing the full `MissionService`. This
  eliminates the deferred-import workaround. Add an explicit lock around
  `_mission_service_instance` creation in `get_mission_service()`.

---

### ARCH-003: Synchronous SQLite Writes in the Async Event Loop (No WAL Mode)
- **Area**: Persistence — `backend/src/core/persistence.py`
- **Severity**: High
- **Description**: `PersistenceLayer.get_connection()` opens a plain synchronous
  `sqlite3.connect()` and yields it via a `@contextmanager`. Every caller (`_persist_mission`,
  `_persist_mission_status`, `add_audit_log`, etc.) calls this directly from async code,
  blocking the event loop for the duration of the SQLite operation. No WAL mode is configured,
  so concurrent reads and writes contend on the same SQLite journal lock. Under active navigation
  (which persists mission status at each waypoint advance) combined with health-check reads and
  telemetry snapshots, this contention will manifest as periodic event-loop stalls.
  `message_persistence.py` additionally holds a **single shared `sqlite3.Connection`**
  (`check_same_thread=False`) that is accessed from potentially multiple threads without an
  explicit lock.
- **Risk**: Event-loop stalls during mission execution delay telemetry broadcasts, safety-trigger
  evaluation, and WebSocket keepalives. A >5 s stall could trigger the firmware's own USB serial
  timeout, causing motors to stop unexpectedly mid-mission. Lock contention in
  `message_persistence.py` can corrupt the in-process SQLite connection.
- **Recommendation**: (1) Enable WAL mode: `conn.execute("PRAGMA journal_mode=WAL")` in
  `_init_database()`. (2) Wrap all persistence calls that run from async context with
  `await asyncio.to_thread(...)`. (3) Add a `threading.Lock` around all accesses to the shared
  connection in `MessagePersistence`.

---

### ARCH-004: WebSocket Broadcast Without Backpressure
- **Area**: Real-time communication — `services/websocket_hub.py`
- **Severity**: Medium
- **Description**: `broadcast_to_topic()` and `broadcast()` iterate over all subscribed clients
  and call `await websocket.send_text()` sequentially in a single coroutine. If one client's
  TCP receive window is full (slow network or unresponsive browser), the `send_text` awaitable
  will block until the kernel buffer drains or the connection errors. During that wait, all
  **other** clients receive no telemetry. At 5 Hz with many topics, a single slow client can
  starve the entire broadcast loop.
  Additionally, `set_cadence()` mutates `self.telemetry_cadence_hz` globally — one client
  requesting 1 Hz slows telemetry for every connected client.
- **Risk**: Safety-critical telemetry (tilt state, E-stop confirmation) is delayed to all
  monitoring clients when even one client is slow. Operators on a healthy connection may not
  receive timely safety alerts.
- **Recommendation**: Send to each client in a `asyncio.create_task()` fan-out so a blocked
  client does not delay others. Apply a short send timeout (e.g., `asyncio.wait_for(..., 0.5)`)
  and disconnect clients that exceed it. Move `cadence_hz` to a per-client dict keyed by
  `client_id`.

---

### ARCH-005: `asyncio.run()` Called from Potentially-Async Contexts
- **Area**: Async patterns — `core/health.py`, `services/maps_service.py`,
  `services/weather_service.py`
- **Severity**: Medium
- **Description**:
  - `health.py:163` calls `asyncio.run(self._async_sensor_health_probe())` inside
    `_default_sensor_health()`, catching the resulting `RuntimeError` as a signal that the
    event loop is already running. This is a pattern that silently degrades health data
    when called from an async handler.
  - `maps_service.py:339,355` calls `asyncio.run(result)` on coroutines returned from
    persistence handlers — these can be called from a live FastAPI request context.
  - `weather_service.py:95` calls `asyncio.run(self.get_current_async(...))` inside the
    synchronous `get_current()`, which is called from unknown contexts.
- **Risk**: `asyncio.run()` inside a running event loop raises `RuntimeError`; the current
  try/except silences it with a degraded result, but map-save operations in `maps_service.py`
  could silently drop saves without any error surfacing to the caller.
- **Recommendation**: Replace all `asyncio.run()` calls in code paths reachable from FastAPI
  handlers with `await` (propagate async up the call chain) or `asyncio.to_thread()` for
  genuine synchronous adapters.

---

### ARCH-006: Safety Monitor Imports from the API Layer (Layer Violation)
- **Area**: Safety system — `backend/src/safety/safety_monitor.py`
- **Severity**: Medium
- **Description**: `safety_monitor.py` contains a module-level import:
  `from ..api.rest import websocket_hub`. The safety subsystem (a lower-level concern) depends
  directly on the API routing layer (a higher-level concern), inverting the natural dependency
  direction. This also creates an implicit startup ordering requirement: the `api.rest` module
  must be importable before `safety_monitor` is instantiated.
- **Risk**: Any future refactoring of `api/rest.py` (route reorganisation, module split) can
  break the safety monitor import without a compiler warning. Testing the safety subsystem in
  isolation requires importing the full API stack.
- **Recommendation**: Pass the `WebSocketHub` instance to `SafetyMonitor.__init__()` as a
  dependency rather than importing it at module level. The `lifespan` function already has
  access to both objects and can wire them together.

---

### ARCH-007: Mission Status Uses HTTP Polling Instead of WebSocket Push
- **Area**: Frontend state management — `frontend/src/stores/mission.ts`
- **Severity**: Medium
- **Description**: The mission store uses `setInterval(pollMissionStatus, 2000)` — a 2-second
  HTTP poll — to track mission progress. The `ws_control` WebSocket endpoint currently only
  echoes acks and does not push mission lifecycle events. This means the UI is always up to 2 s
  behind the backend for completion, abort, and failure transitions. The polling interval also
  starts on `startCurrentMission()` and stops on `pauseCurrentMission()`, so a mission that
  fails autonomously while paused will never update the UI.
- **Risk**: The operator may not notice an autonomous mission failure for up to 2 s; more
  importantly, a failure that occurs while the poll interval is stopped (paused state) is
  never surfaced.
- **Recommendation**: Push mission lifecycle events (`status`, `progress`, `detail`) over the
  existing `system.safety` or a new `mission.status` WebSocket topic. The `ws_control`
  endpoint can be extended to carry mission events. Keep the HTTP poll as a background
  reconciliation guard with a longer interval (30 s).

---

### ARCH-008: Optimistic Frontend State Mutations on Mission Commands
- **Area**: Frontend state management — `frontend/src/stores/mission.ts`
- **Severity**: Low
- **Description**: `abortCurrentMission()` sets `currentMission.value = null` and
  `missionStatus.value = 'aborted'` **before** the HTTP response confirms the operation.
  `pauseCurrentMission()` and `resumeCurrentMission()` similarly set `missionStatus.value`
  optimistically. If the HTTP request fails after the local mutation, the store is in a state
  that no longer matches the server, and the UI provides no recovery path.
- **Risk**: After a failed abort HTTP call, `currentMission` is `null` locally but still active
  on the server. Subsequent UI attempts to pause or resume have no mission ID to act on.
- **Recommendation**: Apply state changes only **after** `await apiService.post(...)` resolves
  successfully. On failure, update `statusDetail` with the error and keep the previous state.

---

### ARCH-009: Multiple `ConfigLoader` Instances Created at Runtime
- **Area**: Configuration — `backend/src/core/config_loader.py`,
  `services/robohat_service.py`
- **Severity**: Low
- **Description**: `ConfigLoader` caches parsed YAML in `self._cache`, but the cache is
  instance-local. `RoboHATService.__init__()` creates a new `ConfigLoader()` to read
  `encoder_enabled`, bypassing the cached instance created in `lifespan()`. Any consumer that
  creates its own `ConfigLoader` re-reads and re-validates YAML from disk, incurring I/O on
  startup and diverging from the canonical config if files change between reads.
- **Risk**: Low in practice, but a config change between the lifespan load and the RoboHAT
  init (e.g., symlink swap) would cause them to see different hardware configs.
- **Recommendation**: Make `ConfigLoader` a true application-scoped singleton (module-level
  instance with a `reload()` method) or pass the already-loaded `HardwareConfig` into
  `RoboHATService.__init__()` as a parameter.

---

### ARCH-010: Geofence Not Enforced During Heading Bootstrap Drive
- **Area**: Navigation safety — `services/navigation_service.py`
- **Severity**: Low
- **Description**: `_bootstrap_heading_from_gps_cog()` drives the mower forward at 60%
  throttle for up to 3 seconds to acquire a GPS COG reading. During this time, the
  geofence check, obstacle avoidance, and E-stop guard that run inside `go_to_waypoint()`'s
  main loop are not active — the bootstrap coroutine only checks
  `_global_emergency_active()`.
- **Risk**: If the mower starts a mission while positioned near the geofence boundary, the
  bootstrap drive could carry it outside the boundary before the main navigation loop begins
  enforcing it. Obstacle avoidance is also inactive during bootstrap.
- **Recommendation**: Run the bootstrap drive with the same safety loop iteration as
  `go_to_waypoint()`, or at minimum add a geofence position check after the drive completes
  and stop/abort the mission if the mower is outside the boundary.

---

## Service Architecture Map

| Service | Role | Key Dependencies |
|---|---|---|
| `robohat_service` | USB serial bridge to RP2040 motor controller; watchdog, motor PWM, blade | pyserial, asyncio.to_thread |
| `sensor_manager` | Aggregates GPS (ZED-F9P), IMU (BNO085), ToF (VL53L0X), power readings | I2C/UART drivers, SensorCoordinator |
| `navigation_service` | Path following, heading control, obstacle/geofence enforcement, dead reckoning | robohat_service, sensor_manager (via update_navigation_state), mission_service (deferred) |
| `mission_service` | Mission CRUD, lifecycle FSM, SQLite persistence, startup recovery | navigation_service, persistence |
| `telemetry_service` | Polls sensor_manager, assembles telemetry snapshot, feeds websocket_hub | sensor_manager, navigation_service (deferred) |
| `websocket_hub` | Fan-out broker for telemetry topics; caches last snapshot | telemetry_service |
| `camera_stream_service` | MJPEG capture/streaming, AI inference input | libcamera / cv2 |
| `ai_service` | Object/hazard detection from camera frames | camera_stream_service, configurable model |
| `calibration_service` | IMU and motor calibration routines | robohat_service, sensor_manager |
| `auth_service` | JWT + TOTP MFA, session management | persistence |
| `settings_service` | YAML-backed settings R/W with WebSocket broadcast on change | persistence, websocket_hub |
| `maps_service` | Zone polygon management, map config persistence | persistence |
| `ntrip_client` | RTCM correction stream forwarder to GPS receiver | GPS driver |
| `weather_service` | Open-Meteo forecast fetch | httpx |
| `acme_service` | Let's Encrypt ACME cert lifecycle | certbot / ACME HTTP-01 |
| `remote_access_service` | Cloudflare tunnel or reverse-proxy tunnel daemon | subprocess |
| `jobs_service` | Scheduled mowing job management | persistence, mission_service |

---

## Recommendations by Priority

### Immediate (safety-critical)

1. **Unify E-stop state (ARCH-001)** — Add a thin `is_emergency_active() -> bool` function in
   `core/globals.py` and make all four safety paths (`safety_triggers`, `estop_handler`,
   `api/rest.py`, `NavigationService`) write to and read from the same backing store. Verify
   with a unit test that a `SafetyTriggerManager.trigger_tilt()` call causes
   `NavigationService._global_emergency_active()` to return `True`.

2. **Protect geofence during bootstrap drive (ARCH-010)** — Add a post-bootstrap geofence
   position check before handing control to `go_to_waypoint()`. Abort the mission if the
   mower is outside boundary after bootstrap.

### Short-term (reliability)

3. **Enable SQLite WAL mode and async writes (ARCH-003)** — `PRAGMA journal_mode=WAL` in
   `_init_database()`; wrap all synchronous persistence calls from async handlers with
   `asyncio.to_thread()`; add a `threading.Lock` to `MessagePersistence`.

4. **Fix `asyncio.run()` in async contexts (ARCH-005)** — Audit all `asyncio.run()` call
   sites reachable from FastAPI request handlers; replace with `await` propagation or
   `asyncio.to_thread()` as appropriate.

5. **WebSocket backpressure and per-client cadence (ARCH-004)** — Fan-out broadcasts to
   per-client tasks; apply send timeouts; move `cadence_hz` to a per-client dict.

6. **Fix safety monitor layer violation (ARCH-006)** — Inject `websocket_hub` into
   `SafetyMonitor` via constructor parameter rather than importing it from the API layer.

### Long-term (maintainability)

7. **Break circular service dependency (ARCH-002)** — Introduce a `MissionStatusReader`
   protocol so `NavigationService` depends on an interface, not the concrete
   `MissionService`.

8. **Mission status over WebSocket (ARCH-007)** — Push lifecycle events on a
   `mission.status` topic; demote HTTP polling to a reconciliation fallback.

9. **Fix optimistic frontend mutations (ARCH-008)** — Apply state changes post-confirmation;
   add error-recovery paths in the mission store.

10. **Singleton `ConfigLoader` (ARCH-009)** — Provide a module-level singleton and inject
    parsed config into service constructors rather than re-reading YAML inside `__init__`.
