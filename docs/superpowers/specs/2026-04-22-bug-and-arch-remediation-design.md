# Bug & Architecture Remediation Design
**Date:** 2026-04-22
**Source documents:** `docs/bug-report-2026-04-22.md`, `docs/architecture-review-2026-04-22.md`
**Status:** Approved — Phase 1 & Phase 2

---

## Context

The 2026-04-22 fleet maintenance pass produced a bug report (20 bugs) and an architecture review
(10 risks). Three critical bugs were patched immediately (auth backdoor, rate limiter, camera
logging). ARCH-001 (fragmented E-stop) was partially fixed by making `_global_emergency_active()`
poll `RobotStateManager`. This design covers the remaining 16 bugs and 9 architecture risks in two
phased plans.

---

## Scope

### Already Fixed (not in scope)
- BUG-001: `admin/admin` auth backdoor — removed (commit `7568f0b`)
- BUG-002: Rate limiter asyncio.Lock race — fixed (commit `7568f0b`)
- BUG-003: `logging` undefined in camera `main()` — fixed (commit `7568f0b`)
- BUG-006: Signal handler using `asyncio.create_task` — fixed (commit `7568f0b`)
- ARCH-001: Navigation reads `RobotStateManager` interlocks — fixed (commit `bc078c1`)

### Phase 1 — Bug Fixes & Reliability Hardening
Functional correctness and runtime safety issues that should be resolved before the next mowing
run. Organized by subsystem to minimize context-switching and enable independent commit/test cycles.

### Phase 2 — Architecture Refactoring & Code Modernization
Structural improvements and cosmetic cleanup. Safe to defer past immediate mowing operations.

---

## Phase 1 Design

### Group 1 — Safety Subsystem
**Files:** `backend/src/services/navigation_service.py`, `backend/src/services/robohat_service.py`
**Bugs fixed:** ARCH-010, BUG-005

#### ARCH-010: Geofence Not Enforced During Heading Bootstrap Drive
`_bootstrap_heading_from_gps_cog()` drives forward at 60% throttle for up to 3 seconds with no
geofence or obstacle checks. If the mower starts near a boundary, it can drive outside it before
the main navigation loop begins.

**Fix:**
- After the bootstrap drive completes, read the current GPS position and call the existing
  geofence-check logic.
- If the position is outside any defined mowing zone, call `_latch_global_emergency_state()` and
  raise `NavigationError("Bootstrap drive exited geofence — mission aborted")` before control
  passes to `go_to_waypoint()`.
- Additionally, call `_global_emergency_active()` inside the bootstrap drive loop (it already
  exists) so a hardware E-stop triggered during bootstrap halts the drive immediately.

#### BUG-005: Emergency Stop Silent on Serial Disconnect
`robohat_service.emergency_stop()` returns `False` when `serial_conn` is `None` without queuing
any recovery state. If serial reconnects, the last PWM command (potentially non-neutral) is
replayed.

**Fix:**
- Add `_pending_estop: bool = False` instance flag.
- In `emergency_stop()`, when serial is unavailable: set `_pending_estop = True`,
  set `self._last_pwm = (1500, 1500)` (neutral), log at `CRITICAL` level.
- In `_maintain_usb_control()` reconnect path: if `_pending_estop` is set, send neutral PWM
  first, then clear the flag. Do not resume any queued non-neutral commands until the flag is
  cleared by an explicit `clear_emergency_stop()` call.

---

### Group 2 — Persistence
**Files:** `backend/src/core/persistence.py`, `backend/src/core/message_persistence.py`
**Bug fixed:** ARCH-003

#### ARCH-003: Synchronous SQLite Blocking the Async Event Loop
`PersistenceLayer` uses synchronous `sqlite3` in async handlers; no WAL mode; `MessagePersistence`
shares a single connection across threads without a lock.

**Fix:**
1. Enable WAL mode in `PersistenceLayer._init_database()`:
   ```python
   conn.execute("PRAGMA journal_mode=WAL")
   conn.execute("PRAGMA synchronous=NORMAL")
   ```
2. Audit all call sites of `_persist_mission`, `_persist_mission_status`, `add_audit_log` and
   any other persistence methods called from `async def` handlers. Wrap each with
   `await asyncio.to_thread(self._sync_method, ...)` where the underlying method is synchronous.
