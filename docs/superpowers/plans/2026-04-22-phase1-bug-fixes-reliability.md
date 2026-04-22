# Phase 1 — Bug Fixes & Reliability Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all functional bugs and runtime safety issues from the 2026-04-22 audit before the next mowing run.

**Architecture:** Surgical fixes organized by subsystem (Safety → Persistence → WebSocket → Async → Security → DI → Code Quality). Each group ends with `pytest tests/unit/ -m "not hardware" -q` and a commit. No structural reorganization — that is Phase 2.

**Tech Stack:** Python 3.11, FastAPI, asyncio, SQLite, `asyncio.Lock`, `threading.Lock`, ruff

**Source:** `docs/superpowers/specs/2026-04-22-bug-and-arch-remediation-design.md` (Phase 1 section)

---

## Task 1: ARCH-010 — Post-Bootstrap Geofence Check

**Files:**
- Modify: `backend/src/services/navigation_service.py` (~line 254)
- Test: `tests/unit/test_navigation_service.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_navigation_service.py`:

```python
@pytest.mark.asyncio
async def test_bootstrap_geofence_violation_aborts_mission():
    """Bootstrap drive that exits geofence must latch emergency and abort."""
    from backend.src.services.navigation_service import NavigationService, NavigationState
    from backend.src.models.navigation import Position
    from unittest.mock import AsyncMock, MagicMock, patch

    nav = NavigationService.__new__(NavigationService)
    # Minimal state setup
    state = NavigationState()
    # Position outside boundary square (0,0)-(1,1)
    state.current_position = Position(latitude=5.0, longitude=5.0)
    state.safety_boundaries = [[
        Position(latitude=0.0, longitude=0.0),
        Position(latitude=0.0, longitude=1.0),
        Position(latitude=1.0, longitude=1.0),
        Position(latitude=1.0, longitude=0.0),
    ]]
    nav.navigation_state = state
    nav._global_emergency_active = MagicMock(return_value=False)
    nav._latch_global_emergency_state = MagicMock()
    nav._bootstrap_heading_from_gps_cog = AsyncMock()
    nav._load_boundaries_from_zones = MagicMock()

    with pytest.raises(RuntimeError, match="Bootstrap drive exited geofence"):
        await nav._run_bootstrap_and_check_geofence()

    nav._latch_global_emergency_state.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/pi/lawnberry && python -m pytest tests/unit/test_navigation_service.py::test_bootstrap_geofence_violation_aborts_mission -xvs -m "not hardware"
```
Expected: `AttributeError: '_run_bootstrap_and_check_geofence' not defined` or `FAILED`

- [ ] **Step 3: Extract bootstrap + geofence check into helper method**

In `backend/src/services/navigation_service.py`, find the `execute_mission` / `_run_mission_loop` block that contains:
```python
await self._bootstrap_heading_from_gps_cog()
```
(approximately line 254)

Replace that single call with a call to a new helper `_run_bootstrap_and_check_geofence()`, and add the helper method near `_bootstrap_heading_from_gps_cog`:

```python
async def _run_bootstrap_and_check_geofence(self) -> None:
    """Run heading bootstrap then abort if mower is outside geofence."""
    await self._bootstrap_heading_from_gps_cog()

    if (
        self.navigation_state.safety_boundaries
        and self.navigation_state.current_position
    ):
        outer_boundary = self.navigation_state.safety_boundaries[0]
        polygon = [(p.latitude, p.longitude) for p in outer_boundary]
        cur = self.navigation_state.current_position
        if not point_in_polygon(cur.latitude, cur.longitude, polygon):
            self._latch_global_emergency_state()
            logger.error(
                "Bootstrap drive exited geofence at (%.6f, %.6f) — mission aborted",
                cur.latitude,
                cur.longitude,
            )
            raise RuntimeError("Bootstrap drive exited geofence — mission aborted")
```

Also update the original call site (line ~254):
```python
# Before:
await self._bootstrap_heading_from_gps_cog()
# After:
await self._run_bootstrap_and_check_geofence()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/unit/test_navigation_service.py::test_bootstrap_geofence_violation_aborts_mission -xvs -m "not hardware"
```
Expected: `PASSED`

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass (282+)

- [ ] **Step 6: Commit**

