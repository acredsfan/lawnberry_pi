# LawnBerry Bug Report — 2026-04-22

## Summary

| Severity | Count |
|---|---|
| Critical | 3 |
| High | 4 |
| Medium | 5 |
| Low / Code Quality | 8 |

Audit methods: `ruff check` static analysis, `mypy` (unavailable — not installed), `pytest` unit suite, and manual code review of safety-critical services (`navigation_service.py`, `robohat_service.py`, `safety_monitor.py`).

---

## Critical Bugs

### BUG-001: Hardcoded `admin/admin` Authentication Backdoor
- **File**: `backend/src/api/rest_v1.py:109`
- **Severity**: Critical
- **Description**: The `/api/v1/auth/login` endpoint contains an explicit shortcut that accepts `username="admin"` / `password="admin"` and silently promotes the request to the real operator credential. This bypasses the intended `LAWN_BERRY_OPERATOR_CREDENTIAL` secret entirely.
  ```python
  if payload.username == "admin" and payload.password == "admin":
      credential = expected_secret
  ```
- **Impact**: Any attacker with network access to the API can authenticate with trivially known credentials, gaining full operator-level access including motor control, blade commands, and mission execution.
- **Suggested fix**: Remove the `admin/admin` shortcut block entirely. Callers that need the credential should supply `LAWN_BERRY_OPERATOR_CREDENTIAL` directly. Also change the default fallback from `"operator123"` (three places: `rest_v1.py`, `routers/auth.py:351`, `auth_service.py:176`) to an environment-variable-required hard failure so deployment without a secret is rejected at startup.

---

### BUG-002: Rate Limiter Burst Enforcement Broken — Test Failing
- **File**: `backend/src/middleware/rate_limiting.py`, `tests/unit/test_global_rate_limiter.py`
- **Severity**: Critical
- **Description**: `test_rate_limiter_allows_burst_then_limits` is the sole passing gate for DoS protection. It is **failing**: the 4th request (which should be rejected after the burst of 3 is exhausted) returns HTTP 200 instead of HTTP 429. The `asyncio.Lock` created in `GlobalRateLimiter.__init__` is instantiated before any asyncio event loop exists (during `app.add_middleware()`). In Python 3.11 with Starlette's `TestClient` worker-thread model, the Lock may bind to a different event loop context than the one that dispatches requests, causing lock acquisition to always succeed and bucket state to be unprotected / reinitialized. Additionally, the per-IP client key resolves to `"anon"` for the test client (no `request.client`), but bucket consumption is not persisting across requests as expected.
- **Impact**: The rate limiter provides zero protection against burst abuse in production. An unauthenticated attacker can flood any endpoint without receiving 429 responses.
- **Suggested fix**: Replace `asyncio.Lock` with `threading.Lock` (the TestClient dispatch is synchronous per-request) or validate that the lock is acquired inside the same event loop that the middleware is dispatched from. Add a stress-test harness that verifies 429 is returned from a real running server process, not just through the TestClient.

---

### BUG-003: `logging` Module Undefined in `camera_stream_service.main()`
- **File**: `backend/src/services/camera_stream_service.py:1016–1018`
- **Severity**: Critical
- **Description**: The standalone `main()` entry point calls `logging.basicConfig(level=logging.INFO, ...)` but `logging` is never imported in this module. The module uses a module-level `logger = logging.getLogger(...)` only within the scope of other imports that happen to bring logging in transitively — but the top-level import list (confirmed by `grep`) does not include `import logging`.
  ```python
  async def main():
      logging.basicConfig(          # NameError: name 'logging' is not defined
          level=logging.INFO,
  ```
- **Impact**: Running the camera service standalone (e.g., `python -m backend.src.services.camera_stream_service`) raises `NameError: name 'logging' is not defined` at startup before any camera work is done.
- **Suggested fix**: Add `import logging` to the module-level imports of `camera_stream_service.py`.

---

## High Severity

### BUG-004: Fire-and-Forget `create_task` for Job Execution — Exceptions Silently Lost
- **File**: `backend/src/services/jobs_service.py:93`
- **Severity**: High
- **Description**: `asyncio.create_task(self._execute_job(job))` stores no reference to the returned Task object. Python's asyncio garbage-collects tasks that have no references; a `Task` that completes with an unhandled exception logs a warning but does not propagate the error to any caller or monitoring surface. The job status will stay `RUNNING` indefinitely if `_execute_job` raises unexpectedly.
  ```python
  asyncio.create_task(self._execute_job(job))   # task handle discarded
  ```
- **Impact**: Silent mission failures. The mower can silently stop executing a job (blade off, motors halted) with no operator notification or state cleanup, leaving `job.status == RUNNING` as a ghost entry.
- **Suggested fix**: Store the task in a set, add a `task.add_done_callback` that removes it and logs/records any exception, and cancel it during service shutdown.

