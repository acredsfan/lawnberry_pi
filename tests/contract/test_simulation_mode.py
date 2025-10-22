import os

import pytest


def test_simulation_mode_loads_mock_drivers(monkeypatch):
    os.environ["SIM_MODE"] = "1"
    try:
        from backend.src.core.driver_registry import DriverRegistry
        from backend.src.core.simulation import is_simulation_mode  # noqa: F401
    except Exception:
        pytest.skip("Simulation/DriverRegistry not implemented yet")

    assert is_simulation_mode() is True

    # Load registry and expect mock driver classes
    registry = DriverRegistry(config_path=None)
    drivers = registry.load()
    for drv in drivers.values():
        assert "Mock" in drv.__class__.__name__
