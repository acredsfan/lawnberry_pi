# Phase 2 — Architecture Refactoring & Code Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate circular dependencies, push mission status over WebSocket, fix optimistic frontend mutations, singleton-ify ConfigLoader, and modernize code style.

**Architecture:** Five independent refactoring groups, each ending with full test suite run and commit. Phase 2 is safe to defer past immediate mowing operations but produces cleaner, more maintainable code. Execute Phase 1 fully before starting Phase 2.

**Tech Stack:** Python 3.11, TypeScript, FastAPI, asyncio, Pinia, WebSocket, ruff, Protocol

**Source:** `docs/superpowers/specs/2026-04-22-bug-and-arch-remediation-design.md` (Phase 2 section)

**Prerequisite:** Phase 1 complete (`docs/superpowers/plans/2026-04-22-phase1-bug-fixes-reliability.md`)

---

## Task 1: ARCH-002 — Break MissionService ↔ NavigationService Circular Dependency

**Files:**
- Create: `backend/src/protocols/__init__.py`
- Create: `backend/src/protocols/mission.py`
- Modify: `backend/src/services/navigation_service.py`
- Test: `tests/unit/test_navigation_service.py`

### Context

`NavigationService` uses deferred imports inside method bodies to avoid a circular import:
```python
from .mission_service import get_mission_service      # line 224, 318
mission_service = get_mission_service()
```
The fix is a `MissionStatusReader` Protocol that `NavigationService` depends on structurally
rather than concretely. `MissionService` satisfies the protocol without changes.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_navigation_service.py`:

```python
def test_navigation_service_accepts_mission_status_reader_protocol():
    """NavigationService must accept any object satisfying MissionStatusReader, not MissionService."""
    from backend.src.protocols.mission import MissionStatusReader
    from unittest.mock import AsyncMock

    class FakeMissionService:
        async def update_waypoint_progress(self, mission_id: str, waypoint_index: int) -> None:
            pass
        async def mark_mission_complete(self, mission_id: str) -> None:
            pass
        async def mark_mission_failed(self, mission_id: str, reason: str) -> None:
            pass
        # Extra attribute not in protocol — protocol is structural, this is fine
        mission_statuses: dict = {}

    fake = FakeMissionService()
    # If this import works, the protocol module exists
    from backend.src.protocols.mission import MissionStatusReader
    # Protocol structural check (runtime)
    assert isinstance(fake, MissionStatusReader)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/pi/lawnberry && python -m pytest tests/unit/test_navigation_service.py::test_navigation_service_accepts_mission_status_reader_protocol -xvs -m "not hardware"