---

### BUG-005: Emergency Stop Returns `False` Without Attempting Safe State
- **File**: `backend/src/services/robohat_service.py:806–814`
- **Severity**: High
- **Description**: `emergency_stop()` returns `False` immediately when `self.serial_conn` is `None`, not open, or `self.running` is `False`. While this guards against sending commands to a closed connection, it means a caller that invokes `emergency_stop()` after a serial disconnect gets a failure response but **no neutral PWM is queued, no blade-off is scheduled, and no retry is attempted**. The mower may still be moving if the serial disconnect was transient.
- **Impact**: During a USB disconnect event coinciding with an obstacle detection trigger, the emergency stop path silently returns `False`. If the reconnect path then re-enables motor control, the mower resumes from whatever the last PWM command was.
- **Suggested fix**: On serial disconnect, immediately set `_last_pwm = (1500, 1500)` as the pending command so that on reconnect `_maintain_usb_control` sends neutral first. Log at `CRITICAL` level when e-stop is called but serial is unavailable. Consider a state flag `_pending_estop` that is flushed on next successful reconnect.

---

### BUG-006: `asyncio.create_task` Called from a Synchronous Signal Handler
- **File**: `backend/src/services/camera_stream_service.py:1022–1024`
- **Severity**: High
- **Description**: A POSIX signal handler (`SIGINT` / `SIGTERM`) calls `asyncio.create_task(camera_service.shutdown())`. Signal handlers in Python run in the main thread but are not guaranteed to run inside the asyncio event loop's execution context. Calling `asyncio.create_task()` from outside the running event loop raises `RuntimeError: no running event loop`.
  ```python
  def signal_handler(sig, frame):
      asyncio.create_task(camera_service.shutdown())   # unsafe from signal context
  ```
- **Impact**: Receiving SIGTERM (e.g., `systemctl stop lawnberry-camera`) will raise an unhandled `RuntimeError` in the signal handler, crash the process without a clean shutdown, and leave camera hardware resources unreleased.
- **Suggested fix**: Use `loop.call_soon_threadsafe(asyncio.ensure_future, camera_service.shutdown())` or, preferably, use `loop.add_signal_handler(signal.SIGTERM, shutdown_callback)` which integrates properly with the asyncio event loop.

---

### BUG-007: `Mission` / `MissionWaypoint` Not Imported — Type Annotations Are Unresolvable
- **File**: `backend/src/services/navigation_service.py:222,316,1402`
- **Severity**: High
- **Description**: `execute_mission(self, mission: "Mission")`, `go_to_waypoint(self, mission: "Mission", waypoint: "MissionWaypoint")`, and `are_waypoints_in_geofence(self, waypoints: List["MissionWaypoint"])` all use forward-reference strings. Ruff flags these as F821 undefined names. More critically, if `from __future__ import annotations` is added (which is in many sibling files) or if any tool calls `typing.get_type_hints()` on these methods, Python will try to resolve the strings against the module namespace and raise `NameError`. FastAPI's dependency injection can trigger this path.
- **Impact**: Adding `from __future__ import annotations` to the navigation service (consistent with the rest of the codebase) would break runtime signature introspection. Schema generation or Pydantic validation that walks these types would raise `NameError`.
- **Suggested fix**: Add `from .mission_service import Mission, MissionWaypoint` inside `TYPE_CHECKING` guard at the top of the file:
  ```python
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
      from .mission_service import Mission, MissionWaypoint
  ```

---

## Medium Severity

### BUG-008: Bare `except:` Swallows `KeyboardInterrupt` and `SystemExit`
- **File**: `backend/src/services/camera_stream_service.py:708`, `backend/src/services/telemetry_hub.py:296`
- **Severity**: Medium
- **Description**: Two bare `except:` clauses catch every possible exception including `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit`. This is flagged as `E722` by ruff. In `telemetry_hub.py` the bare except is in the WebSocket disconnect cleanup path; in `camera_stream_service.py` it is in a PIL font rendering fallback.
  ```python
  except:          # catches KeyboardInterrupt, SystemExit, etc.
      pass
  ```
- **Impact**: A `KeyboardInterrupt` during WebSocket disconnect cleanup would be silently swallowed, preventing graceful shutdown. During camera frame rendering in sim mode, any serious rendering error (e.g., OOM) would be hidden.
- **Suggested fix**: Change both to `except Exception:` to preserve standard Python interrupt/exit semantics.

---

