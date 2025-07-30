"""
Weather Plugin for Hardware Interface Integration
Provides weather data as a standardized sensor plugin
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from ..hardware.plugin_system import HardwarePlugin, PluginConfig
from ..hardware.data_structures import SensorReading
from .weather_service import WeatherService, WeatherCondition, MowingConditions


class WeatherPlugin(HardwarePlugin):
    """Weather service plugin for hardware interface integration"""
    
    def __init__(self, config: PluginConfig, managers: Dict[str, Any]):
        super().__init__(config, managers)
        self.weather_service = WeatherService(
            config_path=config.parameters.get('config_path', 'config/weather.yaml')
        )
        self._last_conditions: Optional[MowingConditions] = None
        self._local_sensor_data: Dict[str, Any] = {}
    
    @property
    def plugin_type(self) -> str:
        return "weather_service"
    
    @property
    def required_managers(self) -> List[str]:
        return []  # Weather service doesn't require hardware managers
    
    async def initialize(self) -> bool:
        """Initialize the weather plugin"""
        async with self._lock:
            if self._initialized:
                return True
            
            try:
                self.logger.info("Initializing weather plugin...")
                
                # Initialize the weather service
                success = await self.weather_service.initialize()
                if not success:
                    self.logger.error("Failed to initialize weather service")
                    return False
                
                self.health.mark_success()
                self._initialized = True
                self.logger.info("Weather plugin initialized successfully")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to initialize weather plugin: {e}")
                self.health.mark_failure()
                return False
    
    async def read_data(self) -> Optional[SensorReading]:
        """Read current weather data as sensor reading"""
        if not self._initialized:
            return None
        
        try:
            # Get current weather conditions
            weather = await self.weather_service.get_current_weather()
            if not weather:
                self.health.mark_failure()
                return None
            
            # Evaluate mowing conditions with local sensor data
            conditions = await self.weather_service.evaluate_mowing_conditions(
                self._local_sensor_data
            )
            self._last_conditions = conditions
            
            # Create comprehensive weather sensor reading
            weather_data = {
                'temperature': weather.temperature,
                'humidity': weather.humidity,
                'precipitation': weather.precipitation,
                'wind_speed': weather.wind_speed,
                'wind_direction': weather.wind_direction,
                'pressure': weather.pressure,
                'visibility': weather.visibility,
                'uv_index': weather.uv_index,
                'cloud_cover': weather.cloud_cover,
                'condition': weather.condition_text,
                'safety_level': conditions.safety_level.value,
                'can_mow': conditions.can_mow,
                'recommended_delay': conditions.recommended_delay,
                'reasons': conditions.reasons
            }
            
            self.health.mark_success()
            
            return SensorReading(
                timestamp=weather.timestamp,
                sensor_id=self.config.name,
                value=weather_data,
                unit="weather_data",
                quality=1.0,
                metadata={
                    'source': 'google_weather_api',
                    'location': {
                        'lat': self.weather_service.config['location']['latitude'],
                        'lon': self.weather_service.config['location']['longitude']
                    }
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to read weather data: {e}")
            self.health.mark_failure()
            return None
    
    async def get_forecast_data(self, days: int = 7) -> Optional[List[Dict[str, Any]]]:
        """Get weather forecast data"""
        if not self._initialized:
            return None
        
        try:
            forecast = await self.weather_service.get_forecast(days)
            return [
                {
                    'date': f.date.isoformat(),
                    'temp_high': f.temp_high,
                    'temp_low': f.temp_low,
                    'precipitation_chance': f.precipitation_chance,
                    'precipitation_amount': f.precipitation_amount,
                    'wind_speed': f.wind_speed,
                    'condition': f.condition_text,
                    'sunrise': f.sunrise.isoformat(),
                    'sunset': f.sunset.isoformat(),
                    'uv_index': f.uv_index,
                    'humidity': f.humidity
                }
                for f in forecast
            ]
        except Exception as e:
            self.logger.error(f"Failed to get forecast data: {e}")
            return None
    
    async def get_solar_prediction(self, hours_ahead: int = 24) -> Optional[List[Dict[str, Any]]]:
        """Get solar charging predictions"""
        if not self._initialized:
            return None
        
        try:
            predictions = await self.weather_service.predict_solar_charging(hours_ahead)
            return [
                {
                    'datetime': dt.isoformat(),
                    'solar_efficiency': efficiency
                }
                for dt, efficiency in predictions
            ]
        except Exception as e:
            self.logger.error(f"Failed to get solar predictions: {e}")
            return None
    
    async def get_weather_trends(self, days: int = 7) -> Optional[Dict[str, Any]]:
        """Get weather trends for optimization"""
        if not self._initialized:
            return None
        
        try:
            return await self.weather_service.get_weather_trends(days)
        except Exception as e:
            self.logger.error(f"Failed to get weather trends: {e}")
            return None
    
    async def update_local_sensor_data(self, sensor_data: Dict[str, Any]):
        """Update local sensor data for enhanced weather evaluation"""
        self._local_sensor_data.update(sensor_data)
    
    async def get_mowing_conditions(self) -> Optional[MowingConditions]:
        """Get current mowing conditions evaluation"""
        return self._last_conditions
    
    async def is_safe_to_mow(self) -> bool:
        """Quick check if it's currently safe to mow"""
        if not self._last_conditions:
            # Trigger a fresh evaluation
            await self.read_data()
        
        return self._last_conditions.can_mow if self._last_conditions else False
    
    async def get_next_optimal_window(self) -> Optional[Dict[str, str]]:
        """Get the next optimal mowing window"""
        if not self._last_conditions:
            return None
        
        if (self._last_conditions.optimal_window_start and 
            self._last_conditions.optimal_window_end):
            return {
                'start': self._last_conditions.optimal_window_start.isoformat(),
                'end': self._last_conditions.optimal_window_end.isoformat()
            }
        
        return None
    
    async def shutdown(self):
        """Shutdown the weather plugin"""
        if self.weather_service:
            await self.weather_service.shutdown()
        await super().shutdown()
