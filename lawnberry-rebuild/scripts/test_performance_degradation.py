#!/usr/bin/env python3
import time
import statistics
import httpx

BASE = "http://127.0.0.1:8001"

if __name__ == "__main__":
    latencies = []
    with httpx.Client(timeout=2.0) as client:
        for _ in range(20):
            t0 = time.perf_counter()
            r = client.get(f"{BASE}/api/v2/dashboard/telemetry")
            r.raise_for_status()
            dt_ms = (time.perf_counter() - t0) * 1000
            latencies.append(dt_ms)
            time.sleep(0.05)
    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(0.95 * len(latencies)) - 1]
    print(f"p50: {p50:.2f} ms, p95: {p95:.2f} ms")
    if p95 > 100:
        print("WARN: p95 latency exceeds 100ms target")
