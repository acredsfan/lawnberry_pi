#!/usr/bin/env python3
"""
Simple smoke-check script that initializes the shared hardware interface,
reads all available sensors, prints JSON output, and performs cleanup.

Usage: PYTHONPATH=$(pwd) python scripts/check_sensors.py
"""
import asyncio
import json
import logging
from pathlib import Path
import os
from src.hardware import create_hardware_interface

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Allow forcing an in-memory config to avoid YAML parsing errors during quick checks
    use_in_memory = os.getenv('USE_IN_MEMORY_CONFIG', '0') in {'1', 'true', 'yes'}
    if use_in_memory:
        hw = create_hardware_interface({})
    else:
        hw = create_hardware_interface()
    try:
        initialized = await hw.initialize()
        if not initialized:
            logger.error("Hardware initialization failed")
            return 1

        data = await hw.get_all_sensor_data()

        # Convert dataclass readings to serializable dicts
        out = {}
        for name, reading in data.items():
            try:
                out[name] = {
                    'timestamp': reading.timestamp.isoformat() if getattr(reading, 'timestamp', None) else None,
                    'value': getattr(reading, 'value', None),
                    'unit': getattr(reading, 'unit', None),
                    'sensor_id': getattr(reading, 'sensor_id', None)
                }
            except Exception:
                out[name] = str(reading)

        print(json.dumps(out, indent=2))

    finally:
        try:
            await hw.cleanup()
        except Exception:
            pass
    return 0

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
