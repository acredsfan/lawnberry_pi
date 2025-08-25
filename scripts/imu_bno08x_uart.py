#!/usr/bin/env python3
"""
IMU runner using Adafruit CircuitPython BNO08x over UART on Raspberry Pi OS (Bookworm).

- Targets Pi 5 IMU on UART1 (GPIO12/13) → /dev/ttyAMA1 by default
- Uses pyserial with the Adafruit BNO08x UART driver (no Blinka pin mapping required)
- Enables Rotation Vector and prints quaternion values for a bounded duration

Example:
  ./scripts/imu_bno08x_uart.py --port /dev/ttyAMA1 --baud 3000000 --duration 10

Requirements (install into repo venv):
  timeout 60s venv/bin/python -m pip install adafruit-circuitpython-bno08x adafruit-blinka
"""

import argparse
import sys
import time
import signal

try:
    import serial  # pyserial
except Exception as e:
    print(f"ERROR: pyserial required: {e}")
    sys.exit(2)

try:
    # Adafruit CircuitPython BNO08x
    # UART class is in submodule adafruit_bno08x.uart
    from adafruit_bno08x.uart import BNO08X_UART
    from adafruit_bno08x import (
        BNO_REPORT_ROTATION_VECTOR,
        BNO_REPORT_GAME_ROTATION_VECTOR,
        BNO_REPORT_ACCELEROMETER,
        BNO_REPORT_GYROSCOPE,
    )
except Exception as e:
    print("ERROR: adafruit-circuitpython-bno08x not fully available.")
    print("Install into venv:")
    print("  timeout 60s venv/bin/python -m pip install adafruit-circuitpython-bno08x adafruit-blinka")
    print(f"Import error: {e}")
    sys.exit(3)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run BNO08x over UART using Adafruit library")
    p.add_argument("--port", default="/dev/ttyAMA1", help="Serial device (default: /dev/ttyAMA1)")
    p.add_argument("--baud", type=int, default=3000000, help="Baud rate (default: 3000000)")
    p.add_argument("--duration", type=float, default=10.0, help="Seconds to run (default: 10.0)")
    p.add_argument("--interval", type=float, default=0.05, help="Read interval seconds (default: 0.05)")
    p.add_argument("--game", action="store_true", help="Use Game Rotation Vector instead of full Rotation Vector")
    p.add_argument("--extra-sensors", action="store_true", help="Enable accel/gyro reports as well")
    p.add_argument("--pre-reset", action="store_true", help="Send UART break and toggle RTS/DTR before init")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # Open pyserial port first (Blinka busio not required when using UART class with pyserial)
    try:
        ser = serial.Serial(args.port, baudrate=args.baud, timeout=0.2)
    except Exception as e:
        print(f"OPEN FAIL {args.port}@{args.baud}: {e}")
        return 2

    print(f"OPEN OK {args.port}@{args.baud}")

    # Optional pre-reset sequence to coax SHTP
    try:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        if args.pre-reset:
            try:
                ser.send_break(duration=0.02)
            except Exception:
                pass
            try:
                ser.rts = False
                ser.dtr = False
                time.sleep(0.02)
                ser.rts = True
                ser.dtr = True
                time.sleep(0.02)
                ser.rts = False
                ser.dtr = False
            except Exception:
                pass
    except Exception:
        pass

    # Guard against library-level hangs using SIGALRM (Linux only)
    class _Timeout:
        def __init__(self, seconds: int):
            self.seconds = seconds
            self._old = None

        def __enter__(self):
            def _handler(signum, frame):
                raise TimeoutError("operation timed out")

            self._old = signal.signal(signal.SIGALRM, _handler)
            signal.alarm(self.seconds)
            return self

        def __exit__(self, exc_type, exc, tb):
            signal.alarm(0)
            if self._old is not None:
                signal.signal(signal.SIGALRM, self._old)
            return False

    try:
        with _Timeout(8):
            bno = BNO08X_UART(ser)  # Adafruit driver accepts a UART-like object (pyserial works)
    except Exception as e:
        print("Failed to initialize BNO08X over UART:")
        print(e)
        try:
            ser.close()
        except Exception:
            pass
        return 4

    # Enable features
    try:
        with _Timeout(6):
            if args.game:
                bno.enable_feature(BNO_REPORT_GAME_ROTATION_VECTOR)
                active = "GAME_ROTATION_VECTOR"
            else:
                bno.enable_feature(BNO_REPORT_ROTATION_VECTOR)
                active = "ROTATION_VECTOR"
            if args.extra_sensors:
                bno.enable_feature(BNO_REPORT_ACCELEROMETER)
                bno.enable_feature(BNO_REPORT_GYROSCOPE)
            print(f"Enabled {active}{' + ACCEL + GYRO' if args.extra_sensors else ''}")
    except Exception as e:
        print(f"Failed to enable features: {e}")
        try:
            ser.close()
        except Exception:
            pass
        return 5

    # Read loop (bounded)
    start = time.time()
    reads = 0
    errors = 0
    while time.time() - start < args.duration:
        time.sleep(args.interval)
        try:
            qi, qj, qk, qr = bno.quaternion  # tuple of 4 floats
            reads += 1
            print(f"quat: i={qi:.5f} j={qj:.5f} k={qk:.5f} r={qr:.5f}")
        except Exception as e:
            # Occasional timeouts are acceptable; count and continue
            errors += 1
            # Keep the output concise
            if errors <= 3:
                print(f"read error: {e}")

    print(f"Done. Reads={reads}, Errors={errors}")
    try:
        ser.close()
    except Exception:
        pass
    return 0 if reads > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