```
Expected: `ModuleNotFoundError: backend.src.protocols.mission`

- [ ] **Step 3: Create the protocols package**

Create `backend/src/protocols/__init__.py` (empty):
```python
```

Create `backend/src/protocols/mission.py`:

```python
"""Protocols for mission–navigation boundary.

Using a structural Protocol breaks the circular import between
MissionService and NavigationService without requiring any changes
to MissionService's implementation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MissionStatusReader(Protocol):
    """Minimal interface NavigationService needs from MissionService."""

    mission_statuses: dict  # read-only access to status dict

    async def update_waypoint_progress(
        self, mission_id: str, waypoint_index: int
    ) -> None: ...

    async def mark_mission_complete(self, mission_id: str) -> None: ...

    async def mark_mission_failed(self, mission_id: str, reason: str) -> None: ...
```

- [ ] **Step 4: Run test to verify protocol exists**

```bash
python -m pytest tests/unit/test_navigation_service.py::test_navigation_service_accepts_mission_status_reader_protocol -xvs -m "not hardware"
```
Expected: `PASSED`

- [ ] **Step 5: Update NavigationService to use the protocol**

In `backend/src/services/navigation_service.py`:

1. Add the protocol import under `TYPE_CHECKING`:
```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..protocols.mission import MissionStatusReader
```

2. Find all deferred `from .mission_service import get_mission_service` calls inside method bodies (lines ~224 and ~318). Replace each one.

For line ~224 (inside `execute_mission`), the current pattern is:
```python
from .mission_service import get_mission_service
mission_service = get_mission_service()
```

The caller of `execute_mission` is the mission service itself. Since navigation already receives `mission_service` as a parameter in `execute_mission(mission, mission_service)`, no deferred import is needed — the object is passed in. Verify the method signature:

```bash
grep -n "def execute_mission\|async def execute_mission" backend/src/services/navigation_service.py
```

If `mission_service` is already a parameter, remove the deferred import. If not, check exactly how it's obtained and refactor so it is always passed as `MissionStatusReader` from the caller (which is `MissionService` itself).

For any type annotation that previously referenced `MissionService`, change to `"MissionStatusReader"` (string to use TYPE_CHECKING guard):
```python
async def execute_mission(
    self, mission: "Mission", mission_service: "MissionStatusReader"
) -> None:
```

- [ ] **Step 6: Verify no circular import remains**

```bash
cd /home/pi/lawnberry
python -c "from backend.src.services.navigation_service import NavigationService; print('OK')"
python -c "from backend.src.services.mission_service import MissionService; print('OK')"
```
Expected: both print `OK` with no ImportError

- [ ] **Step 7: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add backend/src/protocols/ backend/src/services/navigation_service.py \
        tests/unit/test_navigation_service.py
git commit -m "refactor(arch): break mission-navigation circular dependency (ARCH-002)

Add MissionStatusReader Protocol in backend/src/protocols/mission.py.
NavigationService now depends on the Protocol, not MissionService.
MissionService satisfies the protocol structurally without changes.
Remove deferred imports from navigation_service method bodies.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: ARCH-007 — Mission Status WebSocket Push

**Files:**
- Modify: `backend/src/services/mission_service.py`
- Modify: `frontend/src/stores/mission.ts`
- Test: `tests/unit/test_navigation_service.py` (mission lifecycle integration)

### Context

Mission status is polled every 2 seconds from the frontend. This creates unnecessary HTTP load
and introduces up to 2 s of status lag. The fix: emit `mission.status` WebSocket events after
each lifecycle transition. Keep HTTP poll as a 30s reconciliation fallback.

- [ ] **Step 1: Write failing backend test**

Add to `tests/unit/test_job_state_machine.py` (or new `tests/unit/test_mission_ws_push.py`):

```python
@pytest.mark.asyncio
async def test_mission_start_broadcasts_status_event():
    """MissionService.start_mission must emit mission.status WS event."""
    from backend.src.services.mission_service import MissionService
    from unittest.mock import AsyncMock, MagicMock

    mock_hub = MagicMock()
    mock_hub.broadcast_to_topic = AsyncMock()

    svc = MissionService(websocket_hub=mock_hub)
    mission = await svc.create_mission("Test Mission", [])
    await svc.start_mission(mission.id)

    mock_hub.broadcast_to_topic.assert_called()
    call_topics = [c.args[0] for c in mock_hub.broadcast_to_topic.call_args_list]
    assert "mission.status" in call_topics


@pytest.mark.asyncio
async def test_mission_abort_broadcasts_status_event():
    """MissionService.abort_mission must emit mission.status WS event."""
    from backend.src.services.mission_service import MissionService
    from unittest.mock import AsyncMock, MagicMock

    mock_hub = MagicMock()
    mock_hub.broadcast_to_topic = AsyncMock()

    svc = MissionService(websocket_hub=mock_hub)
    mission = await svc.create_mission("Test Mission", [])
    await svc.start_mission(mission.id)
    await svc.abort_mission(mission.id)

    topics = [c.args[0] for c in mock_hub.broadcast_to_topic.call_args_list]
    assert topics.count("mission.status") >= 2  # one for start, one for abort
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/unit/test_mission_ws_push.py -xvs -m "not hardware" 2>/dev/null || \
python -m pytest tests/unit/test_job_state_machine.py::test_mission_start_broadcasts_status_event -xvs -m "not hardware"
```
Expected: `TypeError: __init__() got unexpected keyword argument 'websocket_hub'`

- [ ] **Step 3: Inject WebSocketHub into MissionService**

In `backend/src/services/mission_service.py`:

1. Add TYPE_CHECKING import at top:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .websocket_hub import WebSocketHub
```

2. Find `MissionService.__init__` and add hub parameter:
```python
def __init__(self, websocket_hub: "WebSocketHub | None" = None) -> None:
    # ...existing init...
    self._websocket_hub = websocket_hub
```

3. Add private helper method:
```python
async def _broadcast_status(self, mission_id: str, detail: str = "") -> None:
    """Emit mission.status event over WebSocket to all subscribers."""
    if self._websocket_hub is None:
        return
    status = self.mission_statuses.get(mission_id)
    if status is None:
        return
    try:
        await self._websocket_hub.broadcast_to_topic(
            "mission.status",
            {
                "mission_id": mission_id,
                "status": status.status,
                "progress_pct": getattr(status, "progress_pct", 0),
                "detail": detail,
            },
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to broadcast mission status: %s", exc)
```

4. Call `await self._broadcast_status(mission_id, ...)` at the end of:
   - `start_mission()` — detail: `"Mission started"`
   - `pause_mission()` — detail: `"Mission paused"`
   - `resume_mission()` — detail: `"Mission resumed"`
   - `abort_mission()` — detail: `"Mission aborted"`
   - Any `_complete_mission()` or `mark_complete` equivalent — detail: `"Mission completed"`

5. Update `get_mission_service()` to pass the hub (update the factory function or rely on DI from main.py):

In `backend/src/main.py`, when `MissionService` is constructed or its singleton is initialized, pass `websocket_hub`:
```python
# Find where mission_service is first constructed; pass the hub:
from .services.websocket_hub import websocket_hub as _ws_hub
from .services.mission_service import get_mission_service
_mission_svc = get_mission_service(websocket_hub=_ws_hub)
```

Update `get_mission_service()` in `mission_service.py` to accept and store the hub:
```python
_mission_service_instance: MissionService | None = None

def get_mission_service(websocket_hub: "WebSocketHub | None" = None) -> MissionService:
    global _mission_service_instance
    if _mission_service_instance is None:
        _mission_service_instance = MissionService(websocket_hub=websocket_hub)
    return _mission_service_instance
```

- [ ] **Step 4: Run backend tests**

```bash
python -m pytest tests/unit/ -k "mission" -xvs -m "not hardware"
```
Expected: new tests pass; existing mission tests pass

- [ ] **Step 5: Update frontend mission store to subscribe to WebSocket topic**

In `frontend/src/stores/mission.ts`:

1. Import the WebSocket store (or composable already used in the project):
```bash
grep -n "useWebSocket\|wsStore\|websocket" frontend/src/stores/mission.ts | head -10
```

Find the existing WebSocket connection pattern and add subscription to `mission.status` on connect.

2. After the existing `pollMissionStatus` polling setup, add WebSocket subscription:

```typescript
// Add near the top of the store, with other reactive state:
const wsUnsubscribe = ref<(() => void) | null>(null);

// Add this function:
const subscribeToMissionStatusWS = () => {
  // Find the existing WS send/subscribe mechanism used in this codebase
  // Typical pattern (check actual ws composable):
  const ws = useWebSocketStore(); // or however WS is accessed
  ws.subscribe('mission.status', (payload: any) => {
    if (!currentMission.value || payload.mission_id !== currentMission.value.id) return;
    missionStatus.value = payload.status;
    if (payload.progress_pct !== undefined) {
      missionProgress.value = payload.progress_pct;
    }
    if (payload.detail) {
      statusDetail.value = payload.detail;
    }
    if (['completed', 'aborted', 'failed'].includes(payload.status)) {
      stopStatusPolling();
    }
  });
};
```

3. Extend the polling interval from 2000 ms to 30000 ms (WS push is now primary):
```typescript
// Find: setInterval(pollMissionStatus, 2000)
// Change to:
setInterval(pollMissionStatus, 30000)
```

4. Call `subscribeToMissionStatusWS()` when a mission starts.

**Note:** The exact WebSocket API depends on the composable used elsewhere in the frontend. Before editing, run:
```bash
grep -rn "subscribe\|on_message\|wsStore\|useWs" frontend/src/stores/ frontend/src/composables/ | head -20
```
Follow the existing pattern rather than inventing a new one.

- [ ] **Step 6: Run full backend test suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/src/services/mission_service.py backend/src/main.py \
        frontend/src/stores/mission.ts tests/unit/
git commit -m "feat(mission): WebSocket push for mission status events (ARCH-007)

MissionService emits mission.status WS events after each lifecycle
transition (start/pause/resume/abort/complete). Frontend subscribes
to mission.status topic and updates store reactively. HTTP poll
interval extended from 2s to 30s as reconciliation fallback.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: ARCH-008 — Fix Optimistic Frontend Mutations

**Files:**
- Modify: `frontend/src/stores/mission.ts`
- Test: Manual browser test (no unit test framework for Pinia stores in this project)

### Context

The current store mutates state BEFORE the HTTP request completes:
```typescript
await apiService.post(`/api/v2/missions/${id}/pause`, {});
missionStatus.value = 'paused';  // BUG: set before confirming success
```
If the API call fails, the UI shows "paused" while the backend is still running.

- [ ] **Step 1: Fix `pauseCurrentMission`**

In `frontend/src/stores/mission.ts`, change the existing:
```typescript
const pauseCurrentMission = async () => {
  if (!currentMission.value) return;
    await apiService.post(`/api/v2/missions/${currentMission.value.id}/pause`, {});
    missionStatus.value = 'paused';
    // ...
};
```
To (mutation only on success):
```typescript
const pauseCurrentMission = async () => {
  if (!currentMission.value) return;
  try {
    await apiService.post(`/api/v2/missions/${currentMission.value.id}/pause`, {});
    // Only mutate state after confirmed success:
    missionStatus.value = 'paused';
    statusDetail.value = 'Mission paused';
  } catch (error) {
    console.error('Error pausing mission:', error);
    statusDetail.value = extractMissionErrorMessage(error, 'Unable to pause mission.');
    // Do NOT change missionStatus — keep previous value
    throw error;
  }
};
```

- [ ] **Step 2: Fix `resumeCurrentMission`**

```typescript
const resumeCurrentMission = async () => {
  if (!currentMission.value) return;
  try {
    await apiService.post(`/api/v2/missions/${currentMission.value.id}/resume`, {});
    missionStatus.value = 'running';
    statusDetail.value = 'Mission resumed';
  } catch (error) {
    console.error('Error resuming mission:', error);
    statusDetail.value = extractMissionErrorMessage(error, 'Unable to resume mission.');
    throw error;
  }
};
```

- [ ] **Step 3: Verify `abortCurrentMission` is already correct**

```bash
sed -n '174,194p' frontend/src/stores/mission.ts
```

`abortCurrentMission` already has `try/catch` and only mutates after success. If it mutates before the `await`, apply the same fix as above.

- [ ] **Step 4: Verify `startCurrentMission` is correct**

```bash
grep -A 15 "startCurrentMission\|startMission" frontend/src/stores/mission.ts | head -20
```

Ensure `missionStatus.value = 'running'` only appears after the `await apiService.post(...)` line.

- [ ] **Step 5: Run frontend lint**

```bash
cd /home/pi/lawnberry && npm --prefix frontend run lint 2>/dev/null || cd frontend && npx eslint src/stores/mission.ts
```
Expected: no new errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stores/mission.ts
git commit -m "fix(frontend): optimistic mutations only on HTTP success (ARCH-008)

pauseCurrentMission and resumeCurrentMission previously set missionStatus
before the HTTP response was confirmed. Now state is only mutated after
the API call succeeds. On failure, statusDetail shows the error and
missionStatus retains its previous value.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: ARCH-009 — ConfigLoader Singleton

**Files:**
- Modify: `backend/src/core/config_loader.py`
- Modify: `backend/src/services/robohat_service.py`
- Modify: `backend/src/main.py`
- Test: `tests/unit/test_config_loader.py`

### Context

`RoboHATService.__init__` creates a new `ConfigLoader()` instance on every construction:
```python
from backend.src.core.config_loader import ConfigLoader
hw, _ = ConfigLoader().get()
```
This re-reads YAML from disk each time. The fix: a module-level `get_config_loader()` singleton
that caches the parsed config and is primed once at startup.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_config_loader.py`:

```python
def test_get_config_loader_returns_same_instance():
    """get_config_loader() must return the same object on every call."""
    from backend.src.core import config_loader as _mod
    # Reset singleton for test isolation
    _mod._config_loader_instance = None

    loader1 = _mod.get_config_loader()
    loader2 = _mod.get_config_loader()

    assert loader1 is loader2, "get_config_loader() must return a singleton"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/unit/test_config_loader.py::test_get_config_loader_returns_same_instance -xvs -m "not hardware"
```
Expected: `AttributeError: module 'backend.src.core.config_loader' has no attribute 'get_config_loader'`

- [ ] **Step 3: Add singleton to config_loader.py**

In `backend/src/core/config_loader.py`, add at module level after the `ConfigLoader` class:

```python
import threading as _threading

_config_loader_instance: "ConfigLoader | None" = None
_config_loader_lock = _threading.Lock()


def get_config_loader() -> "ConfigLoader":
    """Return the module-level singleton ConfigLoader, creating it on first call."""
    global _config_loader_instance
    if _config_loader_instance is None:
        with _config_loader_lock:
            if _config_loader_instance is None:
                _config_loader_instance = ConfigLoader()
    return _config_loader_instance
```

- [ ] **Step 4: Update RoboHATService to use the singleton**

In `backend/src/services/robohat_service.py`, find the deferred `ConfigLoader()` call:
```python
from backend.src.core.config_loader import ConfigLoader
hw, _ = ConfigLoader().get()
```

Replace with:
```python
from backend.src.core.config_loader import get_config_loader
hw, _ = get_config_loader().get()
```

- [ ] **Step 5: Prime the singleton in main.py lifespan**

In `backend/src/main.py`, at the top of the lifespan startup block (before services start):
```python
from .core.config_loader import get_config_loader as _get_cfg
_get_cfg()  # prime the singleton cache once at startup
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/unit/test_config_loader.py -xvs -m "not hardware"
```
Expected: all pass (including new singleton test)

- [ ] **Step 7: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add backend/src/core/config_loader.py backend/src/services/robohat_service.py \
        backend/src/main.py tests/unit/test_config_loader.py
git commit -m "refactor(config): ConfigLoader singleton via get_config_loader() (ARCH-009)

Add module-level get_config_loader() that creates ConfigLoader once
and returns the same instance on every call (thread-safe double-checked
locking). RoboHATService now calls get_config_loader() instead of
ConfigLoader() on each construction. Singleton primed in main.py lifespan.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: Code Modernization — ruff format, UP typing, v1 annotation

**Files:**
- All of `backend/src/` (ruff automated changes)
- Modify: `backend/src/api/rest_v1.py` (deprecation annotation, BUG-019)

**⚠️ Warning:** This task generates a large diff (~1300+ lines changed by ruff UP). Review the
diff carefully before committing to catch any unexpected changes. Run the full test suite after
each sub-step.

### 5a: Format — long line normalization (BUG-016)

- [ ] **Step 5a-1: Run ruff format (dry-run first)**

```bash
cd /home/pi/lawnberry
ruff format --line-length 100 --diff backend/src/ | head -80
```

Review the diff: only whitespace/line-break changes expected. No logic changes.

- [ ] **Step 5a-2: Apply format**

```bash
ruff format --line-length 100 backend/src/
```

- [ ] **Step 5a-3: Run test suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 5a-4: Commit format pass**

```bash
git add backend/src/
git commit -m "style: ruff format --line-length 100 backend/src/ (BUG-016)

Normalize 314 long lines to max 100 chars. Automated whitespace-only
changes; no logic changes.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### 5b: Typing modernization — replace old-style annotations (BUG-017)

- [ ] **Step 5b-1: Run UP fix in dry-run mode**

```bash
ruff check backend/src --select UP --diff | head -100
```

Expect `Optional[X]` → `X | None`, `Dict[K,V]` → `dict[K,V]`, `List[T]` → `list[T]`, etc.
Reject any change that touches runtime behavior (not just type annotations).

- [ ] **Step 5b-2: Apply UP fixes**

```bash
ruff check backend/src --select UP --fix
```

- [ ] **Step 5b-3: Run test suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 5b-4: Sort imports**

```bash
ruff check backend/src --select I001 --fix
```

- [ ] **Step 5b-5: Run test suite again**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 5b-6: Commit typing modernization**

```bash
git add backend/src/
git commit -m "style: modernize type annotations via ruff UP (BUG-017)

Replace Optional[X] with X | None, Dict/List/Tuple generics with
built-in equivalents, Union[A, B] with A | B across backend/src/.
Sort imports with ruff I001.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### 5c: Annotate v1 API endpoints as deprecated (BUG-019)

- [ ] **Step 5c-1: Locate v1 router**

```bash
grep -n "router\|@router\|prefix\|tags" backend/src/api/rest_v1.py | head -20
```

- [ ] **Step 5c-2: Add deprecation comment block at top of rest_v1.py**

At the top of `backend/src/api/rest_v1.py`, after the existing module docstring or imports, add:

```python
# =============================================================================
# DEPRECATED: v1 API endpoints — use /api/v2/ endpoints instead.
# These endpoints exist for backwards compatibility with older clients.
# They will be removed in a future release. Do NOT add new functionality here.
# All v1 state is held in memory (no persistence); v2 uses SQLite-backed storage.
# =============================================================================
```

- [ ] **Step 5c-3: Add `deprecated=True` to each v1 route decorator**

For each `@router.get(...)`, `@router.post(...)`, etc. in `rest_v1.py` that does not already have `deprecated=True`:

```python
# BEFORE:
@router.get("/status")
async def get_status():
    ...

# AFTER:
@router.get("/status", deprecated=True)
async def get_status():
    ...
```

Run to find all route decorators:
```bash
grep -n "@router\." backend/src/api/rest_v1.py | wc -l
```

Apply `deprecated=True` to each one. FastAPI will mark them with a strikethrough in the OpenAPI docs.

- [ ] **Step 5c-4: Verify OpenAPI schema shows deprecated routes**

```bash
curl -s http://localhost:8081/openapi.json | python3 -c "
import json, sys
schema = json.load(sys.stdin)
deprecated = [(path, method) for path, methods in schema.get('paths', {}).items()
              for method, spec in methods.items() if spec.get('deprecated')]
print(f'Deprecated routes: {len(deprecated)}')
for p, m in deprecated[:5]:
    print(f'  {m.upper()} {p}')
"
```
Expected: lists the v1 deprecated routes

- [ ] **Step 5c-5: Run full suite**

```bash
python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass

- [ ] **Step 5c-6: Commit v1 deprecation**

```bash
git add backend/src/api/rest_v1.py
git commit -m "docs: annotate v1 API endpoints as deprecated (BUG-019)

Add deprecated=True to all @router decorators in rest_v1.py.
FastAPI marks these with strikethrough in OpenAPI docs. Add
top-of-file deprecation notice explaining v2 is the correct path.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Final Validation

- [ ] **Run complete test suite**

```bash
cd /home/pi/lawnberry && python -m pytest tests/unit/ -m "not hardware" -q
```
Expected: all tests pass (282+ — new tests added in Phase 2 will increase the count)

- [ ] **Restart backend and verify healthy**

```bash
sudo systemctl restart lawnberry-backend

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

New modules added:
- `backend/src/protocols/__init__.py` — empty package
- `backend/src/protocols/mission.py` — `MissionStatusReader` Protocol

New functions added:
- `config_loader.get_config_loader()` — singleton accessor
- `mission_service.MissionService._broadcast_status()` — WS push helper
- `mission_service.get_mission_service(websocket_hub=)` — updated factory

```bash
# Update docs/code_structure_overview.md to reflect new protocols package and functions
# Then commit:
git add docs/code_structure_overview.md
git commit -m "docs: update code_structure_overview.md for Phase 2 additions (auto)"
```

- [ ] **Run frontend lint**

```bash
cd /home/pi/lawnberry && npm --prefix frontend run lint 2>/dev/null
```
Expected: no new errors

---

## Phase 2 Complete ✓

All 5 architecture groups addressed:
1. ✅ ARCH-002: Circular dependency broken via MissionStatusReader Protocol
2. ✅ ARCH-007: Mission status pushed over WebSocket; poll interval 2s → 30s
3. ✅ ARCH-008: Optimistic mutations gated behind HTTP confirmation
4. ✅ ARCH-009: ConfigLoader singleton with thread-safe double-checked locking
5. ✅ BUG-016/017/019: ruff format, UP typing modernization, v1 deprecation annotations

**Combined Phase 1 + Phase 2 closes all 16 bugs and 9 architecture risks from the 2026-04-22 audit.**