```bash
cd /home/pi/lawnberry
git add backend/src/services/navigation_service.py tests/unit/test_navigation_service.py
git commit -m "fix(safety): geofence check after bootstrap drive (ARCH-010)

Bootstrap drive ran for up to 3s with no boundary check. Add
_run_bootstrap_and_check_geofence() that latches emergency and
raises RuntimeError if position is outside any mowing zone after
the drive completes.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: BUG-005 — E-Stop Pending Flag on Serial Disconnect

**Files:**
- Modify: `backend/src/services/robohat_service.py`
- Test: `tests/unit/test_robohat_service_usb_control.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_robohat_service_usb_control.py`:

```python
@pytest.mark.asyncio
async def test_estop_pending_set_when_serial_disconnected():
    """emergency_stop() when serial is None must set _estop_pending."""
    from backend.src.services.robohat_service import RoboHATService

    svc = RoboHATService.__new__(RoboHATService)
    svc.serial_conn = None
    svc.running = False
    svc._estop_pending = False
    svc.status = MagicMock()

    result = await svc.emergency_stop()

    assert svc._estop_pending is True
    assert result is False  # serial not available, can't send yet


@pytest.mark.asyncio
async def test_estop_pending_sends_neutral_on_reconnect():
    """On serial reconnect, if _estop_pending, neutral PWM sent before any other command."""
    from backend.src.services.robohat_service import RoboHATService

    svc = RoboHATService.__new__(RoboHATService)
    svc._estop_pending = True
    sent_lines = []
    svc._send_line = AsyncMock(side_effect=lambda line: sent_lines.append(line) or True)
    svc._last_pwm = (1500, 1500)

    await svc._apply_estop_if_pending()

    assert sent_lines[0] == "pwm,1500,1500"
    assert sent_lines[1] == "blade=off"
    assert svc._estop_pending is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_robohat_service_usb_control.py::test_estop_pending_set_when_serial_disconnected tests/unit/test_robohat_service_usb_control.py::test_estop_pending_sends_neutral_on_reconnect -xvs -m "not hardware"
```
Expected: `AttributeError` or `FAILED`

- [ ] **Step 3: Add `_estop_pending` flag and `_apply_estop_if_pending()` to RoboHATService**

In `backend/src/services/robohat_service.py`, in `__init__` after `self._last_pwm`:
```python
self._estop_pending: bool = False  # set True when e-stop received while disconnected
```

In `emergency_stop()`, change the early-return guard from:
```python
if not self.serial_conn or not self.serial_conn.is_open or not self.running:
    return False
```
to:
```python
if not self.serial_conn or not self.serial_conn.is_open or not self.running:
    self._estop_pending = True
    logger.critical("Serial not available; e-stop queued for next reconnect")
    return False
```

Add new method after `clear_emergency()`:
```python
async def _apply_estop_if_pending(self) -> None:
    """Send queued emergency stop if one was requested while disconnected."""
    if not self._estop_pending:
        return
    logger.critical("Applying queued emergency stop after serial reconnect")
    await self._send_line("pwm,1500,1500")
    await self._send_line("blade=off")
    self._last_pwm = (1500, 1500)
    self._last_pwm_at = time.monotonic()
    self._estop_pending = False
```

In the serial reconnect path — find where `self.status.serial_connected = True` is set (line ~265) and call `_apply_estop_if_pending()` immediately after:
```python
self.status.serial_connected = True
self.running = True
await self._apply_estop_if_pending()  # honour any e-stop received while disconnected
```

In `send_motor_command()`, add guard at the top of the method (after existing serial check):
```python
if self._estop_pending:
    logger.warning("Motor command refused: emergency stop pending")
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/test_robohat_service_usb_control.py::test_estop_pending_set_when_serial_disconnected tests/unit/test_robohat_service_usb_control.py::test_estop_pending_sends_neutral_on_reconnect -xvs -m "not hardware"
```
Expected: `PASSED`

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/src/services/robohat_service.py tests/unit/test_robohat_service_usb_control.py
git commit -m "fix(safety): queue e-stop when serial disconnected (BUG-005)

emergency_stop() now sets _estop_pending=True when serial is unavailable.
On reconnect, _apply_estop_if_pending() sends neutral PWM + blade=off
before any other command. send_motor_command() refuses non-neutral commands
while _estop_pending is True.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: ARCH-003 — SQLite WAL Mode & Thread-Safe Writes

**Files:**
- Modify: `backend/src/core/persistence.py`
- Test: `tests/unit/test_settings_persistence.py` (existing, must keep passing)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_settings_persistence.py` (or a new `tests/unit/test_persistence_wal.py`):

```python
def test_wal_mode_enabled_after_init():
    """Database must use WAL journal mode after initialization."""
    import sqlite3, tempfile, pathlib
    from backend.src.core.persistence import DatabasePersistence

    with tempfile.TemporaryDirectory() as tmp:
        db_path = pathlib.Path(tmp) / "test.db"
        persistence = DatabasePersistence(db_path=db_path)
        with persistence.get_connection() as conn:
            row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal", f"Expected WAL, got {row[0]}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/unit/test_settings_persistence.py::test_wal_mode_enabled_after_init -xvs -m "not hardware" 2>/dev/null || python -m pytest tests/unit/test_persistence_wal.py::test_wal_mode_enabled_after_init -xvs -m "not hardware"
```
Expected: `FAILED` — `AssertionError: Expected WAL, got delete`

