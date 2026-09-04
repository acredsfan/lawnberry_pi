from __future__ import annotations

import csv
import os
import tempfile
from datetime import datetime
from pathlib import Path


def test_hil_probe_generates_csv_and_ranges():
    # Run the probe for a very short time in SIM mode and parse CSV
    import subprocess
    import sys

    out_fd, out_path = tempfile.mkstemp(prefix="hil_", suffix=".csv")
    os.close(out_fd)
    env = os.environ.copy()
    env.setdefault("SIM_MODE", "1")
    cmd = [
        sys.executable,
        str(Path("scripts/hil_probe.py")),
        "--duration",
        "0.4",
        "--interval",
        "0.1",
        "--out",
        out_path,
        "--base-url",
        "http://127.0.0.1:1",
    ]
    subprocess.run(cmd, check=True, env=env)

    assert Path(out_path).exists(), "CSV was not created"
    with open(out_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) >= 3, "Expected multiple samples"
    # Basic schema checks
    required_cols = {
        "timestamp",
        "sample_index",
        "monotonic_elapsed_s",
        "safety_state",
        "watchdog_ms",
        "overall_status",
        "cpu_usage",
        "mem_mb",
    }
    assert required_cols.issubset(rows[0].keys())

    # UTC wall time is useful for correlation but may step when NTP corrects the
    # host. Sample order and elapsed time therefore use the monotonic clock.
    prev_elapsed = None
    for expected_index, row in enumerate(rows):
        ts = row["timestamp"]
        parsed_ts = datetime.fromisoformat(ts)
        assert parsed_ts.tzinfo is not None
        assert int(row["sample_index"]) == expected_index
        elapsed = float(row["monotonic_elapsed_s"])
        if prev_elapsed is not None:
            assert elapsed >= prev_elapsed
        prev_elapsed = elapsed
        if row["cpu_usage"] is not None and row["cpu_usage"] != "":
            try:
                val = float(row["cpu_usage"])  # may serialize as number
            except Exception:
                continue
            assert 0.0 <= val <= 100.0
