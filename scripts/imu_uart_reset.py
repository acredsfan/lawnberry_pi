#!/usr/bin/env python3
"""
IMU UART Reset Utility

Safe utilities to try a soft reset of UART-attached IMUs by using serial break
or toggling the RTS/DTR control lines. Many IMU modules expose a reset pin
wired to RTS/DTR or respond to a serial break; toggling these lines is a
non-invasive way to attempt a reset before power-cycling.

WARNING: Behavior depends on the IMU module wiring. Use carefully.

Examples:
    # Pi 5 (UART1 on GPIO12/13): send a 200ms serial break at 3,000,000 baud
    ./scripts/imu_uart_reset.py --port /dev/ttyAMA1 --baud 3000000 --send-break --break-duration 0.2

    # Pi 4/CM4 (UART4): send a 200ms serial break at 3,000,000 baud
    ./scripts/imu_uart_reset.py --port /dev/ttyAMA4 --baud 3000000 --send-break --break-duration 0.2

    # Pulse DTR low for 100ms (common active-low reset) and then probe manually
    ./scripts/imu_uart_reset.py --port /dev/ttyAMA1 --baud 3000000 --pulse-dtr 100

    # Pulse RTS high for 50ms
    ./scripts/imu_uart_reset.py --port /dev/ttyAMA1 --baud 3000000 --pulse-rts 50 --rts-active-low False
"""

import argparse
import sys
import time

try:
    import serial
except Exception as e:
    print(f"ERROR: pyserial required: {e}")
    sys.exit(2)


def parse_args():
    p = argparse.ArgumentParser(description="IMU UART reset helpers (break/RTS/DTR)")
    p.add_argument('--port', required=True, help='Serial port (e.g. /dev/ttyAMA4)')
    p.add_argument('--baud', type=int, default=115200, help='Baud rate for opening port')
    p.add_argument('--send-break', action='store_true', help='Send a serial break')
    p.add_argument('--break-duration', type=float, default=0.2, help='Break duration seconds')
    p.add_argument('--pulse-dtr', type=int, default=0, help='Pulse DTR for <ms> milliseconds (0 = disabled)')
    p.add_argument('--pulse-rts', type=int, default=0, help='Pulse RTS for <ms> milliseconds (0 = disabled)')
    p.add_argument('--dtr-active-low', action='store_true', help='Treat DTR as active-low (default useful for many modules)')
    p.add_argument('--rts-active-low', action='store_true', help='Treat RTS as active-low')
    return p.parse_args()


def pulse_line(ser: serial.Serial, line: str, ms: int, active_low: bool):
    # line: 'dtr' or 'rts'
    if ms <= 0:
        return
    # compute active and inactive levels
    active = False if active_low else True
    inactive = not active
    try:
        # Set to inactive state first (ensure defined starting point)
        if line == 'dtr':
            if hasattr(ser, 'dtr'):
                ser.dtr = inactive
            else:
                raise AttributeError('serial object has no attribute dtr')
        else:
            if hasattr(ser, 'rts'):
                ser.rts = inactive
            else:
                raise AttributeError('serial object has no attribute rts')
        time.sleep(0.01)
        # set active
        if line == 'dtr':
            ser.dtr = active
        else:
            ser.rts = active
        time.sleep(ms / 1000.0)
        # restore inactive
        if line == 'dtr':
            ser.dtr = inactive
        else:
            ser.rts = inactive
    except Exception as e:
        print(f"Failed to pulse {line.upper()}: {e}")


def main():
    args = parse_args()
    try:
        ser = serial.Serial(args.port, baudrate=args.baud, timeout=0.2)
    except Exception as e:
        print(f"OPEN FAIL {args.port}@{args.baud}: {e}")
        return 2

    print(f"OPEN OK {args.port}@{args.baud}")
    try:
        if args.send_break:
            try:
                print(f"Sending break for {args.break_duration}s...")
                # pyserial: send_break(duration) is supported
                ser.send_break(args.break_duration)
                print("Break sent")
            except Exception as e:
                print(f"send_break failed: {e}")

        if args.pulse_dtr > 0:
            print(f"Pulsing DTR for {args.pulse_dtr} ms (active_low={args.dtr_active_low})")
            pulse_line(ser, 'dtr', args.pulse_dtr, args.dtr_active_low)

        if args.pulse_rts > 0:
            print(f"Pulsing RTS for {args.pulse_rts} ms (active_low={args.rts_active_low})")
            pulse_line(ser, 'rts', args.pulse_rts, args.rts_active_low)

        print("Completed actions. Close the port and re-run probe if desired.")
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