- [ ] **Step 3: Enable WAL mode in `_init_database()`**

In `backend/src/core/persistence.py`, at the end of `_init_database()`, after migrations complete:

```python
def _init_database(self):
    """Initialize database and run migrations."""
    with self.get_connection() as conn:
        current_version = self._get_schema_version(conn)
        for migration in self.MIGRATIONS:
            if migration.version > current_version:
                logger.info(f"Applying migration {migration.version}: {migration.description}")
                conn.executescript(migration.sql)
                conn.commit()
    # Enable WAL mode for better concurrent read/write throughput.
    # WAL mode is sticky — set once and it persists in the database file.
    with self.get_connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        conn.commit()
```

Also add a `threading.Lock` to protect concurrent writes. In `__init__`:
```python
import threading
# ...existing init code...
self._write_lock = threading.Lock()
```

Wrap `add_audit_log` and other write methods with the lock:
```python
def add_audit_log(self, action: str, client_id=None, resource=None, details=None) -> None:
    with self._write_lock:
        with self.get_connection() as conn:
            # ...existing SQL...
```

- [ ] **Step 4: Run WAL test**

```bash
python -m pytest tests/unit/ -k "wal" -xvs -m "not hardware"
```
Expected: `PASSED`

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/src/core/persistence.py tests/unit/
git commit -m "fix(persistence): enable WAL mode and add write lock (ARCH-003)

Set PRAGMA journal_mode=WAL + synchronous=NORMAL on every startup.
WAL allows concurrent readers without blocking writers. Add
threading.Lock around write operations to serialise concurrent
callers from different event-loop threads.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: ARCH-004 — Concurrent WebSocket Fan-Out with Timeout

**Files:**
- Modify: `backend/src/services/websocket_hub.py`
- Test: `tests/unit/test_websocket_hub_state_sync.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_websocket_hub_state_sync.py`:

```python
@pytest.mark.asyncio
async def test_broadcast_to_topic_slow_client_does_not_block_others():
    """A slow client must not block other subscribers from receiving messages."""
    import asyncio
    from backend.src.services.websocket_hub import WebSocketHub

    hub = WebSocketHub()
    results = []

    class FakeWS:
        def __init__(self, delay=0):
            self.delay = delay
        async def send_text(self, msg):
            await asyncio.sleep(self.delay)
            results.append(self.delay)

    hub.clients = {"fast": FakeWS(0), "slow": FakeWS(10)}
    hub.subscriptions = {"test.topic": {"fast", "slow"}}

    start = asyncio.get_event_loop().time()
    await hub.broadcast_to_topic("test.topic", {"x": 1})
    elapsed = asyncio.get_event_loop().time() - start

    # Both attempted; fast client must have completed; elapsed << 10s due to timeout
    assert elapsed < 3.0, f"Fan-out blocked: {elapsed:.1f}s"
    assert 0 in results, "Fast client never received message"


@pytest.mark.asyncio
async def test_broadcast_to_topic_timed_out_client_disconnected():
    """Client that times out during broadcast must be removed from hub."""
    import asyncio
    from backend.src.services.websocket_hub import WebSocketHub

    hub = WebSocketHub()

    class HangingWS:
        async def send_text(self, msg):
            await asyncio.sleep(60)  # never completes within timeout

    hub.clients = {"hanging": HangingWS()}
    hub.subscriptions = {"test.topic": {"hanging"}}

    await hub.broadcast_to_topic("test.topic", {"x": 1})

    assert "hanging" not in hub.clients
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_websocket_hub_state_sync.py::test_broadcast_to_topic_slow_client_does_not_block_others tests/unit/test_websocket_hub_state_sync.py::test_broadcast_to_topic_timed_out_client_disconnected -xvs -m "not hardware"
```
Expected: `FAILED` — timeout test hangs or assertion fails

- [ ] **Step 3: Replace sequential loop with concurrent gather + timeout**

In `backend/src/services/websocket_hub.py`, replace the `broadcast_to_topic` method:

```python
async def broadcast_to_topic(self, topic: str, data: dict):
    if topic not in self.subscriptions:
        return

    payload = {
        "event": "telemetry.data",
        "topic": topic,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    message = json.dumps(jsonable_encoder(payload), default=str)

    subscriber_ids = list(self.subscriptions[topic])
    timed_out: list[str] = []

    async def _send_one(client_id: str) -> None:
        ws = self.clients.get(client_id)
        if ws is None:
            return
        try:
            await asyncio.wait_for(ws.send_text(message), timeout=2.0)
        except asyncio.TimeoutError:
            timed_out.append(client_id)
        except Exception:
            timed_out.append(client_id)

    await asyncio.gather(*(_send_one(cid) for cid in subscriber_ids), return_exceptions=True)

    for client_id in timed_out:
        self.disconnect(client_id)
```

