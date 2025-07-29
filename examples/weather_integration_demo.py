#!/usr/bin/env python3
"""
Weather Integration Service Demo
Demonstrates the weather service integration with the autonomous mower system
"""

import asyncio
import logging
import sys
from pathlib import Path
import json
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from weather import WeatherService, WeatherPlugin, WeatherMQTTClient
    from hardware.plugin_system import PluginConfig
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def demo_weather_service():
    """Demonstrate weather service functionality"""
    logger.info("=== Weather Service Demo ===")
    
    # Initialize weather service
    weather_service = WeatherService()
    
    if not await weather_service.initialize():
        logger.error("Failed to initialize weather service")
        return False
    
    try:
        # Test current weather
        logger.info("Testing current weather...")
        current_weather = await weather_service.get_current_weather()
        if current_weather:
            logger.info(f"Current temperature: {current_weather.temperature}°C")
            logger.info(f"Humidity: {current_weather.humidity}%")
            logger.info(f"Condition: {current_weather.condition_text}")
        else:
            logger.warning("No current weather data available")
        
        # Test weather forecast
        logger.info("Testing weather forecast...")
        forecast = await weather_service.get_forecast(days=3)
        if forecast:
            logger.info(f"Retrieved {len(forecast)} day forecast")
            for i, day in enumerate(forecast):
                logger.info(f"Day {i+1}: {day.temp_low}°C - {day.temp_high}°C, {day.condition_text}")
        else:
            logger.warning("No forecast data available")
        
        # Test mowing conditions evaluation
        logger.info("Testing mowing conditions evaluation...")
        
        # Simulate local BME280 sensor data
        local_sensor_data = {
            'temperature': 22.5,
            'humidity': 68.0,
            'pressure': 1013.25
        }
        
        conditions = await weather_service.evaluate_mowing_conditions(local_sensor_data)
        logger.info(f"Mowing safety level: {conditions.safety_level.value}")
        logger.info(f"Can mow: {conditions.can_mow}")
        if conditions.reasons:
            logger.info(f"Reasons: {', '.join(conditions.reasons)}")
        
        if conditions.optimal_window_start:
            logger.info(f"Optimal mowing window: {conditions.optimal_window_start} - {conditions.optimal_window_end}")
        
        # Test solar charging prediction
        logger.info("Testing solar charging prediction...")
        solar_predictions = await weather_service.predict_solar_charging(hours_ahead=12)
        if solar_predictions:
            logger.info(f"Retrieved {len(solar_predictions)} solar efficiency predictions")
            # Show next few hours
            for i, (dt, efficiency) in enumerate(solar_predictions[:6]):
                logger.info(f"  {dt.strftime('%H:%M')}: {efficiency:.1%} efficiency")
        
        # Test weather trends
        logger.info("Testing weather trends...")
        trends = await weather_service.get_weather_trends(days=7)
        if trends:
            logger.info(f"Weather trends: {json.dumps(trends, indent=2, default=str)}")
        
        logger.info("Weather service demo completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error during weather service demo: {e}")
        return False
    
    finally:
        await weather_service.shutdown()

async def demo_weather_plugin():
    """Demonstrate weather plugin integration"""
    logger.info("=== Weather Plugin Demo ===")
    
    # Create plugin configuration
    plugin_config = PluginConfig(
        name="weather_service",
        enabled=True,
        parameters={
            'config_path': 'config/weather.yaml'
        }
    )
    
    # Create weather plugin (no hardware managers needed)
    weather_plugin = WeatherPlugin(plugin_config, {})
    
    if not await weather_plugin.initialize():
        logger.error("Failed to initialize weather plugin")
        return False
    
    try:
        # Test reading sensor data
        logger.info("Testing weather plugin sensor reading...")
        sensor_reading = await weather_plugin.read_data()
        if sensor_reading:
            logger.info(f"Weather sensor reading timestamp: {sensor_reading.timestamp}")
            logger.info(f"Weather data keys: {list(sensor_reading.value.keys())}")
            logger.info(f"Can mow: {sensor_reading.value.get('can_mow')}")
            logger.info(f"Safety level: {sensor_reading.value.get('safety_level')}")
        
        # Test forecast data
        logger.info("Testing forecast data retrieval...")
        forecast_data = await weather_plugin.get_forecast_data(days=3)
        if forecast_data:
            logger.info(f"Retrieved forecast for {len(forecast_data)} days")
        
        # Test solar predictions
        logger.info("Testing solar prediction retrieval...")
        solar_data = await weather_plugin.get_solar_prediction(hours_ahead=12)
        if solar_data:
            logger.info(f"Retrieved {len(solar_data)} solar predictions")
        
        # Test weather trends
        logger.info("Testing weather trends retrieval...")
        trends_data = await weather_plugin.get_weather_trends(days=7)
        if trends_data:
            logger.info(f"Weather trends data points: {trends_data.get('data_points', 0)}")
        
        # Test safety check
        is_safe = await weather_plugin.is_safe_to_mow()
        logger.info(f"Is safe to mow: {is_safe}")
        
        # Test optimal window
        optimal_window = await weather_plugin.get_next_optimal_window()
        if optimal_window:
            logger.info(f"Next optimal window: {optimal_window['start']} - {optimal_window['end']}")
        
        logger.info("Weather plugin demo completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error during weather plugin demo: {e}")
        return False
    
    finally:
        await weather_plugin.shutdown()

