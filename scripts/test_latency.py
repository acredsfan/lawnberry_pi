#!/usr/bin/env python3
import time

import httpx

BASE = "http://127.0.0.1:8001"

if __name__ == "__main__":
    t0 = time.perf_counter()
    with httpx.Client(timeout=2.0) as client:
        r = client.get(f"{BASE}/health")
        r.raise_for_status()
    dt_ms = (time.perf_counter() - t0) * 1000
    print(f"/health latency: {dt_ms:.2f} ms")
    if dt_ms > 100:
        print("WARN: latency exceeds 100ms target")