Also apply the same pattern to the existing `broadcast()` method:
```python
async def broadcast(self, message: str):
    disconnected: list[str] = []

    async def _send_one(client_id: str, ws) -> None:
        try:
            await asyncio.wait_for(ws.send_text(message), timeout=2.0)
        except Exception:
            disconnected.append(client_id)

    await asyncio.gather(
        *(_send_one(cid, ws) for cid, ws in list(self.clients.items())),
        return_exceptions=True,
    )
    for client_id in disconnected:
        self.disconnect(client_id)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/unit/test_websocket_hub_state_sync.py -xvs -m "not hardware"
```
Expected: all pass

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/src/services/websocket_hub.py tests/unit/test_websocket_hub_state_sync.py
git commit -m "fix(websocket): concurrent fan-out with 2s timeout (ARCH-004)

Replace sequential per-client send loop in broadcast_to_topic() and
broadcast() with asyncio.gather() fan-out. Each send is wrapped in
asyncio.wait_for(..., timeout=2.0) so slow/stalled clients are
disconnected rather than blocking all other subscribers.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Async Hygiene — Remove asyncio.run() from Event Loop Paths

**Files:**
- Modify: `backend/src/core/health.py`
- Modify: `backend/src/services/maps_service.py`
- Modify: `backend/src/services/weather_service.py`
- Modify: `backend/src/services/jobs_service.py`
- Modify: `backend/src/api/rest.py`
- Test: `tests/unit/test_health_api_endpoints.py`, `tests/unit/test_health_service_status.py`

### 5a: health.py — make `_default_sensor_health` async-safe

- [ ] **Step 5a-1: Write the failing test**

Add to `tests/unit/test_health_service_status.py`:

```python
@pytest.mark.asyncio
async def test_default_sensor_health_works_inside_event_loop():
    """_default_sensor_health must not call asyncio.run() inside running loop."""
    from backend.src.core.health import HealthMonitor

    monitor = HealthMonitor()
    # No custom provider — falls through to _default_sensor_health
    result = await monitor._async_evaluate_sensor_health()
    assert isinstance(result, dict)
    assert "status" in result
```

- [ ] **Step 5a-2: Run to verify failure**

```bash
python -m pytest tests/unit/test_health_service_status.py::test_default_sensor_health_works_inside_event_loop -xvs -m "not hardware"
```
Expected: `AttributeError: '_async_evaluate_sensor_health' not defined`

- [ ] **Step 5a-3: Add async version in health.py**

In `backend/src/core/health.py`:

1. Add `async def _async_evaluate_sensor_health(self) -> dict[str, Any]:` right after `_evaluate_sensor_health`:
```python
async def _async_evaluate_sensor_health(self) -> dict[str, Any]:
    """Async variant — use from async callers to avoid asyncio.run() inside event loop."""
    if self._sensor_health_provider:
        try:
            payload = self._sensor_health_provider()
            if asyncio.iscoroutine(payload):
                payload = await payload
        except Exception as exc:
            logger.debug("Custom sensor health provider failed: %s", exc, exc_info=exc)
        else:
            if isinstance(payload, dict):
                return self._normalize_sensor_health(payload)
    return await self._async_sensor_health_probe()
```

2. Leave `_default_sensor_health()` unchanged (it is already guarded by `except RuntimeError` and returns UNKNOWN when inside event loop — that is the sync fallback path for non-FastAPI callers).

- [ ] **Step 5a-4: Run test**

```bash
python -m pytest tests/unit/test_health_service_status.py -xvs -m "not hardware"
```
Expected: pass

### 5b: maps_service.py — remove asyncio.run() dead code path

- [ ] **Step 5b-1: Verify the asyncio.run() branches are guarded**

The `_ensure_not_running_loop()` call already precedes `asyncio.run(result)` in both
`save_map_configuration` and `load_map_configuration`. Since persistence methods are
synchronous, `asyncio.iscoroutine(result)` is always False and these branches are dead code.

Replace the dead code with a defensive log:

In `save_map_configuration` (~line 337):
```python
if asyncio.iscoroutine(result):
    # Persistence implementation returned a coroutine — this is unexpected.
    # Drain it to avoid ResourceWarning.
    logger.error(
        "save_map_configuration: persistence returned a coroutine unexpectedly; "
        "use an async persistence layer instead of asyncio.run()"
    )
    result.close()  # suppress ResourceWarning without running the coroutine
```

