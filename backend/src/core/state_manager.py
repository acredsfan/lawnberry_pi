import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class AppState:
    """Holds shared application state."""
    safety_state: Dict[str, Any] = field(default_factory=lambda: {"emergency_stop_active": False})
    debug_overrides: Dict[str, Any] = field(default_factory=dict)
    hardware_config: Optional[Any] = None
    sensor_manager: Optional[Any] = None
    ntrip_forwarder: Optional[Any] = None
    
    # Singleton instance
    _instance: Optional['AppState'] = None

    @classmethod
    def get_instance(cls) -> 'AppState':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

# Global accessors for backward compatibility during refactor
def get_safety_state() -> Dict[str, Any]:
    return AppState.get_instance().safety_state

def get_debug_overrides() -> Dict[str, Any]:
    return AppState.get_instance().debug_overrides

def set_hardware_config(config: Any) -> None:
    AppState.get_instance().hardware_config = config

def get_hardware_config() -> Optional[Any]:
    return AppState.get_instance().hardware_config

def set_sensor_manager(manager: Any) -> None:
    AppState.get_instance().sensor_manager = manager

def get_sensor_manager() -> Optional[Any]:
    return AppState.get_instance().sensor_manager
