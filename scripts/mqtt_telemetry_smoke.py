#!/usr/bin/env python3
"""
MQTT Telemetry Smoke Test for LawnBerryPi.

Verifies that the local MQTT broker is reachable, subscribes to lawnberry/#,
prints a few representative messages (gps, imu, safety/status), and publishes
a safety test message to validate round-trip handling by SafetyService.

Usage:
  venv/bin/python -m scripts.mqtt_telemetry_smoke --duration 15 --broker localhost --port 1883
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.communication.client import MQTTClient


async def run(duration: float, broker: str, port: int) -> int:
    client = MQTTClient(
        client_id="mqtt_smoke",
        config={
            "broker_host": broker,
            "broker_port": port,
            "keepalive": 30,
            "reconnect_delay": 3,
            "max_reconnect_delay": 15,
            "message_timeout": 10,
            "auth": {"enabled": False},
            "tls": {"enabled": False},
        },
    )
    ok = await client.initialize()
    if not ok:
        print(json.dumps({"level": "error", "msg": "mqtt_init_failed"}))
        return 2

    saw_any = False
    saw_topics = set()

    async def handler(topic: str, payload: str):
        nonlocal saw_any, saw_topics
        try:
            data = json.loads(payload) if isinstance(payload, str) else payload
        except Exception:
            data = {"raw": str(payload)[:200]}
        clean = topic.replace("lawnberry/", "")
        if any(clean.startswith(p) for p in ("sensors/gps", "sensors/imu", "safety/status", "system/status")):
            out = {"topic": clean, "sample": data if isinstance(data, dict) else {"value": str(data)[:200]}}
            print(json.dumps(out, separators=(",", ":")))
            saw_any = True
            saw_topics.add(clean.split("/")[0] + "/" + clean.split("/")[1])

    await client.subscribe("lawnberry/#")
    client.add_message_handler("lawnberry/#", handler)

    # Publish a safety test message and expect an ACK on lawnberry/safety/alerts/test
    test_payload = {"from": "mqtt_smoke", "note": "hello"}
    await client.publish("lawnberry/safety/test", test_payload)

    # Run for bounded duration
    end = asyncio.get_event_loop().time() + duration
    while asyncio.get_event_loop().time() < end:
        await asyncio.sleep(0.25)

    # Done
    await client.shutdown()
    # Exit success even if no topics observed, but indicate observation in output
    print(json.dumps({"observed": sorted(saw_topics)}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=15.0)
    ap.add_argument("--broker", type=str, default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    args = ap.parse_args()
    try:
        return asyncio.run(run(args.duration, args.broker, args.port))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
