import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """Holds shared application state."""

    safety_state: dict[str, Any] = field(default_factory=lambda: {"emergency_stop_active": False})
    debug_overrides: dict[str, Any] = field(default_factory=dict)
    hardware_config: Any | None = None
    sensor_manager: Any | None = None
    ntrip_forwarder: Any | None = None

    # Singleton instance
    _instance: Optional["AppState"] = None

    @classmethod
    def get_instance(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# Global accessors for backward compatibility during refactor
def get_safety_state() -> dict[str, Any]:
    return AppState.get_instance().safety_state


def get_debug_overrides() -> dict[str, Any]:
    return AppState.get_instance().debug_overrides


def set_hardware_config(config: Any) -> None:
    AppState.get_instance().hardware_config = config


def get_hardware_config() -> Any | None:
    return AppState.get_instance().hardware_config


def set_sensor_manager(manager: Any) -> None:
    AppState.get_instance().sensor_manager = manager


def get_sensor_manager() -> Any | None:
    return AppState.get_instance().sensor_manager
