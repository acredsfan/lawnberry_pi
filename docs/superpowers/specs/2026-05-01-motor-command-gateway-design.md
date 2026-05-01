# Motor Command Gateway — Design Spec

**Date:** 2026-05-01
**Plan sections:** §4 (Motor Command Gateway), §11 (Firmware/RoboHAT Contract)
**Status:** Approved, pending implementation plan

---

## Problem

Five module-level globals in `backend/src/core/globals.py` are mutated bidirectionally across four files:

| Symbol | Type | Mutated by |
|---|---|---|
| `_safety_state` | `dict` | `rest.py`, `safety.py` (via `runtime.safety_state`), `navigation_service.py`, `mission_service.py` |
| `_blade_state` | `dict` | `rest.py`, `safety.py` (via `runtime.blade_state`), `navigation_service.py` |
| `_emergency_until` | `float` | `rest.py`, `safety.py` (directly via `rest_api._emergency_until`), `navigation_service.py` |
| `_client_emergency` | `dict[str, float]` | `rest.py`, `safety.py` |
| `_legacy_motors_active` | `bool` | `rest.py`, `navigation_service.py` |

`safety.py` already carries a `# unified under §4 motor gateway` TODO on its `_client_emergency` import. `navigation_service.py` latch-mirrors `rest_api._safety_state` directly. `mission_service.py` reads `rest_api._safety_state` directly.

RoboHAT calls (`send_motor_command`, `send_blade_command`, `emergency_stop`, `clear_emergency`) are duplicated across `/control/drive`, `/control/blade`, `/control/emergency`, `/control/emergency_clear` with inconsistent ack handling, rate-limiting, and audit shapes. It is not possible to prove that every motion path respects the same safety policy without reading all four.

---

## Goal

A single `MotorCommandGateway` that:
- is the only in-process code path from "desired motion" to RoboHAT PWM
- owns all emergency state (latched flag, reason, short-lived TTL, per-client TTL, blade-active flag)
- gates every command through the same safety checks
- makes command outcomes testable without serial hardware

---

## New Package: `backend/src/control/`

### `commands.py` — typed commands and outcomes

**Commands (internal dataclasses, not pydantic):**

```python
@dataclass
class DriveCommand:
    left: float          # -1.0 .. 1.0
    right: float         # -1.0 .. 1.0
    source: str          # "manual" | "mission" | "diagnosis"
    duration_ms: int     # auto-stop deadline; 0 = use default ceiling
    session_id: str | None = None
    max_speed_limit: float = 0.8

@dataclass
class BladeCommand:
    active: bool
    source: str          # "manual" | "mission"
    session_id: str | None = None

@dataclass
class EmergencyTrigger:
    reason: str
    source: str          # "operator" | "navigation" | "safety_trigger"
    request: Request | None = None   # for per-client TTL keying

@dataclass
class EmergencyClear:
    confirmed: bool      # must be True; gateway rejects if False
    operator: str | None = None
```

**Outcomes (dataclasses):**

```python
class CommandStatus(str, Enum):
    ACCEPTED      = "accepted"
    BLOCKED       = "blocked"
    QUEUED        = "queued"       # hardware absent; command acknowledged
    TIMED_OUT     = "timed_out"
    ACK_FAILED    = "ack_failed"
    EMERGENCY_LATCHED = "emergency_latched"
    FIRMWARE_UNKNOWN  = "firmware_unknown"     # Phase E
    FIRMWARE_INCOMPATIBLE = "firmware_incompatible"  # Phase E

@dataclass
class DriveOutcome:
    status: CommandStatus
    audit_id: str
    status_reason: str | None
    active_interlocks: list[str]
    watchdog_latency_ms: float | None
    timestamp: str

@dataclass
class BladeOutcome:
    status: CommandStatus
    audit_id: str
    status_reason: str | None
    timestamp: str

@dataclass
class EmergencyOutcome:
    status: CommandStatus
    audit_id: str
    hardware_confirmed: bool
    idempotent: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
```

### `command_gateway.py` — `MotorCommandGateway`

**Constructor:**

```python
class MotorCommandGateway:
    def __init__(
        self,
        safety_state: dict,       # same dict ref as core.globals._safety_state
        blade_state: dict,        # same dict ref as core.globals._blade_state
        client_emergency: dict,   # same dict ref as core.globals._client_emergency
        robohat: Any,
        persistence: Any,
    ): ...
```