async def demo_mqtt_integration():
    """Demonstrate MQTT integration (if available)"""
    logger.info("=== Weather MQTT Integration Demo ===")
    
    try:
        # Initialize weather service
        weather_service = WeatherService()
        if not await weather_service.initialize():
            logger.error("Failed to initialize weather service for MQTT demo")
            return False
        
        # Initialize MQTT client
        mqtt_config = {
            'broker_host': 'localhost',
            'broker_port': 1883,
            'client_id': 'weather_demo',
            'topics': {
                'current_weather': 'demo/weather/current',
                'forecast': 'demo/weather/forecast',
                'alerts': 'demo/weather/alerts',
                'mowing_conditions': 'demo/weather/conditions',
                'solar_prediction': 'demo/weather/solar',
                'trends': 'demo/weather/trends'
            }
        }
        
        mqtt_client = WeatherMQTTClient(weather_service, mqtt_config)
        
        if await mqtt_client.initialize():
            logger.info("MQTT client initialized successfully")
            
            # Let it run for a short while to publish some data
            await asyncio.sleep(10)
            
            logger.info("MQTT integration demo completed")
            await mqtt_client.shutdown()
        else:
            logger.warning("MQTT broker not available - skipping MQTT demo")
        
        await weather_service.shutdown()
        return True
        
    except Exception as e:
        logger.error(f"Error during MQTT demo: {e}")
        return False

async def create_sample_config():
    """Create sample weather configuration if it doesn't exist"""
    config_path = Path("config/weather.yaml")
    if not config_path.exists():
        logger.info("Creating sample weather configuration...")
        config_path.parent.mkdir(exist_ok=True)
        
        sample_config = """# Sample Weather Configuration
api_key: "YOUR_API_KEY_HERE"  # Replace with actual API key
location:
  latitude: 40.7128
  longitude: -74.0060

temperature_limits:
  min: 5.0
  max: 35.0

wind_limits:
  max: 8.0

cache_duration: 300
"""
        
        with open(config_path, 'w') as f:
            f.write(sample_config)
        
        logger.info(f"Sample config created at {config_path}")
        logger.info("Please update with your actual API key and location")

async def main():
    """Main demo function"""
    logger.info("Starting Weather Integration Service Demo")
    
    # Create sample config if needed
    await create_sample_config()
    
    # Create data directory
    Path("data").mkdir(exist_ok=True)
    
    success = True
    
    # Run weather service demo
    if not await demo_weather_service():
        success = False
    
    await asyncio.sleep(2)
    
    # Run weather plugin demo
    if not await demo_weather_plugin():
        success = False
    
    await asyncio.sleep(2)
    
    # Run MQTT demo (optional)
    try:
        if not await demo_mqtt_integration():
            logger.warning("MQTT demo failed (this is optional)")
    except Exception as e:
        logger.warning(f"MQTT demo skipped: {e}")
    
    if success:
        logger.info("=== All demos completed successfully! ===")
        logger.info("Weather integration service is ready for use")
        logger.info("Next steps:")
        logger.info("1. Configure your Google Weather API key in config/weather.yaml")
        logger.info("2. Set your location coordinates")
        logger.info("3. Add weather plugin to hardware configuration")
        logger.info("4. Integrate with MQTT broker for system communication")
    else:
        logger.error("Some demos failed - check the logs above")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
