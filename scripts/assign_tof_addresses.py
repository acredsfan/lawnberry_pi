#!/usr/bin/env python3
"""
One-time helper to assign VL53L0X ToF sensor addresses (0x29 and 0x30) using GPIO sequencing.

Requirements:
- Run inside the repo venv: `venv/bin/python scripts/assign_tof_addresses.py`
- Ensure no other process holds GPIO 22/23 (stop system services or remap pins).
- Enforces a global timeout and persists no-GPIO flag when addresses are confirmed.

This script is safe on Raspberry Pi OS Bookworm (aarch64) and uses timeouts to avoid hangs.
"""
import asyncio
import os
import sys
from pathlib import Path


async def _assign_and_persist() -> int:
    # Make sure we import from this repository's src
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    # Force GPIO sequencing for address assignment
    os.environ.setdefault('LAWNBERY_TOF_NO_GPIO', 'never')

    from src.hardware.tof_manager import ToFSensorManager  # type: ignore

    mgr = ToFSensorManager()
    try:
        # Initialize with an overall timeout
        ok = await asyncio.wait_for(mgr.initialize(), timeout=60.0)
        if not ok:
            print("ERROR: ToF manager initialization failed", file=sys.stderr)
            return 2
    except asyncio.TimeoutError:
        print("ERROR: ToF initialization timed out", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"ERROR: ToF initialization raised: {e}", file=sys.stderr)
        return 4

    # Scan the I2C bus to confirm addresses
    addrs = []
    try:
        i2c = getattr(mgr, 'i2c', None)
        if i2c and i2c.try_lock():
            try:
                addrs = i2c.scan()
            finally:
                i2c.unlock()
    except Exception:
        pass

    print("I2C devices:", [hex(a) for a in addrs])
    have_both = (0x29 in addrs) and (0x30 in addrs)

    # Persist no-GPIO flag for future runs if both addresses confirmed
    if have_both:
        try:
            if hasattr(mgr, '_persist_no_gpio_flag'):
                mgr._persist_no_gpio_flag()  # type: ignore[attr-defined]
                print("Persisted no-GPIO flag (data/tof_no_gpio.json)")
        except Exception as e:
            print(f"WARN: Could not persist no-GPIO flag: {e}", file=sys.stderr)

    # Cleanly shutdown with timeout
    try:
        await asyncio.wait_for(mgr.shutdown(), timeout=10.0)
    except Exception:
        pass

    if not have_both:
        print("ERROR: Did not detect both 0x29 and 0x30. Ensure GPIO pins are free and wiring is correct.", file=sys.stderr)
        return 1

    print("SUCCESS: ToF sensors confirmed at 0x29 and 0x30.")
    return 0


def main() -> int:
    try:
        return asyncio.run(_assign_and_persist())
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 10


if __name__ == '__main__':
    sys.exit(main())