### BUG-009: Default Operator Credential Hardcoded as `"operator123"`
- **File**: `backend/src/api/rest_v1.py:106`, `backend/src/api/routers/auth.py:351`, `backend/src/services/auth_service.py:169,176`
- **Severity**: Medium
- **Description**: Three independent places fall back to the literal string `"operator123"` when `LAWN_BERRY_OPERATOR_CREDENTIAL` is not set. This default will be used in production if the environment variable is omitted from the systemd unit or `.env` file.
- **Impact**: Any operator deployment that does not explicitly configure a credential is protected only by an open-source default that is trivially guessable from the public repository.
- **Suggested fix**: Change all three fallbacks to raise a `RuntimeError` (or `ValueError`) at startup when the env var is absent, so misconfigured deployments fail fast rather than silently accepting the default.

---

### BUG-010: F-String Without Placeholders in RoboHAT Error Logger
- **File**: `backend/src/services/robohat_service.py:299`
- **Severity**: Medium
- **Description**: `logger.error(f"Failed to send RoboHAT command line '%s': %s", line, exc)` uses an f-string (`f"..."`) but relies on `%s` positional args for the logging formatter. This is technically correct (the f-prefix is redundant; logging `%s` substitution still works), **but** if a future refactor converts it to f-string interpolation (`f"...{line}...{exc}"`) the `line` and `exc` arguments will become orphaned, changing the output silently.
- **Impact**: Misleading code; future refactors are likely to introduce a latent bug where the error context is dropped from log output.
- **Suggested fix**: Either remove the `f` prefix (`logger.error("Failed to send...%s: %s", line, exc)`) or convert to a proper f-string (`logger.error(f"Failed to send RoboHAT command line {line!r}: {exc}")`).

---

