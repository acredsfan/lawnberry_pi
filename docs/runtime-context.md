# Runtime Context

The `RuntimeContext` (`backend/src/core/runtime.py`) is the typed dependency
that safety-critical FastAPI routers receive instead of importing module-level
globals or calling `.get_instance()` chains. It implements §1 of the
architecture plan.

## Shape

`RuntimeContext` is a `@dataclass` with these fields:

| Field             | What it is                                | Source                                        |
| ----------------- | ----------------------------------------- | --------------------------------------------- |
| `config_loader`   | The `ConfigLoader` singleton              | `backend/src/core/config_loader.py`           |
| `hardware_config` | Loaded `HardwareConfig`                   | YAML via `ConfigLoader().get()`               |
| `safety_limits`   | Loaded `SafetyLimits`                     | YAML via `ConfigLoader().get()`               |
| `sensor_manager`  | `SensorManager` snapshot                  | `AppState.sensor_manager` (see caveat below)  |
| `navigation`      | `NavigationService` singleton             | `NavigationService.get_instance()`            |
| `mission_service` | `MissionService` instance                 | `get_mission_service(...)`                    |
| `safety_state`    | Live emergency-stop dict                  | `core/globals._safety_state` (same dict)      |
| `blade_state`     | Live blade-active dict                    | `core/globals._blade_state` (same dict)       |
| `robohat`         | `RoboHATService` or `None`                | `get_robohat_service()`                       |
| `websocket_hub`   | `WebSocketHub` module-level singleton     | `services/websocket_hub.websocket_hub`        |
| `persistence`     | `PersistenceLayer` module-level singleton | `core/persistence.persistence`                |

The fields are *references*, not copies. Mutations to `runtime.safety_state`
propagate to `core/globals._safety_state` and vice versa, because they're the
same dict object. This lets new and legacy code paths coexist without
diverging.

### Known caveat: `sensor_manager` is a snapshot, not a live reference

At lifespan-construction time, `AppState.sensor_manager` is typically `None`
because the telemetry loop initializes it lazily on first use. The runtime
captures whatever is there *at that moment*, so `runtime.sensor_manager` is
likely `None` for the lifetime of the process even after `AppState`'s
attribute is set. **Do not migrate routers to `runtime.sensor_manager` until
this is fixed** — fall back to `AppState.get_instance().sensor_manager` for
live reads, or use the existing telemetry/websocket access paths. See the
TODO at `backend/src/main.py` near the runtime construction. Tracked as a
follow-up; will be fixed when `sensor_manager` becomes a property that
delegates to AppState.

## Using it from a router

```python
from fastapi import APIRouter, Depends

from ..core.runtime import RuntimeContext, get_runtime

router = APIRouter()


@router.post("/example")
async def example(runtime: RuntimeContext = Depends(get_runtime)):
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
