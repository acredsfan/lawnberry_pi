#!/usr/bin/env python3
"""
Publish a simple test message to the MQTT broker using the project's MQTTClient
"""
import asyncio
import logging
from src.communication.client import MQTTClient

logging.basicConfig(level=logging.INFO)

async def main():
    client = MQTTClient('test_publisher', config={'broker_host': 'localhost', 'broker_port': 1883})
    ok = await client.initialize()
    if not ok:
        print('MQTT client failed to initialize (paho-mqtt missing or broker unreachable)')
        return 1
    payload = {'test': True, 'timestamp': None}
    await client.publish('lawnberry/test/hello', payload, qos=0)
    await client.shutdown()
    return 0

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
