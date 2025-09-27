#!/usr/bin/env python3
import asyncio
import json
import websockets

URI = "ws://127.0.0.1:8001/api/v2/ws/telemetry"

async def main():
    async with websockets.connect(URI, ping_interval=None) as ws:
        # subscribe to telemetry updates and set cadence
        await ws.send(json.dumps({"type": "subscribe", "topic": "telemetry/updates"}))
        await ws.send(json.dumps({"type": "set_cadence", "cadence_hz": 10}))
        count = 0
        try:
            while count < 10:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                evt = json.loads(msg)
                if evt.get("event") == "telemetry.data":
                    count += 1
                    print(f"received telemetry #{count}")
        except asyncio.TimeoutError:
            print("WARN: timed out waiting for telemetry messages")

if __name__ == "__main__":
    asyncio.run(main())
