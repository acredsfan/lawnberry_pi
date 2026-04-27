# RuntimeContext Implementation Plan (§1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a typed `RuntimeContext` injected via FastAPI's `Depends` so safety-critical routers stop importing module-level globals and singletons by name. The context is a thin façade that captures references to existing services; nothing is copied or replaced. Implements §1 of `docs/major-architecture-and-code-improvement-plan.md`.

**Architecture:**

A `@dataclass` named `RuntimeContext` aggregates references to existing objects: `config_loader`, `hardware_config`, `safety_limits`, `sensor_manager`, `navigation`, `mission_service`, `safety_state`, `blade_state`, `robohat`, `websocket_hub`, `persistence`. The fields are *references* to the same objects in `core/globals.py`, `core/state_manager.AppState`, and the various `get_*` factories — so the runtime view and the legacy view stay synchronized for the duration of the process.

Construction happens once near the end of `main.py`'s lifespan startup, after all services are initialized. The runtime is stored on `app.state.runtime`, and a FastAPI dependency `get_runtime(request: Request) -> RuntimeContext` reads it back. Routers convert from `from .. import _safety_state` to `runtime: RuntimeContext = Depends(get_runtime)` and access state via `runtime.safety_state`.

The migration scope is deliberately narrow: only `safety.py` (which has the worst global-mutation pain) and `mission.py` (which already uses `Depends` and just needs its dependency seam adjusted). `navigation.py` and `telemetry.py` aren't touched in this plan because they don't mutate shared state in ways that hurt today, and gratuitous migration risks regressions on user-facing endpoints. `rest.py`'s 29 global usages are the natural seam for the §4 motor command gateway and stay out of scope here.

Tests use `app.dependency_overrides[get_runtime]` to inject fake contexts, mirroring the existing `get_mission_service` pattern in `tests/test_mission_api.py:29-33`.

**Tech Stack:** Python 3.11, FastAPI, `@dataclasses.dataclass`, pytest, pytest-asyncio. No new dependencies.

**Out of scope for this plan:**

- Removing `AppState` (architecture plan §1 explicitly defers; remains alongside RuntimeContext indefinitely).
- Migrating `rest.py` drive/emergency endpoints (those align with §4 motor command gateway).
- Migrating `motors.py` (stateless, no benefit).
- Migrating `navigation.py` and `telemetry.py` (no current pain; risk > benefit until a real refactor reaches them).
- Replacing module-level `websocket_hub` / `persistence` / `telemetry_service` singletons with constructor injection (the runtime just *holds references* to them).
- Refactoring `RoboHATService.get_robohat_service()` factory (stays as-is; runtime stores the result).
- Frontend changes (none needed).

---

## File Structure

**Created:**

- `backend/src/core/runtime.py` — `RuntimeContext` dataclass + `get_runtime()` FastAPI dependency. ≤90 lines.
- `tests/unit/test_runtime_context.py` — dataclass shape + dependency wiring tests.
- `tests/integration/test_safety_router_runtime.py` — safety endpoints work via injected runtime, not direct imports.

**Modified:**

- `backend/src/main.py` — construct `RuntimeContext` at end of lifespan startup; assign to `app.state.runtime`; log a one-line inventory.
- `backend/src/api/safety.py` — replace `from .rest import _blade_state, _client_emergency, _safety_state` with `runtime: RuntimeContext = Depends(get_runtime)` and access via runtime fields. Body of each endpoint mutates `runtime.safety_state` / `runtime.blade_state` (which are the same dict objects as the globals — no behavior change, just cleaner accessor).
- `backend/src/api/mission.py` — change `Depends(get_mission_service)` to `Depends(get_runtime)` then read `runtime.mission_service`. Cosmetic seam shift; behavior identical. (Keeps `get_mission_service` factory available for legacy callers.)
- `tests/conftest.py` — add cleanup for `app.state.runtime` references and document the `app.dependency_overrides[get_runtime]` pattern.

---

## Pre-flight

The implementer must have:

- A working SIM_MODE Python environment for this repo. Run `cd /home/pi/lawnberry/.worktrees/feat-runtime-context && SIM_MODE=1 .venv/bin/pytest tests/unit/test_diagnostics_capture.py -v` and confirm 7 tests pass — that proves the worktree is correctly set up.
- The current branch checked out: `feat/runtime-context` (worktree at `.worktrees/feat-runtime-context`).
- `pytest`, `pytest-asyncio`, `httpx` installed (already in dev deps).

If running tests fails with `ModuleNotFoundError: backend`, the project root must be on `sys.path` — `tests/conftest.py:28-32` adds it automatically when invoked as `pytest` from the repo root.

---

### Task 1: Add `RuntimeContext` dataclass and `get_runtime` dependency

**Files:**
- Create: `backend/src/core/runtime.py`
- Test: `tests/unit/test_runtime_context.py`

**Why:** The shape of the runtime context is the contract that lets routers (and tests) treat dependency-injected services uniformly. A small dataclass with named fields plus a single `get_runtime` factory is the minimum that satisfies §1's acceptance criteria. Everything else in this plan is migration to use this contract.

**Design notes:**

