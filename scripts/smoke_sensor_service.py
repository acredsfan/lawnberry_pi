#!/usr/bin/env python3
"""Smoke runner for SensorService that captures MQTT publishes in-memory

This script monkeypatches `communication.client.MQTTClient` with a lightweight
fake that records all published messages so we can validate topics/payloads
without requiring an external MQTT broker.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import hardware.sensor_service as sensor_service
SensorService = sensor_service.SensorService

# Simple in-memory MQTT client replacement
class FakeMQTTClient:
    def __init__(self, client_id: str, config=None):
        self.client_id = client_id
        self.config = config or {}
        self.logger = logging.getLogger(f"fake_mqtt.{client_id}")
        self.published = []  # list of (topic, payload)
        self._connected = True

    async def initialize(self):
        self.logger.info("FakeMQTT: initialize called")
        return True

    async def publish(self, topic, message, qos=0, retain=False):
        # normalize payload to JSON string for stable output
        try:
            if isinstance(message, str):
                payload = message
            else:
                payload = json.dumps(message, default=str)
        except Exception:
            payload = str(message)
        self.published.append((topic, payload))
        self.logger.debug(f"FakeMQTT: publish {topic} -> {payload}")
        return True

    async def disconnect(self):
        self._connected = False
        return True

async def run_smoke(iterations: int = 3):
    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Monkeypatch MQTTClient in both communication.client and the imported sensor_service
    import communication.client as comm_client
    comm_client.MQTTClient = FakeMQTTClient
    # sensor_service module imported above bound MQTTClient at import-time; replace it there too
    try:
        sensor_service.MQTTClient = FakeMQTTClient
    except Exception:
        pass

    service = SensorService()
    try:
        await service.initialize()
    except Exception as e:
        print(f"Initialization failed: {e}")
        return 2

    # Run a few iterations of the main loop (without blocking infinite run)
    try:
        for i in range(iterations):
            sensor_data = await service.read_sensor_data()
            if sensor_data:
                await service.publish_sensor_data(sensor_data)
            await asyncio.sleep(service.poll_interval)

        # After runs, print captured publishes
        mqtt_client = service.mqtt_client
        print("Captured publishes:")
        for topic, payload in getattr(mqtt_client, 'published', []):
            print(topic, payload)

        # Stop the service
        await service.stop()
        return 0
    except Exception as e:
        print(f"Smoke run failed: {e}")
        return 3

if __name__ == '__main__':
    import sys
    loop = asyncio.get_event_loop()
    exit_code = loop.run_until_complete(run_smoke())
    sys.exit(exit_code)
