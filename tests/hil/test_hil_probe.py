from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path


def test_hil_probe_generates_csv_and_ranges():
    # Run the probe for a very short time in SIM mode and parse CSV
    import subprocess, sys

    out_fd, out_path = tempfile.mkstemp(prefix="hil_", suffix=".csv")
    os.close(out_fd)
    env = os.environ.copy()
    env.setdefault("SIM_MODE", "1")
    cmd = [sys.executable, str(Path("scripts/hil_probe.py")), "--duration", "2", "--interval", "0.2", "--out", out_path]
    subprocess.run(cmd, check=True, env=env)

    assert Path(out_path).exists(), "CSV was not created"
    with open(out_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) >= 3, "Expected multiple samples"
    # Basic schema checks
    required_cols = {"timestamp", "safety_state", "watchdog_ms", "overall_status", "cpu_usage", "mem_mb"}
    assert required_cols.issubset(rows[0].keys())

    # Monotonic timestamps and sane value formats
    prev_ts = None
    for row in rows:
        ts = row["timestamp"]
        assert isinstance(ts, str) and len(ts) > 10
        if prev_ts is not None:
            assert ts >= prev_ts
        prev_ts = ts
        if row["cpu_usage"] is not None and row["cpu_usage"] != "":
            try:
                val = float(row["cpu_usage"])  # may serialize as number
            except Exception:
                continue
            assert 0.0 <= val <= 100.0
