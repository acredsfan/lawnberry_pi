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
    command_gateway: Any = None  # MotorCommandGateway; Any to avoid import cycle
    localization: Any = None     # LocalizationService; Any to avoid import cycle

    @property
    def sensor_manager(self) -> Any:
        from .state_manager import AppState

        return AppState.get_instance().sensor_manager


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
