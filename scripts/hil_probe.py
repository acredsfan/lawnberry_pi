#!/usr/bin/env python3
from __future__ import annotations

"""Hardware-in-the-Loop probe script (HIL) (T122).

Collects safety and system health snapshots periodically and writes CSV.

Guard rails:
- SIM by default; no motion commands here
- REAL_HW only when REAL_HW=1
- Will never enable motors or blades; RUN_ENABLE must be 1 to allow any actuation (not used)
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone


def _bool_env(name: str, default: bool = False) -> bool:
    return str(os.getenv(name, "1" if default else "0")).strip() in {"1", "true", "yes"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def probe_once(client, base_url: str) -> dict:
    row = {
        "timestamp": _now_iso(),
        "safety_state": None,
        "watchdog_ms": None,
        "overall_status": None,
        "cpu_usage": None,
        "mem_mb": None,
    }
    try:
        r = client.get(f"{base_url}/api/v2/health", timeout=2.0)
        if r.status_code < 400:
            hp = r.json() or {}
            row["overall_status"] = (hp.get("overall_status") or "").lower()
            metrics = hp.get("metrics") or {}
            row["cpu_usage"] = metrics.get("cpu_usage_percent")
            row["mem_mb"] = metrics.get("memory_usage_mb")
    except Exception:
        pass

    try:
        r = client.get(f"{base_url}/api/v2/hardware/robohat", timeout=2.0)
        if r.status_code < 400:
            rp = r.json() or {}
            row["safety_state"] = rp.get("safety_state")
            row["watchdog_ms"] = rp.get("watchdog_heartbeat_ms")
    except Exception:
        pass

    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="LawnBerry HIL probe to CSV")
    parser.add_argument("--duration", type=int, default=30, help="Duration seconds")
    parser.add_argument(
        "--out",
        type=str,
        default=f"/home/pi/lawnberry/logs/hil_{int(time.time())}.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Sample interval seconds",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("LAWNBERRY_API_URL", "http://127.0.0.1:8000"),
        help="API base URL",
    )
    args = parser.parse_args()

    # Guard rails
    REAL_HW = _bool_env("REAL_HW", False)
    RUN_ENABLE = _bool_env("RUN_ENABLE", False)
    SIM_MODE = _bool_env("SIM_MODE", True)

    if REAL_HW and not RUN_ENABLE:
        print("WARNING: REAL_HW=1 but RUN_ENABLE!=1; proceeding read-only", file=sys.stderr)

    # Prepare client
    import httpx

    client = httpx.Client()
    fields = ["timestamp", "safety_state", "watchdog_ms", "overall_status", "cpu_usage", "mem_mb"]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        t_end = time.time() + max(1, int(args.duration))
        while time.time() < t_end:
            row = probe_once(client, args.base_url)
            writer.writerow(row)
            f.flush()
            time.sleep(max(0.05, float(args.interval)))

    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