### BUG-011: `asyncio.create_task` in REST Audit Path Not Error-Checked
- **File**: `backend/src/api/rest.py:996–998`
- **Severity**: Medium
- **Description**: `asyncio.create_task(asyncio.to_thread(persistence.add_audit_log, ...))` discards the task reference. If `persistence.add_audit_log` raises (e.g., database locked on a Pi's SD card), the exception is silently swallowed after Python logs a `Task exception was never retrieved` warning.
- **Impact**: Drive-command audit logs are silently lost without any operator notification, undermining the audit trail relied upon for incident analysis.
- **Suggested fix**: Wrap in a helper that adds a `done_callback` to log exceptions, or use `asyncio.shield` with proper error handling.

---

### BUG-012: Tank-Turn Watchdog at 30 s May Allow Prolonged Uncontrolled Motion
- **File**: `backend/src/services/navigation_service.py:348,564`
- **Severity**: Medium
- **Description**: `_TANK_TURN_TIMEOUT_S = 30.0` means the mower will continue counter-rotating wheels for up to 30 seconds before the watchdog aborts the waypoint. During a 30-second tank turn at turn speed 0.5–1.0, the mower travels laterally at 0.5–1.5 m/s rotational — potentially well outside the intended mowing zone.
- **Impact**: On magnetometer EMI corruption (noted in the comments as a known hardware issue with the BNO085), the mower spins for 30 seconds in an unconstrained direction before stopping. This is a physical safety hazard.
- **Suggested fix**: Reduce `_TANK_TURN_TIMEOUT_S` to 8–10 seconds. A healthy in-place tank turn from 180° misalignment completes in under 3 seconds at 0.5 throttle. 30 seconds suggests the value was set conservatively for debugging but never tuned down for production.

---

## Low / Code Quality

### BUG-013: 72 Unused Imports (F401) Across Backend
- **Severity**: Low
- **Description**: `ruff --select F401` reports 72 unused imports across `backend/src/`. Key affected files include `backend/src/api/rest.py`, `backend/src/models/__init__.py`, `backend/src/api/routers/sensors.py`, and many drivers. Unused imports increase import time (meaningful on Pi 4), inflate memory footprint, and create confusion about actual dependencies.
- **Suggested fix**: Run `ruff check backend/src --select F401 --fix` to auto-remove them, then review the result for any that were intentional re-exports.

### BUG-014: 18 `raise` Without `from` Inside `except` Clauses (B904)
- **File**: Multiple files — `backend/src/api/rest_v1.py`, `backend/src/api/routers/auth.py`, `backend/src/api/routers/camera.py`, and others (see `ruff --select B904` output)
- **Severity**: Low
- **Description**: Exceptions raised inside `except` blocks without `raise ... from err` lose the original exception chain, making error tracing significantly harder.
- **Suggested fix**: Run `ruff check --select B904` to enumerate all 18 sites and add `from exc` or `from None` as appropriate.

### BUG-015: 7 Unused Variables (F841)
- **Severity**: Low
- **Description**: Seven local variables are assigned but never read. Most are in service files and likely represent leftover refactor artifacts. These can mask real logic errors where a result was intended to be used.
- **Suggested fix**: Run `ruff check --select F841` and either remove or act on the assigned values.

### BUG-016: 314 Lines Exceeding 101 Characters (E501)
- **Severity**: Low
- **Description**: 314 lines exceed the project line-length limit. Several span 150–200 characters, making code review in terminal environments difficult (relevant for Pi SSH sessions). These are in `navigation_service.py`, `camera_stream_service.py`, `rest.py`, and others.
- **Suggested fix**: Configure `ruff format` with `line-length = 100` (or the project standard) and run it.

### BUG-017: Deprecated `typing.List` / `typing.Optional` Usage (UP006, UP035, UP045)
- **Severity**: Low
- **Description**: 1,318+ occurrences of `from typing import List, Optional, ...` where modern Python 3.11 syntax (`list[...]`, `X | None`) should be used. This is a cosmetic and future-compatibility issue.
- **Suggested fix**: Run `ruff check backend/src --select UP --fix` to auto-migrate.

### BUG-018: 4 Redefined-While-Unused Symbols (F811)
- **Severity**: Low
- **Description**: Four symbols are re-imported or re-defined after an earlier definition, shadowing the first. In `backend/src/api/rest.py` the same import appears twice at line 647 (shadowing line 21). This can cause subtle behavior where later code uses the second definition unknowingly.
- **Suggested fix**: Remove duplicate imports.

### BUG-019: `rest_v1.py` In-Memory Stores Not Suitable for Any Persistence
- **Severity**: Low
- **Description**: `_zones_store: List[Zone] = []` and `_jobs_store: List[Job] = []` are module-level lists that are reset on every process restart. These back the v1 zone and job endpoints. There is a comment `# Storage (in-memory for now)` but no migration path or persistence adapter is wired.
- **Impact**: Every service restart loses all v1 zones and jobs. This is a silent data loss issue for any consumer of the v1 API.
- **Suggested fix**: Wire the existing `persistence` module into these stores or add a clear note in the API response that the v1 endpoint is ephemeral.

### BUG-020: `DEBUG` Comment Left in Navigation Hot Path
- **File**: `backend/src/services/navigation_service.py:490`
- **Severity**: Low
- **Description**: `# DEBUG: Log heading control every 2 seconds` marks an active rate-limited log that fires at `logger.debug(...)` on every navigation loop iteration (every ~0.1 s) and emits at INFO level every 2 s. In production with DEBUG log level enabled, this generates ~10 log lines/second from the navigation loop alone.
- **Suggested fix**: Remove the `# DEBUG:` comment tag and ensure the log level is correct (it appears to use `logger.debug` per the surrounding code, which is acceptable; verify it is not elevated to INFO).

---

## Linter Output Summary

```
Tool: ruff check backend/src
Total violations: 2,371
Auto-fixable:     1,824 (ruff --fix)

Top categories:
  UP045  766   Optional[X] → X | None
  UP006  552   List[X] → list[X]
  E501   314   line too long
  UP017  259   datetime.timezone.utc → UTC
  UP035  167   deprecated typing imports
  I001   110   import sort order
  F401    72   unused imports
  E402    39   module-level import not at top
  B904    18   raise without from in except
  B008    14   Depends/Query in default args (FastAPI pattern — expected)
  F841     7   unused variables
  F821     6   undefined names (3 real, 3 forward-ref false-positives)
  F811     4   redefined while unused
  E722     2   bare except
  F541     2   f-string without placeholders
```

`mypy` was **not available** in this environment (`/usr/bin/python: No module named mypy`). Full type-checking is recommended as a follow-up (`pip install mypy` and run against `backend/src`).

---

## Test Results

```
Test suite: tests/unit/ -m "not hardware"
Result: 1 FAILED, 281 passed, 1 skipped

FAILED: tests/unit/test_global_rate_limiter.py::test_rate_limiter_allows_burst_then_limits
  Expected HTTP 429 after burst of 3, received HTTP 200 on 4th request.
  Root cause: asyncio.Lock state not persisting correctly across TestClient requests.
  See BUG-002 above.
```

---

## Risk Summary — Top 3 Most Critical

| Rank | Bug | Why it matters |
|---|---|---|
| 1 | **BUG-001** `admin/admin` backdoor | Any network-reachable attacker gains full mower control. Motors, blade, and missions are all accessible. |
| 2 | **BUG-002** Rate limiter broken | DoS protection is completely ineffective. The failing test proves the middleware is not enforcing burst limits. |
| 3 | **BUG-003** `logging` undefined in `main()` | Camera service cannot start standalone. SIGTERM/SIGINT-triggered shutdown path (BUG-006) also references the same broken handler. |

---

*Generated by automated static analysis + manual review on 2026-04-22. Hardware-dependent code paths (sensor drivers, motor PWM, GPS serial) were reviewed for logic correctness but not executed against live hardware.*
