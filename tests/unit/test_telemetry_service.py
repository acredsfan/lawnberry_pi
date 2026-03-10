import pytest
import asyncio
from unittest.mock import MagicMock, patch
from backend.src.services.telemetry_service import TelemetryService
from backend.src.core.state_manager import AppState

@pytest.mark.asyncio
async def test_telemetry_service_initialization():
    service = TelemetryService()
    # Mock AppState
    with patch('backend.src.core.state_manager.AppState.get_instance') as mock_get_instance:
        mock_app_state = MagicMock()
        mock_app_state.sensor_manager = None
        mock_get_instance.return_value = mock_app_state
        service.app_state = mock_app_state
        
        # Mock SensorManager init
        with patch('backend.src.services.sensor_manager.SensorManager') as MockSensorManager:
            mock_manager = MockSensorManager.return_value
            mock_manager.initialize = MagicMock(side_effect=lambda: asyncio.sleep(0))
            
            await service.initialize_sensors()
            
            assert service.app_state.sensor_manager is not None
            mock_manager.initialize.assert_called_once()

@pytest.mark.asyncio
async def test_get_telemetry_simulated():
    service = TelemetryService()
    # Mock AppState
    mock_app_state = MagicMock()
    mock_app_state.sensor_manager = None
    service.app_state = mock_app_state
    
    # Force sim mode via argument
    telemetry = await service.get_telemetry(sim_mode=True)
    
    assert telemetry["simulated"] is True
    assert "battery" in telemetry
    assert "position" in telemetry
    assert telemetry["source"] == "simulated"

@pytest.mark.asyncio
async def test_get_telemetry_hardware():
    service = TelemetryService()
    mock_app_state = MagicMock()
    mock_manager = MagicMock()
    mock_manager.initialized = True
    
    # Mock sensor data
    mock_data = MagicMock()
    mock_data.power.battery_voltage = 12.5
    mock_data.gps.latitude = 40.0
    
    # Make read_all_sensors awaitable
    future = asyncio.Future()
    future.set_result(mock_data)
    mock_manager.read_all_sensors.return_value = future
    
    mock_app_state.sensor_manager = mock_manager
    service.app_state = mock_app_state
    
    telemetry = await service.get_telemetry(sim_mode=False)
    
    assert telemetry["simulated"] is False
    assert telemetry["source"] == "hardware"
    assert telemetry["battery"]["voltage"] == 12.5
    assert telemetry["position"]["latitude"] == 40.0
