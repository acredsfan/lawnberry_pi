#!/usr/bin/env python3
"""
Poll the LawnBerry RTK diagnostics endpoint and print live NTRIP/GPS status.

Usage:
  python scripts/rtk_diagnostics_watch.py [--url http://127.0.0.1:8000] [--seconds 30] [--interval 2]

Shows whether NTRIP is connected, bytes forwarded and rate, and current GPS RTK status.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from typing import Any, Dict


def fetch(url: str) -> Dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status != 200:
                sys.stderr.write(f"HTTP {resp.status} from {url}\n")
                return None
            data = resp.read()
            try:
                return json.loads(data.decode("utf-8"))
            except Exception:
                sys.stderr.write("Failed to decode JSON response\n")
                return None
    except urllib.error.URLError as e:
        sys.stderr.write(f"Request error: {e}\n")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="Backend base URL")
    ap.add_argument("--seconds", type=int, default=30, help="Total duration to watch")
    ap.add_argument("--interval", type=float, default=2.0, help="Polling interval seconds")
    args = ap.parse_args()

    endpoint = args.url.rstrip("/") + "/api/v2/sensors/gps/rtk/diagnostics"
    deadline = time.time() + max(1, args.seconds)

    last_total = None
    print("Watching:", endpoint)
    while time.time() < deadline:
        payload = fetch(endpoint)
        if payload is None:
            time.sleep(args.interval)
            continue
        ntrip = payload.get("ntrip", {}) if isinstance(payload, dict) else {}
        gps = payload.get("gps", {}) if isinstance(payload, dict) else {}
        hw = payload.get("hardware", {}) if isinstance(payload, dict) else {}

        connected = ntrip.get("connected")
        total = ntrip.get("total_bytes_forwarded")
        rate = ntrip.get("approx_rate_bps")
        last_age = ntrip.get("last_forward_age_s")
        mount = ntrip.get("mountpoint")
        serial_dev = ntrip.get("serial_device")
        rtk = None
        if isinstance(gps.get("reading"), dict):
            rtk = gps["reading"].get("rtk_status")
        sats = gps.get("satellites")
        hdop = gps.get("last_hdop")

        if isinstance(total, int) and isinstance(last_total, int):
            delta = total - last_total
        else:
            delta = None
        last_total = total if isinstance(total, int) else last_total

        status = [
            f"connected={connected}",
            f"mount={mount}",
            f"serial={serial_dev}",
            f"bytes_total={total}",
            f"delta={delta}",
            f"rate_bps={rate}",
            f"last_fwd_age_s={last_age}",
            f"rtk_status={rtk}",
            f"hdop={hdop}",
            f"sats={sats}",
            f"gps_mode={gps.get('mode')}",
            f"nmea_gga={'yes' if isinstance(gps.get('nmea'), dict) and 'GGA' in gps['nmea'] else 'no'}",
        ]
        print("[RTK] ", "; ".join(str(s) for s in status))
        time.sleep(max(0.25, args.interval))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
