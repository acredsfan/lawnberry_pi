#!/usr/bin/env python3
"""
Simple integration test for OpenWeather API
Run this to test the OpenWeather API integration
"""

import asyncio
import logging
import os
from src.weather.weather_service import WeatherService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_openweather_integration():
    """Test OpenWeather API integration"""
    
    # Check if API key is available
    api_key = os.getenv('OPENWEATHER_API_KEY')
    if not api_key:
        logger.error("OPENWEATHER_API_KEY environment variable not set")
        logger.info("Please set your OpenWeather API key:")
        logger.info("export OPENWEATHER_API_KEY='your_api_key_here'")
        return False
    
    logger.info("Testing OpenWeather API integration...")
    
    # Initialize weather service
    weather_service = WeatherService()
    
    try:
        # Initialize the service
        if not await weather_service.initialize():
            logger.error("Failed to initialize weather service")
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
        
        # Test mowing conditions evaluation
        logger.info("Evaluating mowing conditions...")
        conditions = await weather_service.evaluate_mowing_conditions()
        
        logger.info("✓ Mowing conditions evaluated:")
        logger.info(f"  Safety Level: {conditions.safety_level.value}")
        logger.info(f"  Can Mow: {conditions.can_mow}")
        if conditions.reasons:
            logger.info(f"  Reasons: {', '.join(conditions.reasons)}")
        
        # Test weather alerts
        logger.info("Fetching weather alerts...")
        alerts = await weather_service.get_weather_alerts()
        logger.info(f"✓ Weather alerts checked ({len(alerts)} active alerts)")
        
        logger.info("✓ All OpenWeather API integration tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Integration test failed: {e}")
        return False
    
    finally:
        # Clean up
        await weather_service.cleanup()

if __name__ == "__main__":
    success = asyncio.run(test_openweather_integration())
    exit(0 if success else 1)
