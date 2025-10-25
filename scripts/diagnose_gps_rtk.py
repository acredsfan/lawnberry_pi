#!/usr/bin/env python3
import os
import sys
import time
from typing import Optional, Tuple

try:
    import serial  # type: ignore
except Exception:
    print("pyserial not installed; cannot run diagnosis", file=sys.stderr)
    sys.exit(2)

DEVICE = os.environ.get("GPS_DEVICE") or os.environ.get("NTRIP_SERIAL_DEVICE") or "/dev/ttyACM1"
BAUD = int(os.environ.get("GPS_BAUD", os.environ.get("NTRIP_SERIAL_BAUD", "115200")))
DURATION = float(os.environ.get("GPS_DIAG_DURATION", "12"))


def parse_nmea_coord(val: str, hemi: str) -> Optional[float]:
    try:
        if not val or not hemi:
            return None
        if "." not in val:
            return None
        dot = val.find(".")
        deg_len = dot - 2
        deg = int(val[:deg_len])
        mins = float(val[deg_len:])
        dec = deg + mins / 60.0
        if hemi in ("S", "W"):
            dec = -dec
        return dec
    except Exception:
        return None


def parse_gga(line: str) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[float], Optional[int]]:
    # returns (lat, lon, sats, hdop, fix_quality)
    parts = line.split(",")
    lat = parse_nmea_coord(parts[2], parts[3]) if len(parts) > 4 else None
    lon = parse_nmea_coord(parts[4], parts[5]) if len(parts) > 6 else None
    fix_quality = int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else None
    sats = int(parts[7]) if len(parts) > 7 and parts[7].isdigit() else None
    try:
        hdop = float(parts[8]) if len(parts) > 8 and parts[8] != "" else None
    except Exception:
        hdop = None
    return lat, lon, sats, hdop, fix_quality


def parse_gst(line: str) -> Optional[float]:
    parts = line.split(",")
    if len(parts) < 9:
        return None
    try:
        sd_lat = float(parts[6]) if parts[6] else None
        sd_lon = float(parts[7]) if parts[7] else None
        if sd_lat is None or sd_lon is None:
            return None
        # horiz 1-sigma meters
        return (sd_lat ** 2 + sd_lon ** 2) ** 0.5
    except Exception:
        return None


def main() -> int:
    print(f"Opening {DEVICE} at {BAUD} for {DURATION}s ...")
    ser = serial.Serial(DEVICE, BAUD, timeout=0.25)
    t_end = time.time() + DURATION
    last_gga = None
    best_gst = None
    while time.time() < t_end:
        raw = ser.readline()
        if not raw:
            continue
        try:
            s = raw.decode("ascii", errors="ignore").strip()
        except Exception:
            continue
        if s.startswith(("$GPGGA", "$GNGGA")):
            last_gga = parse_gga(s)
        elif s.startswith(("$GPGST", "$GNGST")):
            val = parse_gst(s)
            if val is not None:
                if best_gst is None or val < best_gst:
                    best_gst = val
    ser.close()

    print("\n=== GPS Summary ===")
    if last_gga:
        lat, lon, sats, hdop, q = last_gga
        print(f"Lat,Lon: {lat:.6f if lat is not None else 'n/a'}, {lon:.6f if lon is not None else 'n/a'}")
        print(f"Satellites: {sats}")
        print(f"HDOP: {hdop}")
        quality_map = {0: 'NO_FIX', 1: 'GPS', 2: 'DGPS', 4: 'RTK_FIXED', 5: 'RTK_FLOAT'}
        q_name = quality_map.get(q, str(q))
        print(f"GGA Fix Quality: {q} ({q_name})")
    else:
        print("No GGA observed.")

    if best_gst is not None:
        print(f"Best GST horizontal 1-sigma accuracy: {best_gst:.3f} m")
    else:
        print("No GST observed (receiver may not be outputting).")

    print("\nIf GGA quality is not 4 or 5, the receiver is not in RTK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