- `RuntimeContext` is a plain `@dataclass`, not a Pydantic model. It captures *references* (not values) to live services. Pydantic validation would copy or coerce, which we do not want.
- Each field is typed with `Any` where the concrete service class would create circular imports (e.g. `NavigationService`, `MissionService`, `RoboHATService`). The runtime's job is to expose a uniform handle — type tightening can come later when we split modules.
- The dependency function reads `request.app.state.runtime` and raises `RuntimeError` if startup hasn't run. That's loud-on-misuse and fast-fail at first request.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_runtime_context.py` with this exact content:

```python
"""Unit tests for RuntimeContext and get_runtime."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.src.core.runtime import RuntimeContext, get_runtime


def _make_runtime(**overrides: Any) -> RuntimeContext:
    """Build a RuntimeContext where every field is a sentinel MagicMock unless overridden."""
    defaults: dict[str, Any] = {
        "config_loader": MagicMock(name="config_loader"),
        "hardware_config": MagicMock(name="hardware_config"),
        "safety_limits": MagicMock(name="safety_limits"),
        "sensor_manager": MagicMock(name="sensor_manager"),
        "navigation": MagicMock(name="navigation"),
        "mission_service": MagicMock(name="mission_service"),
        "safety_state": {"emergency_stop_active": False, "estop_reason": None},
        "blade_state": {"active": False},
        "robohat": MagicMock(name="robohat"),
        "websocket_hub": MagicMock(name="websocket_hub"),
        "persistence": MagicMock(name="persistence"),
    }
    defaults.update(overrides)
    return RuntimeContext(**defaults)


def test_runtime_context_holds_all_required_fields():
    runtime = _make_runtime()
    # Each field is reachable by name; we don't validate types beyond presence.
    for field_name in (
        "config_loader",
        "hardware_config",
        "safety_limits",
        "sensor_manager",
        "navigation",
        "mission_service",
        "safety_state",
        "blade_state",
        "robohat",
        "websocket_hub",
        "persistence",
    ):
        assert hasattr(runtime, field_name), f"missing field: {field_name}"


def test_runtime_context_safety_state_is_a_live_reference():
    """Mutations to runtime.safety_state must propagate (it's the same dict, not a copy)."""
    shared = {"emergency_stop_active": False}
    runtime = _make_runtime(safety_state=shared)
    runtime.safety_state["emergency_stop_active"] = True
    assert shared["emergency_stop_active"] is True


def test_get_runtime_returns_app_state_runtime():
    app = FastAPI()
    app.state.runtime = _make_runtime()

    @app.get("/probe")
    def probe(runtime: RuntimeContext = pytest.importorskip("fastapi").Depends(get_runtime)):
        return {"has_navigation": runtime.navigation is not None}

    with TestClient(app) as client:
        response = client.get("/probe")
        assert response.status_code == 200
        assert response.json() == {"has_navigation": True}


def test_get_runtime_raises_runtime_error_when_not_initialized():
    app = FastAPI()
    # Deliberately do NOT set app.state.runtime.

    @app.get("/probe")
    def probe(runtime: RuntimeContext = pytest.importorskip("fastapi").Depends(get_runtime)):
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/probe")
        # FastAPI surfaces dependency errors as 500.
        assert response.status_code == 500


def test_dependency_override_replaces_get_runtime():
    """Tests inject fake runtimes via app.dependency_overrides — the canonical pattern."""
    app = FastAPI()
    app.state.runtime = _make_runtime()

    @app.get("/probe")
    def probe(runtime: RuntimeContext = pytest.importorskip("fastapi").Depends(get_runtime)):
        return {"nav_kind": type(runtime.navigation).__name__}

    fake_runtime = _make_runtime(navigation="not-a-mock")
    app.dependency_overrides[get_runtime] = lambda: fake_runtime
    try:
        with TestClient(app) as client:
            response = client.get("/probe")
            assert response.status_code == 200
            assert response.json() == {"nav_kind": "str"}
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/pi/lawnberry/.worktrees/feat-runtime-context && SIM_MODE=1 .venv/bin/pytest tests/unit/test_runtime_context.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.src.core.runtime'`.

- [ ] **Step 3: Create `backend/src/core/runtime.py`**

Create `backend/src/core/runtime.py` with this exact content:

```python
"""Typed RuntimeContext for safety-critical FastAPI routers.

The context aggregates references to existing services and shared state so
routers can declare a single `Depends(get_runtime)` parameter instead of
importing module-level globals or calling `.get_instance()` chains.

The fields are *references*, not copies. `runtime.safety_state` is the same
dict object as `backend.src.core.globals._safety_state`, so mutations from
either side are visible through both. This keeps the legacy code path
working unchanged while we migrate routers piecemeal.

Construction happens in the FastAPI lifespan; see `backend/src/main.py`. The
context is stored on `app.state.runtime` and read back via `get_runtime`.

Out of scope here: removing AppState, migrating rest.py drive/emergency
endpoints (those align with the §4 motor command gateway), or replacing
module-level singletons. See docs/major-architecture-and-code-improvement-plan.md
for the larger picture.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request


@dataclass
class RuntimeContext:
    """References to the safety-critical services and shared state.

    Field types are intentionally `Any` for service slots to avoid import
    cycles with the service modules (NavigationService, MissionService, etc.).
    Tighten the types when we split those services into focused modules.
    """

    config_loader: Any
    hardware_config: Any
    safety_limits: Any
    sensor_manager: Any
    navigation: Any
    mission_service: Any
    safety_state: dict[str, Any]
    blade_state: dict[str, Any]
    robohat: Any
    websocket_hub: Any
    persistence: Any


def get_runtime(request: Request) -> RuntimeContext:
    """FastAPI dependency. Returns the RuntimeContext built at lifespan startup.

    Raises RuntimeError if startup has not run — that's a real bug and we want
    it to surface loudly on the first request rather than producing None
    references that crash deeper in the call stack.
    """
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise RuntimeError(
            "RuntimeContext not initialized; lifespan startup did not run "
            "or did not assign app.state.runtime"
        )
    return runtime


__all__ = ["RuntimeContext", "get_runtime"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `SIM_MODE=1 .venv/bin/pytest tests/unit/test_runtime_context.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/src/core/runtime.py tests/unit/test_runtime_context.py
git commit -m "feat(runtime): add RuntimeContext dataclass and get_runtime dependency"
```

---

### Task 2: Wire `RuntimeContext` in `main.py` lifespan

**Files:**
- Modify: `backend/src/main.py`
- Test: `tests/integration/test_runtime_lifespan.py`

**Why:** Without lifespan wiring, the dependency raises and no router can use it. Construction happens once, at the end of startup, after every dependency it captures has been initialized. We also log a concise inventory line so operators can confirm the runtime is healthy at boot.

**Edit location:** Insertion goes immediately before `yield` at the end of the lifespan startup block. As of `87894c3`, that's around `backend/src/main.py:182-183` — verify with:

```bash
grep -n "^    yield" backend/src/main.py
```

If the line number has shifted significantly OR there is more than one `yield` inside `lifespan`, **STOP and report NEEDS_CONTEXT** — do not guess.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_runtime_lifespan.py` with this exact content:

```python
"""Integration test: lifespan startup populates app.state.runtime."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.src.core.runtime import RuntimeContext


def test_lifespan_startup_assigns_runtime_to_app_state():
    """After app startup runs, app.state.runtime is a populated RuntimeContext."""
    from backend.src.main import app

    with TestClient(app) as _client:
        runtime = getattr(app.state, "runtime", None)
        assert runtime is not None, "lifespan did not assign app.state.runtime"
        assert isinstance(runtime, RuntimeContext)
        # Sanity checks on key fields.
        assert runtime.navigation is not None
        assert runtime.mission_service is not None
        assert runtime.websocket_hub is not None
        assert runtime.persistence is not None
        # safety_state and blade_state must be the live globals dicts.
        from backend.src.core import globals as global_state

        assert runtime.safety_state is global_state._safety_state
        assert runtime.blade_state is global_state._blade_state
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SIM_MODE=1 .venv/bin/pytest tests/integration/test_runtime_lifespan.py -v`
Expected: FAIL — `assert runtime is not None` (lifespan hasn't been wired yet).

- [ ] **Step 3: Edit `main.py` to construct the runtime at lifespan startup**

Locate the line containing `yield` inside the `lifespan` async context manager (around line 183). Immediately **before** that `yield`, insert this block:

```python
        # Build the typed RuntimeContext once all services are up. This is
        # consumed by safety-critical routers via Depends(get_runtime).
        # See docs/superpowers/plans/2026-04-26-runtime-context.md.
        from backend.src.core import globals as global_state
        from backend.src.core.persistence import persistence
        from backend.src.core.runtime import RuntimeContext
        from backend.src.services.robohat_service import get_robohat_service

        app.state.runtime = RuntimeContext(
            config_loader=loader,
            hardware_config=hardware_cfg,
            safety_limits=safety_limits,
            sensor_manager=shared_state.sensor_manager,
            navigation=nav_service,
            mission_service=mission_service,
            safety_state=global_state._safety_state,
            blade_state=global_state._blade_state,
            robohat=get_robohat_service(),
            websocket_hub=websocket_hub,
            persistence=persistence,
        )
        _log.info(
            "RuntimeContext ready: navigation=%s mission=%s robohat=%s",
            type(app.state.runtime.navigation).__name__,
            type(app.state.runtime.mission_service).__name__,
            type(app.state.runtime.robohat).__name__ if app.state.runtime.robohat else "none",
        )
```

Notes:
- `loader`, `hardware_cfg`, `safety_limits`, `shared_state`, `nav_service`, `mission_service` are all already in scope at that point (see lines 86-172).
- The local imports inside the lifespan body match the existing late-import pattern used elsewhere in `main.py` and avoid module-load-time cycles.
- `get_robohat_service()` returns `None` if RoboHAT init was skipped (e.g., SIM_MODE without serial); the runtime is still valid in that case and downstream callers handle `runtime.robohat is None`.

Verify your edit with:

```bash
cd /home/pi/lawnberry/.worktrees/feat-runtime-context
grep -n "app.state.runtime = RuntimeContext" backend/src/main.py
```

Expected: one match, located immediately before the `yield` at the end of lifespan startup.

- [ ] **Step 4: Run integration test**

Run: `SIM_MODE=1 .venv/bin/pytest tests/integration/test_runtime_lifespan.py -v`
Expected: PASS — 1 test.

- [ ] **Step 5: Run unit + integration tests for runtime to confirm no regression**

Run: `SIM_MODE=1 .venv/bin/pytest tests/unit/test_runtime_context.py tests/integration/test_runtime_lifespan.py tests/integration/test_main_capture_wiring.py -v`
Expected: 6 tests pass total (5 unit + 1 lifespan; capture wiring still passes).

- [ ] **Step 6: Commit**

```bash
git add backend/src/main.py tests/integration/test_runtime_lifespan.py
git commit -m "feat(runtime): construct RuntimeContext in lifespan startup"
```

---

### Task 3: Add conftest cleanup for `app.state.runtime`

**Files:**
- Modify: `tests/conftest.py`

**Why:** Tests that import `backend.src.main.app` reuse the same FastAPI instance across tests. If one test sets `app.dependency_overrides[get_runtime]` and forgets to clear it, every subsequent test runs against the override. The same trap exists for `app.state.runtime` itself.

The autouse `reset_control_safety_state` fixture in conftest already resets shared state for each test. We extend it to also clear `app.dependency_overrides` and `app.state.runtime` between tests, which prevents cross-test leakage of injected fakes.

- [ ] **Step 1: Read the fixture's current shape**

Run: `grep -n "def reset_control_safety_state\|def isolate_ui_settings_storage\|app.dependency_overrides" tests/conftest.py`

Expected: see the `reset_control_safety_state` autouse fixture around line 103-200, and confirm `app.dependency_overrides` is not currently mentioned anywhere in conftest.

- [ ] **Step 2: Append a new autouse fixture after the existing ones**

At the end of `tests/conftest.py`, append:

```python


@pytest.fixture(autouse=True)
def reset_app_state_runtime_and_overrides():
    """Reset app.state.runtime and dependency_overrides between tests.

    Without this, a test that sets app.dependency_overrides[get_runtime] = ...
    leaks the override into every subsequent test in the session. Same for
    app.state.runtime if a test mutates it.
    """
    try:
        from backend.src.main import app
    except Exception:
        # If main.py fails to import (e.g. during very early collection), the
        # other reset fixtures will surface that; this one is a no-op.
        yield
        return

    yield

    try:
        app.dependency_overrides.clear()
    except Exception:
        pass
    # Do NOT clear app.state.runtime — lifespan rebuilds it on the next
    # TestClient startup, but if a test ran without TestClient (just imports
    # `app`), there is nothing to rebuild and clearing here would just hide
    # bugs.
```

- [ ] **Step 3: Run a representative slice of tests to confirm the fixture doesn't break anything**

Run:

```bash
SIM_MODE=1 .venv/bin/pytest tests/unit/test_runtime_context.py \
                              tests/integration/test_runtime_lifespan.py \
                              tests/integration/test_main_capture_wiring.py \
                              tests/test_mission_api.py -q
```

Expected: all pass (the existing `test_mission_api.py` tests confirm the dependency_overrides clearing doesn't conflict with their own fixture-managed override patterns).

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test(runtime): clear dependency_overrides between tests to prevent leakage"
```

---

### Task 4: Migrate `safety.py` to use `RuntimeContext`

**Files:**
- Modify: `backend/src/api/safety.py`
- Test: `tests/integration/test_safety_router_runtime.py`

**Why:** `safety.py` is the strongest case for migration — it currently does `from .rest import _blade_state, _client_emergency, _safety_state` (creating a soft circular dependency on `rest.py`) and mutates those globals directly across multiple endpoints. Migrating it removes that import, isolates state ownership, and gives us a working test for `Depends(get_runtime)`.

The behavioral contract is: every `_safety_state[...] = ...` becomes `runtime.safety_state[...] = ...`. Same dict object, same mutation, same observable effect. The only thing that changes is *how the router gets a handle to the dict*.

`_client_emergency` in `safety.py` reads from `rest._client_emergency`. That's a per-client TTL map. Since we're not migrating `rest.py` in this plan, we keep the import for `_client_emergency` only — the runtime field would have to mirror it and double the source of truth, which is worse than the current state. Note this in a comment so it's clear the partial migration is deliberate.

- [ ] **Step 1: Read current `safety.py` to understand the endpoints**

Run: `cat backend/src/api/safety.py`

Confirm structure:
- `from .rest import _blade_state, _client_emergency, _safety_state` near top.
- Endpoints `clear_emergency_stop()` and any others that mutate `_safety_state` or `_blade_state`.
- Any helpers that read these globals.

- [ ] **Step 2: Write the failing integration test**

Create `tests/integration/test_safety_router_runtime.py` with this exact content:

```python
"""Integration test: safety router endpoints work via injected RuntimeContext."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.src.core.runtime import RuntimeContext, get_runtime


def _make_runtime(**overrides: Any) -> RuntimeContext:
    defaults: dict[str, Any] = {
        "config_loader": MagicMock(name="config_loader"),
        "hardware_config": MagicMock(name="hardware_config"),
        "safety_limits": MagicMock(name="safety_limits"),
        "sensor_manager": MagicMock(name="sensor_manager"),
        "navigation": MagicMock(name="navigation"),
        "mission_service": MagicMock(name="mission_service"),
        "safety_state": {"emergency_stop_active": True, "estop_reason": "test"},
        "blade_state": {"active": True},
        "robohat": MagicMock(name="robohat"),
        "websocket_hub": MagicMock(name="websocket_hub"),
        "persistence": MagicMock(name="persistence"),
    }
    defaults.update(overrides)
    return RuntimeContext(**defaults)


def test_clear_emergency_stop_resets_safety_state_via_runtime():
    """Calling the clear-emergency-stop endpoint mutates runtime.safety_state."""
    from backend.src.main import app

    fake_runtime = _make_runtime()
    app.dependency_overrides[get_runtime] = lambda: fake_runtime
    try:
        with TestClient(app) as client:
            # Sanity: starts with emergency latched on the fake runtime.
            assert fake_runtime.safety_state["emergency_stop_active"] is True
            response = client.post("/api/v2/safety/emergency-stop/clear")
            assert response.status_code in (200, 204), (
                f"unexpected status: {response.status_code} body={response.text}"
            )
            assert fake_runtime.safety_state["emergency_stop_active"] is False
            assert fake_runtime.blade_state["active"] is False
    finally:
        app.dependency_overrides.clear()


def test_safety_endpoints_do_not_import_globals_from_rest():
    """Regression guard: safety.py must not depend on rest.py for state."""
    from backend.src.api import safety

    src = safety.__file__
    text = open(src).read()
    # The migration removes _blade_state and _safety_state imports from rest.
    # _client_emergency import remains by design (see plan §4 deferral note).
    assert "_blade_state" not in text or "from .rest import _blade_state" not in text, (
        "safety.py still imports _blade_state from rest.py"
    )
    assert "from .rest import _safety_state" not in text, (
        "safety.py still imports _safety_state from rest.py"
    )
```

Note: The exact endpoint path (`/api/v2/safety/emergency-stop/clear`) needs to be verified against the existing safety router. If the path is different, adjust the test before running. Use:

```bash
grep -n "@router\.\|router = APIRouter" backend/src/api/safety.py
```

to confirm the route prefix and path.

- [ ] **Step 3: Run test to verify it fails**

Run: `SIM_MODE=1 .venv/bin/pytest tests/integration/test_safety_router_runtime.py -v`
Expected: FAIL — likely on the second test asserting that `_blade_state` is no longer imported (the file still imports it). The first test may also fail depending on whether the current handler reads the global directly (which would not see our injected runtime).

- [ ] **Step 4: Migrate `safety.py`**

Replace the imports and modify each endpoint. Open `backend/src/api/safety.py` and:

1. **Remove** the line `from .rest import _blade_state, _client_emergency, _safety_state`.
2. **Add** these imports:
   ```python
   from fastapi import Depends

   from ..core.runtime import RuntimeContext, get_runtime
   ```
3. **Keep** the `_client_emergency` reference — but now import it fresh inline:
   ```python
   from .rest import _client_emergency  # noqa: PLC0415  # cross-module map; see §4 motor gateway
   ```
   (Or accept the unused import warning; this map is mutated by rest.py and read here. It will be unified under §4.)
4. **For every endpoint** in `safety.py`, add `runtime: RuntimeContext = Depends(get_runtime)` to the signature.
5. **Replace** every `_safety_state[...]` with `runtime.safety_state[...]` and every `_blade_state[...]` with `runtime.blade_state[...]`.

For the `clear_emergency_stop` endpoint specifically, the body should look like:

```python
async def clear_emergency_stop(
    runtime: RuntimeContext = Depends(get_runtime),
) -> dict[str, Any]:
    """Clear the latched emergency stop and reset blade state."""
    runtime.safety_state["emergency_stop_active"] = False
    runtime.safety_state["estop_reason"] = None
    runtime.blade_state["active"] = False
    # _client_emergency is mutated from rest.py; we leave it untouched here
    # until §4 motor command gateway unifies emergency state ownership.
    return {"status": "cleared"}
```

(Adapt to whatever the existing function signature and return shape are. The point is: signature gets `runtime: RuntimeContext = Depends(get_runtime)` added; body uses `runtime.<field>` instead of bare globals.)

- [ ] **Step 5: Run the safety router test**

Run: `SIM_MODE=1 .venv/bin/pytest tests/integration/test_safety_router_runtime.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 6: Run the existing safety/contract tests for regression check**

Run:

```bash
SIM_MODE=1 .venv/bin/pytest tests/contract/test_rest_api_control.py tests/integration/test_runtime_lifespan.py -v
```

Expected: same pass/skip/xfail counts as before this task. No new failures. (Some `test_rest_api_control.py` tests are `xfail` on main; they should remain `xfail`, not become `XPASS` or `FAIL`.)

- [ ] **Step 7: Commit**

```bash
git add backend/src/api/safety.py tests/integration/test_safety_router_runtime.py
git commit -m "feat(safety): migrate safety router to RuntimeContext via Depends(get_runtime)"
```

---

### Task 5: Refactor `mission.py` to use `RuntimeContext`

**Files:**
- Modify: `backend/src/api/mission.py`
- Test: extend `tests/test_mission_api.py` (add one regression test)

**Why:** `mission.py` already uses dependency injection — it has `Depends(get_mission_service)` on every endpoint (lines 29, 42, 55, 68, 81, 94, 106 per the explorer report). Migrating to `Depends(get_runtime)` is a seam shift, not a structural change: each endpoint goes from "give me a MissionService" to "give me the runtime, which contains a MissionService." Behavior is identical.

We do this migration for consistency: once two routers (safety + mission) use `RuntimeContext`, the pattern is established and §4's motor gateway has a clear template. We also keep `get_mission_service` as a public factory for any legacy importer.

- [ ] **Step 1: Read current `mission.py` and `test_mission_api.py`**

Run:

```bash
grep -n "Depends\|get_mission_service" backend/src/api/mission.py | head -10
grep -n "dependency_overrides\|get_mission_service" tests/test_mission_api.py | head -10
```

Confirm: 7 endpoints use `Depends(get_mission_service)`; the test file overrides `get_mission_service` via `app.dependency_overrides`.

- [ ] **Step 2: Write the regression-prevention test**

Append to `tests/test_mission_api.py` (do not replace existing tests):

```python


def test_mission_endpoints_resolve_via_runtime_dependency():
    """Confirm mission endpoints accept the runtime override path.

    After migration to Depends(get_runtime), tests can either override
    get_runtime (preferred) or continue overriding get_mission_service
    (legacy path). This test confirms the runtime path works.
    """
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from backend.src.core.runtime import RuntimeContext, get_runtime
    from backend.src.main import app

    mock_mission = MagicMock()
    mock_mission.list_missions.return_value = []

    fake_runtime = RuntimeContext(
        config_loader=MagicMock(),
        hardware_config=MagicMock(),
        safety_limits=MagicMock(),
        sensor_manager=MagicMock(),
        navigation=MagicMock(),
        mission_service=mock_mission,
        safety_state={},
        blade_state={},
        robohat=MagicMock(),
        websocket_hub=MagicMock(),
        persistence=MagicMock(),
    )

    app.dependency_overrides[get_runtime] = lambda: fake_runtime
    try:
        with TestClient(app) as client:
            response = client.get("/api/v2/mission")
            # 200 with empty list, or 401 if auth gate is enforced — either
            # confirms we reached the handler via the runtime path.
            assert response.status_code in (200, 401), (
                f"status={response.status_code} body={response.text}"
            )
    finally:
        app.dependency_overrides.clear()
```

Adjust the path `/api/v2/mission` to match whatever the actual list endpoint is — look it up via the `grep -n "@router" backend/src/api/mission.py` output from Step 1.

- [ ] **Step 3: Run the test to verify it fails**

Run: `SIM_MODE=1 .venv/bin/pytest tests/test_mission_api.py::test_mission_endpoints_resolve_via_runtime_dependency -v`

Expected: FAIL — the endpoints still use `Depends(get_mission_service)`, so overriding `get_runtime` does nothing.

- [ ] **Step 4: Migrate `mission.py`**

In `backend/src/api/mission.py`:

1. **Add** these imports at the top alongside the existing FastAPI imports:
   ```python
   from ..core.runtime import RuntimeContext, get_runtime
   ```
2. **For every endpoint**, replace the parameter `mission_service: MissionService = Depends(get_mission_service)` with:
   ```python
   runtime: RuntimeContext = Depends(get_runtime)
   ```
3. **Inside each endpoint body**, replace usages of the `mission_service` parameter with `runtime.mission_service`. (Or: rebind locally on the first line: `mission_service = runtime.mission_service`. The latter minimizes diff and keeps the rest of each function unchanged.)

The minimum-diff form for each endpoint becomes:

```python
@router.get("/...")
async def list_missions(runtime: RuntimeContext = Depends(get_runtime), ...):
    mission_service = runtime.mission_service
    # ... existing body unchanged ...
```

- [ ] **Step 5: Run the mission test suite**

Run: `SIM_MODE=1 .venv/bin/pytest tests/test_mission_api.py -v`

Expected: PASS — both the new test and all existing mission tests. The pre-existing `app.dependency_overrides[get_mission_service]` pattern from `tests/test_mission_api.py:29-33` should still work because `get_mission_service` is still a defined factory; the override just doesn't take effect for endpoints that now use `get_runtime`. If the existing tests fail, switch their override to `app.dependency_overrides[get_runtime] = lambda: _make_runtime(mission_service=mock_mission_service)`.

- [ ] **Step 6: Run the broader regression check**

Run:

```bash
SIM_MODE=1 .venv/bin/pytest tests/integration/test_runtime_lifespan.py \
                              tests/integration/test_safety_router_runtime.py \
                              tests/test_mission_api.py \
                              tests/integration/test_main_capture_wiring.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/api/mission.py tests/test_mission_api.py
git commit -m "feat(mission): migrate mission router to RuntimeContext via Depends(get_runtime)"
```

---

### Task 6: End-to-end verification, documentation, and PR

**Files:**
- Create: `docs/runtime-context.md`
- Modify: `AGENTS.md`

**Why:** Capture the contract operators and developers need to know — what the runtime contains, how to use it from a router, how to test against it — and link it from the project map.

- [ ] **Step 1: Run the full diagnostics + runtime test set**

Run:

```bash
SIM_MODE=1 .venv/bin/pytest tests/unit/test_runtime_context.py \
                              tests/integration/test_runtime_lifespan.py \
                              tests/integration/test_safety_router_runtime.py \
                              tests/test_mission_api.py \
                              tests/integration/test_main_capture_wiring.py \
                              tests/unit/test_diagnostics_capture.py \
                              tests/unit/test_diagnostics_replay.py \
                              tests/unit/test_navigation_service_capture.py \
                              tests/integration/test_navigation_replay.py -v
```

Expected: all PASS. Specifically: 5 + 1 + 2 + (existing mission tests + 1 new) + 3 + 7 + 5 + 3 + 1 = at least 28 tests pass.

- [ ] **Step 2: Run the broader regression suite**

Run: `SIM_MODE=1 LBY_ACCEL=cpu .venv/bin/pytest --tb=no -rxX -q 2>&1 | tail -3`

Expected: same `passed / xfailed / xpassed / skipped` counts as on `main` before this branch (no new failures). The 13 existing `xfail` markers should remain `xfail` or `xpass` — never become hard `FAIL`.

- [ ] **Step 3: Create `docs/runtime-context.md`**

Create `docs/runtime-context.md` with this exact content:

````markdown
# Runtime Context

The `RuntimeContext` (`backend/src/core/runtime.py`) is the typed dependency
that safety-critical FastAPI routers receive instead of importing module-level
globals or calling `.get_instance()` chains. It implements §1 of the
architecture plan.

## Shape

`RuntimeContext` is a `@dataclass` with these fields:

| Field             | What it is                                   | Source                                        |
| ----------------- | -------------------------------------------- | --------------------------------------------- |
| `config_loader`   | The `ConfigLoader` singleton                 | `backend/src/core/config_loader.py`           |
| `hardware_config` | Loaded `HardwareConfig`                      | YAML via `ConfigLoader().get()`               |
| `safety_limits`   | Loaded `SafetyLimits`                        | YAML via `ConfigLoader().get()`               |
| `sensor_manager`  | Active `SensorManager`                       | `AppState.sensor_manager`                     |
| `navigation`      | `NavigationService` singleton                | `NavigationService.get_instance()`            |
| `mission_service` | `MissionService` instance                    | `get_mission_service(...)`                    |
| `safety_state`    | Live emergency-stop dict                     | `core/globals._safety_state` (same dict)      |
| `blade_state`     | Live blade-active dict                       | `core/globals._blade_state` (same dict)       |
| `robohat`         | `RoboHATService` or None                     | `get_robohat_service()`                       |
| `websocket_hub`   | `WebSocketHub` module-level singleton        | `services/websocket_hub.websocket_hub`        |
| `persistence`     | `PersistenceLayer` module-level singleton    | `core/persistence.persistence`                |

The fields are *references*, not copies. Mutations to `runtime.safety_state`
propagate to `core/globals._safety_state` and vice versa, because they're the
same dict object. This lets new and legacy code paths coexist without
diverging.

## Using it from a router

```python
from fastapi import APIRouter, Depends

from ..core.runtime import RuntimeContext, get_runtime

router = APIRouter()


@router.post("/example")
async def example(runtime: RuntimeContext = Depends(get_runtime)):
    # Read or mutate state via the runtime, never via direct global imports.
    if runtime.safety_state["emergency_stop_active"]:
        return {"refused": True, "reason": runtime.safety_state.get("estop_reason")}
    return {"ok": True}
```

## Testing against it

Tests inject fakes via `app.dependency_overrides`:

```python
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend.src.core.runtime import RuntimeContext, get_runtime
from backend.src.main import app


def test_example():
    fake = RuntimeContext(
        config_loader=MagicMock(),
        hardware_config=MagicMock(),
        safety_limits=MagicMock(),
        sensor_manager=MagicMock(),
        navigation=MagicMock(),
        mission_service=MagicMock(),
        safety_state={"emergency_stop_active": False, "estop_reason": None},
        blade_state={"active": False},
        robohat=MagicMock(),
        websocket_hub=MagicMock(),
        persistence=MagicMock(),
    )
    app.dependency_overrides[get_runtime] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post("/api/v2/example")
            assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
```

`tests/conftest.py` clears `app.dependency_overrides` after every test, so
forgotten overrides don't leak between tests.

## What's NOT in the runtime

These are intentionally still accessed via their existing pathways:

- `AppState` / `get_robot_state_manager()` — legacy state holder; remains for
  routers that haven't been migrated. Will be removed when all consumers
  switch to the runtime, which is a multi-phase undertaking outside §1.
- `auth_service.primary_auth_service` — auth flow has its own factory that
  predates this work.
- `TractionControlService.get_instance()` — owned by the motor command
  gateway (§4); will be folded into the runtime there.
- `_client_emergency` (per-client TTL map) — still imported from `rest.py` by
  `safety.py`; will be unified under §4.

## What scope was migrated in §1

Only `safety.py` and `mission.py` migrated to `Depends(get_runtime)`.
`navigation.py` and `telemetry.py` were not migrated because they don't have
ownership-confusion pain today; gratuitous churn there risks regressions on
user-facing endpoints. `rest.py`'s drive/emergency endpoints stay on globals
until §4 (motor command gateway) lands — that's the natural seam.
````

- [ ] **Step 4: Add a one-line pointer in `AGENTS.md`**

Open `AGENTS.md`. Find the "## Repository Map" section (or the `docs/` references near it). Add this single line at a sensible spot:

```markdown
- `docs/runtime-context.md` documents the typed `RuntimeContext` injected via FastAPI's `Depends(get_runtime)` for safety-critical routers.
```

- [ ] **Step 5: Commit docs**

```bash
git add docs/runtime-context.md AGENTS.md
git commit -m "docs(runtime): operator/developer guide for RuntimeContext"
```

- [ ] **Step 6: Push the branch**

```bash
git push -u origin feat/runtime-context
```

- [ ] **Step 7: Open the PR**

```bash
gh pr create --title "feat: typed RuntimeContext for safety-critical routers (§1)" --body "$(cat <<'EOF'
## Summary

Implements §1 of \`docs/major-architecture-and-code-improvement-plan.md\`. Adds a typed \`RuntimeContext\` dataclass injected via FastAPI's \`Depends(get_runtime)\` so safety-critical routers stop importing module-level globals by name. The context is a thin façade — fields are *references* to existing services and dicts, not copies — so legacy code paths and new code paths see the same state.

## What this delivers

- \`backend/src/core/runtime.py\`: \`RuntimeContext\` dataclass + \`get_runtime\` FastAPI dependency.
- \`backend/src/main.py\`: builds the runtime once at end of lifespan startup, stores on \`app.state.runtime\`, logs an inventory line.
- \`backend/src/api/safety.py\`: migrated to \`Depends(get_runtime)\`; no longer imports \`_blade_state\` / \`_safety_state\` from \`rest.py\`.
- \`backend/src/api/mission.py\`: migrated from \`Depends(get_mission_service)\` to \`Depends(get_runtime)\`; \`get_mission_service\` factory remains for any legacy importer.
- \`tests/conftest.py\`: clears \`app.dependency_overrides\` between tests.
- \`docs/runtime-context.md\`: developer guide.

## Migration scope

Deliberately narrow: only \`safety.py\` and \`mission.py\`. \`navigation.py\` and \`telemetry.py\` aren't touched because they don't have pain to solve today, and gratuitous migration risks regressions. \`rest.py\`'s 29 global usages are the natural seam for the §4 motor command gateway and stay out of scope here.

\`AppState\` is unchanged and remains the way legacy routers access shared state. The architecture plan explicitly defers its removal indefinitely.

## Test plan

- [x] Unit tests for the dataclass shape and \`get_runtime\` dependency (5 tests).
- [x] Integration test confirming lifespan startup populates \`app.state.runtime\`.
- [x] Integration test confirming \`safety.py\` mutates state through the injected runtime.
- [x] Existing \`test_mission_api.py\` continues to pass after the seam shift.
- [x] Replay-harness tests, capture wiring tests, and the broader regression suite show no new failures.

## Known limitations / interim choices

- \`safety.py\` still imports \`_client_emergency\` from \`rest.py\` because that per-client TTL map is mutated from both files; unifying it requires §4. Documented in code comment.
- \`navigation.py\` and \`telemetry.py\` keep their existing access patterns; migration deferred until concrete pain or §4 reaches them.
- \`rest.py\` drive/emergency endpoints stay on direct globals — §4 territory.

## Follow-up items (non-blocking)

- Tighten \`RuntimeContext\` field types from \`Any\` to concrete service classes once those services are split into focused modules (Phase 2).
- Migrate \`rest.py\` drive/emergency to runtime when §4 lands.
- Move \`_client_emergency\` into the runtime when §4 unifies emergency state ownership.
- Eventually retire \`AppState\` — but only when all consumers have migrated.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

---

## Self-review checklist

The plan author has run this checklist; the implementer should verify briefly before starting.

- **Spec coverage:** Every acceptance criterion in §1 of `docs/major-architecture-and-code-improvement-plan.md` maps to a task:
  - "Tests can create an isolated `RuntimeContext` for safety-critical paths without resetting module globals." → Task 1 (`_make_runtime` helper, dependency_overrides test) + Task 3 (conftest cleanup).
  - "`NavigationService.get_instance()` is no longer used by new code in scope." → Tasks 4 and 5 (safety + mission converted to runtime; new code reads `runtime.navigation`).
  - "Safety state has one authoritative owner." → Task 4 (safety state mutated via runtime; runtime.safety_state IS the global dict).
  - "Backend startup logs a concise inventory of the runtime context services." → Task 2 (`_log.info("RuntimeContext ready: ...")`).
- **Placeholder scan:** No "TBD", every code step has a code block, every command has expected output.
- **Type consistency:** `RuntimeContext`, `get_runtime`, `runtime.safety_state`, `runtime.blade_state`, `runtime.mission_service`, `runtime.navigation`, `runtime.robohat` are spelled identically across all tasks.
- **TDD discipline:** Every implementation task starts with a failing test (verified by running and seeing the failure) before writing code.
- **Frequent commits:** 6 commits, one per task, each independently revertable.

## Known limitations of this plan

- **`navigation.py` and `telemetry.py` remain unmigrated** by design. They don't currently exhibit ownership confusion that the runtime would solve, and they serve user-facing endpoints. Migrating them is busy-work with regression risk.
- **`rest.py` is unchanged.** Its 29 global usages will land with §4 (motor command gateway).
- **`safety.py` keeps a `_client_emergency` import from `rest.py`.** That per-client TTL map is bidirectionally mutated; unifying it without breaking the cross-module mutation pattern needs §4's gateway as the central owner.
- **Field types in `RuntimeContext` are `Any`.** Concrete types would create import cycles today. Tighten them when services are split (Phase 2).
