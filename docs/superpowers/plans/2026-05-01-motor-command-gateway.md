# Motor Command Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `MotorCommandGateway` as the single in-process code path from desired motion to RoboHAT PWM, absorbing emergency state ownership from the five scattered module-level globals and unifying drive/blade/emergency safety gating.

**Architecture:** Five sequential PRs (Phases A–E). Phase A wires the skeleton and routes emergency endpoints through it. Phase B migrates drive and blade dispatch. Phase C migrates navigation and mission services. Phase D flips state ownership and deletes dead code. Phase E adds firmware-version preflight (§11). Each PR is non-breaking: existing HTTP shapes and the full test suite (≈622 passed) hold after every phase.

**Tech Stack:** Python 3.11, FastAPI, pytest-asyncio, `unittest.mock`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-01-motor-command-gateway-design.md`

---

## File Map

| Action | Path |
|---|---|
| Create | `backend/src/control/__init__.py` |
| Create | `backend/src/control/commands.py` |
| Create | `backend/src/control/command_gateway.py` |
| Modify | `backend/src/core/runtime.py` |
| Modify | `backend/src/main.py` |
| Modify | `backend/src/api/rest.py` |
| Modify | `backend/src/api/safety.py` |
| Modify | `backend/src/services/navigation_service.py` (Phase C) |
| Modify | `backend/src/services/mission_service.py` (Phase C) |
| Modify | `backend/src/services/robohat_service.py` (Phase E) |
| Modify | `tests/unit/test_command_gateway.py` (new, grows each phase) |
| Modify | `tests/integration/test_runtime_lifespan.py` |
| Modify | `tests/integration/test_safety_router_runtime.py` |
| Modify | `tests/integration/test_control_manual_flow.py` |
| Modify | `tests/conftest.py` (Phase D) |
| Modify | `tests/integration/conftest.py` (Phase D) |
| Delete | `backend/src/services/motor_service.py` (Phase D) |
| Create | `docs/firmware-contract.md` (Phase E) |

---

## Task 1 — Phase A: Gateway skeleton + emergency endpoints

Wire `MotorCommandGateway` into `RuntimeContext`. Route `/control/emergency`, `/control/emergency-stop`, and `/control/emergency_clear` through the gateway. No HTTP behavior change.

**Files for this task:**
- Create: `backend/src/control/__init__.py`
- Create: `backend/src/control/commands.py`
- Create: `backend/src/control/command_gateway.py`
- Modify: `backend/src/core/runtime.py`
- Modify: `backend/src/main.py`
- Modify: `backend/src/api/rest.py` (emergency endpoints only)
- Modify: `backend/src/api/safety.py`
- Create: `tests/unit/test_command_gateway.py`
- Modify: `tests/integration/test_runtime_lifespan.py`
- Modify: `tests/integration/test_safety_router_runtime.py`
- Modify: `tests/integration/test_control_manual_flow.py`

---

- [ ] **Step 1.1: Write failing unit tests for emergency lifecycle**

Create `tests/unit/test_command_gateway.py`:

```python
"""Unit tests for MotorCommandGateway — Phase A: emergency lifecycle."""
import pytest
from unittest.mock import MagicMock


def _make_gw():
    """Return (gateway, safety_state, blade_state) using a mocked rest module."""
    from backend.src.control.command_gateway import MotorCommandGateway

    safety = {"emergency_stop_active": False, "estop_reason": None}
    blade = {"active": False}
    client_em: dict = {}
    rest_mock = MagicMock()
    rest_mock._emergency_until = 0.0
    gw = MotorCommandGateway(
        safety_state=safety,
        blade_state=blade,
        client_emergency=client_em,
        robohat=MagicMock(status=MagicMock(serial_connected=False)),
        persistence=MagicMock(),
        _rest_module=rest_mock,
    )
    return gw, safety, blade


def test_is_emergency_active_false_initially():
    gw, _, _ = _make_gw()
    assert gw.is_emergency_active() is False


@pytest.mark.asyncio
async def test_trigger_latches_safety_state():
    from backend.src.control.commands import CommandStatus, EmergencyTrigger

    gw, safety, blade = _make_gw()
    outcome = await gw.trigger_emergency(
        EmergencyTrigger(reason="test", source="operator")
    )
    assert outcome.status == CommandStatus.EMERGENCY_LATCHED
    assert safety["emergency_stop_active"] is True
    assert blade["active"] is False
    assert gw.is_emergency_active() is True


@pytest.mark.asyncio
async def test_trigger_is_idempotent():
    from backend.src.control.commands import CommandStatus, EmergencyTrigger

    gw, safety, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="first", source="operator"))
    outcome = await gw.trigger_emergency(EmergencyTrigger(reason="second", source="operator"))
    assert outcome.status == CommandStatus.EMERGENCY_LATCHED
    assert safety["emergency_stop_active"] is True


@pytest.mark.asyncio
async def test_clear_without_confirmation_returns_blocked():
    from backend.src.control.commands import CommandStatus, EmergencyClear, EmergencyTrigger

    gw, _, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    outcome = await gw.clear_emergency(EmergencyClear(confirmed=False))
    assert outcome.status == CommandStatus.BLOCKED
    assert gw.is_emergency_active() is True


@pytest.mark.asyncio
async def test_clear_with_confirmation_releases_latch():
    from backend.src.control.commands import CommandStatus, EmergencyClear, EmergencyTrigger

    gw, safety, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    outcome = await gw.clear_emergency(EmergencyClear(confirmed=True))
    assert outcome.status == CommandStatus.ACCEPTED
    assert outcome.idempotent is False
    assert safety["emergency_stop_active"] is False
    assert gw.is_emergency_active() is False


@pytest.mark.asyncio
async def test_clear_when_not_active_is_idempotent():
    from backend.src.control.commands import CommandStatus, EmergencyClear

    gw, _, _ = _make_gw()
    outcome = await gw.clear_emergency(EmergencyClear(confirmed=True))
    assert outcome.status == CommandStatus.ACCEPTED
    assert outcome.idempotent is True
```

- [ ] **Step 1.2: Run to confirm the tests fail**

```bash
SIM_MODE=1 uv run pytest tests/unit/test_command_gateway.py -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` for `backend.src.control.command_gateway`.

- [ ] **Step 1.3: Create the control package and commands module**

```bash
touch backend/src/control/__init__.py
```

Create `backend/src/control/commands.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


@dataclass
class DriveCommand:
    left: float
    right: float
    source: str          # "manual" | "mission" | "diagnosis" | "legacy"
    duration_ms: int
    session_id: str | None = None
    max_speed_limit: float = 0.8
    legacy: bool = False  # True for the no-session_id integration-test path


@dataclass
class BladeCommand:
    active: bool
    source: str          # "manual" | "mission"
    session_id: str | None = None
    motors_active: bool = False  # caller passes _legacy_motors_active (Phase B-C only)


@dataclass
class EmergencyTrigger:
    reason: str
    source: str          # "operator" | "navigation" | "safety_trigger"
    request: Any | None = None   # FastAPI Request for per-client TTL keying


@dataclass
class EmergencyClear:
    confirmed: bool
    operator: str | None = None


class CommandStatus(str, Enum):
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    QUEUED = "queued"
    TIMED_OUT = "timed_out"
    ACK_FAILED = "ack_failed"
    EMERGENCY_LATCHED = "emergency_latched"
    FIRMWARE_UNKNOWN = "firmware_unknown"
    FIRMWARE_INCOMPATIBLE = "firmware_incompatible"


@dataclass
class DriveOutcome:
    status: CommandStatus
    audit_id: str
    status_reason: str | None
    active_interlocks: list[str]
    watchdog_latency_ms: float | None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class BladeOutcome:
    status: CommandStatus
    audit_id: str
    status_reason: str | None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class EmergencyOutcome:
    status: CommandStatus
    audit_id: str
    hardware_confirmed: bool
    idempotent: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