3. Add `self._lock = threading.Lock()` to `MessagePersistence.__init__()`. Wrap all `execute()`
   and `fetchall()` calls with `with self._lock:`.

**Testing:** Add a unit test that calls `add_audit_log` concurrently from multiple async tasks
and verifies no `sqlite3.OperationalError: database is locked` is raised.

---

### Group 3 — WebSocket Hub
**File:** `backend/src/services/websocket_hub.py`
**Bug fixed:** ARCH-004

#### ARCH-004: Sequential Broadcast Blocks on Slow Clients
`broadcast_to_topic()` iterates clients sequentially — one slow client stalls all others.
`set_cadence()` applies globally, not per-client.

**Fix:**
1. Replace the sequential `for client_id, ws in subscribers.items(): await ws.send_text(...)` with
   a fan-out using `asyncio.gather()`:
   ```python
   tasks = [_send_with_timeout(ws, payload) for ws in subscribers.values()]
   await asyncio.gather(*tasks, return_exceptions=True)
   ```
   Where `_send_with_timeout` wraps each send in `asyncio.wait_for(..., timeout=0.5)` and
   disconnects the client on `asyncio.TimeoutError`.
2. Replace `self.telemetry_cadence_hz: float` with
   `self._client_cadence: dict[str, float]` defaulting to `5.0`.
   `set_cadence(client_id, hz)` sets per-client rate; `get_cadence(client_id)` returns it.
   The `TelemetryService` loop queries each client's cadence independently.

**Testing:** Unit test with a mock slow client (send takes 1 s) verifying other clients receive
their broadcast within 100 ms.

---

### Group 4 — Async Hygiene
**Files:** `backend/src/core/health.py`, `backend/src/services/maps_service.py`,
`backend/src/services/weather_service.py`, `backend/src/services/jobs_service.py`,
`backend/src/api/rest.py`
**Bugs fixed:** ARCH-005, BUG-004, BUG-011

#### ARCH-005: `asyncio.run()` Called from Async Contexts
Three locations call `asyncio.run()` which raises `RuntimeError` when a loop is already running.

**Fix per site:**
- `health.py:163` — `_default_sensor_health()` is called from a FastAPI background task.
  Change to `await self._async_sensor_health_probe()` and make the caller `async`.
- `maps_service.py:339,355` — persistence coroutines called via `asyncio.run()`. Change to
  `await persistence_call(...)` (callers in this file are already async).
- `weather_service.py:95` — `get_current()` is a synchronous public method that internally
  calls `asyncio.run(...)`. Rename the sync method to `get_current_sync()` for truly synchronous
  callers (non-FastAPI paths). Create `async def get_current_async()` that directly awaits the
  HTTP call. FastAPI route handlers call `await get_current_async()`. The sync wrapper
  `get_current_sync()` may only be called from outside an event loop; add an assertion
  `assert not asyncio.get_event_loop().is_running()` to surface misuse clearly.

#### BUG-004: Fire-and-Forget Task in `jobs_service.py`
`asyncio.create_task(self._execute_job(job))` discards the task; exceptions are silently lost.

**Fix:**
```python
task = asyncio.create_task(self._execute_job(job))
self._running_tasks.add(task)
task.add_done_callback(self._running_tasks.discard)
task.add_done_callback(self._log_task_exception)
```
Add `_log_task_exception(task)` callback that calls `task.exception()` and logs at `ERROR`.
Add `_running_tasks: set[asyncio.Task]` initialized in `__init__`.
Cancel all tasks in `shutdown()`.

#### BUG-011: Audit Log Task Not Error-Checked
`asyncio.create_task(asyncio.to_thread(persistence.add_audit_log, ...))` in `rest.py` silently
drops exceptions.

**Fix:** Same done-callback pattern as BUG-004 — add a callback that logs any exception at
`WARNING` level (audit failures are non-fatal but should be visible in logs).

---

### Group 5 — Security/Auth
**Files:** `backend/src/api/rest_v1.py`, `backend/src/api/routers/auth.py`,
`backend/src/services/auth_service.py`
**Bug fixed:** BUG-009

#### BUG-009: Hardcoded `"operator123"` Default Credential
Three files fall back to `"operator123"` when `LAWN_BERRY_OPERATOR_CREDENTIAL` is unset.