In `load_map_configuration` (~line 353):
```python
if asyncio.iscoroutine(result):
    logger.error(
        "load_map_configuration: persistence returned a coroutine unexpectedly; "
        "returning None"
    )
    result.close()
    return None
```

- [ ] **Step 5b-2: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass (no regressions)

### 5c: BUG-004 — Track fire-and-forget task in jobs_service.py

- [ ] **Step 5c-1: Write the failing test**

Add to `tests/unit/test_job_state_machine.py`:

```python
@pytest.mark.asyncio
async def test_job_task_exception_logged(caplog):
    """Exceptions from _execute_job must be logged, not silently discarded."""
    import logging, asyncio
    from backend.src.services.jobs_service import JobsService, Job, JobStatus
    from datetime import datetime, timezone

    svc = JobsService()

    async def _bad_handler():
        raise ValueError("test job failure")

    job = Job(
        id="j1",
        name="bad",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        handler=_bad_handler,
    )
    svc.jobs["j1"] = job

    with caplog.at_level(logging.ERROR, logger="backend.src.services.jobs_service"):
        svc.start_job("j1")
        await asyncio.sleep(0.1)  # let task run

    assert any("j1" in r.message or "test job failure" in r.message for r in caplog.records), \
        "Expected error log for failed job task"
```

- [ ] **Step 5c-2: Run to verify failure**

```bash
python -m pytest tests/unit/test_job_state_machine.py::test_job_task_exception_logged -xvs -m "not hardware"
```
Expected: `FAILED` — no error log emitted

- [ ] **Step 5c-3: Add `_running_tasks` set and done callback to jobs_service.py**

In `backend/src/services/jobs_service.py`, in `__init__`:
```python
self._running_tasks: set[asyncio.Task] = set()
```

Replace the `asyncio.create_task(self._execute_job(job))` call in `start_job()`:
```python
task = asyncio.create_task(self._execute_job(job))
self._running_tasks.add(task)
task.add_done_callback(self._running_tasks.discard)
task.add_done_callback(self._on_job_task_done)
```

Add the callback method:
```python
def _on_job_task_done(self, task: asyncio.Task) -> None:
    """Log any unhandled exception from a job task."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Unhandled exception in job task: %s", exc, exc_info=exc)
```

In `shutdown()` (or add if missing):
```python
async def shutdown(self) -> None:
    for task in list(self._running_tasks):
        task.cancel()
    if self._running_tasks:
        await asyncio.gather(*self._running_tasks, return_exceptions=True)
    self._running_tasks.clear()
```

- [ ] **Step 5c-4: Run test**

```bash
python -m pytest tests/unit/test_job_state_machine.py -xvs -m "not hardware"
```
Expected: pass

### 5d: BUG-011 — Add error callback to audit log task in rest.py

- [ ] **Step 5d-1: Locate the audit log create_task call in rest.py**

Find in `backend/src/api/rest.py` (~line 996):
```python
asyncio.create_task(
    asyncio.to_thread(persistence.add_audit_log, "control.drive.v2", None, None, _audit_details)
)
```

Replace with:
```python
_audit_task = asyncio.create_task(
    asyncio.to_thread(persistence.add_audit_log, "control.drive.v2", None, None, _audit_details)
)

def _log_audit_exc(t: asyncio.Task) -> None:
    if not t.cancelled() and t.exception():
        import logging as _log
        _log.getLogger(__name__).warning("Audit log write failed: %s", t.exception())

_audit_task.add_done_callback(_log_audit_exc)
```

- [ ] **Step 5d-2: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 5e: Commit all async hygiene fixes**