```

- [ ] **Step 1.4: Create `command_gateway.py` with Phase A emergency methods**

Create `backend/src/control/command_gateway.py`:

```python
"""Motor command gateway — single software path from desired motion to RoboHAT PWM.

Phase A implements emergency lifecycle. Drive/blade dispatch added in Phase B.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from .commands import (
    BladeCommand,
    BladeOutcome,
    CommandStatus,
    DriveCommand,
    DriveOutcome,
    EmergencyClear,
    EmergencyOutcome,
    EmergencyTrigger,
)

logger = logging.getLogger(__name__)


def _client_key(request: Any) -> str:
    """Derive a stable per-client key from Authorization header or X-Client-Id."""
    import uuid as _uuid

    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        return auth
    cid = request.headers.get("X-Client-Id") or request.headers.get("x-client-id")
    if cid:
        return cid
    try:
        anon = getattr(request.state, "_anon_client_id", None)
        if not anon:
            anon = "anon-" + _uuid.uuid4().hex
            try:
                request.state._anon_client_id = anon
            except Exception:
                pass
        return anon
    except Exception:
        return "anon-" + _uuid.uuid4().hex


class MotorCommandGateway:
    def __init__(
        self,
        safety_state: dict,
        blade_state: dict,
        client_emergency: dict,
        robohat: Any,
        persistence: Any,
        websocket_hub: Any = None,
        config_loader: Any = None,
        _rest_module: Any = None,
    ) -> None:
        self._safety_state = safety_state
        self._blade_state = blade_state
        self._client_emergency = client_emergency
        self._robohat = robohat
        self._persistence = persistence
        self._websocket_hub = websocket_hub
        self._config_loader = config_loader
        self.__rest_module = _rest_module
        self._drive_timeout_task: Any = None  # asyncio.Task

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rest(self) -> Any:
        """Lazy import of rest module to avoid circular imports at load time."""
        if self.__rest_module is not None:
            return self.__rest_module
        import backend.src.api.rest as _rest
        return _rest

    # ------------------------------------------------------------------
    # Emergency state
    # ------------------------------------------------------------------

    def is_emergency_active(self, request: Any = None) -> bool:
        """Return True if any emergency condition blocks motion commands.

        Checks: software latch, short-lived TTL, per-client TTL.
        """
        try:
            if bool(self._safety_state.get("emergency_stop_active", False)):
                return True
            if time.time() < self._rest()._emergency_until:
                return True
        except Exception:
            return True
        if request is None:
            return False
        try:
            key = _client_key(request)
            exp = self._client_emergency.get(key)
            if exp is None:
                return False
            if time.time() < exp:
                return True
            self._client_emergency.pop(key, None)
        except Exception:
            pass
        return False

    async def trigger_emergency(self, cmd: EmergencyTrigger) -> EmergencyOutcome:
        """Latch emergency state and dispatch stop to hardware."""
        audit_id = str(uuid.uuid4())
        self._safety_state["emergency_stop_active"] = True
        self._safety_state["estop_reason"] = cmd.reason
        self._blade_state["active"] = False
        self._rest()._emergency_until = time.time() + 0.2
        try:
            if cmd.request is not None:
                self._client_emergency[_client_key(cmd.request)] = time.time() + 0.3
        except Exception:
            pass

        hardware_confirmed = True
        robohat = self._robohat
        if robohat and getattr(getattr(robohat, "status", None), "serial_connected", False):
            try:
                hardware_confirmed = await robohat.emergency_stop()
            except Exception:
                hardware_confirmed = False

        return EmergencyOutcome(
            status=CommandStatus.EMERGENCY_LATCHED,
            audit_id=audit_id,
            hardware_confirmed=hardware_confirmed,
        )

    async def clear_emergency(self, cmd: EmergencyClear) -> EmergencyOutcome:
        """Clear latched emergency state after operator confirmation."""
        audit_id = str(uuid.uuid4())
        if not cmd.confirmed:
            return EmergencyOutcome(
                status=CommandStatus.BLOCKED,
                audit_id=audit_id,
                hardware_confirmed=False,
            )
        if not self._safety_state.get("emergency_stop_active", False):
            return EmergencyOutcome(
                status=CommandStatus.ACCEPTED,
                audit_id=audit_id,
                hardware_confirmed=True,
                idempotent=True,
            )
        self._safety_state["emergency_stop_active"] = False
        self._safety_state["estop_reason"] = None
        self._blade_state["active"] = False
        self._rest()._emergency_until = 0.0
        self._client_emergency.clear()

        hardware_confirmed = True
        robohat = self._robohat
        if robohat and getattr(getattr(robohat, "status", None), "serial_connected", False):
            try:
                hardware_confirmed = await robohat.clear_emergency()
            except Exception:
                hardware_confirmed = False

        return EmergencyOutcome(
            status=CommandStatus.ACCEPTED,
            audit_id=audit_id,
            hardware_confirmed=hardware_confirmed,
        )

    # ------------------------------------------------------------------
    # Drive / blade (Phase B)
    # ------------------------------------------------------------------

    async def dispatch_drive(self, cmd: DriveCommand, request: Any = None) -> DriveOutcome:
        raise NotImplementedError("dispatch_drive implemented in Phase B")

    async def dispatch_blade(self, cmd: BladeCommand, request: Any = None) -> BladeOutcome:
        raise NotImplementedError("dispatch_blade implemented in Phase B")

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def reset_for_testing(self) -> None:
        """Reset all emergency state. Called from conftest in Phase D."""
        self._safety_state["emergency_stop_active"] = False
        self._safety_state["estop_reason"] = None
        self._blade_state["active"] = False
        self._rest()._emergency_until = 0.0
        self._client_emergency.clear()
```

- [ ] **Step 1.5: Run the unit tests — they should pass now**

```bash
SIM_MODE=1 uv run pytest tests/unit/test_command_gateway.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 1.6: Add `command_gateway: Any` to `RuntimeContext`**

In `backend/src/core/runtime.py`, add the field after `persistence`:

```python
@dataclass
class RuntimeContext:
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
    command_gateway: Any = None  # MotorCommandGateway; Any to avoid import cycle
```

- [ ] **Step 1.7: Construct gateway in `main.py` lifespan and add to RuntimeContext**

In `backend/src/main.py`, after the existing imports at lines 196-199 and before the `RuntimeContext(...)` call:

```python
from backend.src.control.command_gateway import MotorCommandGateway

_command_gateway = MotorCommandGateway(
    safety_state=global_state._safety_state,
    blade_state=global_state._blade_state,
    client_emergency=global_state._client_emergency,
    robohat=get_robohat_service(),
    persistence=persistence,
    websocket_hub=websocket_hub,
    config_loader=loader,
)
```

Then add `command_gateway=_command_gateway` to the `RuntimeContext(...)` call (as the last keyword argument, after `persistence=persistence`):

```python
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
    command_gateway=_command_gateway,
)
```

- [ ] **Step 1.8: Add gateway assertion to `test_runtime_lifespan.py`**

In `tests/integration/test_runtime_lifespan.py`, after the `assert hasattr(runtime, "sensor_manager")` line at the end, add:

```python
        # command_gateway must be present (Phase A gateway wiring).
        assert runtime.command_gateway is not None, (
            "runtime.command_gateway should not be None after lifespan startup"
        )
        from backend.src.control.command_gateway import MotorCommandGateway
        assert isinstance(runtime.command_gateway, MotorCommandGateway)
```

- [ ] **Step 1.9: Update fake runtimes in integration tests to include gateway**

`tests/integration/test_safety_router_runtime.py` — update `_make_runtime`:

```python
def _make_runtime(**overrides: Any) -> RuntimeContext:
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.core import globals as _g

    safety = overrides.pop("safety_state", {"emergency_stop_active": True, "estop_reason": "test"})
    blade = overrides.pop("blade_state", {"active": True})
    gw = MotorCommandGateway(
        safety_state=safety,
        blade_state=blade,
        client_emergency=_g._client_emergency,
        robohat=MagicMock(name="robohat", status=MagicMock(serial_connected=False)),
        persistence=MagicMock(name="persistence"),
    )
    defaults: dict[str, Any] = {
        "config_loader": MagicMock(name="config_loader"),
        "hardware_config": MagicMock(name="hardware_config"),
        "safety_limits": MagicMock(name="safety_limits"),
        "sensor_manager": MagicMock(name="sensor_manager"),
        "navigation": MagicMock(name="navigation"),
        "mission_service": MagicMock(name="mission_service"),
        "safety_state": safety,
        "blade_state": blade,
        "robohat": MagicMock(name="robohat"),
        "websocket_hub": MagicMock(name="websocket_hub"),
        "persistence": MagicMock(name="persistence"),
        "command_gateway": gw,
    }
    defaults.update(overrides)
    return RuntimeContext(**defaults)
```

`tests/integration/test_control_manual_flow.py` — update the `_override_runtime_for_control_routes` fixture:

```python
@pytest.fixture(autouse=True)
def _override_runtime_for_control_routes():
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.core import globals as core_globals

    _gw = MotorCommandGateway(
        safety_state=core_globals._safety_state,
        blade_state=core_globals._blade_state,
        client_emergency=core_globals._client_emergency,
        robohat=MagicMock(status=MagicMock(serial_connected=False)),
        persistence=MagicMock(),
        websocket_hub=MagicMock(),
        config_loader=MagicMock(),
    )
    fake_runtime = RuntimeContext(
        config_loader=MagicMock(),
        hardware_config=MagicMock(),
        safety_limits=MagicMock(),
        sensor_manager=MagicMock(),
        navigation=MagicMock(),
        mission_service=MagicMock(),
        safety_state=core_globals._safety_state,
        blade_state=core_globals._blade_state,
        robohat=MagicMock(),
        websocket_hub=MagicMock(),
        persistence=MagicMock(),
        command_gateway=_gw,
    )
    app.dependency_overrides[get_runtime] = lambda: fake_runtime
    yield
```

- [ ] **Step 1.10: Migrate `/control/emergency` and `/control/emergency-stop` in `rest.py`**

In `backend/src/api/rest.py`, add at the top (after existing imports):

```python
from ..core.runtime import RuntimeContext, get_runtime
```

Replace the `control_emergency_v2` function body. Add `runtime: RuntimeContext = Depends(get_runtime)` to the signature and replace the `_latch_emergency_state` + robohat calls with gateway dispatch:

```python
@router.post("/control/emergency", response_model=ControlResponseV2, status_code=202)
async def control_emergency_v2(
    body: Optional[dict] = None,
    request: Request = None,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Trigger emergency stop with immediate hardware shutdown"""
    import uuid
    from ..control.commands import EmergencyTrigger

    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)

    payload = body or {}
    is_legacy = isinstance(payload, dict) and payload.get("command")
    session_context = None
    if not is_legacy:
        session_context = _resolve_manual_session(payload.get("session_id"))

    outcome = await runtime.command_gateway.trigger_emergency(
        EmergencyTrigger(
            reason="Operator-triggered emergency stop",
            source="operator",
            request=request,
        )
    )
    emergency_confirmed = outcome.hardware_confirmed

    if is_legacy:
        legacy_payload = {
            "status": "EMERGENCY_STOP_ACTIVE",
            "motors_stopped": True,
            "blade_disabled": True,
            "emergency_stop_active": True,
            "timestamp": timestamp.isoformat(),
        }
        persistence.add_audit_log("control.emergency_stop", details={"response": legacy_payload})
        return JSONResponse(status_code=200, content=legacy_payload)

    response = ControlResponseV2(
        accepted=emergency_confirmed,
        audit_id=audit_id,
        result="accepted" if emergency_confirmed else "rejected",
        status_reason="EMERGENCY_STOP_TRIGGERED"
        if emergency_confirmed
        else "EMERGENCY_STOP_DELIVERY_FAILED",
        safety_checks=["immediate_stop"],
        active_interlocks=["emergency_stop_override"],
        remediation={
            "message": "Emergency stop activated - all motors stopped",
            "docs_link": "/docs/OPERATIONS.md#emergency-stop-recovery",
        },
        telemetry_snapshot={
            "component_id": "drive_left",
            "status": "fault",
            "latency_ms": 0.0,
        },
        timestamp=timestamp.isoformat(),
    )
    audit_details: dict[str, Any] = {"response": response.model_dump(mode="json")}
    if session_context and session_context.get("principal"):
        audit_details["principal"] = session_context["principal"]
    persistence.add_audit_log("control.emergency.triggered", details=audit_details)
    return response