**Fix:** Change all three fallbacks from:
```python
os.getenv("LAWN_BERRY_OPERATOR_CREDENTIAL", "operator123")
```
to:
```python
os.getenv("LAWN_BERRY_OPERATOR_CREDENTIAL") or _require_credential()
```
Where `_require_credential()` raises `RuntimeError("LAWN_BERRY_OPERATOR_CREDENTIAL is required. Set it in /etc/lawnberry.env or the systemd unit.")` — evaluated once at import time in each module, not lazily on first request.

**Startup impact:** If the env var is missing the backend will refuse to start, which is the
correct behavior — a misconfigured deployment should fail loudly.

---

### Group 6 — Safety Monitor Dependency Injection
**Files:** `backend/src/safety/safety_monitor.py`, `backend/src/api/rest.py` (lifespan)
**Bug fixed:** ARCH-006

#### ARCH-006: Safety Monitor Imports from the API Layer
`safety_monitor.py` imports `websocket_hub` directly from `api.rest`, inverting the dependency
direction.

**Fix:**
1. Add `websocket_hub: "WebSocketHub | None" = None` parameter to `SafetyMonitor.__init__()`.
2. Remove `from ..api.rest import websocket_hub` module-level import.
3. Store `self._websocket_hub = websocket_hub`.
4. Replace all `websocket_hub.broadcast(...)` calls with
   `if self._websocket_hub: await self._websocket_hub.broadcast(...)`.
5. In `lifespan()` in `rest.py`, pass `websocket_hub` when constructing `SafetyMonitor`.

---

### Group 7 — Code Quality
**Files:** Various — `navigation_service.py`, `robohat_service.py`, `camera_stream_service.py`,
`telemetry_hub.py`; ruff auto-fix across `backend/src/`
**Bugs fixed:** BUG-007, BUG-008, BUG-010, BUG-012, BUG-013, BUG-014, BUG-015, BUG-018, BUG-020

| Bug | File | Fix |
|-----|------|-----|
| BUG-007 | `navigation_service.py` | Add `TYPE_CHECKING` guard: `if TYPE_CHECKING: from .mission_service import Mission, MissionWaypoint` |
| BUG-008 | `camera_stream_service.py:708`, `telemetry_hub.py:296` | `except:` → `except Exception:` |
| BUG-010 | `robohat_service.py:299` | Remove `f` prefix: `logger.error("Failed to send RoboHAT command line '%s': %s", line, exc)` |
| BUG-012 | `navigation_service.py:348` | `_TANK_TURN_TIMEOUT_S = 30.0` → `8.0` |
| BUG-020 | `navigation_service.py:490` | Remove `# DEBUG:` comment; verify log level is `logger.debug` |
| BUG-013/014/015/018 | `backend/src/` | `ruff check --select F401,B904,F841,F811,E722,F541 --fix`; review diff before committing |

---

## Phase 2 Design

### Group 1 — Break Circular Service Dependency
**Files:** new `backend/src/protocols/mission.py`, `navigation_service.py`, `mission_service.py`
**Bug fixed:** ARCH-002

#### ARCH-002: Circular MissionService ↔ NavigationService Dependency

**Fix:**
1. Create `backend/src/protocols/mission.py` with a `MissionStatusReader` Protocol:
   ```python
   from typing import Protocol
   class MissionStatusReader(Protocol):
       async def update_waypoint_progress(self, mission_id: str, waypoint_index: int) -> None: ...
       async def mark_mission_complete(self, mission_id: str) -> None: ...
       async def mark_mission_failed(self, mission_id: str, reason: str) -> None: ...
   ```
2. `NavigationService` type-annotates its `mission_service` dependency as `MissionStatusReader`
   (under `TYPE_CHECKING` for runtime). Remove all deferred `from .mission_service import ...`
   inside method bodies.
3. `MissionService` already satisfies the protocol structurally (no changes needed to its
   implementation).
4. Add `threading.Lock()` guard around `_mission_service_instance` in `get_mission_service()`.

**Testing:** Add unit test that constructs `NavigationService` with a mock `MissionStatusReader`
to verify the dependency is correctly inverted.

---

