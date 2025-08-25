#!/usr/bin/env python3
"""
IMU Serial Probe Utility

Safely probe common serial ports and baud rates to detect IMU output.
Designed for Raspberry Pi OS Bookworm on LawnBerryPi.

- Non-interactive, bounded reads with timeouts
- Supports ASCII line mode and raw/binary mode
- Prints short decoded lines and basic hex preview
- Defaults: ports [/dev/ttyAMA4, /dev/ttyAMA0], bauds [3000000, 921600, 115200]

Usage examples:
    ./scripts/imu_probe.py
    ./scripts/imu_probe.py --ports /dev/ttyAMA4 --bauds 3000000 115200 --duration 3.0
    ./scripts/imu_probe.py --mode raw --hex --limit 64
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
        default=["/dev/ttyAMA1", "/dev/ttyS1", "/dev/ttyAMA4", "/dev/ttyAMA0"],
        help=(
            "Serial ports to probe (default tries: /dev/ttyAMA1 /dev/ttyS1 /dev/ttyAMA4 /dev/ttyAMA0). "
            "Pi 5 IMU is typically on AMA1 or S1 when mapped to GPIO12/13; Pi 4/CM4 often uses AMA4."
        ),
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
        "--mode",
        choices=["auto", "ascii", "raw"],
        default="auto",
        help="Read mode: 'ascii' for newline-terminated text, 'raw' for binary chunks, 'auto' tries ascii then raw (default)",
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
    p.add_argument(
        "--bytes-per-read",
        type=int,
        default=128,
        help="Bytes to attempt per raw read when in raw/auto mode (default: 128)",
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
                # Helper lambdas
                def do_ascii_read() -> bool:
                    nonlocal lines, raw_total
                    raw = ser.readline()
                    if not raw:
                        return False
                    raw_total += len(raw)
                    txt = ""
                    try:
                        txt = raw.decode("utf-8", errors="ignore").strip()
                    except Exception:
                        txt = ""
                    if txt:
                        print(f"{port}@{baud}: {txt[:160]}")
                        lines += 1
                        return True
                    if args.hex:
                        print(f"{port}@{baud} [HEX]: {hex_preview(raw, args.limit)}")
                    return True

                def do_raw_read() -> bool:
                    nonlocal raw_total
                    raw = ser.read(args.bytes_per_read)
                    if not raw:
                        return False
                    raw_total += len(raw)
                    if args.hex:
                        print(f"{port}@{baud} [RAW HEX]: {hex_preview(raw, args.limit)}")
                    return True

                while time.time() - start < args.duration:
                    if args.mode == "ascii":
                        did = do_ascii_read()
                    elif args.mode == "raw":
                        did = do_raw_read()
                    else:  # auto
                        did = do_ascii_read()
                        if not did:
                            did = do_raw_read()
                    # Tight loop guard on no data
                    if not did:
                        # small sleep to avoid busy-wait; keep dependency-free
                        time.sleep(0.01)
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
        print("No data observed in ASCII or raw modes. Check UART overlay, wiring, and IMU power/mode.")
        print(
            "Hints: Pi 5 → use dtoverlay=uart1,txd1_pin=12,rxd1_pin=13 and probe /dev/ttyAMA1 or /dev/ttyS1; "
            "Pi 4/CM4 → dtoverlay=uart4 and probe /dev/ttyAMA4. Ensure enable_uart=1 and IMU PS1=3.3V (UART mode)."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