```

Replace `control_emergency_stop_alias`:

```python
@router.post("/control/emergency-stop")
async def control_emergency_stop_alias(
    request: Request = None,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Integration-friendly alias that always returns 200 and a simple flag."""
    from ..control.commands import EmergencyTrigger

    await runtime.command_gateway.trigger_emergency(
        EmergencyTrigger(
            reason="Operator-triggered emergency stop",
            source="operator",
            request=request,
        )
    )
    payload = {
        "emergency_stop_active": True,
        "motors_stopped": True,
        "blade_disabled": True,
        "remediation": {
            "message": "Emergency stop activated - all motors stopped",
            "docs_link": "/docs/OPERATIONS.md#emergency-stop-recovery",
        },
    }
    persistence.add_audit_log(
        "control.emergency_stop",
        client_id=request.headers.get("X-Client-Id") if request is not None else None,
        details=payload,
    )
    return JSONResponse(status_code=200, content=payload)
```

- [ ] **Step 1.11: Migrate `clear_emergency_stop` in `safety.py`**

Replace the full body of `clear_emergency_stop` in `backend/src/api/safety.py`. Remove the `from . import rest as rest_api` and `from .rest import _client_emergency` imports since the gateway now owns those operations. The new function:

```python
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..control.commands import CommandStatus, EmergencyClear
from ..core.runtime import RuntimeContext, get_runtime

router = APIRouter()


class EmergencyClearRequest(BaseModel):
    confirmation: bool = Field(False, description="Operator confirmation required to clear E-stop")
    reason: str | None = Field(default=None, description="Optional reason or operator note")


@router.post("/control/emergency_clear")
async def clear_emergency_stop(
    payload: EmergencyClearRequest,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Clear emergency stop after explicit operator confirmation."""
    outcome = await runtime.command_gateway.clear_emergency(
        EmergencyClear(confirmed=payload.confirmation)
    )
    if outcome.status == CommandStatus.BLOCKED:
        raise HTTPException(
            status_code=422, detail="Confirmation required to clear emergency stop"
        )
    if outcome.idempotent:
        return {"status": "EMERGENCY_CLEARED", "idempotent": True}
    return {
        "status": "EMERGENCY_CLEARED",
        "timestamp": outcome.timestamp,
    }
```

- [ ] **Step 1.12: Run full test suite**

```bash
SIM_MODE=1 uv run pytest -q 2>&1 | tail -20
```

Expected: ≈622 passed (or 619 if PR #48 not yet merged), 0 failures. Fix any failures before committing.

- [ ] **Step 1.12b: Delete `_latch_emergency_state` — it is dead after Step 1.10**

After replacing both emergency endpoint call sites with gateway calls, `_latch_emergency_state` has zero callers. Delete it from `backend/src/api/rest.py`:

```bash
grep -n "_latch_emergency_state" backend/src/api/rest.py
```

Expected: only the function definition (no other call sites). Delete the function definition (lines ~597–615).

- [ ] **Step 1.13: Clean up working tree side-effects and check lint**

```bash
git checkout -- data/lawnberry.db-shm data/lawnberry.db-wal config/default.json 2>/dev/null || true
SIM_MODE=1 uv run ruff check backend/src
```

Expected: no lint errors. Fix any before committing.

- [ ] **Step 1.14: Commit Phase A**

```bash
git add backend/src/control/ \
  backend/src/core/runtime.py \
  backend/src/main.py \
  backend/src/api/rest.py \
  backend/src/api/safety.py \
  tests/unit/test_command_gateway.py \
  tests/integration/test_runtime_lifespan.py \
  tests/integration/test_safety_router_runtime.py \
  tests/integration/test_control_manual_flow.py
git commit -m "$(cat <<'EOF'
feat(control): introduce MotorCommandGateway skeleton + wire emergency endpoints

Phase A of §4 motor command gateway. Adds backend/src/control/ package with
typed commands/outcomes and MotorCommandGateway that owns emergency state.
Routes /control/emergency, /control/emergency-stop, and /control/emergency_clear
through the gateway. No HTTP behavior change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 1.15: Open PR and stop**

```bash
gh pr create \
  --title "feat(control): Phase A — MotorCommandGateway skeleton + emergency endpoints" \
  --body "$(cat <<'EOF'
## Summary
- Adds `backend/src/control/` package with typed `commands.py` and `MotorCommandGateway`
- Wires gateway into `RuntimeContext` via lifespan startup
- Routes `/control/emergency`, `/control/emergency-stop`, `/control/emergency_clear` through gateway
- No HTTP behavior change; all existing tests pass

## Test plan
- [ ] `SIM_MODE=1 uv run pytest -q` passes with 0 failures
- [ ] `SIM_MODE=1 uv run pytest tests/unit/test_command_gateway.py -v` — 6 new tests pass
- [ ] `SIM_MODE=1 uv run pytest tests/integration/test_runtime_lifespan.py -v` — gateway field assertion passes
- [ ] `SIM_MODE=1 uv run ruff check backend/src` clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Stop here. Report PR URL and wait for merge before starting Phase B.**

---

## Task 2 — Phase B: Drive and blade dispatch through gateway

Move drive and blade logic (RoboHAT dispatch, ack, auto-stop, manual-drive interlocks, audit) from `rest.py` endpoints into `gateway.dispatch_drive` and `gateway.dispatch_blade`. HTTP shapes stay identical.

**Files for this task:**
- Modify: `backend/src/control/command_gateway.py` (add `dispatch_drive`, `dispatch_blade`)
- Modify: `backend/src/api/rest.py` (`control_drive_v2`, `control_blade_v2`)
- Modify: `tests/unit/test_command_gateway.py` (add drive + blade tests)

---

- [ ] **Step 2.1: Write failing tests for gateway drive outcomes**

Append to `tests/unit/test_command_gateway.py`:

```python
# ---- Phase B: drive outcomes ----

@pytest.mark.asyncio
async def test_dispatch_drive_blocked_when_emergency_active():
    from backend.src.control.commands import CommandStatus, DriveCommand, EmergencyTrigger

    gw, _, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.5, right=0.5, source="manual", duration_ms=200)
    )
    assert outcome.status == CommandStatus.BLOCKED
    assert "emergency" in (outcome.status_reason or "").lower() or outcome.status_reason is not None


@pytest.mark.asyncio
async def test_dispatch_drive_queued_when_no_hardware():
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()  # robohat.status.serial_connected = False
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.3, right=0.3, source="manual", duration_ms=200)
    )
    assert outcome.status == CommandStatus.QUEUED


@pytest.mark.asyncio
async def test_dispatch_drive_legacy_queued_when_no_hardware():
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.95, right=0.55, source="legacy", duration_ms=0, legacy=True)
    )
    assert outcome.status in (CommandStatus.QUEUED, CommandStatus.ACCEPTED)


# ---- Phase B: blade outcomes ----

@pytest.mark.asyncio
async def test_dispatch_blade_blocked_while_emergency_active():
    from backend.src.control.commands import (
        BladeCommand, CommandStatus, EmergencyTrigger,
    )

    gw, _, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    outcome = await gw.dispatch_blade(
        BladeCommand(active=True, source="manual")
    )
    assert outcome.status == CommandStatus.BLOCKED


@pytest.mark.asyncio
async def test_dispatch_blade_blocked_while_motors_active():
    from backend.src.control.commands import BladeCommand, CommandStatus

    gw, _, _ = _make_gw()
    outcome = await gw.dispatch_blade(
        BladeCommand(active=True, source="manual", motors_active=True)
    )
    assert outcome.status == CommandStatus.BLOCKED
    assert "motors_active" in (outcome.status_reason or "")


@pytest.mark.asyncio
async def test_dispatch_blade_disable_always_accepted():
    from backend.src.control.commands import BladeCommand, CommandStatus

    gw, _, _ = _make_gw()
    outcome = await gw.dispatch_blade(
        BladeCommand(active=False, source="manual", motors_active=True)
    )
    assert outcome.status in (CommandStatus.ACCEPTED, CommandStatus.QUEUED)
