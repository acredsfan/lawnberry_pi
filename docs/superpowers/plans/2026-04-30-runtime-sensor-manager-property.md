# RuntimeContext.sensor_manager → Live-Reference Property

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `RuntimeContext.sensor_manager` from a snapshot dataclass field captured at lifespan startup (typically `None` because `AppState.sensor_manager` is lazy-initialized later by the telemetry loop) into a `@property` that always reads the current value of `AppState.get_instance().sensor_manager`.

**Architecture:** Drop `sensor_manager` from the dataclass field list, add a property that delegates to `AppState`. Drop the now-redundant `sensor_manager=` kwarg from all 6 call sites (1 production, 5 tests). Strengthen the lifespan integration test from "snapshot gap is acceptable" to "live identity must hold". Update `docs/runtime-context.md` to remove the landmine warning.

**Tech Stack:** Python `@dataclass` with a `@property` (not a field) for the delegated attribute. `AppState` singleton via `AppState.get_instance()`.

**Issue:** [#44](https://github.com/acredsfan/lawnberry/issues/44)

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `backend/src/core/runtime.py` | Modify | Remove `sensor_manager: Any` field; add `@property sensor_manager` delegating to AppState. |
| `backend/src/main.py` | Modify | Remove `sensor_manager=shared_state.sensor_manager` kwarg from `RuntimeContext(...)`; collapse the multi-paragraph TODO comment to one line referring to the docs. |
| `tests/unit/test_runtime_context.py` | Modify | Remove `sensor_manager` from `_make_runtime` defaults and `expected` set; add 3 new tests proving property semantics. |
| `tests/integration/test_safety_router_runtime.py` | Modify | Remove `sensor_manager` kwarg from `_make_runtime`. |
| `tests/integration/test_control_manual_flow.py` | Modify | Remove `sensor_manager` kwarg from fixture. |
| `tests/test_mission_api.py` | Modify | Remove `sensor_manager` kwarg from both fixture constructions. |
| `tests/integration/test_runtime_lifespan.py` | Modify | Replace "known snapshot gap" docstring + `hasattr` check with a positive identity assertion against `AppState.get_instance().sensor_manager`. |
| `docs/runtime-context.md` | Modify | Drop "Known caveat" section; update field table to show `sensor_manager` is a `@property` reading `AppState`; remove the "do not migrate" guidance. |

---

## Task 1: Branch setup

**Files:** none (git only)

- [ ] **Step 1: Restore stray test artifacts**

```bash
git restore data/lawnberry.db-shm data/lawnberry.db-wal
```

- [ ] **Step 2: Create feature branch**

```bash
git checkout -b feat/runtime-sensor-manager-property
git status
```

Expected: `On branch feat/runtime-sensor-manager-property`, working tree clean.

---

## Task 2: Add failing tests for property semantics

**Files:**
- Test: `tests/unit/test_runtime_context.py`

- [ ] **Step 1: Append the three new tests to the bottom of the file**

```python
def test_sensor_manager_is_a_property_not_a_dataclass_field():
    """Issue #44: sensor_manager must be a @property delegating to AppState,
    not a dataclass field captured as a snapshot at construction time."""
    from dataclasses import fields

    field_names = {f.name for f in fields(RuntimeContext)}
    assert "sensor_manager" not in field_names, (
        "sensor_manager is still a dataclass field; convert it to a @property"
    )
    assert isinstance(
        getattr(RuntimeContext, "sensor_manager", None), property
    ), "sensor_manager must be exposed as a @property on RuntimeContext"


def test_runtime_context_constructor_rejects_sensor_manager_kwarg():
    """Once converted to a property, the dataclass __init__ must not accept
    sensor_manager= — silent acceptance would mask call-site bugs."""
    with pytest.raises(TypeError):
        _make_runtime(sensor_manager=MagicMock())  # type: ignore[arg-type]


def test_runtime_sensor_manager_reads_live_from_appstate():
    """runtime.sensor_manager must reflect the current AppState value, not a
    snapshot taken at construction time. This is the entire point of #44."""
    from backend.src.core.state_manager import AppState

    app_state = AppState.get_instance()
    original = app_state.sensor_manager
    try:
        sentinel_a = object()
        app_state.sensor_manager = sentinel_a
        runtime = _make_runtime()
        assert runtime.sensor_manager is sentinel_a

        # Mutate AppState after runtime construction; live reads must follow.
        sentinel_b = object()
        app_state.sensor_manager = sentinel_b
        assert runtime.sensor_manager is sentinel_b
    finally:
        app_state.sensor_manager = original
```

- [ ] **Step 2: Run new tests, confirm RED**

```bash
SIM_MODE=1 uv run pytest tests/unit/test_runtime_context.py::test_sensor_manager_is_a_property_not_a_dataclass_field tests/unit/test_runtime_context.py::test_runtime_context_constructor_rejects_sensor_manager_kwarg tests/unit/test_runtime_context.py::test_runtime_sensor_manager_reads_live_from_appstate -v
```

Expected: all 3 fail (sensor_manager is currently a field; constructor accepts the kwarg; reads return the snapshot, not the live value).

---

## Task 3: Convert sensor_manager to a property

**Files:**
- Modify: `backend/src/core/runtime.py`

- [ ] **Step 1: Remove the `sensor_manager: Any` field and add the property**

Replace the dataclass body so the field list no longer includes `sensor_manager`, and add a property after the field list:

```python
@dataclass
class RuntimeContext:
    """References to the safety-critical services and shared state.

    Field types are intentionally `Any` for service slots to avoid import
    cycles with the service modules (NavigationService, MissionService, etc.).
    Tighten the types when we split those services into focused modules.

    `sensor_manager` is exposed as a property (not a field) because
    `AppState.sensor_manager` is lazy-initialized after lifespan startup
    completes — capturing it at construction time would freeze a `None`
    snapshot. See Issue #44 and docs/runtime-context.md.
    """

    config_loader: Any
    hardware_config: Any
    safety_limits: Any
    navigation: Any
    mission_service: Any
    safety_state: dict[str, Any]
    blade_state: dict[str, Any]
    robohat: Any
    websocket_hub: Any
    persistence: Any

    @property
    def sensor_manager(self) -> Any:
        # Local import: state_manager imports nothing from this module today,
        # but keep this lazy to stay defensive against future cycles.
        from .state_manager import AppState

        return AppState.get_instance().sensor_manager
```

- [ ] **Step 2: Run new property tests, confirm GREEN**

```bash
SIM_MODE=1 uv run pytest tests/unit/test_runtime_context.py::test_sensor_manager_is_a_property_not_a_dataclass_field tests/unit/test_runtime_context.py::test_runtime_context_constructor_rejects_sensor_manager_kwarg tests/unit/test_runtime_context.py::test_runtime_sensor_manager_reads_live_from_appstate -v
```

Expected: all 3 PASS.

- [ ] **Step 3: Run full test_runtime_context.py — confirm legacy tests are now RED**

```bash
SIM_MODE=1 uv run pytest tests/unit/test_runtime_context.py -v
```

Expected: legacy tests that pass `sensor_manager=` kwarg or expect it in `fields(RuntimeContext)` now fail. Those are fixed in Task 4.

---

## Task 4: Drop sensor_manager kwarg from all call sites

**Files:**
- Modify: `tests/unit/test_runtime_context.py`
- Modify: `tests/integration/test_safety_router_runtime.py`
- Modify: `tests/integration/test_control_manual_flow.py`
- Modify: `tests/test_mission_api.py`
- Modify: `backend/src/main.py`

- [ ] **Step 1: Update `tests/unit/test_runtime_context.py` `_make_runtime` defaults**

Remove the line:
```python
        "sensor_manager": MagicMock(name="sensor_manager"),
```
from the `defaults` dict in `_make_runtime`.

In `test_runtime_context_holds_all_required_fields`, remove `"sensor_manager",` from the `expected` set and from the `for name in expected` loop's coverage of dataclass fields. Leave a separate `assert hasattr(_make_runtime(), "sensor_manager")` after the field-set assertion to document that the property is still reachable.

Resulting block:
```python
def test_runtime_context_holds_all_required_fields():
    from dataclasses import fields

    expected = {
        "config_loader",
        "hardware_config",
        "safety_limits",
        "navigation",
        "mission_service",
        "safety_state",
        "blade_state",
        "robohat",
        "websocket_hub",
        "persistence",
    }
    actual = {f.name for f in fields(RuntimeContext)}
    assert actual == expected, f"field set drift: extra={actual-expected}, missing={expected-actual}"

    runtime = _make_runtime()
    for name in expected:
        assert hasattr(runtime, name)

    # sensor_manager is exposed as a @property (Issue #44), not a dataclass field.
    assert hasattr(runtime, "sensor_manager")
```

- [ ] **Step 2: Update `tests/integration/test_safety_router_runtime.py`**

Remove `"sensor_manager": MagicMock(name="sensor_manager"),` from the `defaults` dict in `_make_runtime`.

- [ ] **Step 3: Update `tests/integration/test_control_manual_flow.py`**

Remove the `sensor_manager=MagicMock(),` line from the `RuntimeContext(...)` call inside `_override_runtime_for_control_routes`.

- [ ] **Step 4: Update `tests/test_mission_api.py`** (two `RuntimeContext(...)` constructions)

Remove `sensor_manager=MagicMock(),` from both call sites (lines ~33 and ~152).

- [ ] **Step 5: Update `backend/src/main.py`**

Replace the multi-paragraph NOTE/TODO block (`# NOTE on sensor_manager:` through `# TODO(v3): convert sensor_manager to a live-reference property - Issue #44`) and the `sensor_manager=shared_state.sensor_manager,` line so the construction reads:

```python
    # Build the typed RuntimeContext once all services are up. This is
    # consumed by safety-critical routers via Depends(get_runtime).
    # See docs/superpowers/plans/2026-04-26-runtime-context.md.
    # `sensor_manager` is a property on RuntimeContext that reads AppState
    # live (Issue #44 / docs/runtime-context.md), so it is not passed here.
    from backend.src.core import globals as global_state
    from backend.src.core.persistence import persistence
    from backend.src.core.runtime import RuntimeContext
    from backend.src.services.robohat_service import get_robohat_service

    app.state.runtime = RuntimeContext(
        config_loader=loader,
        hardware_config=hardware_cfg,
        safety_limits=safety_limits,
        navigation=nav_service,
        mission_service=mission_service,
        safety_state=global_state._safety_state,
        blade_state=global_state._blade_state,
        robohat=get_robohat_service(),
        websocket_hub=websocket_hub,
        persistence=persistence,
    )
```

- [ ] **Step 6: Run all RuntimeContext-touching tests, confirm GREEN**

```bash
SIM_MODE=1 uv run pytest tests/unit/test_runtime_context.py tests/integration/test_safety_router_runtime.py tests/integration/test_control_manual_flow.py tests/test_mission_api.py tests/integration/test_runtime_lifespan.py -v
```

Expected: all pass (lifespan test uses `hasattr` and is still satisfied by the property; we strengthen it in Task 5).

---

## Task 5: Strengthen lifespan integration test

**Files:**
- Modify: `tests/integration/test_runtime_lifespan.py`

- [ ] **Step 1: Replace docstring + sensor_manager assertion block**

Replace the multi-line "sensor_manager: KNOWN GAP" portion of the docstring with:

```
    - sensor_manager: exposed as a @property on RuntimeContext that reads
      AppState.sensor_manager live (Issue #44). After lifespan startup, the
      telemetry loop lazy-initializes AppState.sensor_manager, so the live
      read may yield either None or a SensorManager instance — but it must
      reflect AppState's current value by identity, not a snapshot.
```

Replace the final `assert hasattr(runtime, "sensor_manager")` with:

```python
        # sensor_manager is now a live property delegating to AppState
        # (Issue #44). Identity must hold regardless of whether telemetry
        # has lazy-initialized it yet.
        from backend.src.core.state_manager import AppState

        assert runtime.sensor_manager is AppState.get_instance().sensor_manager
```

- [ ] **Step 2: Run the lifespan test, confirm GREEN**

```bash
SIM_MODE=1 uv run pytest tests/integration/test_runtime_lifespan.py -v
```

Expected: PASS.

---

## Task 6: Update docs/runtime-context.md

**Files:**
- Modify: `docs/runtime-context.md`

- [ ] **Step 1: Update the field table row**

Change the `sensor_manager` row in the table from:

```
| `sensor_manager`  | `SensorManager` snapshot                  | `AppState.sensor_manager` (see caveat below)  |
```

to:

```
| `sensor_manager`  | Live `SensorManager` (or `None`) via property | `AppState.sensor_manager` (read on every access) |
```

- [ ] **Step 2: Replace the "Known caveat" section**

Delete the entire `### Known caveat: sensor_manager is a snapshot, not a live reference` subsection (heading + body) and replace with:

```markdown
### `sensor_manager` is a property, not a stored field

`AppState.sensor_manager` is `None` at lifespan startup and lazy-initialized
later by the telemetry loop. To avoid freezing a `None` snapshot at
RuntimeContext construction, `sensor_manager` is exposed as a `@property`
that reads `AppState.get_instance().sensor_manager` on every access. Routers
that need live sensor access can read `runtime.sensor_manager` directly.
Resolved in Issue #44.
```

- [ ] **Step 3: Update the "Testing against it" example**

Remove the `sensor_manager=MagicMock(),` line from the `RuntimeContext(...)` call in the doctest-style example block.

---

## Task 7: Verification

**Files:** none (verification only)

- [ ] **Step 1: Restore any pytest side-effect files**

```bash
git checkout -- data/lawnberry.db-shm data/lawnberry.db-wal config/default.json 2>/dev/null || true
git status
```

- [ ] **Step 2: Full test suite**

```bash
SIM_MODE=1 uv run pytest -q
```

Expected: ≈619 passed, 47 skipped, 11 xfailed, 3 xpassed (counts from the handoff baseline; ±2 variance acceptable). **Zero failures.**

- [ ] **Step 3: Lint scope**

```bash
uv run ruff check backend/src
```

Expected: clean (no new violations).

- [ ] **Step 4: Re-restore artifacts before staging**

```bash
git checkout -- data/lawnberry.db-shm data/lawnberry.db-wal config/default.json 2>/dev/null || true
git status
```

Expected staged-eligible diff: `backend/src/core/runtime.py`, `backend/src/main.py`, `docs/runtime-context.md`, `docs/superpowers/plans/2026-04-30-runtime-sensor-manager-property.md`, the 5 test files.

---

## Task 8: Commit, push, open PR

**Files:** none (git only)

- [ ] **Step 1: Commit**

```bash
git add backend/src/core/runtime.py backend/src/main.py docs/runtime-context.md docs/superpowers/plans/2026-04-30-runtime-sensor-manager-property.md tests/unit/test_runtime_context.py tests/integration/test_runtime_lifespan.py tests/integration/test_safety_router_runtime.py tests/integration/test_control_manual_flow.py tests/test_mission_api.py
git commit -m "$(cat <<'EOF'
fix(runtime): expose sensor_manager as live property delegating to AppState

Closes #44. RuntimeContext.sensor_manager was captured as a snapshot at
lifespan-startup time, when AppState.sensor_manager is still None (telemetry
loop initializes it lazily). Convert to a @property that reads
AppState.get_instance().sensor_manager on every access so the live value
is always returned. Drop the now-meaningless sensor_manager= kwarg from
all 5 call sites and strengthen the lifespan integration test from a
hasattr check to an identity check against AppState.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feat/runtime-sensor-manager-property
gh pr create --title "fix(runtime): expose sensor_manager as live property (Issue #44)" --body "$(cat <<'EOF'
## Summary
- Convert `RuntimeContext.sensor_manager` from a snapshot dataclass field (captured at lifespan startup, almost always `None`) to a `@property` delegating to `AppState.get_instance().sensor_manager` — closes #44.
- Drop the now-meaningless `sensor_manager=` kwarg from all 5 call sites (1 production, 4 test).
- Strengthen `test_runtime_lifespan.py` from a `hasattr` check to an identity assertion against the AppState singleton.
- Remove the "Known caveat" landmine warning from `docs/runtime-context.md`.

Plan: [docs/superpowers/plans/2026-04-30-runtime-sensor-manager-property.md](docs/superpowers/plans/2026-04-30-runtime-sensor-manager-property.md)

## Test plan
- [ ] `SIM_MODE=1 uv run pytest -q` matches baseline (≈619 passed, 0 failed)
- [ ] `uv run ruff check backend/src` clean
- [ ] New unit tests assert: not a dataclass field, IS a property, constructor rejects `sensor_manager=` kwarg, reads track AppState mutations
- [ ] Lifespan integration test asserts identity with `AppState.get_instance().sensor_manager`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

---

## Self-Review Notes

- **Spec coverage:** The handoff identifies one deliverable (#44 sensor_manager → property). All 8 tasks roll up to that. No spec gaps.
- **Property collision:** `@dataclass` permits `@property` definitions for names not in the field list. Tested mentally — this is the standard Python pattern.
- **Singleton leakage:** `AppState._instance` persists across tests. The new live-read test snapshots and restores `app_state.sensor_manager` in a `try/finally` to avoid leaking a sentinel into other tests.
- **No new public API surface:** This is a behavior change only; no router migration, no new endpoints. Routers that want to read `runtime.sensor_manager` will start getting live values, but there are zero current callers (verified via grep).
