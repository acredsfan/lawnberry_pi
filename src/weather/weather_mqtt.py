"""
Weather Service MQTT Integration
Provides weather data distribution via MQTT for microservices coordination
"""

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, Optional

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from .weather_service import MowingConditions, WeatherCondition, WeatherService


class WeatherMQTTClient:
    """MQTT client for weather data distribution"""

    def __init__(self, weather_service: WeatherService, mqtt_config: Dict[str, Any] = None):
        self.weather_service = weather_service
        self.logger = logging.getLogger(__name__)

        # MQTT Configuration
        self.mqtt_config = mqtt_config or {
            "broker_host": "localhost",
            "broker_port": 1883,
            "keepalive": 60,
            "client_id": "weather_service",
            "topics": {
                "current_weather": "lawnberry/weather/current",
                "forecast": "lawnberry/weather/forecast",
                "alerts": "lawnberry/weather/alerts",
                "mowing_conditions": "lawnberry/weather/mowing_conditions",
                "solar_prediction": "lawnberry/weather/solar_prediction",
                "trends": "lawnberry/weather/trends",
            },
        }

        # MQTT Client
        self.client: Optional[mqtt.Client] = None
        self._connected = False
        self._publish_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

        # Publishing intervals (seconds)
        self.intervals = {
            "current_weather": 300,  # 5 minutes
            "forecast": 3600,  # 1 hour
            "alerts": 60,  # 1 minute
            "mowing_conditions": 180,  # 3 minutes
            "solar_prediction": 1800,  # 30 minutes
            "trends": 7200,  # 2 hours
        }

        # Last publish times
        self._last_publish = {key: 0 for key in self.intervals.keys()}

    async def initialize(self) -> bool:
        """Initialize MQTT client and connection"""
        if mqtt is None:
            self.logger.error("paho-mqtt not installed. Install with: pip install paho-mqtt")
            return False

        try:
            self.logger.info("Initializing weather MQTT client...")

            # Create MQTT client
            self.client = mqtt.Client(self.mqtt_config["client_id"])
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            # Connect to broker
            self.client.connect(
                self.mqtt_config["broker_host"],
                self.mqtt_config["broker_port"],
                self.mqtt_config["keepalive"],
            )

            # Start MQTT loop in background
            self.client.loop_start()

            # Wait for connection
            for _ in range(50):  # 5 second timeout
                if self._connected:
                    break
                await asyncio.sleep(0.1)

            if not self._connected:
                self.logger.error("Failed to connect to MQTT broker")
                return False

            # Start publishing task
            self._publish_task = asyncio.create_task(self._publish_loop())

            self.logger.info("Weather MQTT client initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize weather MQTT client: {e}")
            return False

    async def shutdown(self):
        """Shutdown MQTT client"""
        self.logger.info("Shutting down weather MQTT client...")

        self._shutdown_event.set()

        if self._publish_task:
            self._publish_task.cancel()
            try:
                await self._publish_task
            except asyncio.CancelledError:
                pass

        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

        self.logger.info("Weather MQTT client shut down")

    def _on_connect(self, client, _userdata, _flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self._connected = True
            self.logger.info("Connected to MQTT broker")

            # Subscribe to command topics
            client.subscribe("lawnberry/weather/commands/+")
        else:
            self.logger.error(f"Failed to connect to MQTT broker: {rc}")

    def _on_disconnect(self, client, _userdata, rc):
        """MQTT disconnection callback"""
        self._connected = False
        if rc != 0:
            self.logger.warning("Unexpected MQTT disconnection")

    def _on_message(self, client, _userdata, msg):
        """Handle incoming MQTT messages"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())

            self.logger.debug(f"Received MQTT message on {topic}: {payload}")

            # Handle weather service commands
            if topic.endswith("/refresh"):
                asyncio.create_task(self._handle_refresh_command())
            elif topic.endswith("/forecast"):
                days = payload.get("days", 7)
                asyncio.create_task(self._handle_forecast_request(days))
            elif topic.endswith("/solar_prediction"):
                hours = payload.get("hours", 24)
                asyncio.create_task(self._handle_solar_prediction_request(hours))

        except Exception as e:
            self.logger.error(f"Error handling MQTT message: {e}")

    async def _publish_loop(self):
        """Main publishing loop"""
        while not self._shutdown_event.is_set():
            try:
                current_time = datetime.now().timestamp()

                # Check each topic for publishing
                for topic_key, interval in self.intervals.items():
                    if current_time - self._last_publish[topic_key] >= interval:
                        await self._publish_data(topic_key)
                        self._last_publish[topic_key] = current_time

                # Sleep for a short interval
                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in publish loop: {e}")
                await asyncio.sleep(30)  # Wait before retrying

    async def _publish_data(self, topic_key: str):
        """Publish specific weather data"""
        if not self._connected:
            return

        try:
            topic = self.mqtt_config["topics"][topic_key]
            payload = None

            if topic_key == "current_weather":
                weather = await self.weather_service.get_current_weather()
                if weather:
                    payload = asdict(weather)

            elif topic_key == "forecast":
                forecast = await self.weather_service.get_forecast()
                if forecast:
                    payload = [asdict(f) for f in forecast]

            elif topic_key == "alerts":
                alerts = await self.weather_service.get_weather_alerts()
                if alerts:
                    payload = [asdict(a) for a in alerts]

            elif topic_key == "mowing_conditions":
                # Get local sensor data from hardware interface if available
                local_data = {}  # This would be injected from hardware interface
                conditions = await self.weather_service.evaluate_mowing_conditions(local_data)
                if conditions:
                    payload = asdict(conditions)

            elif topic_key == "solar_prediction":
                predictions = await self.weather_service.predict_solar_charging()
                if predictions:
                    payload = [
                        {"datetime": dt.isoformat(), "efficiency": eff} for dt, eff in predictions
                    ]

            elif topic_key == "trends":
                trends = await self.weather_service.get_weather_trends()
                if trends:
                    payload = trends

            if payload:
                # Add metadata
                message = {
                    "timestamp": datetime.now().isoformat(),
                    "source": "weather_service",
                    "data": payload,
                }

                # Publish to MQTT
                self.client.publish(topic, json.dumps(message, default=str), qos=1, retain=True)

                self.logger.debug(f"Published {topic_key} data to {topic}")

        except Exception as e:
            self.logger.error(f"Failed to publish {topic_key}: {e}")

    async def _handle_refresh_command(self):
        """Handle weather data refresh command"""
        try:
            await self.weather_service.get_current_weather(force_refresh=True)
            self.logger.info("Weather data refreshed via MQTT command")
        except Exception as e:
            self.logger.error(f"Failed to refresh weather data: {e}")

    async def _handle_forecast_request(self, days: int):
        """Handle forecast request command"""
        try:
            forecast = await self.weather_service.get_forecast(days)
            if forecast:
                topic = self.mqtt_config["topics"]["forecast"]
                message = {
                    "timestamp": datetime.now().isoformat(),
                    "source": "weather_service",
                    "requested_days": days,
                    "data": [asdict(f) for f in forecast],
                }

                self.client.publish(topic, json.dumps(message, default=str), qos=1)
        except Exception as e:
            self.logger.error(f"Failed to handle forecast request: {e}")

    async def _handle_solar_prediction_request(self, hours: int):
        """Handle solar prediction request command"""
        try:
            predictions = await self.weather_service.predict_solar_charging(hours)
            if predictions:
                topic = self.mqtt_config["topics"]["solar_prediction"]
                message = {
                    "timestamp": datetime.now().isoformat(),
                    "source": "weather_service",
                    "requested_hours": hours,
                    "data": [
                        {"datetime": dt.isoformat(), "efficiency": eff} for dt, eff in predictions
                    ],
                }

                self.client.publish(topic, json.dumps(message, default=str), qos=1)
        except Exception as e:
            self.logger.error(f"Failed to handle solar prediction request: {e}")

    async def publish_immediate_alert(self, alert_data: Dict[str, Any]):
        """Publish immediate weather alert"""
        if not self._connected:
            return

        try:
            topic = self.mqtt_config["topics"]["alerts"]
            message = {
                "timestamp": datetime.now().isoformat(),
                "source": "weather_service",
                "urgent": True,
                "data": alert_data,
            }

            self.client.publish(
                topic, json.dumps(message, default=str), qos=2  # Ensure delivery for alerts
            )

            self.logger.info("Published immediate weather alert")

        except Exception as e:
            self.logger.error(f"Failed to publish immediate alert: {e}")