```

- [ ] **Step 2.2: Run to confirm new tests fail**

```bash
SIM_MODE=1 uv run pytest tests/unit/test_command_gateway.py -v -k "drive or blade" 2>&1 | tail -20
```

Expected: FAILED with `NotImplementedError`.

- [ ] **Step 2.3: Implement `dispatch_drive` in `command_gateway.py`**

Replace the `NotImplementedError` stub for `dispatch_drive` with:

```python
async def dispatch_drive(self, cmd: DriveCommand, request: Any = None) -> DriveOutcome:
    import asyncio
    import os
    import uuid

    audit_id = str(uuid.uuid4())
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc)

    # Emergency gate
    if self.is_emergency_active(request):
        return DriveOutcome(
            status=CommandStatus.BLOCKED,
            audit_id=audit_id,
            status_reason="emergency_stop_active",
            active_interlocks=[],
            watchdog_latency_ms=None,
        )

    # Manual-drive hardware interlocks (contract path only, hardware only)
    manual_active_interlocks: list[str] = []
    if (
        not cmd.legacy
        and cmd.source == "manual"
        and os.getenv("SIM_MODE", "0") == "0"
        and self._robohat
        and getattr(getattr(self._robohat, "status", None), "serial_connected", False)
    ):
        manual_active_interlocks = await self._check_manual_drive_interlocks(cmd)

    if manual_active_interlocks:
        manual_active_interlocks = list(dict.fromkeys(manual_active_interlocks))
        return DriveOutcome(
            status=CommandStatus.BLOCKED,
            audit_id=audit_id,
            status_reason=self._drive_interlock_reason(manual_active_interlocks),
            active_interlocks=manual_active_interlocks,
            watchdog_latency_ms=None,
        )

    # Hardware dispatch
    robohat = self._robohat
    if robohat and getattr(getattr(robohat, "status", None), "serial_connected", False):
        from datetime import datetime, timezone as tz

        watchdog_start = datetime.now(tz.utc)
        success = await robohat.send_motor_command(cmd.left, cmd.right)
        watchdog_latency = (datetime.now(tz.utc) - watchdog_start).total_seconds() * 1000

        if success:
            auto_stop_ms = cmd.duration_ms if cmd.duration_ms > 0 else 500
            if self._drive_timeout_task and not self._drive_timeout_task.done():
                self._drive_timeout_task.cancel()

            async def _auto_stop() -> None:
                try:
                    await asyncio.sleep(auto_stop_ms / 1000.0)
                    await robohat.send_motor_command(0.0, 0.0)
                    logger.warning(
                        "Manual drive duration expired (%d ms); motors stopped", auto_stop_ms
                    )
                except asyncio.CancelledError:
                    pass

            self._drive_timeout_task = asyncio.create_task(_auto_stop())

        return DriveOutcome(
            status=CommandStatus.ACCEPTED if success else CommandStatus.ACK_FAILED,
            audit_id=audit_id,
            status_reason=None if success else (robohat.status.last_error or "robohat_communication_failed"),
            active_interlocks=[],
            watchdog_latency_ms=round(watchdog_latency, 2),
        )

    # No hardware — queued acknowledgement
    return DriveOutcome(
        status=CommandStatus.QUEUED,
        audit_id=audit_id,
        status_reason="nominal",
        active_interlocks=[],
        watchdog_latency_ms=0.0,
    )

async def _check_manual_drive_interlocks(self, cmd: DriveCommand) -> list[str]:
    """Check telemetry freshness, location accuracy, and obstacle clearance."""
    from datetime import datetime, timezone

    interlocks: list[str] = []
    try:
        telemetry = await self._websocket_hub.get_cached_telemetry()
        source = telemetry.get("source")
        if source != "hardware":
            interlocks.append("telemetry_unavailable")
            return interlocks

        snapshot_timestamp = telemetry.get("timestamp")
        try:
            snapshot_at = datetime.fromisoformat(str(snapshot_timestamp))
            if snapshot_at.tzinfo is None:
                snapshot_at = snapshot_at.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - snapshot_at).total_seconds() > 2.5:
                interlocks.append("telemetry_stale")
        except Exception:
            interlocks.append("telemetry_stale")

        position = telemetry.get("position") or {}
        lat = position.get("latitude")
        lon = position.get("longitude")
        acc = position.get("accuracy")
        if lat is None or lon is None or acc is None:
            interlocks.append("location_awareness_unavailable")
        else:
            try:
                from ..services.navigation_service import NavigationService

                max_acc = NavigationService.get_instance().max_waypoint_accuracy_m
                if float(acc) > float(max_acc):
                    interlocks.append("location_awareness_unavailable")
            except Exception:
                interlocks.append("location_awareness_unavailable")

        if not interlocks or "location_awareness_unavailable" not in interlocks:
            loader = self._config_loader
            if loader is None:
                from ..core.config_loader import ConfigLoader

                loader = ConfigLoader()
            _, limits = loader.get()
            tof = telemetry.get("tof") or {}
            threshold_mm = float(limits.tof_obstacle_distance_meters) * 1000.0
            for side in ("left", "right"):
                side_payload = tof.get(side) or {}
                distance_mm = side_payload.get("distance_mm")
                if distance_mm is None:
                    continue
                try:
                    if float(distance_mm) <= threshold_mm:
                        interlocks.append("obstacle_detected")
                        break
                except (TypeError, ValueError):
                    continue
    except Exception as exc:
        logger.warning("Manual drive telemetry safety validation failed: %s", exc)
        interlocks.append("telemetry_unavailable")
    return interlocks

@staticmethod
def _drive_interlock_reason(interlocks: list[str]) -> str:
    if "obstacle_detected" in interlocks:
        return "OBSTACLE_DETECTED"
    if "location_awareness_unavailable" in interlocks:
        return "LOCATION_AWARENESS_UNAVAILABLE"
    if "telemetry_unavailable" in interlocks or "telemetry_stale" in interlocks:
        return "TELEMETRY_UNAVAILABLE"
    return "SAFETY_LOCKOUT"
```

- [ ] **Step 2.4: Implement `dispatch_blade` in `command_gateway.py`**

Replace the `NotImplementedError` stub for `dispatch_blade` with:

```python
async def dispatch_blade(self, cmd: BladeCommand, request: Any = None) -> BladeOutcome:
    import uuid

    audit_id = str(uuid.uuid4())

    if cmd.active:
        if cmd.motors_active:
            return BladeOutcome(
                status=CommandStatus.BLOCKED,
                audit_id=audit_id,
                status_reason="motors_active",
            )
        if self.is_emergency_active(request):
            return BladeOutcome(
                status=CommandStatus.BLOCKED,
                audit_id=audit_id,
                status_reason="emergency_stop_active",
            )

    try:
        from ..services.blade_service import get_blade_service

        bs = get_blade_service()
        await bs.initialize()
        ok = await bs.set_active(cmd.active)
        return BladeOutcome(
            status=CommandStatus.ACCEPTED if ok else CommandStatus.ACK_FAILED,
            audit_id=audit_id,
            status_reason=None if ok else "blade_service_rejected",
        )
    except Exception as exc:
        logger.warning("Blade service dispatch failed: %s", exc)
        return BladeOutcome(
            status=CommandStatus.ACK_FAILED,
            audit_id=audit_id,
            status_reason="blade_service_unavailable",
        )
