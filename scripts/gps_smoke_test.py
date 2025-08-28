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
#!/usr/bin/env python3
"""
Bounded GPS smoke test.

- Uses existing HardwareInterface, PluginManager, and SerialManager pathing
- Auto-detects GPS port/baud using the GPSPlugin logic
- Prints parsed latitude/longitude/HDOP/satellites for a fixed duration
- Exits cleanly; safe to run alongside services (does not publish MQTT)

Usage:
  python3 scripts/gps_smoke_test.py --duration 20 --log-level INFO

Tip:
  If your GPS enumerates on a different node (e.g., /dev/ttyACM0), you can pass
  --port /dev/ttyACM0 --baud 115200 to force detection.
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Ensure src is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))

from hardware.hardware_interface import create_hardware_interface
from hardware.plugin_system import PluginConfig, GPSPlugin


async def main():
    parser = argparse.ArgumentParser(description="LawnBerry GPS smoke test")
    parser.add_argument("--duration", type=float, default=20.0, help="Seconds to run the test")
    parser.add_argument("--interval", type=float, default=0.5, help="Read interval seconds")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level")
    parser.add_argument("--port", type=str, default=None, help="Force GPS serial port (optional)")
    parser.add_argument("--baud", type=int, default=None, help="Force GPS baud rate (optional)")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    logger = logging.getLogger("gps_smoke_test")

    # Create a hardware interface instance (shared); we won't start the full service
    hw = create_hardware_interface(shared=False, force_new=True)

    # Prepare a minimal plugin config; pass forced port/baud if provided
    params = {}
    if args.port:
        params["port"] = args.port
    if args.baud:
        params["baud"] = int(args.baud)
    cfg = PluginConfig(name="gps", enabled=True, parameters=params)

    # Create and initialize the GPS plugin directly using the managers from hw
    plugin = GPSPlugin(cfg, {
        'serial': hw.serial_manager
    })

    ok = await plugin.initialize()
    if not ok:
        logger.warning("GPS plugin initialize() returned False; proceeding to try reads")

    # Display selected port/baud, if available
    port = getattr(plugin, '_port', None) or plugin.managers['serial'].devices.get('gps', {}).get('port')
    baud = getattr(plugin, '_baud', None) or plugin.managers['serial'].devices.get('gps', {}).get('baud')
    if port and baud:
        logger.info(f"GPS selected: {port} @ {baud}")
    else:
        logger.info("GPS port not yet selected; will try to read and auto-detect")

    # Run bounded read loop
    logger.info(f"Reading GPS for {args.duration}s ...")
    deadline = asyncio.get_event_loop().time() + args.duration
    reads = 0
    fixes = 0
    last_fix = None

    try:
        while asyncio.get_event_loop().time() < deadline:
            reading = await plugin.read_data()
            reads += 1
            if reading and isinstance(reading.value, dict):
                lat = reading.value.get('latitude', 0.0)
                lon = reading.value.get('longitude', 0.0)
                hdop = reading.value.get('accuracy', 0.0)
                sats = reading.value.get('satellites', 0)
                if lat != 0.0 or lon != 0.0:
                    fixes += 1
                    last_fix = (lat, lon, hdop, sats)
                    logger.info(f"GPS fix: lat={lat:.6f}, lon={lon:.6f}, hdop={hdop:.1f}, sats={sats}")
                else:
                    logger.debug("No fix yet (zeros)")
            await asyncio.sleep(args.interval)
    finally:
        # Cleanup serial resources
        try:
            await hw.serial_manager.cleanup()
        except Exception:
            pass

    logger.info(f"Reads={reads}, Fixes={fixes}")
    if last_fix:
        lat, lon, hdop, sats = last_fix
        logger.info(f"Last fix: lat={lat:.6f}, lon={lon:.6f}, hdop={hdop:.1f}, sats={sats}")
    else:
        logger.warning("No GPS fixes observed; check port/baud and sky view")


if __name__ == "__main__":
    asyncio.run(main())
