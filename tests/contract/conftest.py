import os
import os.path
import pytest

# Skip placeholder WebSocket topic tests by default until implemented
RUN_PLACEHOLDER = os.getenv("RUN_PLACEHOLDER_CONTRACT", "0") == "1"

# Placeholder-gated contract tests for upcoming phases
# These are authored first (TDD) and skipped by default to keep CI green.
# Enable with RUN_PLACEHOLDER_CONTRACT=1 to execute (expected to fail until implemented).
PLACEHOLDER_BASENAMES = {
    # Phase 3: Sensors & Extended Safety contract tests
    "test_tof_sensors.py",
    "test_imu_tilt.py",
    "test_bme280.py",
    "test_ina3221.py",
    "test_sensor_fusion.py",
    # Phase 4: Navigation contract tests
    "test_gps.py",
    "test_geofence.py",
    "test_waypoint_navigation.py",
    "test_navigation_modes.py",
}


def pytest_collection_modifyitems(config, items):
    if RUN_PLACEHOLDER:
        return

    skip_placeholder = pytest.mark.skip(
        reason=(
            "Placeholder contract test skipped by default. "
            "Set RUN_PLACEHOLDER_CONTRACT=1 to run."
        )
    )

    for item in items:
        basename = os.path.basename(str(item.fspath))
        if basename in PLACEHOLDER_BASENAMES:
            item.add_marker(skip_placeholder)
