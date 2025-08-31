"""
Test suite for Weather Integration Service
Tests weather service functionality, plugin integration, and MQTT communication
"""

import asyncio
import pytest
import pytest_asyncio
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from weather import (
    WeatherService, 
    WeatherPlugin, 
    WeatherCondition, 
    WeatherForecast,
    WeatherSafety,
    MowingConditions
)
from src.hardware.plugin_system import PluginConfig


class TestWeatherService:
    """Test weather service core functionality"""
    
    @pytest_asyncio.fixture
    async def weather_service(self):
        """Create weather service with mock configuration"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config = {
                'api_key': 'test_key',
                'location': {'latitude': 40.7128, 'longitude': -74.0060},
                'cache_duration': 300,
                'temperature_limits': {'min': 5.0, 'max': 40.0},
                'wind_limits': {'max': 10.0}
            }
            import yaml
            yaml.dump(config, f)
            config_path = f.name
        
        # Pass only config_path; WeatherService accepts this and can run in offline/test mode
        service = WeatherService(config_path)

        # Mock the API calls to avoid network
        with patch.object(service, '_fetch_current_weather', new=AsyncMock()) as mock_fetch:
            with patch.object(service, '_fetch_forecast', new=AsyncMock(return_value=[])):
                mock_weather = WeatherCondition(
                    timestamp=datetime.now(),
                    temperature=20.0,
                    humidity=65.0,
                    precipitation=0.0,
                    wind_speed=3.5,
                    wind_direction=180,
                    pressure=1013.25,
                    visibility=10.0,
                    uv_index=5.0,
                    cloud_cover=25.0,
                    condition_code="partly_cloudy",
                    condition_text="Partly Cloudy"
                )
                mock_fetch.return_value = mock_weather

                # For tests, bypass real API requirement: mark initialized without creating HTTP session
                service._initialized = True
                try:
                    yield service
                finally:
                    await service.shutdown()
                    Path(config_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_current_weather(self, weather_service):
        """Test getting current weather conditions"""
        weather = await weather_service.get_current_weather()
        
        assert weather is not None
        assert weather.temperature == 20.0
        assert weather.humidity == 65.0
        assert weather.condition_text == "Partly Cloudy"
    
    @pytest.mark.asyncio
    async def test_mowing_conditions_safe(self, weather_service):
        """Test mowing conditions evaluation - safe conditions"""
        conditions = await weather_service.evaluate_mowing_conditions()
        
        assert conditions.safety_level == WeatherSafety.SAFE
        assert conditions.can_mow == True
        assert len(conditions.reasons) == 0
    
    @pytest.mark.asyncio
    async def test_mowing_conditions_rain(self, weather_service):
        """Test mowing conditions evaluation - rainy conditions"""
        # Mock rainy weather
        with patch.object(weather_service, '_fetch_current_weather') as mock_fetch:
            rainy_weather = WeatherCondition(
                timestamp=datetime.now(),
                temperature=18.0,
                humidity=95.0,
                precipitation=2.5,  # 2.5mm/hour rain
                wind_speed=4.0,
                wind_direction=180,
                pressure=1008.0,
                visibility=5.0,
                uv_index=1.0,
                cloud_cover=90.0,
                condition_code="rain",
                condition_text="Rain"
            )
            mock_fetch.return_value = rainy_weather
            
            conditions = await weather_service.evaluate_mowing_conditions()
            
            assert conditions.safety_level == WeatherSafety.UNSAFE
            assert conditions.can_mow == False
            assert any("Rain detected" in reason for reason in conditions.reasons)
            assert conditions.recommended_delay == 120
    
    @pytest.mark.asyncio
    async def test_mowing_conditions_extreme_temperature(self, weather_service):
        """Test mowing conditions evaluation - extreme temperature"""
        # Mock extreme cold weather
        with patch.object(weather_service, '_fetch_current_weather') as mock_fetch:
            cold_weather = WeatherCondition(
                timestamp=datetime.now(),
                temperature=-5.0,  # Below minimum
                humidity=70.0,
                precipitation=0.0,
                wind_speed=2.0,
                wind_direction=180,
                pressure=1020.0,
                visibility=10.0,
                uv_index=2.0,
                cloud_cover=50.0,
                condition_code="clear",
                condition_text="Clear"
            )
            mock_fetch.return_value = cold_weather
            
            conditions = await weather_service.evaluate_mowing_conditions()
            
            assert conditions.safety_level == WeatherSafety.UNSAFE
            assert conditions.can_mow == False
            assert any("Temperature too low" in reason for reason in conditions.reasons)
    
    @pytest.mark.asyncio
    async def test_mowing_conditions_high_wind(self, weather_service):
        """Test mowing conditions evaluation - high wind"""
        # Mock windy weather
        with patch.object(weather_service, '_fetch_current_weather') as mock_fetch:
            windy_weather = WeatherCondition(
                timestamp=datetime.now(),
                temperature=22.0,
                humidity=60.0,
                precipitation=0.0,
                wind_speed=15.0,  # Above maximum
                wind_direction=180,
                pressure=1010.0,
                visibility=10.0,
                uv_index=6.0,
                cloud_cover=30.0,
                condition_code="windy",
                condition_text="Windy"
            )
            mock_fetch.return_value = windy_weather
            
            conditions = await weather_service.evaluate_mowing_conditions()
            
            assert conditions.safety_level == WeatherSafety.UNSAFE
            assert conditions.can_mow == False
            assert any("Wind too strong" in reason for reason in conditions.reasons)
    
    @pytest.mark.asyncio
    async def test_mowing_conditions_with_local_sensor(self, weather_service):
        """Test mowing conditions with local sensor data"""
        local_data = {
            'humidity': 97.0,  # High humidity indicating recent rain
            'temperature': 21.0,
            'pressure': 1012.0
        }
        
        conditions = await weather_service.evaluate_mowing_conditions(local_data)
        
        # Should be cautious due to high local humidity
        assert conditions.safety_level in [WeatherSafety.CAUTION, WeatherSafety.SAFE]
        if conditions.safety_level == WeatherSafety.CAUTION:
            assert any("High local humidity" in reason for reason in conditions.reasons)
    
    @pytest.mark.asyncio
    async def test_solar_prediction(self, weather_service):
        """Test solar charging predictions"""
        with patch.object(weather_service, 'get_forecast') as mock_forecast:
            mock_forecast_data = [
                WeatherForecast(
                    date=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                    temp_high=25.0,
                    temp_low=15.0,
                    precipitation_chance=10.0,
                    precipitation_amount=0.0,
                    wind_speed=4.0,
                    condition_code="sunny",
                    condition_text="Sunny",
                    sunrise=datetime.now().replace(hour=6, minute=30),
                    sunset=datetime.now().replace(hour=19, minute=45),
                    uv_index=6.0,
                    humidity=60.0
                )
            ]
            mock_forecast.return_value = mock_forecast_data
            
            predictions = await weather_service.predict_solar_charging(hours_ahead=12)
            
            assert len(predictions) > 0
            # Check that predictions are tuples of (datetime, efficiency)
            for dt, efficiency in predictions:
                assert isinstance(dt, datetime)
                assert 0.0 <= efficiency <= 1.0


class TestWeatherPlugin:
    """Test weather plugin integration"""
    
    @pytest_asyncio.fixture
    async def weather_plugin(self):
        """Create weather plugin with mock weather service"""
        config = PluginConfig(
            name="weather_test",
            enabled=True,
            parameters={'config_path': None}
        )
        
        plugin = WeatherPlugin(config, {})
        
        # Mock the weather service
        mock_weather_service = Mock()
        mock_weather_service.initialize = AsyncMock(return_value=True)
        mock_weather_service.shutdown = AsyncMock()
        mock_weather_service.get_current_weather = AsyncMock()
        mock_weather_service.evaluate_mowing_conditions = AsyncMock()
        mock_weather_service.get_forecast = AsyncMock()
        mock_weather_service.predict_solar_charging = AsyncMock()
        mock_weather_service.get_weather_trends = AsyncMock()
        
        plugin.weather_service = mock_weather_service
        
        if await plugin.initialize():
            yield plugin
        else:
            pytest.fail("Failed to initialize weather plugin")
        
        await plugin.shutdown()
    
    @pytest.mark.asyncio
    async def test_plugin_initialization(self, weather_plugin):
        """Test plugin initialization"""
        assert weather_plugin.is_initialized
        assert weather_plugin.plugin_type == "weather_service"
        assert weather_plugin.required_managers == []
    
    @pytest.mark.asyncio
    async def test_plugin_read_data(self, weather_plugin):
        """Test reading data from weather plugin"""
        # Setup mock data
        mock_weather = WeatherCondition(
            timestamp=datetime.now(),
            temperature=22.0,
            humidity=70.0,
            precipitation=0.0,
            wind_speed=5.0,
            wind_direction=180,
            pressure=1015.0,
            visibility=10.0,
            uv_index=4.0,
            cloud_cover=40.0,
            condition_code="partly_cloudy",
            condition_text="Partly Cloudy"
        )
        
        mock_conditions = MowingConditions(
            safety_level=WeatherSafety.SAFE,
            can_mow=True,
            recommended_delay=None,
            reasons=[],
            optimal_window_start=None,
            optimal_window_end=None
        )
        
        weather_plugin.weather_service.get_current_weather.return_value = mock_weather
        weather_plugin.weather_service.evaluate_mowing_conditions.return_value = mock_conditions
        
        # Read sensor data
        reading = await weather_plugin.read_data()
        
        assert reading is not None
        assert reading.sensor_id == "weather_test"
        assert reading.unit == "weather_data"
        assert isinstance(reading.value, dict)
        assert 'temperature' in reading.value
        assert 'can_mow' in reading.value
        assert 'safety_level' in reading.value
        assert reading.value['can_mow'] == True
        assert reading.value['safety_level'] == 'safe'
    
    @pytest.mark.asyncio
    async def test_plugin_safety_check(self, weather_plugin):
        """Test plugin safety check functionality"""
        mock_conditions = MowingConditions(
            safety_level=WeatherSafety.UNSAFE,
            can_mow=False,
            recommended_delay=60,
            reasons=["Rain detected"],
            optimal_window_start=None,
            optimal_window_end=None
        )
        
        weather_plugin._last_conditions = mock_conditions
        
        is_safe = await weather_plugin.is_safe_to_mow()
        assert is_safe == False
    
    @pytest.mark.asyncio
    async def test_plugin_local_sensor_update(self, weather_plugin):
        """Test updating local sensor data"""
        local_data = {
            'temperature': 23.5,
            'humidity': 75.0,
            'pressure': 1018.0
        }
        
        await weather_plugin.update_local_sensor_data(local_data)
        
        assert weather_plugin._local_sensor_data == local_data


class TestWeatherIntegration:
    """Test overall weather integration"""
    
    @pytest.mark.asyncio
    async def test_weather_decision_making_scenarios(self):
        """Test various weather decision making scenarios"""
        scenarios = [
            {
                'name': 'Perfect conditions',
                'weather': {
                    'temperature': 22.0,
                    'humidity': 60.0,
                    'precipitation': 0.0,
                    'wind_speed': 3.0
                },
                'expected_safe': True,
                'expected_level': WeatherSafety.SAFE
            },
            {
                'name': 'Light rain',
                'weather': {
                    'temperature': 18.0,
                    'humidity': 85.0,
                    'precipitation': 0.5,
                    'wind_speed': 4.0
                },
                'expected_safe': False,
                'expected_level': WeatherSafety.UNSAFE
            },
            {
                'name': 'Too hot',
                'weather': {
                    'temperature': 45.0,
                    'humidity': 40.0,
                    'precipitation': 0.0,
                    'wind_speed': 2.0
                },
                'expected_safe': False,
                'expected_level': WeatherSafety.UNSAFE
            },
            {
                'name': 'Too cold',
                'weather': {
                    'temperature': 2.0,
                    'humidity': 70.0,
                    'precipitation': 0.0,
                    'wind_speed': 3.0
                },
                'expected_safe': False,
                'expected_level': WeatherSafety.UNSAFE
            },
            {
                'name': 'Too windy',
                'weather': {
                    'temperature': 20.0,
                    'humidity': 65.0,
                    'precipitation': 0.0,
                    'wind_speed': 12.0
                },
                'expected_safe': False,
                'expected_level': WeatherSafety.UNSAFE
            }
        ]
        
        for scenario in scenarios:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                config = {
                    'api_key': 'test_key',
                    'location': {'latitude': 40.7128, 'longitude': -74.0060},
                    'temperature_limits': {'min': 5.0, 'max': 40.0},
                    'wind_limits': {'max': 10.0}
                }
                import yaml
                yaml.dump(config, f)
                config_path = f.name
            
            service = WeatherService(config_path)
            
            # Mock weather data
            mock_weather = WeatherCondition(
                timestamp=datetime.now(),
                temperature=scenario['weather']['temperature'],
                humidity=scenario['weather']['humidity'],
                precipitation=scenario['weather']['precipitation'],
                wind_speed=scenario['weather']['wind_speed'],
                wind_direction=180,
                pressure=1013.25,
                visibility=10.0,
                uv_index=5.0,
                cloud_cover=25.0,
                condition_code="test",
                condition_text="Test"
            )
            
            with patch.object(service, '_fetch_current_weather', new=AsyncMock(return_value=mock_weather)):
                # Bypass real initialization and networking
                service._initialized = True
                # Proceed to evaluate conditions directly
                conditions = await service.evaluate_mowing_conditions()
                
                assert conditions.can_mow == scenario['expected_safe'], \
                    f"Scenario '{scenario['name']}' failed: expected can_mow={scenario['expected_safe']}, got {conditions.can_mow}"
                
                assert conditions.safety_level == scenario['expected_level'], \
                    f"Scenario '{scenario['name']}' failed: expected level={scenario['expected_level']}, got {conditions.safety_level}"
                
                await service.shutdown()
            
            Path(config_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
