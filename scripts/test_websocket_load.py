#!/usr/bin/env python3
import asyncio
import json

import websockets

URI = "ws://127.0.0.1:8081/api/v2/ws/telemetry"

async def main():
    async with websockets.connect(URI, ping_interval=None) as ws:
        # subscribe to telemetry updates and set cadence
        await ws.send(json.dumps({"type": "subscribe", "topic": "telemetry.power"}))
        await ws.send(json.dumps({"type": "set_cadence", "cadence_hz": 5}))
        count = 0
        idle_ticks = 0
        try:
            # Allow longer time for first frames to arrive due to lazy sensor init
            while count < 5 and idle_ticks < 40:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    idle_ticks += 1
                    continue
                evt = json.loads(msg)
                if evt.get("event") == "telemetry.data" and evt.get("topic") == "telemetry.power":
                    count += 1
                    data = evt.get("data", {})
                    power = data.get("power", {}) if isinstance(data, dict) else {}
                    print(f"#{count} Vb={power.get('battery_voltage')}V Ib={power.get('battery_current')}A Pb={power.get('battery_power')}W | "
                          f"Vs={power.get('solar_voltage')}V Is={power.get('solar_current')}A Ps={power.get('solar_power')}W Yt={power.get('solar_yield_today_wh')}Wh | "
                          f"Il={power.get('load_current')}A")
                else:
                    # Print first few non-data events for diagnostics
                    if idle_ticks < 3 and evt.get("event") != "telemetry.data":
                        print("event:", evt.get("event"), "topic:", evt.get("topic"))
        except Exception as e:
            print("ERROR:", e)
        if count == 0:
            print("WARN: timed out waiting for telemetry.power messages")

if __name__ == "__main__":
    asyncio.run(main())