```bash
git add backend/src/core/health.py backend/src/services/maps_service.py \
        backend/src/services/jobs_service.py backend/src/api/rest.py \
        tests/unit/
git commit -m "fix(async): remove asyncio.run() inside event loop; track tasks (ARCH-005, BUG-004, BUG-011)

health.py: Add _async_evaluate_sensor_health() for async callers.
maps_service.py: Replace asyncio.run() dead branches with defensive log.
jobs_service.py: Track fire-and-forget tasks; log unhandled exceptions.
rest.py: Add done-callback to audit log task to surface write failures.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: BUG-009 — Require Operator Credential at Startup

**Files:**
- Modify: `backend/src/services/auth_service.py`
- Modify: `backend/src/api/routers/auth.py`
- Test: `tests/unit/test_auth_security_levels.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_auth_security_levels.py`:

```python
def test_auth_service_raises_if_credential_unset(monkeypatch):
    """AuthService must raise RuntimeError if LAWN_BERRY_OPERATOR_CREDENTIAL is unset."""
    monkeypatch.delenv("LAWN_BERRY_OPERATOR_CREDENTIAL", raising=False)
    monkeypatch.setenv("SIM_MODE", "0")

    import importlib, backend.src.services.auth_service as _mod
    importlib.reload(_mod)  # force re-evaluation of module-level check

    with pytest.raises(RuntimeError, match="LAWN_BERRY_OPERATOR_CREDENTIAL"):
        _mod.AuthService()
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/unit/test_auth_security_levels.py::test_auth_service_raises_if_credential_unset -xvs -m "not hardware"
```
Expected: `FAILED` — no RuntimeError raised; `AuthService()` succeeds with fallback

- [ ] **Step 3: Change fallback to startup error in auth_service.py**

In `backend/src/services/auth_service.py`, in `AuthService.__init__()`, change:
```python
# BEFORE:
default_secret = os.getenv("LAWN_BERRY_OPERATOR_CREDENTIAL", operator_credential)
```
to:
```python
# AFTER:
_raw_cred = os.getenv("LAWN_BERRY_OPERATOR_CREDENTIAL")
if not _raw_cred and not self._simulation_mode:
    raise RuntimeError(
        "LAWN_BERRY_OPERATOR_CREDENTIAL is required. "
        "Set it in /etc/lawnberry.env or the systemd unit Environment= directive. "
        "Example: LAWN_BERRY_OPERATOR_CREDENTIAL=your-secret-passphrase"
    )
default_secret = _raw_cred or "sim-mode-credential"
```

Note: `self._simulation_mode` is set before this line — move its init above if needed:
```python
self._simulation_mode = os.getenv("SIM_MODE", "0") == "1"
```
Make sure `_simulation_mode` is set before the credential check.

- [ ] **Step 4: Update auth.py to match**

In `backend/src/api/routers/auth.py`, line ~351:
```python
# BEFORE:
credential = os.getenv("LAWN_BERRY_OPERATOR_CREDENTIAL", "operator123")
# AFTER:
credential = os.getenv("LAWN_BERRY_OPERATOR_CREDENTIAL")
if not credential:
    raise RuntimeError(
        "LAWN_BERRY_OPERATOR_CREDENTIAL is required — cannot authenticate without it."
    )
```

Also verify no other fallback to `"operator123"` remains in the file:
```bash
grep -n "operator123" backend/src/api/routers/auth.py backend/src/services/auth_service.py
```
Expected: no output

- [ ] **Step 5: Verify .env has credential set (do not commit credential)**

```bash
grep "LAWN_BERRY_OPERATOR_CREDENTIAL" /home/pi/lawnberry/.env /etc/lawnberry.env 2>/dev/null | head -5
```
If missing from `.env`, add a placeholder (do not commit):
```bash
echo "LAWN_BERRY_OPERATOR_CREDENTIAL is set" # verify only — do not echo actual value
```
The CI test environment should set `SIM_MODE=1` to bypass the check.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/unit/test_auth_security_levels.py -xvs -m "not hardware"
```
Expected: new test passes; all existing auth tests pass

- [ ] **Step 7: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add backend/src/services/auth_service.py backend/src/api/routers/auth.py \
        tests/unit/test_auth_security_levels.py
git commit -m "fix(security): require LAWN_BERRY_OPERATOR_CREDENTIAL at startup (BUG-009)

Replace 'operator123' hardcoded fallback with RuntimeError if the
env var is unset in non-SIM_MODE. Backend will refuse to start on
a misconfigured deployment rather than silently use a known credential.
SIM_MODE=1 bypasses the check for test environments.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 7: ARCH-006 — Safety Monitor Dependency Injection

**Files:**
- Modify: `backend/src/safety/safety_monitor.py`
- Modify: `backend/src/main.py` (lifespan wiring)
- Test: `tests/unit/test_safety_triggers.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_safety_triggers.py`:

```python
@pytest.mark.asyncio
async def test_safety_monitor_broadcasts_via_injected_hub():
    """SafetyMonitor must use the injected WebSocketHub, not an import."""
    from backend.src.safety.safety_monitor import SafetyMonitor
    from backend.src.models.safety_interlock import SafetyInterlock, InterlockType, InterlockState
    from unittest.mock import AsyncMock

    mock_hub = AsyncMock()
    mock_hub.broadcast_to_topic = AsyncMock()

    monitor = SafetyMonitor(websocket_hub=mock_hub)
    interlock = SafetyInterlock(
        interlock_type=InterlockType.TILT,
        state=InterlockState.ACTIVE,
        reason="test tilt",
    )
    await monitor.handle_interlock_event("activate", interlock)

    mock_hub.broadcast_to_topic.assert_called_once()
    call_args = mock_hub.broadcast_to_topic.call_args
    assert call_args[0][0] == "system.safety"


@pytest.mark.asyncio
async def test_safety_monitor_works_without_hub():
    """SafetyMonitor must not raise when no WebSocketHub is injected."""
    from backend.src.safety.safety_monitor import SafetyMonitor
    from backend.src.models.safety_interlock import SafetyInterlock, InterlockType, InterlockState

    monitor = SafetyMonitor()  # no hub
    interlock = SafetyInterlock(
        interlock_type=InterlockType.OBSTACLE,
        state=InterlockState.ACTIVE,
        reason="test obstacle",
    )
    # Must not raise
    await monitor.handle_interlock_event("activate", interlock)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_safety_triggers.py::test_safety_monitor_broadcasts_via_injected_hub tests/unit/test_safety_triggers.py::test_safety_monitor_works_without_hub -xvs -m "not hardware"
```
Expected: `TypeError: __init__() got unexpected keyword argument 'websocket_hub'`

- [ ] **Step 3: Add injection parameter to SafetyMonitor**

In `backend/src/safety/safety_monitor.py`:

1. Remove the module-level import:
```python
# REMOVE THIS LINE:
from ..api.rest import websocket_hub
```

2. Add `TYPE_CHECKING` import at the top:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..services.websocket_hub import WebSocketHub
```

3. Change `__init__`:
```python
def __init__(self, websocket_hub: "WebSocketHub | None" = None) -> None:
    self._events: list[SafetyEvent] = []
    self._lock = asyncio.Lock()
    self._websocket_hub = websocket_hub
```

4. In `handle_interlock_event`, replace `await websocket_hub.broadcast_to_topic(...)` with:
```python
if self._websocket_hub is not None:
    try:
        await self._websocket_hub.broadcast_to_topic(
            "system.safety",
            {
                "action": action,
                "interlock": interlock.model_dump(),
                "timestamp": evt.timestamp,
            },
        )
    except Exception:
        pass
```

5. Update `get_safety_monitor()` to accept and pass the hub:
```python
def get_safety_monitor(websocket_hub: "WebSocketHub | None" = None) -> SafetyMonitor:
    global _monitor
    if _monitor is None:
        _monitor = SafetyMonitor(websocket_hub=websocket_hub)
    return _monitor
```

- [ ] **Step 4: Wire the hub in main.py**

In `backend/src/main.py`, find where `get_safety_monitor()` is called (~line 105) and pass the hub:

```python
# Import websocket_hub from rest.py at the top of main.py (it's already imported elsewhere)
from .api.rest import websocket_hub  # if not already imported

# In lifespan, replace:
monitor = get_safety_monitor()
# With:
monitor = get_safety_monitor(websocket_hub=websocket_hub)
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/unit/test_safety_triggers.py -xvs -m "not hardware"
```
Expected: all pass

- [ ] **Step 6: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/src/safety/safety_monitor.py backend/src/main.py \
        tests/unit/test_safety_triggers.py
git commit -m "fix(arch): inject WebSocketHub into SafetyMonitor (ARCH-006)

SafetyMonitor previously imported websocket_hub from api.rest,
inverting the dependency direction. SafetyMonitor now receives the
hub via __init__(websocket_hub=). Works gracefully when hub is None.
Wired in main.py lifespan.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 8: Code Quality — BUG-007, BUG-008, BUG-010, BUG-012, BUG-018, BUG-020

**Files:**
- Modify: `backend/src/services/navigation_service.py`
- Modify: `backend/src/services/robohat_service.py`
- Modify: `backend/src/services/camera_stream_service.py`
- Modify: `backend/src/services/telemetry_hub.py`

- [ ] **Step 1: BUG-010 — Remove spurious f-prefix from robohat_service.py:299**

In `backend/src/services/robohat_service.py`, change line ~299:
```python
# BEFORE:
logger.error(f"Failed to send RoboHAT command line '%s': %s", line, exc)
# AFTER:
logger.error("Failed to send RoboHAT command line '%s': %s", line, exc)
```

Verify:
```bash
grep -n "f\"Failed to send RoboHAT" backend/src/services/robohat_service.py
```
Expected: no output

- [ ] **Step 2: BUG-012 — Correct tank-turn timeout value**

In `backend/src/services/navigation_service.py`, line ~348:
```python
# BEFORE:
_TANK_TURN_TIMEOUT_S: float = 30.0
# AFTER:
_TANK_TURN_TIMEOUT_S: float = 8.0
```

30 seconds is far too long — 8 seconds is enough for any turn on real hardware.

- [ ] **Step 3: BUG-018 — Remove DEBUG comment from navigation_service.py**

Find and change lines ~490-500:
```python
# BEFORE (keep the log call, remove only the comment):
# DEBUG: Log heading control every 2 seconds
_now = time.monotonic()
if _now - _last_nav_log > 2.0:
    logger.info(...)
    _last_nav_log = _now

