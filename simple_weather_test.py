#!/usr/bin/env python3
"""
Simple test for OpenWeather API integration - direct WeatherService test
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import asyncio
import logging
from weather.weather_service import WeatherService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_weather_service():
    """Test WeatherService directly"""
    
    # Check if API key is available
    api_key = os.getenv('OPENWEATHER_API_KEY')
    if not api_key:
        logger.warning("OPENWEATHER_API_KEY environment variable not set")
        logger.info("Testing with configuration file API key (if available)")
    
    logger.info("Testing OpenWeather API integration...")
    
    # Initialize weather service
    weather_service = WeatherService()
    
    try:
        # Check API key availability
        if weather_service.api_key:
            logger.info(f"✓ API key loaded: {weather_service.api_key[:8]}...")
        else:
            logger.warning("✗ No API key available - API calls will fail")
            logger.info("Set OPENWEATHER_API_KEY environment variable for testing")
            return False
        
        # Initialize the service
        if not await weather_service.initialize():
            logger.error("✗ Failed to initialize weather service")
            return False
        
        logger.info("✓ Weather service initialized successfully")
        
        # Test current weather
        logger.info("Fetching current weather...")
        current_weather = await weather_service.get_current_weather()
        
        if current_weather:
            logger.info("✓ Current weather fetched successfully:")
            logger.info(f"  Temperature: {current_weather.temperature}°C")
            logger.info(f"  Humidity: {current_weather.humidity}%")
            logger.info(f"  Condition: {current_weather.condition_text}")
            logger.info(f"  Wind Speed: {current_weather.wind_speed} m/s")
            logger.info(f"  Pressure: {current_weather.pressure} hPa")
            logger.info(f"  Timestamp: {current_weather.timestamp}")
        else:
            logger.error("✗ Failed to fetch current weather")
            return False
        
        # Test forecast
        logger.info("Fetching weather forecast...")
        forecast = await weather_service.get_forecast(days=3)
        
        if forecast:
            logger.info(f"✓ Weather forecast fetched successfully ({len(forecast)} days):")
            for day in forecast[:2]:  # Show first 2 days
                logger.info(f"  {day.date.strftime('%Y-%m-%d')}: {day.temp_low}°C - {day.temp_high}°C, {day.condition_text}")
        else:
            logger.error("✗ Failed to fetch weather forecast")
            return False
        
        logger.info("✓ All OpenWeather API integration tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up
        await weather_service.cleanup()

if __name__ == "__main__":
    success = asyncio.run(test_weather_service())
    exit(0 if success else 1)
