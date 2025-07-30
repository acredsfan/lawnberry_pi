"""
Weather Service Integration for LawnBerry Pi Autonomous Mower
Provides Google Weather API integration for enhanced weather awareness and scheduling optimization
"""

import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
import yaml
from pathlib import Path

# Weather data structures
@dataclass
class WeatherCondition:
    """Current weather conditions"""
    timestamp: datetime
    temperature: float  # Celsius
    humidity: float     # Percentage
    precipitation: float  # mm/hour
    wind_speed: float   # m/s
    wind_direction: int  # degrees
    pressure: float     # hPa
    visibility: float   # km
    uv_index: float
    cloud_cover: float  # percentage
    condition_code: str  # Weather condition code
    condition_text: str  # Human readable condition

@dataclass
class WeatherForecast:
    """Weather forecast data"""
    date: datetime
    temp_high: float
    temp_low: float
    precipitation_chance: float  # percentage
    precipitation_amount: float  # mm
    wind_speed: float
    condition_code: str
    condition_text: str
    sunrise: datetime
    sunset: datetime
    uv_index: float
    humidity: float

@dataclass
class WeatherAlert:
    """Weather alert/warning"""
    alert_id: str
    title: str
    description: str
    severity: str  # minor, moderate, severe, extreme
    start_time: datetime
    end_time: datetime
    categories: List[str]

class WeatherSafety(Enum):
    """Weather safety levels for mowing operations"""
    SAFE = "safe"
    CAUTION = "caution"
    UNSAFE = "unsafe"
    EMERGENCY = "emergency"

@dataclass
class MowingConditions:
    """Evaluated mowing conditions based on weather"""
    safety_level: WeatherSafety
    can_mow: bool
    recommended_delay: Optional[int]  # minutes
    reasons: List[str]
    optimal_window_start: Optional[datetime]
    optimal_window_end: Optional[datetime]