# AFTER: Change logger.info to logger.debug and remove the DEBUG comment
_now = time.monotonic()
if _now - _last_nav_log > 2.0:
    logger.debug(
        "NAV_CONTROL: target_bearing=%.1f° current_heading=%.1f° error=%.1f° | "
        "tank_mode=%s in_turn=%s",
        heading_to_target, current_heading, heading_error,
        _in_tank_mode, (abs(heading_error) > 10),
    )
    _last_nav_log = _now
```

- [ ] **Step 4: BUG-007 — Add TYPE_CHECKING guard in navigation_service.py**

Check the current imports at the top of `backend/src/services/navigation_service.py`:
```bash
head -40 backend/src/services/navigation_service.py
```

If `Mission` or `MissionWaypoint` are imported at module level (unconditionally), move them under TYPE_CHECKING:
```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mission_service import Mission, MissionWaypoint
```

If they are already under TYPE_CHECKING or only used as string annotations, skip this step.

- [ ] **Step 5: BUG-008 — Fix bare except clauses**

```bash
grep -n "except:" backend/src/services/camera_stream_service.py backend/src/services/telemetry_hub.py
```

For each bare `except:`, change to `except Exception:`.

Example in `camera_stream_service.py:708`:
```python
# BEFORE:
except:
    pass
# AFTER:
except Exception:
    pass
```

- [ ] **Step 6: BUG-020 — Remove `_TANK_TURN_TIMEOUT_S` shadowing if present**

The class-level variable `_TANK_TURN_TIMEOUT_S` was already addressed in step 2. Verify there are no local variable shadowing issues:
```bash
grep -n "_TANK_TURN_TIMEOUT_S" backend/src/services/navigation_service.py
```
Should only appear at definition and usage sites.

- [ ] **Step 7: Run ruff for targeted functional lint fixes**

```bash
cd /home/pi/lawnberry
ruff check backend/src --select F401,F541,E722,B904 --fix
git diff --stat
```
Review the diff — accept all changes (these are functional: unused imports, f-string without placeholder, bare except, exception chaining).

- [ ] **Step 8: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 9: Commit**

```bash
git add backend/src/
git commit -m "fix(quality): code quality sweep BUG-007/008/010/012/018/020

BUG-007: TYPE_CHECKING guard for mission imports in navigation_service.py
BUG-008: bare except -> except Exception in camera/telemetry_hub
BUG-010: remove spurious f-prefix from robohat logger.error
BUG-012: tank-turn timeout 30s -> 8s (30s is unreachable in normal operation)
BUG-018: remove DEBUG: comment, demote heading log to logger.debug
BUG-020: tank-turn timeout constant audit
ruff: fix F401/F541/E722/B904 across backend/src/

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Final Validation

- [ ] **Run complete test suite one final time**

```bash
cd /home/pi/lawnberry && python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass (282+, 0 failed)

- [ ] **Restart backend and verify healthy**

```bash
sudo systemctl restart lawnberry-backend

# Poll for up to 2 minutes
for i in $(seq 1 24); do
    sleep 5
    if curl -sf http://localhost:8081/api/v2/status > /dev/null 2>&1; then
        echo "Backend up after $((i*5))s"
        break
    fi
    echo "Waiting... ($((i*5))s)"
done
curl -s http://localhost:8081/api/v2/status | python3 -m json.tool | head -20
```

- [ ] **Update code_structure_overview.md**

Any new methods added (e.g., `_run_bootstrap_and_check_geofence`, `_apply_estop_if_pending`,
`_async_evaluate_sensor_health`, `_on_job_task_done`) must appear in `docs/code_structure_overview.md`.

```bash
# Trigger a Code Structure Regenerator agent or update manually
git add docs/code_structure_overview.md
git commit -m "docs: update code_structure_overview.md for Phase 1 additions (auto)"
```

---

## Phase 1 Complete ✓

All 7 subsystem groups addressed:
1. ✅ ARCH-010: Bootstrap geofence check
2. ✅ BUG-005: E-stop pending on serial disconnect
3. ✅ ARCH-003: WAL mode + write lock
4. ✅ ARCH-004: Concurrent WebSocket fan-out
5. ✅ ARCH-005 / BUG-004 / BUG-011: Async hygiene
6. ✅ BUG-009: Startup credential required
7. ✅ ARCH-006: Safety Monitor DI
8. ✅ BUG-007/008/010/012/018/020: Code quality

**Next step:** Phase 2 plan → `docs/superpowers/plans/2026-04-22-phase2-arch-refactoring.md`
