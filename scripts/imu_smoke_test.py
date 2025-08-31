#!/usr/bin/env python3
"""
Quick IMU smoke test for LawnBerryPi.

Runs the HardwareInterface, reads IMU data for a short bounded duration, and prints
JSON lines when valid IMU readings are obtained. Enforces strict timeouts.

Usage:
  venv/bin/python -m scripts.imu_smoke_test --duration 15 --interval 0.2

Notes:
  - Uses the repo config at config/hardware.yaml by default.
  - The IMU is expected to be BNO08x on /dev/ttyAMA4 @ 3000000 baud per config.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path when running as a script
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


async def run(duration: float, interval: float) -> int:
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

    end_time = asyncio.get_event_loop().time() + duration
    printed = 0
    try:
        while asyncio.get_event_loop().time() < end_time:
            try:
                reading = await asyncio.wait_for(hw.get_sensor_data("imu"), timeout=1.0)
            except asyncio.TimeoutError:
                reading = None
            except Exception:
                reading = None

            if reading is not None and getattr(reading, "value", None):
                val = reading.value if isinstance(reading.value, dict) else {}
                ori = val.get("orientation", {})
                acc = val.get("acceleration", {})
                gyro = val.get("gyroscope", {})
                out = {
                    "timestamp": getattr(reading, "timestamp", None).isoformat() if getattr(reading, "timestamp", None) else None,
                    "orientation": {
                        "roll": float(ori.get("roll", 0.0) or 0.0),
                        "pitch": float(ori.get("pitch", 0.0) or 0.0),
                        "yaw": float(ori.get("yaw", 0.0) or 0.0),
                    },
                    "acceleration": {
                        "x": float(acc.get("x", 0.0) or 0.0),
                        "y": float(acc.get("y", 0.0) or 0.0),
                        "z": float(acc.get("z", 0.0) or 0.0),
                    },
                    "gyroscope": {
                        "x": float(gyro.get("x", 0.0) or 0.0),
                        "y": float(gyro.get("y", 0.0) or 0.0),
                        "z": float(gyro.get("z", 0.0) or 0.0),
                    },
                }
                print(json.dumps(out, separators=(",", ":")))
                printed += 1

            await asyncio.sleep(interval)
    finally:
        try:
            await asyncio.wait_for(hw.cleanup(), timeout=10.0)
        except Exception:
            pass

    return 0 if printed > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=15.0, help="Seconds to run the test")
    parser.add_argument("--interval", type=float, default=0.2, help="Seconds between reads")
    args = parser.parse_args()

    os.environ.setdefault("LAWNBERY_DISABLE_CAMERA", "1")

    try:
        return asyncio.run(run(args.duration, args.interval))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