class WeatherService:
    """
    Weather service providing Google Weather API integration
    for enhanced weather awareness and scheduling optimization
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.config_path = Path(config_path) if config_path else Path("config/weather.yaml")
        self.config = self._load_config()
        
        # State
        self._current_weather: Optional[WeatherCondition] = None
        self._forecast_data: List[WeatherForecast] = []
        self._active_alerts: List[WeatherAlert] = []
        self._last_api_call = 0
        self._cache_duration = 300  # 5 minutes
        
        # Session for HTTP requests
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Weather patterns and learning
        self._weather_history: List[WeatherCondition] = []
        self._max_history_days = 30
        
        # Temperature limits for operation
        self.temp_min = self.config.get('temperature_limits', {}).get('min', 5.0)  # 5°C
        self.temp_max = self.config.get('temperature_limits', {}).get('max', 40.0)  # 40°C
        self.wind_max = self.config.get('wind_limits', {}).get('max', 10.0)  # 10 m/s
        
        # Integration flags
        self._initialized = False
        self._shutdown_event = asyncio.Event()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load weather service configuration"""
        default_config = {
            'api_key': '',
            'location': {
                'latitude': 40.7128,
                'longitude': -74.0060
            },
            'cache_duration': 300,
            'temperature_limits': {
                'min': 5.0,
                'max': 40.0
            },
            'wind_limits': {
                'max': 10.0
            },
            'api_rate_limit': {
                'calls_per_hour': 100,
                'calls_per_day': 1000
            }
        }
        
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    default_config.update(config)
            except Exception as e:
                self.logger.warning(f"Failed to load weather config: {e}, using defaults")
        
        return default_config
    
    async def initialize(self) -> bool:
        """Initialize the weather service"""
        if self._initialized:
            return True
        
        try:
            self.logger.info("Initializing weather service...")
            
            # Validate API key
            if not self.config.get('api_key'):
                self.logger.error("Google Weather API key not configured")
                return False
            
            # Create HTTP session
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
            # Test API connection
            test_weather = await self._fetch_current_weather()
            if test_weather is None:
                self.logger.error("Failed to connect to weather API")
                return False
            
            # Load historical data if available
            await self._load_weather_history()
            
            self._initialized = True
            self.logger.info("Weather service initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize weather service: {e}")
            return False
    
    async def shutdown(self):
        """Shutdown the weather service"""
        self.logger.info("Shutting down weather service...")
        self._shutdown_event.set()
        
        if self._session:
            await self._session.close()
        
        # Save weather history
        await self._save_weather_history()
        
        self.logger.info("Weather service shut down")
    
    async def get_current_weather(self, force_refresh: bool = False) -> Optional[WeatherCondition]:
        """Get current weather conditions"""
        if not self._initialized:
            return None
        
        # Check cache
        current_time = time.time()
        if (not force_refresh and 
            self._current_weather and 
            current_time - self._last_api_call < self._cache_duration):
            return self._current_weather
        
        # Fetch fresh data
        weather = await self._fetch_current_weather()
        if weather:
            self._current_weather = weather
            self._last_api_call = current_time
            
            # Add to history
            self._weather_history.append(weather)
            self._trim_weather_history()
        
        return self._current_weather
    
    async def get_forecast(self, days: int = 7) -> List[WeatherForecast]:
        """Get weather forecast for specified number of days"""
        if not self._initialized:
            return []
        
        # Check cache
        current_time = time.time()
        if (self._forecast_data and 
            current_time - self._last_api_call < self._cache_duration):
            return self._forecast_data[:days]
        
        # Fetch fresh forecast data
        forecast = await self._fetch_forecast(days)
        if forecast:
            self._forecast_data = forecast
        
        return self._forecast_data[:days]
    
    async def get_weather_alerts(self) -> List[WeatherAlert]:
        """Get active weather alerts"""
        if not self._initialized:
            return []
        
        # This would integrate with weather alert APIs
        # For now, return cached alerts
        return self._active_alerts
    
    async def evaluate_mowing_conditions(self, 
                                       local_sensor_data: Optional[Dict] = None) -> MowingConditions:
        """
        Evaluate current conditions for mowing safety
        Combines weather API data with local BME280 sensor data
        """
        current_weather = await self.get_current_weather()
        if not current_weather:
            return MowingConditions(
                safety_level=WeatherSafety.UNSAFE,
                can_mow=False,
                recommended_delay=60,
                reasons=["Weather data unavailable"],
                optimal_window_start=None,
                optimal_window_end=None
            )
        
        reasons = []
        safety_level = WeatherSafety.SAFE
        can_mow = True
        recommended_delay = None
        
        # Temperature checks
        if current_weather.temperature < self.temp_min:
            reasons.append(f"Temperature too low: {current_weather.temperature:.1f}°C")
            safety_level = WeatherSafety.UNSAFE
            can_mow = False
        elif current_weather.temperature > self.temp_max:
            reasons.append(f"Temperature too high: {current_weather.temperature:.1f}°C")
            safety_level = WeatherSafety.UNSAFE
            can_mow = False
        
        # Precipitation checks
        if current_weather.precipitation > 0.1:  # 0.1mm/hour threshold
            reasons.append(f"Rain detected: {current_weather.precipitation:.1f}mm/h")
            safety_level = WeatherSafety.UNSAFE
            can_mow = False
            recommended_delay = 120  # Wait 2 hours after rain
        
        # Combine with local sensor data if available
        if local_sensor_data and 'humidity' in local_sensor_data:
            local_humidity = local_sensor_data['humidity']
            if local_humidity > 95:  # Very high humidity suggests recent rain
                reasons.append(f"High local humidity: {local_humidity:.1f}%")
                if safety_level == WeatherSafety.SAFE:
                    safety_level = WeatherSafety.CAUTION
        
        # Wind checks
        if current_weather.wind_speed > self.wind_max:
            reasons.append(f"Wind too strong: {current_weather.wind_speed:.1f}m/s")
            safety_level = WeatherSafety.UNSAFE
            can_mow = False
        
        # Check for severe weather alerts
        alerts = await self.get_weather_alerts()
        severe_alerts = [a for a in alerts if a.severity in ['severe', 'extreme']]
        if severe_alerts:
            reasons.extend([f"Weather alert: {a.title}" for a in severe_alerts])
            safety_level = WeatherSafety.EMERGENCY
            can_mow = False
        
        # Find optimal mowing window
        optimal_start, optimal_end = await self._find_optimal_mowing_window()
        
        return MowingConditions(
            safety_level=safety_level,
            can_mow=can_mow,
            recommended_delay=recommended_delay,
            reasons=reasons,
            optimal_window_start=optimal_start,
            optimal_window_end=optimal_end
        )
    
    async def predict_solar_charging(self, hours_ahead: int = 24) -> List[Tuple[datetime, float]]:
        """
        Predict solar charging availability based on cloud cover forecast
        Returns list of (datetime, solar_efficiency) tuples
        """
        forecast = await self.get_forecast(days=2)
        if not forecast:
            return []
        
        solar_predictions = []
        now = datetime.now()
        
        for forecast_day in forecast:
            # Calculate hourly solar predictions
            for hour in range(24):
                forecast_time = forecast_day.date.replace(hour=hour, minute=0, second=0)
                if forecast_time < now or (forecast_time - now).total_seconds() > hours_ahead * 3600:
                    continue
                
                # Base solar efficiency on cloud cover and time of day
                solar_efficiency = self._calculate_solar_efficiency(
                    forecast_time, 
                    forecast_day.sunrise,
                    forecast_day.sunset,
                    100 - forecast_day.humidity  # Use humidity as proxy for cloud cover
                )
                
                solar_predictions.append((forecast_time, solar_efficiency))
        
        return solar_predictions
    
    def _calculate_solar_efficiency(self, time: datetime, sunrise: datetime, 
                                  sunset: datetime, clear_sky_percent: float) -> float:
        """Calculate solar panel efficiency for given time and conditions"""
        # Solar efficiency is 0 outside daylight hours
        if time < sunrise or time > sunset:
            return 0.0
        
        # Calculate sun angle efficiency (simplified)
        daylight_duration = (sunset - sunrise).total_seconds()
        time_since_sunrise = (time - sunrise).total_seconds()
        sun_angle_factor = 1.0 - abs(0.5 - time_since_sunrise / daylight_duration) * 2
        sun_angle_factor = max(0.1, sun_angle_factor)  # Minimum 10% efficiency
        
        # Apply cloud cover impact
        cloud_factor = clear_sky_percent / 100.0
        
        return sun_angle_factor * cloud_factor
    
    async def _find_optimal_mowing_window(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Find the next optimal mowing window based on weather forecast"""
        forecast = await self.get_forecast(days=2)
        if not forecast:
            return None, None
        
        now = datetime.now()
        
        for forecast_day in forecast:
            # Check each hour of the day
            for hour in range(6, 20):  # Mow between 6 AM and 8 PM
                window_start = forecast_day.date.replace(hour=hour, minute=0, second=0)
                window_end = window_start + timedelta(hours=3)  # 3-hour window
                
                if window_start < now:
                    continue
                
                # Check if conditions are suitable
                if (forecast_day.precipitation_chance < 20 and  # Less than 20% chance of rain
                    forecast_day.temp_high < self.temp_max and
                    forecast_day.temp_low > self.temp_min and
                    forecast_day.wind_speed < self.wind_max):
                    
                    return window_start, window_end
        
        return None, None
    
    async def _fetch_current_weather(self) -> Optional[WeatherCondition]:
        """Fetch current weather from Google Weather API"""
        if not self._session:
            return None
        
        try:
            # This is a simplified example - actual Google Weather API integration
            # would require proper API endpoints and authentication
            lat = self.config['location']['latitude']
            lon = self.config['location']['longitude']
            api_key = self.config['api_key']
            
            # Example API call (replace with actual Google Weather API)
            url = f"https://api.weather.gov/points/{lat},{lon}"
            
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Parse weather data (this is example data structure)
                    return WeatherCondition(
                        timestamp=datetime.now(),
                        temperature=20.0,  # Parse from API response
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
        
        except Exception as e:
            self.logger.error(f"Failed to fetch current weather: {e}")
        
        return None
    
    async def _fetch_forecast(self, days: int) -> Optional[List[WeatherForecast]]:
        """Fetch weather forecast from Google Weather API"""
        if not self._session:
            return None
        
        try:
            # Example forecast data - replace with actual API integration
            forecast_data = []
            base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            for i in range(days):
                forecast_date = base_date + timedelta(days=i)
                forecast_data.append(WeatherForecast(
                    date=forecast_date,
                    temp_high=25.0 + i,
                    temp_low=15.0 + i,
                    precipitation_chance=10.0,
                    precipitation_amount=0.0,
                    wind_speed=4.0,
                    condition_code="sunny",
                    condition_text="Sunny",
                    sunrise=forecast_date.replace(hour=6, minute=30),
                    sunset=forecast_date.replace(hour=19, minute=45),
                    uv_index=6.0,
                    humidity=60.0
                ))
            
            return forecast_data
        
        except Exception as e:
            self.logger.error(f"Failed to fetch weather forecast: {e}")
        
        return None
    
    def _trim_weather_history(self):
        """Trim weather history to maximum days"""
        if len(self._weather_history) > self._max_history_days * 24:  # 24 readings per day
            cutoff_date = datetime.now() - timedelta(days=self._max_history_days)
            self._weather_history = [
                w for w in self._weather_history 
                if w.timestamp > cutoff_date
            ]
    
    async def _load_weather_history(self):
        """Load weather history from file"""
        history_file = Path("data/weather_history.json")
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    history_data = json.load(f)
                    self._weather_history = [
                        WeatherCondition(**item) for item in history_data
                    ]
                self.logger.info(f"Loaded {len(self._weather_history)} weather history records")
            except Exception as e:
                self.logger.warning(f"Failed to load weather history: {e}")
    
    async def _save_weather_history(self):
        """Save weather history to file"""
        history_file = Path("data/weather_history.json")
        history_file.parent.mkdir(exist_ok=True)
        
        try:
            history_data = [asdict(w) for w in self._weather_history]
            with open(history_file, 'w') as f:
                json.dump(history_data, f, default=str, indent=2)
            self.logger.info(f"Saved {len(self._weather_history)} weather history records")
        except Exception as e:
            self.logger.warning(f"Failed to save weather history: {e}")

    async def get_weather_trends(self, days: int = 7) -> Dict[str, Any]:
        """Analyze weather trends for scheduling optimization"""
        if len(self._weather_history) < 24:  # Need at least 24 hours of data
            return {}
        
        recent_history = [
            w for w in self._weather_history 
            if w.timestamp > datetime.now() - timedelta(days=days)
        ]
        
        if not recent_history:
            return {}
        
        # Calculate trends
        avg_temp = sum(w.temperature for w in recent_history) / len(recent_history)
        avg_humidity = sum(w.humidity for w in recent_history) / len(recent_history)
        total_precipitation = sum(w.precipitation for w in recent_history)
        
        # Find best mowing times based on historical data
        hourly_conditions = {}
        for w in recent_history:
            hour = w.timestamp.hour
            if hour not in hourly_conditions:
                hourly_conditions[hour] = []
            hourly_conditions[hour].append(w)
        
        best_hours = []
        for hour, conditions in hourly_conditions.items():
            avg_precip = sum(c.precipitation for c in conditions) / len(conditions)
            avg_wind = sum(c.wind_speed for c in conditions) / len(conditions)
            
            if avg_precip < 0.1 and avg_wind < self.wind_max:
                best_hours.append(hour)
        
        return {
            'average_temperature': avg_temp,
            'average_humidity': avg_humidity,
            'total_precipitation': total_precipitation,
            'best_mowing_hours': sorted(best_hours),
            'data_points': len(recent_history)
        }