### Group 2 — Mission Status WebSocket Push
**Files:** `mission_service.py`, `websocket_hub.py`, `frontend/src/stores/mission.ts`
**Bug fixed:** ARCH-007

#### ARCH-007: Mission Status Uses HTTP Polling Instead of WebSocket Push

**Fix:**
1. In `MissionService`, after each lifecycle transition (start, pause, resume, complete, abort,
   fail), emit a WebSocket event on topic `mission.status`:
   ```python
   await self._websocket_hub.broadcast_to_topic("mission.status", {
       "mission_id": mission.mission_id,
       "status": mission.status,
       "progress_pct": mission.progress_pct,
       "detail": detail_message,
   })
   ```
2. In `frontend/src/stores/mission.ts`, subscribe to `mission.status` topic on WebSocket
   connect. On receipt, update `currentMission`, `missionStatus`, and `missionProgress` from
   the event payload.
3. Keep the existing `setInterval` HTTP poll but extend interval from 2000 ms → 30000 ms as
   a reconciliation fallback.
4. The `MissionService` gets `websocket_hub` injected (already established as the pattern from
   ARCH-006 fix).

---

### Group 3 — Fix Optimistic Frontend Mutations
**File:** `frontend/src/stores/mission.ts`
**Bug fixed:** ARCH-008

#### ARCH-008: State Mutations Before HTTP Confirmation

**Fix:** In `abortCurrentMission()`, `pauseCurrentMission()`, and `resumeCurrentMission()`:
1. Call `await apiService.post(...)` first.
2. Only on success (2xx): apply the state mutation.
3. On failure: set `statusDetail.value` to the error message; keep previous `currentMission`
   and `missionStatus` values.
4. No UI component changes needed — they bind reactively to the store.

---

### Group 4 — ConfigLoader Singleton
**Files:** `backend/src/core/config_loader.py`, `backend/src/services/robohat_service.py`
**Bug fixed:** ARCH-009

#### ARCH-009: Multiple ConfigLoader Instances

**Fix:**
1. Add module-level singleton to `config_loader.py`:
   ```python
   _instance: ConfigLoader | None = None
   def get_config_loader() -> ConfigLoader:
       global _instance
       if _instance is None:
           _instance = ConfigLoader()
       return _instance
   ```
2. `RoboHATService.__init__()` accepts `hardware_config: HardwareConfig | None = None`;
   if `None`, calls `get_config_loader().get_hardware_config()`.
3. `lifespan()` calls `get_config_loader()` once on startup (primes the cache).

---

### Group 5 — Code Modernization
**Files:** All of `backend/src/`
**Bugs fixed:** BUG-016, BUG-017, BUG-019, remaining cosmetic items

| Step | Command | Scope |
|------|---------|-------|
| Format long lines | `ruff format --line-length 100 backend/src/` | BUG-016 (314 lines) |
| Modernize typing | `ruff check backend/src --select UP --fix` | BUG-017 (~1,318+ changes) |
| Sort imports | `ruff check backend/src --select I001 --fix` | 110 files |
| Annotate v1 endpoints | Manual — add comment + `Deprecation` header | BUG-019 |

Review full diff before committing. The UP/I001 pass is large; commit separately from format.

---

## Cross-Cutting Concerns

### Testing Gate
Every group ends with:
```bash
python -m pytest tests/unit/ -m "not hardware" -q
# Expected: 282 passed, 0 failed
```

### Documentation
Any structural change (new `protocols/` module, DI wiring, WebSocket topics) must update
`docs/code_structure_overview.md` in the same commit.

### Commit Convention
- Phase 1 commits: `fix(group): description` (e.g., `fix(safety): geofence check after bootstrap`)
- Phase 2 commits: `refactor(group): description` (e.g., `refactor(arch): break mission-navigation circular dep`)
- Each commit references the bug/arch ID in the body (e.g., `Fixes ARCH-010, BUG-005`)

---

## What This Does Not Cover

- ARCH-001 E-stop unification into a single authoritative function (the navigation read-path is
  fixed; full unification of the four state sources is a deeper refactor deferred to a future pass)
- Installing `mypy` and adding full static type checking to CI
- Replacing the v1 API in-memory stores with real persistence (BUG-019 is annotated, not fixed)
- Hardware-dependent test paths (sensor drivers, motor PWM, GPS serial)
