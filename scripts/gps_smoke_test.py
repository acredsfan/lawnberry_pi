#!/usr/bin/env python3
"""
Quick GPS smoke test for LawnBerryPi.

Runs the HardwareInterface, reads GPS data for a short bounded duration, and prints
JSON lines when valid GPS readings are obtained. Enforces strict timeouts to avoid
hanging terminals as per Bookworm agent guidelines.

Usage:
  venv/bin/python -m scripts.gps_smoke_test --duration 20 --interval 0.5

Notes:
  - Uses the repo config at config/hardware.yaml by default.
  - Will not seize RoboHAT serial port; GPSPlugin already avoids conflicting ports.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path


async def run(duration: float, interval: float) -> int:
    # Lazy import to avoid heavy deps during module load
    from src.hardware.hardware_interface import create_hardware_interface

    hw = create_hardware_interface(str(Path("config/hardware.yaml")), shared=False, force_new=True)
    try:
        ok = await asyncio.wait_for(hw.initialize(), timeout=30.0)
        if not ok:
            print(json.dumps({"level": "error", "msg": "hardware_initialize_failed"}))
            return 2
    except asyncio.TimeoutError:
        print(json.dumps({"level": "error", "msg": "initialize_timeout"}))
        return 3
    except Exception as e:
        print(json.dumps({"level": "error", "msg": f"initialize_exception: {e}"}))
        return 4

    # Read loop
    end_time = asyncio.get_event_loop().time() + duration
    printed = 0
    try:
        while asyncio.get_event_loop().time() < end_time:
            try:
                reading = await asyncio.wait_for(hw.get_sensor_data("gps"), timeout=1.2)
            except asyncio.TimeoutError:
                reading = None
            except Exception:
                reading = None

            if reading is not None and getattr(reading, "value", None):
                # Serialize a compact line for quick verification
                val = reading.value if isinstance(reading.value, dict) else {}
                out = {
                    "timestamp": getattr(reading, "timestamp", None).isoformat() if getattr(reading, "timestamp", None) else None,
                    "lat": val.get("latitude"),
                    "lon": val.get("longitude"),
                    "alt": val.get("altitude"),
                    "acc": val.get("accuracy"),
                    "sats": val.get("satellites"),
                    "fix": val.get("fix_type"),
                }
                print(json.dumps(out, separators=(",", ":")))
                printed += 1

            await asyncio.sleep(interval)
    finally:
        try:
            await asyncio.wait_for(hw.cleanup(), timeout=10.0)
        except Exception:
            pass

    # Exit code 0 even if no GPS lock yet; the purpose is smoke visibility
    return 0 if printed > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=20.0, help="Seconds to run the test")
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds between reads")
    args = parser.parse_args()

    # Respect environment flag that may be used by sensor service to disable camera init
    os.environ.setdefault("LAWNBERY_DISABLE_CAMERA", "1")

    try:
        return asyncio.run(run(args.duration, args.interval))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