In Phase A–C the constructor receives the existing dict references from `main.py` lifespan so that legacy callers reading the globals still see live state. `_emergency_until` (a bare float) is immutable and cannot be shared by reference; in Phase A–C the gateway imports `backend.src.core.globals` and reads/writes `_g._emergency_until` directly. In Phase D the gateway internalises all state and the globals become shims.

**Public async API:**

```python
async def dispatch_drive(cmd: DriveCommand, request: Request | None = None) -> DriveOutcome
async def dispatch_blade(cmd: BladeCommand, request: Request | None = None) -> BladeOutcome
async def trigger_emergency(cmd: EmergencyTrigger) -> EmergencyOutcome
async def clear_emergency(cmd: EmergencyClear) -> EmergencyOutcome
def is_emergency_active(request: Request | None = None) -> bool
def reset_for_testing() -> None    # clears all state; called by conftest autouse in Phase D
```

**Gateway responsibilities (unchanged from §4 plan):**
1. Apply safety gates (emergency-active check, client-TTL check, blade-while-motors interlock, manual-drive interlocks)
2. Send command to RoboHAT (`robohat.send_motor_command` / `send_blade_command` / `emergency_stop` / `clear_emergency`)
3. Require firmware acknowledgement (existing ack mechanism in `send_motor_command` / `_wait_for_pwm_ack`)
4. Update command audit logs via `persistence.add_audit_log`
5. Return typed outcome; caller maps to HTTP response shape

**Safety gating order (drive):**
1. `is_emergency_active(request)` — combines latch check (`_safety_state["emergency_stop_active"]`) and short-lived TTL and per-client TTL; returns BLOCKED if any is true
2. Manual-drive interlocks (telemetry freshness, location accuracy, obstacle distance) — hardware-only, skipped in SIM_MODE; returns BLOCKED with active_interlocks list
3. RoboHAT dispatch → ACCEPTED / QUEUED / ACK_FAILED / TIMED_OUT
4. Auto-stop task creation (cancels previous, schedules stop after `duration_ms`)

---

## Wiring Through RuntimeContext

New field added to `RuntimeContext` dataclass:

```python
command_gateway: Any   # MotorCommandGateway; Any to avoid import cycle in Phase A
```

Constructed in `backend/src/main.py` lifespan after RoboHAT service initialises:

```python
from .control.command_gateway import MotorCommandGateway
app.state.runtime = RuntimeContext(
    ...,
    command_gateway=MotorCommandGateway(
        safety_state=global_state._safety_state,
        blade_state=global_state._blade_state,
        ...
    ),
)
```

Tests inject a fake gateway via `app.dependency_overrides[get_runtime]`, matching the §1 RuntimeContext pattern.

---

## Phased Delivery

Each phase is one PR. The acceptance test suite (≈622 passed) must remain green after every phase.

### Phase A — Gateway skeleton + emergency endpoints

**Files changed:**
- New: `backend/src/control/__init__.py`, `commands.py`, `command_gateway.py`
- Modified: `backend/src/core/runtime.py` (add `command_gateway` field)
- Modified: `backend/src/main.py` (construct gateway in lifespan)
- Modified: `backend/src/api/rest.py` (`control_emergency_v2` and `control_emergency_stop_alias` call `runtime.command_gateway.trigger_emergency(...)` rather than `_latch_emergency_state`; the `_latch_emergency_state` helper is kept for now since it is called from contexts that may not have runtime)
- Modified: `backend/src/api/safety.py` (`clear_emergency_stop` calls `runtime.command_gateway.clear_emergency(...)`)

**No behavior change.** All HTTP response shapes identical. The `_latch_emergency_state` / `_emergency_active` helpers remain in `rest.py` through Phase C; they are deleted in Phase D.

**New tests:** `tests/unit/test_command_gateway.py` — emergency lifecycle (trigger, idempotent trigger, clear-without-confirmation 422, clear-with-confirmation, is_emergency_active).

### Phase B — Drive and blade dispatch

**Files changed:**
- Modified: `backend/src/api/rest.py` (`control_drive_v2`, `control_blade_v2` call gateway methods; response built from `DriveOutcome`/`BladeOutcome`)
- Modified: `backend/src/control/command_gateway.py` (drive and blade dispatch implemented)

