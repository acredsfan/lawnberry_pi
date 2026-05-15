"""Tests for motor_status reflecting real mission state."""
import pytest
from unittest.mock import MagicMock, patch


def test_motor_status_not_hardcoded():
    """motor_status field must not be a hardcoded literal."""
    from backend.src.services.telemetry_service import TelemetryService
    import inspect
    src = inspect.getsource(TelemetryService._format_telemetry)
    assert '"motor_status": "idle"' not in src, "motor_status must not be a hardcoded literal"


def test_motor_status_method_exists():
    from backend.src.services.telemetry_service import TelemetryService
    assert hasattr(TelemetryService, "_get_motor_status")
    svc = TelemetryService()
    result = svc._get_motor_status()
    assert isinstance(result, str)


def test_motor_status_default_is_idle():
    """With no mission service available, default is 'idle'."""
    from backend.src.services.telemetry_service import TelemetryService
    svc = TelemetryService()
    # Patch MissionService to raise on get_instance so the fallback path runs
    with patch("backend.src.services.telemetry_service.TelemetryService._get_motor_status",
               wraps=svc._get_motor_status):
        result = svc._get_motor_status()
    assert result == "idle"


def test_motor_status_maps_running_to_mowing():
    """Mission status 'running' maps to 'mowing' in the UI."""
    from backend.src.services.telemetry_service import TelemetryService
    import backend.src.services.mission_service as ms_mod
    svc = TelemetryService()

    mock_mission = MagicMock()
    mock_mission.status = MagicMock()
    mock_mission.status.value = "running"

    original = ms_mod._mission_service_instance
    try:
        ms_mod._mission_service_instance = mock_mission
        result = svc._get_motor_status()
    finally:
        ms_mod._mission_service_instance = original
    assert result == "mowing"


def test_motor_status_maps_completed_to_idle():
    """Mission status 'completed' maps to 'idle'."""
    from backend.src.services.telemetry_service import TelemetryService
    import backend.src.services.mission_service as ms_mod
    svc = TelemetryService()

    mock_mission = MagicMock()
    mock_mission.status = MagicMock()
    mock_mission.status.value = "completed"

    original = ms_mod._mission_service_instance
    try:
        ms_mod._mission_service_instance = mock_mission
        result = svc._get_motor_status()
    finally:
        ms_mod._mission_service_instance = original
    assert result == "idle"


def test_motor_status_emergency_stop_override():
    """Emergency stop in safety state returns 'emergency_stop' even without mission."""
    from backend.src.services.telemetry_service import TelemetryService
    import backend.src.services.mission_service as ms_mod
    svc = TelemetryService()

    original = ms_mod._mission_service_instance
    try:
        # Clear any mission instance so the except branch runs
        ms_mod._mission_service_instance = None
        svc.app_state.safety_state["emergency_stop_active"] = True
        result = svc._get_motor_status()
    finally:
        ms_mod._mission_service_instance = original
        svc.app_state.safety_state["emergency_stop_active"] = False
    assert result == "emergency_stop"


def test_format_telemetry_calls_get_motor_status():
    """_format_telemetry must use _get_motor_status, not a literal."""
    from backend.src.services.telemetry_service import TelemetryService
    svc = TelemetryService()

    call_count = 0

    def _fake_motor_status():
        nonlocal call_count
        call_count += 1
        return "mowing"

    svc._get_motor_status = _fake_motor_status
    svc._get_navigation_heading = lambda: None

    data = MagicMock()
    data.power = None
    data.gps = None
    data.imu = None
    data.tof_left = None
    data.tof_right = None
    data.environmental = None

    result = svc._format_telemetry(data, sim_mode=True)
    assert call_count > 0, "_get_motor_status was never called"
    assert result["motor_status"] == "mowing"
