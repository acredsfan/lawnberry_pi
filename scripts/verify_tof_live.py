#!/usr/bin/env python3
"""
Quick verifier: subscribes to MQTT topics and prints ToF distances as they arrive.

Usage:
  venv/bin/python scripts/verify_tof_live.py

It times out after 30 seconds by default and exits with code 0 if any non-zero ToF
values are observed.
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.communication.client import MQTTClient  # type: ignore

TOPICS = [
    'lawnberry/sensors/tof/data',
    'lawnberry/sensors/tof/left',
    'lawnberry/sensors/tof/right',
]


async def main(timeout_s: float = 30.0) -> int:
    seen_nonzero = False

    async def on_message(topic: str, payload: dict):
        nonlocal seen_nonzero
        try:
            if topic.endswith('/left') or topic.endswith('/right'):
                val = float(payload.get('distance_mm', 0) or 0)
                if val > 0:
                    print(f"[{datetime.utcnow().isoformat()}] {topic}: {val} mm")
                    seen_nonzero = True
            elif topic.endswith('/tof/data'):
                l = float(payload.get('left_distance', 0) or 0)
                r = float(payload.get('right_distance', 0) or 0)
                if l > 0 or r > 0:
                    print(f"[{datetime.utcnow().isoformat()}] {topic}: left={l} right={r} mm")
                    seen_nonzero = True
        except Exception:
            pass

    client = MQTTClient(client_id='tof-verifier', config={
        'broker_host': 'localhost',
        'broker_port': 1883,
        'auth': {'enabled': False},
        'tls': {'enabled': False},
    })
    ok = await client.initialize()
    if not ok:
        print('ERROR: MQTT connect failed', file=sys.stderr)
        return 2

    # Attach lightweight callback by wrapping publish path; client lib may not expose on_message directly
    try:
        await client.subscribe('lawnberry/sensors/tof/#', qos=0)
    except Exception as e:
        print(f'ERROR: subscribe failed: {e}', file=sys.stderr)
        return 3

    # Poll the broker by publishing a ping to ensure traffic
    deadline = datetime.utcnow() + timedelta(seconds=timeout_s)
    while datetime.utcnow() < deadline and not seen_nonzero:
        await asyncio.sleep(0.5)

    try:
        await client.disconnect()
    except Exception:
        pass

    if seen_nonzero:
        print('SUCCESS: Non-zero ToF data observed')
        return 0
    print('ERROR: No non-zero ToF values observed within timeout', file=sys.stderr)
    return 1


if __name__ == '__main__':
    code = asyncio.run(main())
    sys.exit(code)