**Behavior change inside gateway:** RoboHAT call, ack wait, auto-stop task, and 1 Hz audit sampling all move inside gateway. HTTP response shapes remain byte-compatible (verified by `tests/contract/test_rest_api_control.py`).

**New tests:** gateway drive blocked/queued/ack-failed outcomes; blade interlock while legacy-motors-active.

### Phase C — Navigation and mission service migration

**Files changed:**
- Modified: `backend/src/services/navigation_service.py` — `_global_emergency_active` reads via `gateway.is_emergency_active()`; `_latch_global_emergency_state` calls `gateway.trigger_emergency(...)`; no more direct `rest_api._safety_state` imports
- Modified: `backend/src/services/mission_service.py` — reads emergency state via `gateway.is_emergency_active()`

**Invariant:** `test_safety_router_runtime.py::test_safety_py_does_not_import_state_directly` already guards `safety.py`; analogous guards added for `navigation_service.py` and `mission_service.py`.

### Phase D — State ownership flip + cleanup

**Files changed:**
- Modified: `backend/src/control/command_gateway.py` — emergency state stored internally in `EmergencyState` dataclass; no longer wraps globals
- Modified: `backend/src/core/globals.py` — `_safety_state`, `_blade_state`, `_emergency_until`, `_client_emergency` become read-only shim properties that delegate to the gateway's `EmergencyState`
- Modified: `backend/src/api/rest.py` — `_latch_emergency_state`, `_emergency_active`, `_client_emergency_active` helpers deleted; their call sites call gateway directly
- Modified: `tests/conftest.py`, `tests/integration/conftest.py` — reset via `gateway.reset_for_testing()` instead of mutating globals
- Deleted: `backend/src/services/motor_service.py` (dead code; gateway supersedes it)
- Deleted: `_legacy_motors_active` from globals (absorbed into gateway as `_motors_active: bool`)

**Tests:** verify that after `gateway.reset_for_testing()` all state is clean; existing integration tests still pass.

### Phase E — Firmware/RoboHAT contract (§11)

**Files changed:**
- Modified: `backend/src/services/robohat_service.py` — parse firmware version from boot banner; expose `firmware_version: str | None` on `RoboHATStatus`
- Modified: `backend/src/control/command_gateway.py` — preflight check: if `robohat.status.firmware_version is None` and hardware present, `dispatch_drive`/`dispatch_blade` return `firmware_unknown` outcome; if version does not match `SUPPORTED_FIRMWARE_VERSIONS`, return `firmware_incompatible`
- Modified: `backend/src/api/rest.py` `/hardware/robohat` endpoint — surface `firmware_version` field
- New: `docs/firmware-contract.md` — command bytes, ack format, ack-timeout budget, retry policy, hardware-latch behavior, firmware version compatibility matrix
- Modified: startup log — log firmware version at `INFO` level

**New tests:** gateway simulated firmware-version mismatch, simulated ack timeout.
**Note:** HIL validation of hardware-side estop latch is flagged in the doc but not gated in CI.

---

## Non-Behavioral Invariants (all phases)

- **Audit event names and shapes** remain byte-compatible through Phase D. Normalization is a follow-up task.
- **Hardware estop boundary:** `RoboHATService.emergency_stop()` retains its `_estop_pending` queue-on-disconnect; watchdog task is untouched.
- **SIM_MODE=1** skips all RoboHAT calls; gateway must produce the same `QUEUED` / accepted responses as today.
- **Test reset:** conftest autouse resets all gateway state between tests. No test leaks emergency latch to the next test.

---

## Test File Map

| File | Coverage |
|---|---|
| `tests/unit/test_command_gateway.py` | Gateway unit tests — grows each phase |
| `tests/contract/test_rest_api_control.py` | HTTP shape lock — must stay green every phase |
| `tests/integration/test_control_manual_flow.py` | End-to-end drive + emergency flow |
| `tests/integration/test_safety_router_runtime.py` | Import-purity guards (extend in Phase C) |
| `tests/integration/test_runtime_lifespan.py` | Lifespan wiring — add gateway field assertion in Phase A |

---

## Out of Scope

- Removing `AppState` (explicit §4 deferral, stays until all consumers migrate).
- `RuntimeContext` field type tightening (deferred to Phase 2 service split per §1 design).
- Audit shape normalization (post-§4 cleanup, flagged in architecture plan §6).
- Frontend changes (API shapes preserved; no frontend impact).
