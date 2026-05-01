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
| `sensor_manager`  | Live `SensorManager` (or `None`) via property | `AppState.sensor_manager` (read on every access) |
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

### `sensor_manager` is a property, not a stored field

`AppState.sensor_manager` is `None` at lifespan startup and lazy-initialized
later by the telemetry loop. To avoid freezing a `None` snapshot at
RuntimeContext construction, `sensor_manager` is exposed as a `@property`
that reads `AppState.get_instance().sensor_manager` on every access. Routers
that need live sensor access can read `runtime.sensor_manager` directly.
Resolved in Issue #44.

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
