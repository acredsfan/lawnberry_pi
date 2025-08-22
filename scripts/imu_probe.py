#!/usr/bin/env python3
"""
IMU Serial Probe Utility

Safely probe common serial ports and baud rates to detect IMU output.
Designed for Raspberry Pi OS Bookworm on LawnBerryPi.

- Non-interactive, bounded reads with timeouts
- Prints short decoded lines and basic hex preview
- Defaults: ports [/dev/ttyAMA4, /dev/ttyAMA0], bauds [3000000, 921600, 115200]

Usage examples:
  ./scripts/imu_probe.py
  ./scripts/imu_probe.py --ports /dev/ttyAMA4 --bauds 3000000 115200 --duration 3.0
  ./scripts/imu_probe.py --hex --limit 64
"""

import argparse
import sys
import time
from typing import List

try:
    import serial  # pyserial
except Exception as e:
    print(f"ERROR: pyserial not available: {e}")
    sys.exit(2)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="IMU Serial Probe Utility")
    p.add_argument(
        "--ports",
        nargs="+",
        default=["/dev/ttyAMA4", "/dev/ttyAMA0"],
        help="Serial ports to probe (default: /dev/ttyAMA4 /dev/ttyAMA0)",
    )
    p.add_argument(
        "--bauds",
        nargs="+",
        type=int,
        default=[3000000, 921600, 115200],
        help="Baud rates to try (default: 3000000 921600 115200)",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=2.0,
        help="Seconds to read per port/baud (default: 2.0)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=0.2,
        help="Serial read timeout seconds (default: 0.2)",
    )
    p.add_argument(
        "--hex",
        action="store_true",
        help="Print a hex preview of raw bytes in addition to decoded lines",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=32,
        help="Max bytes to show in hex preview (default: 32)",
    )
    return p.parse_args()


def hex_preview(b: bytes, limit: int) -> str:
    s = b[:limit]
    return " ".join(f"{x:02X}" for x in s)


def main() -> int:
    args = parse_args()
    any_success = False

    for port in args.ports:
        for baud in args.bauds:
            try:
                ser = serial.Serial(port, baudrate=baud, timeout=args.timeout)
                print(f"\n--- PROBE OPEN OK {port} @ {baud} ---")
            except Exception as e:
                print(f"\n--- PROBE OPEN FAIL {port} @ {baud}: {e} ---")
                continue

            start = time.time()
            lines = 0
            raw_total = 0
            try:
                while time.time() - start < args.duration:
                    # Prefer line reads; many IMUs emit readable ASCII/NMEA/diagnostic frames
                    raw = ser.readline()
                    if not raw:
                        continue
                    raw_total += len(raw)
                    try:
                        txt = raw.decode("utf-8", errors="ignore").strip()
                    except Exception:
                        txt = ""  # non-decodable
                    if txt:
                        print(f"{port}@{baud}: {txt[:160]}")
                        lines += 1
                    elif args.hex:
                        print(f"{port}@{baud} [HEX]: {hex_preview(raw, args.limit)}")
            except KeyboardInterrupt:
                pass
            except Exception as e:
                print(f"{port}@{baud} READ ERROR: {e}")
            finally:
                try:
                    ser.close()
                except Exception:
                    pass

            print(f"READ {lines} decoded lines, {raw_total} raw bytes from {port}@{baud}")
            if lines > 0 or raw_total > 0:
                any_success = True

    if not any_success:
        print("No data observed. Check UART overlay, wiring (TXD4/RXD4), and IMU power/mode.")
        print("Hints: enable_uart=1, dtoverlay=uart4, PS1=3.3V for BNO085 UART mode.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
