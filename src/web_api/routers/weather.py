"""
Weather Router
Weather data and forecast endpoints.
"""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Request
from datetime import datetime

from ..models import WeatherCondition, WeatherForecast
from ..auth import get_current_user
from ..exceptions import ServiceUnavailableError, NotFoundError
from ..mqtt_bridge import MQTTBridge

router = APIRouter()

@router.get("/current", response_model=WeatherCondition)
async def get_current_weather(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current weather conditions"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get weather data from cache
    weather_data = mqtt_bridge.get_cached_data("weather/current")
    
    if not weather_data:
        raise NotFoundError("weather_data", "No current weather data available")
    
    return WeatherCondition(
        temperature=weather_data.get("temperature", 20.0),
        humidity=weather_data.get("humidity", 50.0),
        precipitation=weather_data.get("precipitation", 0.0),
        wind_speed=weather_data.get("wind_speed", 0.0),
        wind_direction=weather_data.get("wind_direction"),
        pressure=weather_data.get("pressure"),
        visibility=weather_data.get("visibility"),
        conditions=weather_data.get("conditions", "clear"),
        timestamp=datetime.fromisoformat(weather_data.get("timestamp", datetime.utcnow().isoformat()))
    )

@router.get("/forecast", response_model=List[WeatherForecast])
async def get_weather_forecast(
    request: Request,
    days: int = 7,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get weather forecast"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get forecast data from cache
    forecast_data = mqtt_bridge.get_cached_data("weather/forecast")
    
    if not forecast_data:
        raise NotFoundError("forecast_data", "No forecast data available")
    
    # Parse forecast data (simplified)
    forecasts = []
    forecast_list = forecast_data.get("forecast", [])
    
    for day_forecast in forecast_list[:days]:
        forecasts.append(WeatherForecast(
            date=datetime.fromisoformat(day_forecast.get("date", datetime.utcnow().isoformat())),
            temperature_high=day_forecast.get("temperature_high", 25.0),
            temperature_low=day_forecast.get("temperature_low", 15.0),
            precipitation_probability=day_forecast.get("precipitation_probability", 0.0),
            precipitation_amount=day_forecast.get("precipitation_amount", 0.0),
            wind_speed=day_forecast.get("wind_speed", 0.0),
            conditions=day_forecast.get("conditions", "clear")
        ))
    
    return forecasts

@router.get("/alerts")
async def get_weather_alerts(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get weather alerts and warnings"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get alerts data from cache
    alerts_data = mqtt_bridge.get_cached_data("weather/alerts")
    
    return alerts_data or {"alerts": [], "warnings": []}

@router.get("/suitable-for-mowing")
async def check_mowing_suitability(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Check if current weather is suitable for mowing"""
    try:
        current_weather = await get_current_weather(request, current_user)
        
        # Basic suitability check
        suitable = True
        reasons = []
        
        if current_weather.precipitation > 0.1:
            suitable = False
            reasons.append("Rain detected")
        
        if current_weather.temperature < 5 or current_weather.temperature > 40:
            suitable = False
            reasons.append("Temperature outside safe range")
        
        if current_weather.wind_speed > 10:  # m/s
            suitable = False
            reasons.append("Wind speed too high")
        
        return {
            "suitable": suitable,
            "reasons": reasons,
            "weather_conditions": current_weather.dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "suitable": False,
            "reasons": ["Weather data unavailable"],
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