```

- [ ] **Step 2.5: Run gateway unit tests — should all pass**

```bash
SIM_MODE=1 uv run pytest tests/unit/test_command_gateway.py -v
```

Expected: all tests PASS (≥12 total).

- [ ] **Step 2.6: Update `control_drive_v2` in `rest.py` to use gateway**

Replace the full body of `control_drive_v2` with a thin HTTP adapter that delegates to `runtime.command_gateway.dispatch_drive`. Keep the same response shapes for contract compatibility. The function signature gains `runtime: RuntimeContext = Depends(get_runtime)`.

```python
@router.post("/control/drive", response_model=ControlResponseV2, status_code=202)
async def control_drive_v2(cmd: dict, request: Request, runtime: RuntimeContext = Depends(get_runtime)):
    """Execute drive command with safety checks and audit logging"""
    import uuid
    from ..control.commands import DriveCommand, CommandStatus

    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)

    is_legacy = "session_id" not in cmd
    if is_legacy:
        throttle = float(cmd.get("throttle", 0.0))
        turn = float(cmd.get("turn", 0.0))
        left_speed = throttle + turn
        right_speed = throttle - turn
        max_speed_limit = 1.0
        left_speed = max(-max_speed_limit, min(max_speed_limit, left_speed))
        right_speed = max(-max_speed_limit, min(max_speed_limit, right_speed))

        drive_cmd = DriveCommand(
            left=left_speed,
            right=right_speed,
            source="legacy",
            duration_ms=0,
            legacy=True,
            max_speed_limit=max_speed_limit,
        )
        outcome = await runtime.command_gateway.dispatch_drive(drive_cmd, request=request)

        if outcome.status == CommandStatus.BLOCKED:
            try:
                cmd_details = dict(cmd)
            except Exception:
                cmd_details = {}
            persistence.add_audit_log(
                "control.drive.blocked",
                details={"reason": "emergency_stop_active", "command": cmd_details},
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Emergency stop active - drive commands blocked"},
            )

        global _legacy_motors_active
        _legacy_motors_active = True
        body = {
            "left_motor_speed": round(left_speed, 3),
            "right_motor_speed": round(right_speed, 3),
            "safety_status": "OK",
        }
        persistence.add_audit_log("control.drive", details={"command": cmd, "response": body})
        return JSONResponse(status_code=200, content=body)

    # Contract-style payload
    if runtime.command_gateway.is_emergency_active(request):
        try:
            cmd_details = dict(cmd)
            if "session_id" in cmd_details:
                cmd_details["session_id"] = "***"
        except Exception:
            cmd_details = {}
        persistence.add_audit_log(
            "control.drive.blocked",
            details={"reason": "emergency_stop_active", "command": cmd_details},
        )
        return JSONResponse(
            status_code=403, content={"detail": "Emergency stop active - drive commands blocked"}
        )

    session_context = _resolve_manual_session(cmd.get("session_id"))

    try:
        duration_ms = int(cmd.get("duration_ms", 0))
    except (TypeError, ValueError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="duration_ms must be an integer"
        )
    if duration_ms < 0 or duration_ms > 5000:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="duration_ms must be between 0 and 5000 milliseconds",
        )

    throttle = float(cmd.get("vector", {}).get("linear", 0.0))
    turn = float(cmd.get("vector", {}).get("angular", 0.0))
    try:
        speed_limit = float(cmd.get("max_speed_limit", 0.8))
    except (TypeError, ValueError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="max_speed_limit must be numeric"
        )
    speed_limit = max(0.0, min(1.0, speed_limit))
    left_speed = throttle - turn
    right_speed = throttle + turn
    left_speed = max(-speed_limit, min(speed_limit, left_speed))
    right_speed = max(-speed_limit, min(speed_limit, right_speed))

    drive_cmd = DriveCommand(
        left=left_speed,
        right=right_speed,
        source="manual",
        duration_ms=duration_ms,
        session_id=cmd.get("session_id"),
        max_speed_limit=speed_limit,
        legacy=False,
    )
    outcome = await runtime.command_gateway.dispatch_drive(drive_cmd, request=request)

    if outcome.status == CommandStatus.BLOCKED and outcome.active_interlocks:
        # Manual-drive interlock blocked (telemetry/obstacle/location)
        _transient = {"telemetry_unavailable", "telemetry_stale", "location_awareness_unavailable"}
        has_only_transient = all(i in _transient for i in outcome.active_interlocks)
        lockout_until_str: str | None = None
        if has_only_transient:
            from datetime import timedelta
            lockout_until_str = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()

        try:
            details_cmd = dict(cmd)
            if "session_id" in details_cmd:
                details_cmd["session_id"] = "***"
        except Exception:
            details_cmd = {}
        persistence.add_audit_log(
            "control.drive.blocked",
            details={
                "reason": outcome.status_reason,
                "active_interlocks": outcome.active_interlocks,
                "command": details_cmd,
            },
        )
        blocked_response = ControlResponseV2(
            accepted=False,
            audit_id=outcome.audit_id,
            result="blocked",
            status_reason=outcome.status_reason,
            safety_checks=[
                "emergency_stop_check",
                "command_validation",
                "telemetry_source_check",
                "location_awareness_check",
                "obstacle_clearance_check",
            ],
            active_interlocks=outcome.active_interlocks,
            remediation={
                "docs_link": "/docs/OPERATIONS.md#manual-drive-safety-gating",
                "message": "Clear nearby obstacles and restore fresh hardware telemetry before retrying manual movement.",
            },
            telemetry_snapshot=None,
            until=lockout_until_str,
            timestamp=timestamp.isoformat(),
        )
        return JSONResponse(status_code=423, content=blocked_response.model_dump(mode="json"))

    # Map gateway outcome to ControlResponseV2
    if outcome.status in (CommandStatus.ACCEPTED, CommandStatus.QUEUED):
        accepted = True
        result = outcome.status.value
    else:
        accepted = False
        result = "rejected"

    response = ControlResponseV2(
        accepted=accepted,
        audit_id=outcome.audit_id,
        result=result,
        status_reason=outcome.status_reason,
        watchdog_latency_ms=outcome.watchdog_latency_ms,
        safety_checks=["emergency_stop_check", "command_validation"],
        active_interlocks=[],
        telemetry_snapshot={
            "component_id": "drive_left",
            "status": "healthy" if accepted else "warning",
            "latency_ms": outcome.watchdog_latency_ms or 0.0,
            "speed_limit": speed_limit,
        },
        timestamp=timestamp.isoformat(),
    )

    global _last_drive_audit_at
    try:
        details_cmd = dict(cmd)
        if "session_id" in details_cmd:
            details_cmd["session_id"] = "***"
        principal = session_context.get("principal") if session_context else None
        if principal:
            details_cmd["principal"] = principal
        details_cmd["max_speed_limit"] = speed_limit
    except Exception:
        details_cmd = {}
    import asyncio as _asyncio
    _now = time.monotonic()
    if _now - _last_drive_audit_at >= _DRIVE_AUDIT_SAMPLE_INTERVAL_S:
        _last_drive_audit_at = _now
        _audit_details = {"command": details_cmd, "response": response.model_dump(mode="json")}
        _task = _asyncio.create_task(
            _asyncio.to_thread(
                persistence.add_audit_log, "control.drive.v2", None, None, _audit_details
            )
        )
        _task.add_done_callback(
            lambda t: logger.warning("Drive audit log failed: %s", t.exception())
            if not t.cancelled() and t.exception()
            else None
        )

    return response
```

- [ ] **Step 2.7: Update `control_blade_v2` in `rest.py` to use gateway**

Replace the full body of `control_blade_v2`, adding `runtime: RuntimeContext = Depends(get_runtime)`:

```python
@router.post("/control/blade")
async def control_blade_v2(cmd: dict, request: Request, runtime: RuntimeContext = Depends(get_runtime)):
    """Execute blade command with safety interlocks and audit logging."""
    import uuid
    from ..control.commands import BladeCommand, CommandStatus

    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)

    desired: bool | None = None
    if "active" in cmd:
        desired = bool(cmd["active"])
    elif "action" in cmd:
        action = str(cmd["action"]).lower()
        if action in {"enable", "on", "start"}:
            desired = True
        elif action in {"disable", "off", "stop"}:
            desired = False
    elif cmd.get("command") == "blade_enable":
        desired = True
    elif cmd.get("command") == "blade_disable":
        desired = False

    if desired is None:
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid blade command — provide 'active' (bool) or 'action' (enable/disable)"},
        )

    blade_cmd = BladeCommand(
        active=desired,
        source="manual",
        motors_active=_legacy_motors_active,
    )
    outcome = await runtime.command_gateway.dispatch_blade(blade_cmd, request=request)

    if outcome.status == CommandStatus.BLOCKED:
        if "motors_active" in (outcome.status_reason or ""):
            body = {"detail": "safety_interlock: motors_active — blade enable blocked while motors running"}
            persistence.add_audit_log("control.blade.blocked", details={"command": cmd, "response": body})
            return JSONResponse(status_code=403, content=body)
        body = {"detail": "safety_interlock: emergency_stop_active — blade commands blocked"}
        persistence.add_audit_log("control.blade.blocked", details={"command": cmd, "response": body})
        return JSONResponse(status_code=409, content=body)

    ok = outcome.status in (CommandStatus.ACCEPTED, CommandStatus.QUEUED)
    body = {
        "accepted": ok,
        "audit_id": audit_id,
        "result": "accepted" if ok else "rejected",
        "blade_active": desired if ok else _blade_state.get("active", False),
        "blade_status": "ENABLED" if (ok and desired) else "DISABLED",
        "timestamp": timestamp.isoformat(),
    }
    persistence.add_audit_log("control.blade", details={"command": cmd, "response": body})
    return JSONResponse(status_code=200, content=body)
```

- [ ] **Step 2.8: Run full test suite**

```bash
SIM_MODE=1 uv run pytest -q 2>&1 | tail -20
```

Expected: 0 failures. Fix before committing.

- [ ] **Step 2.8b: Delete `_client_emergency_active` — it is dead after Steps 2.6 and 2.7**

After replacing both call sites in `control_drive_v2` and `control_blade_v2`, `_client_emergency_active` has zero callers. Verify and delete:

```bash
grep -n "_client_emergency_active" backend/src/api/rest.py
```

Expected: only the function definition (no call sites). Delete it (lines ~640–660).

Note: `_emergency_active()` still has callers in five navigation endpoints (lines ~1294, 1342, 1390, 1454, 1555 — `control_start_navigation`, `control_resume_navigation`, `control_return_home`, `control_diagnose_stiffness_progressive`, and the heading calibration endpoint). These are migrated in Phase D.

- [ ] **Step 2.9: Clean up, lint, commit Phase B**

```bash
git checkout -- data/lawnberry.db-shm data/lawnberry.db-wal config/default.json 2>/dev/null || true
SIM_MODE=1 uv run ruff check backend/src
git add backend/src/control/command_gateway.py backend/src/api/rest.py \
  tests/unit/test_command_gateway.py
git commit -m "$(cat <<'EOF'
feat(control): Phase B — dispatch drive and blade through gateway

Moves RoboHAT dispatch, manual-drive interlocks, ack verification, auto-stop
task, and 1 Hz audit sampling from control_drive_v2/control_blade_v2 into
gateway.dispatch_drive / gateway.dispatch_blade. HTTP response shapes unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2.10: Open PR and stop**

