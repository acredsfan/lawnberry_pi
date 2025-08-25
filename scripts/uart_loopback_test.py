#!/usr/bin/env python3
"""
UART Loopback Test

Validate that a UART device (e.g., /dev/ttyAMA1 on Pi 5 UART1 GPIO12/13) can
transmit and receive data by shorting TX to RX externally (jumper between
GPIO12 and GPIO13 for Pi 5 with dtoverlay=uart1,txd1_pin=12,rxd1_pin=13).

Usage examples:
  ./scripts/uart_loopback_test.py --port /dev/ttyAMA1 --baud 115200
  ./scripts/uart_loopback_test.py --port /dev/ttyAMA1 --baud 3000000 --message LBK-3000 --retries 5

Notes:
  - Requires a physical jumper from TX to RX at the header.
  - Use short messages to avoid buffer issues; script trims comparisons.
  - Safe and bounded: uses small timeouts and fails fast.
"""

import argparse
import sys
import time

try:
    import serial  # pyserial
except Exception as e:
    print(f"ERROR: pyserial not available: {e}")
    sys.exit(2)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="UART loopback test")
    p.add_argument("--port", required=True, help="Serial device, e.g., /dev/ttyAMA1")
    p.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    p.add_argument("--message", default="LBK-TEST\r\n", help="Message to send (default: 'LBK-TEST\\r\\n')")
    p.add_argument("--timeout", type=float, default=0.3, help="Serial read timeout seconds (default: 0.3)")
    p.add_argument("--retries", type=int, default=3, help="Retries to attempt (default: 3)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ser = serial.Serial(args.port, baudrate=args.baud, timeout=args.timeout)
    except Exception as e:
        print(f"OPEN FAIL {args.port}@{args.baud}: {e}")
        return 2

    print(f"OPEN OK {args.port}@{args.baud}")
    msg = args.message.encode("utf-8", errors="ignore")
    try:
        # clean buffer
        try:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except Exception:
            pass

        for attempt in range(1, args.retries + 1):
            ser.write(msg)
            ser.flush()
            time.sleep(0.05)
            rx = ser.read(len(msg) + 32)
            print(f"Attempt {attempt}: wrote {len(msg)}B, read {len(rx)}B: {rx!r}")
            if msg in rx:
                print("LOOPBACK PASS: Sent bytes observed on RX")
                return 0
            time.sleep(0.1)

        print("LOOPBACK FAIL: Did not read back the sent bytes.\n"
              "- Ensure TX and RX are physically shorted (jumper).\n"
              "- Verify correct device and baud.\n"
              "- Check that no other process is holding the port.")
        return 1
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
