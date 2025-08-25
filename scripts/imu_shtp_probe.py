#!/usr/bin/env python3
"""
SHTP (BNO08x) Serial Frame Probe

Attempt to detect SHTP-style binary frames from BNO08x IMUs.

Reads raw bytes and scans for SHTP packet length headers (little-endian uint16 length)
and prints basic info (port, baud, channel, seq, payload hex preview).

Usage:
    # Pi 5 (UART1 on GPIO12/13):
    ./scripts/imu_shtp_probe.py --port /dev/ttyAMA1 --baud 3000000 --duration 6
    # Pi 4/CM4 (UART4):
    ./scripts/imu_shtp_probe.py --port /dev/ttyAMA4 --baud 3000000 --duration 6
"""

import argparse
import sys
import time

try:
    import serial
except Exception as e:
    print(f"ERROR: pyserial not available: {e}")
    sys.exit(2)


def parse_args():
    p = argparse.ArgumentParser(description="SHTP serial probe for BNO08x frames")
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=3000000)
    p.add_argument("--duration", type=float, default=6.0)
    p.add_argument("--limit", type=int, default=64, help="Hex preview limit")
    return p.parse_args()


def hex_preview(b: bytes, limit: int) -> str:
    return " ".join(f"{x:02X}" for x in b[:limit])


def run_probe(port: str, baud: int, duration: float, limit: int) -> int:
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=0.5)
    except Exception as e:
        print(f"OPEN FAIL {port}@{baud}: {e}")
        return 1

    print(f"OPEN OK {port}@{baud} - scanning for SHTP frames for {duration}s")
    start = time.time()
    buf = bytearray()
    found = 0
    try:
        while time.time() - start < duration:
            chunk = ser.read(512)
            if not chunk:
                continue
            buf.extend(chunk)
            # Try to parse SHTP packets: 2-byte little-endian length, then channel(1) seq(1)
            while len(buf) >= 4:
                length = buf[0] | (buf[1] << 8)
                if length < 4 or length > 4096:
                    # Not a valid SHTP length at this offset: drop first byte
                    buf.pop(0)
                    continue
                if len(buf) < length:
                    # wait for more
                    break
                packet = bytes(buf[:length])
                # SHTP header: length(2 LE), channel(1), seq(1)
                channel = packet[2]
                seq = packet[3]
                payload = packet[4:]
                now = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                print(f"{now} {port}@{baud} SHTP len={length} ch={channel} seq={seq} payload_len={len(payload)}")
                print(hex_preview(payload, limit))
                found += 1
                # consume
                del buf[:length]
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"READ ERROR: {e}")
    finally:
        try:
            ser.close()
        except Exception:
            pass

    if found == 0:
        print(f"No SHTP frames detected on {port}@{baud}")
        return 1
    print(f"Detected {found} SHTP packets on {port}@{baud}")
    return 0


def main():
    args = parse_args()
    return run_probe(args.port, args.baud, args.duration, args.limit)


if __name__ == '__main__':
    sys.exit(main())