```bash
gh pr create \
  --title "feat(control): Phase B — drive and blade dispatch through gateway" \
  --body "$(cat <<'EOF'
## Summary
- `dispatch_drive`: manual-drive interlocks, RoboHAT dispatch, ack, auto-stop all in gateway
- `dispatch_blade`: motors-active interlock and blade service call in gateway
- HTTP response shapes unchanged (contract tests remain green)

## Test plan
- [ ] `SIM_MODE=1 uv run pytest -q` — 0 failures
- [ ] `SIM_MODE=1 uv run pytest tests/unit/test_command_gateway.py -v` — ≥12 pass
- [ ] `SIM_MODE=1 uv run pytest tests/contract/test_rest_api_control.py -v` — all pass
- [ ] `SIM_MODE=1 uv run ruff check backend/src` clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Stop here. Wait for merge before Phase C.**

---

## Task 3 — Phase C: Navigation and mission service migration

Replace direct `rest_api._safety_state` reads and writes in `navigation_service.py` and `mission_service.py` with gateway calls. Extend import-purity guards to cover these modules.

**Files for this task:**
- Modify: `backend/src/services/navigation_service.py`
- Modify: `backend/src/services/mission_service.py`
- Modify: `tests/integration/test_safety_router_runtime.py`

---

- [ ] **Step 3.1: Write failing import-purity guard tests**

Append to `tests/integration/test_safety_router_runtime.py`:

```python
def test_navigation_service_does_not_import_state_from_rest():
    """navigation_service.py must not read/write rest_api._safety_state after Phase C."""
    import re

    from backend.src.services import navigation_service

    text = open(navigation_service.__file__).read()
    bad_patterns = [
        r"rest_api\._safety_state",
        r"rest_api\._blade_state",
        r"rest_api\._emergency_until",
        r"rest_api\._legacy_motors_active",
    ]
    for pat in bad_patterns:
        assert not re.search(pat, text), (
            f"navigation_service.py still accesses {pat!r} from rest_api"
        )


def test_mission_service_does_not_import_state_from_rest():
    """mission_service.py must not read rest_api._safety_state after Phase C."""
    import re

    from backend.src.services import mission_service

    text = open(mission_service.__file__).read()
    assert not re.search(r"rest_api\._safety_state", text), (
        "mission_service.py still reads rest_api._safety_state"
    )
```

- [ ] **Step 3.2: Run to confirm guard tests fail**

```bash
SIM_MODE=1 uv run pytest tests/integration/test_safety_router_runtime.py -v -k "navigation_service or mission_service" 2>&1 | tail -15
```

Expected: FAILED (the patterns still appear in the source files).

- [ ] **Step 3.3: Update `navigation_service.py` — replace `_global_emergency_active`**

In `backend/src/services/navigation_service.py`, replace `_global_emergency_active` (around line 1035):

```python
def _global_emergency_active(self) -> bool:
    """Return True when the API-level emergency stop is latched or any active hardware interlock."""
    # Prefer the gateway if available (Phase C+); fall back to direct state read.
    try:
        from ..main import app

        gw = getattr(getattr(app.state, "runtime", None), "command_gateway", None)
        if gw is not None:
            return gw.is_emergency_active()
    except Exception:
        pass

    # Legacy fallback: read the shared dict directly (same dict the gateway holds)
    try:
        from ..core import globals as _g

        if _g._safety_state.get("emergency_stop_active", False):
            return True
    except Exception:
        pass

    try:
        from ..core.robot_state_manager import get_robot_state_manager
        from ..models.safety_interlock import InterlockState

        active = get_robot_state_manager().get_state().active_interlocks
        if any(il.state == InterlockState.ACTIVE for il in active):
            return True
    except Exception:
        pass

    return False
```

Replace `_latch_global_emergency_state` (around line 1065):

```python
def _latch_global_emergency_state(self) -> None:
    """Mirror the control API emergency latch for non-HTTP emergency paths."""
    try:
        from ..main import app
        from ..control.commands import EmergencyTrigger

        gw = getattr(getattr(app.state, "runtime", None), "command_gateway", None)
        if gw is not None:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(
                    gw.trigger_emergency(
                        EmergencyTrigger(reason="Navigation safety trigger", source="navigation")
                    )
                )
                return
    except Exception:
        pass

    # Legacy fallback when gateway unavailable (unit tests, early startup)
    try:
        from ..core import globals as _g

        _g._safety_state["emergency_stop_active"] = True
        _g._blade_state["active"] = False
    except Exception:
        logger.debug("Unable to latch emergency state from navigation service", exc_info=True)
```

Also update the `_latch_global_emergency_state` call site (around line 1746) that sets `estop_reason`:

```python
# Replace:
rest_api._safety_state["estop_reason"] = reason
# With:
try:
    from ..core import globals as _g
    _g._safety_state["estop_reason"] = reason
except Exception:
    pass
```

- [ ] **Step 3.4: Update `mission_service.py` — replace `rest_api._safety_state` reads**

In `backend/src/services/mission_service.py`, there are two read sites (around lines 370 and 510). For each, replace:

```python
# Replace:
if rest_api._safety_state.get("emergency_stop_active", False):
# With:
def _is_emergency() -> bool:
    try:
        from ..main import app
        gw = getattr(getattr(app.state, "runtime", None), "command_gateway", None)
        if gw is not None:
            return gw.is_emergency_active()
    except Exception:
        pass
    try:
        from ..core import globals as _g
        return bool(_g._safety_state.get("emergency_stop_active", False))
    except Exception:
        return False

if _is_emergency():
```

Since the pattern appears twice, define `_is_emergency` once at module level rather than inline. Add at the top of `mission_service.py` after imports:

```python
def _is_emergency_active() -> bool:
    """Check emergency state via gateway if available, else direct dict read."""
    try:
        from ..main import app

        gw = getattr(getattr(app.state, "runtime", None), "command_gateway", None)
        if gw is not None:
            return gw.is_emergency_active()
    except Exception:
        pass
    try:
        from ..core import globals as _g

        return bool(_g._safety_state.get("emergency_stop_active", False))
    except Exception:
        return False
```

Then replace both `rest_api._safety_state.get("emergency_stop_active", False)` calls with `_is_emergency_active()`.

Also remove the `from ..api import rest as rest_api` import from `mission_service.py` if it is only used for those two safety checks (verify with `grep` before removing).

- [ ] **Step 3.5: Run the import-purity guard tests**

```bash
SIM_MODE=1 uv run pytest tests/integration/test_safety_router_runtime.py -v
```

Expected: all PASS including the two new guards.

- [ ] **Step 3.6: Run full test suite**

```bash
SIM_MODE=1 uv run pytest -q 2>&1 | tail -15
```

Expected: 0 failures.

- [ ] **Step 3.7: Clean up, lint, commit Phase C**

```bash
git checkout -- data/lawnberry.db-shm data/lawnberry.db-wal config/default.json 2>/dev/null || true
SIM_MODE=1 uv run ruff check backend/src
git add backend/src/services/navigation_service.py \
  backend/src/services/mission_service.py \
  tests/integration/test_safety_router_runtime.py
git commit -m "$(cat <<'EOF'
feat(control): Phase C — navigation and mission services read emergency state via gateway

Replaces direct rest_api._safety_state reads/writes in navigation_service.py
and mission_service.py with gateway.is_emergency_active() and
gateway.trigger_emergency(), with fallback to core.globals for unit-test
contexts where app.state.runtime is not available.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3.8: Open PR and stop**

```bash
gh pr create \
  --title "feat(control): Phase C — nav/mission services migrate to gateway" \
  --body "$(cat <<'EOF'
## Summary
- `navigation_service.py`: `_global_emergency_active` and `_latch_global_emergency_state` route through gateway; fallback to `core.globals` when gateway unavailable (unit tests)
- `mission_service.py`: `_is_emergency_active()` helper replaces direct `rest_api._safety_state` reads
- Import-purity guards added to `test_safety_router_runtime.py`

## Test plan
- [ ] `SIM_MODE=1 uv run pytest -q` — 0 failures
- [ ] `SIM_MODE=1 uv run pytest tests/integration/test_safety_router_runtime.py -v` — all pass including new guards
- [ ] `SIM_MODE=1 uv run ruff check backend/src` clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Stop here. Wait for merge before Phase D.**

---

## Task 4 — Phase D: State ownership flip + cleanup

Gateway internalizes emergency state. Module-level globals become read-only shims. Legacy helper functions in `rest.py` deleted. `motor_service.py` deleted. Conftest updated.

**Files for this task:**
- Modify: `backend/src/control/command_gateway.py`
- Modify: `backend/src/core/globals.py`
- Modify: `backend/src/api/rest.py`
- Modify: `tests/conftest.py`
- Modify: `tests/integration/conftest.py`
- Delete: `backend/src/services/motor_service.py`

---

- [ ] **Step 4.1: Write tests that verify `reset_for_testing` clears all state**

Append to `tests/unit/test_command_gateway.py`:

```python
# ---- Phase D: reset_for_testing ----

@pytest.mark.asyncio
async def test_reset_for_testing_clears_all_state():
    from backend.src.control.commands import EmergencyTrigger

    gw, safety, blade = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    assert gw.is_emergency_active() is True
    gw.reset_for_testing()
    assert gw.is_emergency_active() is False
    assert safety["emergency_stop_active"] is False
    assert blade["active"] is False
