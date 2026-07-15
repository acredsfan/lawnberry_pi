"""Service package exports without import-time runtime side effects.

Service entrypoints such as ``python -m backend.src.services.camera_stream_service``
must not initialize authentication, navigation, or camera singletons merely because
Python imports the package first. Public convenience exports are therefore lazy.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "AIService": (".ai_service", "AIService"),
    "AuthService": (".auth_service", "AuthService"),
    "CameraClient": (".camera_client", "CameraClient"),
    "NavigationService": (".navigation_service", "NavigationService"),
    "SensorManager": (".sensor_manager", "SensorManager"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*globals(), *__all__])
