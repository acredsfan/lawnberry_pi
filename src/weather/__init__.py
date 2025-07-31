"""
Weather Service Package for LawnBerry Pi Autonomous Mower
Provides comprehensive weather integration for enhanced operation optimization
"""

from .weather_service import (
    WeatherService,
    WeatherCondition,
    WeatherForecast,
    WeatherAlert,
    WeatherSafety,
    MowingConditions
)

from .weather_plugin import WeatherPlugin
from .weather_mqtt import WeatherMQTTClient

__all__ = [
    'WeatherService',
    'WeatherCondition', 
    'WeatherForecast',
    'WeatherAlert',
    'WeatherSafety',
    'MowingConditions',
    'WeatherPlugin',
    'WeatherMQTTClient'
]

__version__ = '1.0.0'