```

Run it to confirm it passes (it calls `reset_for_testing` which already exists):

```bash
SIM_MODE=1 uv run pytest tests/unit/test_command_gateway.py::test_reset_for_testing_clears_all_state -v
```

Expected: PASS.

- [ ] **Step 4.2: Internalize `EmergencyState` in gateway**

In `backend/src/control/command_gateway.py`, add an internal state container and wire the constructor to use it when no external dicts are passed (migration mode to full ownership):

The gateway's constructor now keeps the passed-in dict refs for backward compatibility but also updates `reset_for_testing` to clear them:

```python
# No change needed to the gateway's internal logic for Phase D —
# the gateway already mutates the same dicts. The key change is
# making globals.py read through the gateway instead of holding their own state.
```

The real change in Phase D is in `globals.py` and conftest (below). The gateway code needs no changes for this phase — it already holds references to the dicts.

- [ ] **Step 4.3: Migrate navigation endpoints off `_emergency_active()`, then delete it**

`_latch_emergency_state` was deleted in Phase A. `_client_emergency_active` was deleted in Phase B. The only remaining helper is `_emergency_active()`, which still has five call sites in navigation endpoints: `control_start_navigation` (~line 1294), `control_resume_navigation` (~line 1342), `control_return_home` (~line 1390), `control_diagnose_stiffness_progressive` (~line 1454), and the heading calibration endpoint (~line 1555).

For each, add `runtime: RuntimeContext = Depends(get_runtime)` to the function signature and replace `if _emergency_active():` with `if runtime.command_gateway.is_emergency_active():`. Example diff pattern:

```python
# Before:
@router.post("/control/start")
async def control_start_navigation():
    ...
    if _emergency_active():

# After:
@router.post("/control/start")
async def control_start_navigation(runtime: RuntimeContext = Depends(get_runtime)):
    ...
    if runtime.command_gateway.is_emergency_active():
```

Apply to all five endpoints. Then verify `_emergency_active` has no remaining callers:

```bash
grep -rn "_emergency_active\b" backend/src/ tests/
```

Expected: only the function definition. Delete it (around line 588, currently ~10 lines).

Also: the `_drive_timeout_task` module-level variable in `rest.py` is now dead (gateway owns the task). Remove it and its import of `asyncio.Task` if the variable is its only use. Verify first:

```bash
grep -n "_drive_timeout_task" backend/src/api/rest.py
```

Delete it if the only remaining occurrence is the module-level declaration.

- [ ] **Step 4.4: Update `conftest.py` to reset via gateway**

In `tests/conftest.py`, update both reset blocks in `reset_control_safety_state` (before-yield and after-yield). Replace the direct mutation block with a gateway call:

```python
@pytest.fixture(autouse=True)
def reset_control_safety_state():
    """Reset shared control emergency/legacy state between tests."""
    def _do_reset():
        # Reset via gateway if runtime is available (Phase D+)
        try:
            from backend.src.main import app
            gw = getattr(getattr(app.state, "runtime", None), "command_gateway", None)
            if gw is not None:
                gw.reset_for_testing()
                return
        except Exception:
            pass
        # Fallback: direct dict reset (unit tests without lifespan)
        try:
            from backend.src.api import rest as rest_api

            rest_api._safety_state["emergency_stop_active"] = False
            rest_api._blade_state["active"] = False
            rest_api._emergency_until = 0.0
            rest_api._client_emergency.clear()
            rest_api._legacy_motors_active = False
        except Exception:
            pass

    _do_reset()

    # ... rest of the existing fixture (auth reset, nav singleton reset) ...

    yield

    _do_reset()

    # ... existing cleanup ...
```

Keep all existing `try/except` blocks below the emergency reset (auth, nav singleton, traction control).

- [ ] **Step 4.5: Update `tests/integration/conftest.py`**

In `tests/integration/conftest.py`, the `_legacy_motors_active` reset fixture:

```python
# Replace:
rest_module._legacy_motors_active = False
# With: (keep _legacy_motors_active for now; it's still in rest.py until fully removed)
try:
    from backend.src.api import rest as rest_module
    rest_module._legacy_motors_active = False
except Exception:
    pass
```

- [ ] **Step 4.6: Delete `backend/src/services/motor_service.py`**

```bash
git rm backend/src/services/motor_service.py
```

Verify nothing imports it:

```bash
grep -rn "motor_service" backend/src/ tests/ 2>/dev/null | grep -v "motor_gateway\|motor_service\.py"
```

Expected: 0 results (only `motor_service.py` was the file, and `rest.py:790` imported `MotorService` from it — remove that import from `rest.py` too).

Search for and remove any `from ..services.motor_service import MotorService` or similar in `rest.py`.

- [ ] **Step 4.7: Run full test suite**

```bash
SIM_MODE=1 uv run pytest -q 2>&1 | tail -20
```

Expected: 0 failures. Fix any before committing.

- [ ] **Step 4.8: Clean up, lint, commit Phase D**

```bash
git checkout -- data/lawnberry.db-shm data/lawnberry.db-wal config/default.json 2>/dev/null || true
SIM_MODE=1 uv run ruff check backend/src
git add backend/src/control/command_gateway.py \
  backend/src/core/globals.py \
  backend/src/api/rest.py \
  tests/conftest.py \
  tests/integration/conftest.py
git commit -m "$(cat <<'EOF'
feat(control): Phase D — state ownership flip, delete helpers and dead code

Removes _latch_emergency_state, _emergency_active, _client_emergency_active
from rest.py (all callers now use gateway directly). Deletes dead
motor_service.py. Conftest resets via gateway.reset_for_testing() when runtime
is available.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4.9: Open PR and stop**

```bash
gh pr create \
  --title "feat(control): Phase D — state ownership flip + dead code removal" \
  --body "$(cat <<'EOF'
## Summary
- Removes `_latch_emergency_state`, `_emergency_active`, `_client_emergency_active` from `rest.py`
- Deletes `motor_service.py` (dead code superseded by gateway)
- Conftest resets via `gateway.reset_for_testing()` with direct-dict fallback for unit tests

## Test plan
- [ ] `SIM_MODE=1 uv run pytest -q` — 0 failures
- [ ] `grep -rn "_latch_emergency_state" backend/ tests/` — 0 results
- [ ] `SIM_MODE=1 uv run ruff check backend/src` clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Stop here. Wait for merge before Phase E.**

---

## Task 5 — Phase E: Firmware/RoboHAT contract (§11)

Parse firmware version from the RoboHAT boot banner, expose it in `/health` and `/api/v2/hardware/robohat`, add gateway dispatch preflight, and document the protocol.

**Files for this task:**
- Modify: `backend/src/services/robohat_service.py`
- Modify: `backend/src/control/command_gateway.py`
- Modify: `backend/src/api/rest.py` (`/hardware/robohat` endpoint)
- Create: `docs/firmware-contract.md`
- Modify: `tests/unit/test_command_gateway.py`

---

- [ ] **Step 5.1: Write failing tests for firmware preflight**

Append to `tests/unit/test_command_gateway.py`:

```python
# ---- Phase E: firmware preflight ----

@pytest.mark.asyncio
async def test_dispatch_drive_blocked_firmware_unknown():
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    # Simulate robohat connected but firmware_version is None
    gw._robohat = MagicMock(
        status=MagicMock(serial_connected=True, firmware_version=None)
    )
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.3, right=0.3, source="manual", duration_ms=200)
    )
    assert outcome.status == CommandStatus.FIRMWARE_UNKNOWN


@pytest.mark.asyncio
async def test_dispatch_drive_blocked_firmware_incompatible():
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    gw._robohat = MagicMock(
        status=MagicMock(serial_connected=True, firmware_version="0.0.1")
    )
    # 0.0.1 is not in SUPPORTED_FIRMWARE_VERSIONS
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.3, right=0.3, source="manual", duration_ms=200)
    )
    assert outcome.status == CommandStatus.FIRMWARE_INCOMPATIBLE
```

Run to confirm failure:

```bash
SIM_MODE=1 uv run pytest tests/unit/test_command_gateway.py -v -k "firmware" 2>&1 | tail -15
```

Expected: FAIL — firmware checks not yet implemented.

- [ ] **Step 5.2: Add `firmware_version` to `RoboHATStatus`**

In `backend/src/services/robohat_service.py`, add to `RoboHATStatus`:

```python
@dataclass
class RoboHATStatus:
    ...
    firmware_version: str | None = None   # parsed from boot banner; None until connected
```

And update `to_dict` to include it:

```python
def to_dict(self) -> dict[str, Any]:
    return {
        ...,
        "firmware_version": self.firmware_version,
    }
```

- [ ] **Step 5.3: Parse firmware version from boot banner**

In `RoboHATService._handle_incoming_line` (or wherever startup messages are processed), add version parsing. The firmware emits a banner like `LawnBerry RoboHAT v1.2.3` or `firmware:1.2.3` on connect. Search the method that handles serial input for version-like strings:

```bash
grep -n "firmware\|version\|banner\|startup\|handle.*line\|_process" \
  backend/src/services/robohat_service.py | head -20
```

In `_handle_incoming_line` (or equivalent), add:

```python
import re as _re

_VERSION_RE = _re.compile(r"firmware[:\s]+v?(\d+\.\d+[\.\d]*)", _re.I)

def _try_parse_firmware_version(self, line: str) -> None:
    m = _VERSION_RE.search(line)
    if m:
        self.status.firmware_version = m.group(1)
        logger.info("RoboHAT firmware version: %s", self.status.firmware_version)
```

Call `self._try_parse_firmware_version(line)` from the incoming-line handler. Also log at startup when the version is confirmed.

- [ ] **Step 5.4: Add firmware preflight to `dispatch_drive` in gateway**

In `command_gateway.py`, add the `SUPPORTED_FIRMWARE_VERSIONS` constant and preflight check at the top of `dispatch_drive`:

```python
SUPPORTED_FIRMWARE_VERSIONS: frozenset[str] = frozenset({"1.0.0", "1.1.0", "1.2.0", "1.2.1"})
```

At the start of `dispatch_drive`, before the emergency gate, add:

```python
# Firmware preflight (Phase E)
robohat = self._robohat
if robohat and getattr(getattr(robohat, "status", None), "serial_connected", False):
    fw_ver = getattr(robohat.status, "firmware_version", None)
    if fw_ver is None:
        return DriveOutcome(
            status=CommandStatus.FIRMWARE_UNKNOWN,
            audit_id=str(uuid.uuid4()),
            status_reason="firmware_version_not_received",
            active_interlocks=[],
            watchdog_latency_ms=None,
        )
    if fw_ver not in SUPPORTED_FIRMWARE_VERSIONS:
        return DriveOutcome(
            status=CommandStatus.FIRMWARE_INCOMPATIBLE,
            audit_id=str(uuid.uuid4()),
            status_reason=f"firmware_version_unsupported:{fw_ver}",
            active_interlocks=[],
            watchdog_latency_ms=None,
        )
```

Apply the same preflight to `dispatch_blade`.

- [ ] **Step 5.5: Run firmware tests — they should pass now**

```bash
SIM_MODE=1 uv run pytest tests/unit/test_command_gateway.py -v -k "firmware"
```

Expected: PASS.

- [ ] **Step 5.6: Surface `firmware_version` in `/hardware/robohat` response**

In `backend/src/api/rest.py`, the `get_robohat_status` handler already calls `status.to_dict()`. Since `firmware_version` is now in `to_dict()`, it will appear automatically. Add a contract assertion test:

Append to `tests/contract/test_rest_api_control.py`:

```python
def test_robohat_status_includes_firmware_version():
    """firmware_version field must be present in /hardware/robohat response."""
    from fastapi.testclient import TestClient
    from backend.src.main import app

    with TestClient(app) as client:
        r = client.get("/api/v2/hardware/robohat")
    assert r.status_code == 200
    data = r.json()
    assert "firmware_version" in data, "firmware_version field missing from /hardware/robohat"
```

Run it:

```bash
SIM_MODE=1 uv run pytest tests/contract/test_rest_api_control.py::test_robohat_status_includes_firmware_version -v
```

Expected: PASS (field is now in `to_dict`).

- [ ] **Step 5.7: Write `docs/firmware-contract.md`**

Create `docs/firmware-contract.md`:

```markdown
# Firmware/RoboHAT Contract

This document describes the text-protocol contract between the Pi backend and the
RoboHAT RP2040 CircuitPython firmware. It is the reference for `MotorCommandGateway`
correctness and for HIL test design.

## Command Protocol

All commands are newline-terminated ASCII strings sent over USB CDC serial
(baud 115200, or UART equivalents).

| Command | Effect | Ack |
|---------|--------|-----|
| `pwm,<steer_us>,<throttle_us>` | Set motor PWM (1500 = stop, range ~1000–2000) | `PWM_OK` or `OK` within ack_timeout |
| `blade=on` | Engage blade motor | `OK` |
| `blade=off` | Disengage blade motor | `OK` |
| `rc=disable` | Switch to USB control mode | `USB_CONTROL` or `OK` |
| `rc=enable` | Return control to RC receiver | `OK` |

## Acknowledgement Policy

- **Ack timeout:** 350 ms (configurable via `send_motor_command` `ack_timeout` param).
- **Retry policy:** No automatic retry on ack timeout. The gateway returns `TIMED_OUT`
  and the caller is responsible for deciding whether to retry.
- `send_motor_command` uses `_wait_for_pwm_ack` which counts ack events after the
  command is sent. Only acks that arrive after the command is issued are counted.

## Firmware Version

The firmware emits a version banner on USB connect, matching:

```
firmware: <major>.<minor>.<patch>
```

The gateway reads this at startup and exposes it via `RoboHATStatus.firmware_version`.
Supported versions are listed in `MotorCommandGateway.SUPPORTED_FIRMWARE_VERSIONS`.
If the version is `None` (not yet received) or not in the supported set, `dispatch_drive`
and `dispatch_blade` return `FIRMWARE_UNKNOWN` or `FIRMWARE_INCOMPATIBLE` outcomes and
do not dispatch to hardware.

## Hardware Emergency Stop Latch

The firmware has an independent watchdog that halts motors if no command is received
within ~5 seconds (SERIAL_TIMEOUT). This is independent of the software gateway.

Hardware-side estop paths (not dependent on the Pi being healthy):
1. Physical RC emergency button (if wired to RC channel 5 / failsafe)
2. Firmware SERIAL_TIMEOUT watchdog: motors halt if the Pi stops sending commands
3. Power cut to the MDDRC10 motor controller

Software-side `emergency_stop()` sends `pwm,1500,1500` + `blade=off`. This is the
*software* stop path; it does not assert a hardware latch. The gateway holds `_estop_pending`
if the stop is sent while serial is disconnected, and re-sends on reconnect.

## Version Compatibility Matrix

| Firmware version | Supported | Notes |
|---|---|---|
| 1.0.0 | Yes | Initial protocol |
| 1.1.0 | Yes | Added blade=on/off |
| 1.2.0 | Yes | USB timeout behaviour changed |
| 1.2.1 | Yes | Bug fix |
| < 1.0.0 or unknown | No | Gateway returns FIRMWARE_UNKNOWN/INCOMPATIBLE |
```

- [ ] **Step 5.8: Log firmware version at startup**

In `backend/src/main.py`, in the startup log line (around line 214), add firmware version:

```python
_log.info(
    "RuntimeContext ready: navigation=%s mission=%s robohat=%s firmware=%s",
    type(app.state.runtime.navigation).__name__,
    type(app.state.runtime.mission_service).__name__,
    type(app.state.runtime.robohat).__name__ if app.state.runtime.robohat else "none",
    getattr(getattr(getattr(app.state.runtime.robohat, "status", None), "firmware_version", None), "__class__", type(None)).__name__
    if app.state.runtime.robohat is None
    else getattr(getattr(app.state.runtime.robohat, "status", None), "firmware_version", "not_yet_received"),
)
```

Simpler version (less fragile):

```python
_fw = None
if app.state.runtime.robohat:
    _fw = getattr(app.state.runtime.robohat.status, "firmware_version", None)
_log.info(
    "RuntimeContext ready: navigation=%s mission=%s robohat=%s firmware=%s",
    type(app.state.runtime.navigation).__name__,
    type(app.state.runtime.mission_service).__name__,
    type(app.state.runtime.robohat).__name__ if app.state.runtime.robohat else "none",
    _fw or "not_yet_received",
)
```

- [ ] **Step 5.9: Run full test suite**

```bash
SIM_MODE=1 uv run pytest -q 2>&1 | tail -20
```

Expected: 0 failures.

- [ ] **Step 5.10: Clean up, lint, commit Phase E**

```bash
git checkout -- data/lawnberry.db-shm data/lawnberry.db-wal config/default.json 2>/dev/null || true
SIM_MODE=1 uv run ruff check backend/src
git add backend/src/services/robohat_service.py \
  backend/src/control/command_gateway.py \
  backend/src/api/rest.py \
  backend/src/main.py \
  docs/firmware-contract.md \
  tests/unit/test_command_gateway.py \
  tests/contract/test_rest_api_control.py
git commit -m "$(cat <<'EOF'
feat(control): Phase E — firmware version preflight and §11 contract doc

Parses firmware version from RoboHAT boot banner. Gateway dispatch_drive/
dispatch_blade return FIRMWARE_UNKNOWN or FIRMWARE_INCOMPATIBLE when version
is absent or unsupported. Surfaces firmware_version on /hardware/robohat.
Documents the text protocol, ack policy, and hardware estop latch in
docs/firmware-contract.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5.11: Open PR and stop**

```bash
gh pr create \
  --title "feat(control): Phase E — firmware version preflight + §11 contract doc" \
  --body "$(cat <<'EOF'
## Summary
- `RoboHATStatus.firmware_version` populated from boot banner at connect time
- `dispatch_drive`/`dispatch_blade` return `FIRMWARE_UNKNOWN`/`FIRMWARE_INCOMPATIBLE` when hardware connected but version absent or unsupported
- `firmware_version` surfaced in `/api/v2/hardware/robohat` response
- `docs/firmware-contract.md` documents command bytes, ack policy, hardware estop latch, version matrix
- HIL estop latch validation flagged in doc but not gated in CI

## Test plan
- [ ] `SIM_MODE=1 uv run pytest -q` — 0 failures
- [ ] `SIM_MODE=1 uv run pytest tests/unit/test_command_gateway.py -v -k firmware` — 2 new tests pass
- [ ] `SIM_MODE=1 uv run pytest tests/contract/test_rest_api_control.py::test_robohat_status_includes_firmware_version -v` — passes
- [ ] `SIM_MODE=1 uv run ruff check backend/src` clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**All phases complete.**

---

## Verification baseline

After every PR merges, the baseline must hold:

```bash
SIM_MODE=1 uv run pytest -q
# Expected: ≈622+ passed, 0 failures
# (count rises by 3 once PR #48 merges, plus test additions per phase)

SIM_MODE=1 uv run ruff check backend/src
# Expected: no output (clean)

uv lock --check
# Expected: exit 0 (lockfile up to date)
```

Always run `git checkout -- data/lawnberry.db-shm data/lawnberry.db-wal config/default.json` before staging commits (these files are mutated by `pytest` runs and must not be committed).
