"""Smoke tests for scripts/replay_navigation.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "replay_navigation.py"
FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "navigation" / "synthetic_straight_drive.jsonl"
)


def test_replay_script_exits_zero_on_synthetic_fixture():
    assert SCRIPT.exists()
    assert FIXTURE.exists()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"SIM_MODE": "1", "PATH": "/usr/bin:/bin"},
        timeout=30,
    )
    assert result.returncode == 0, (
        f"replay script exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "OK" in result.stdout or "PASS" in result.stdout.upper()


def test_replay_script_exits_nonzero_on_missing_fixture(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "no-such.jsonl")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"SIM_MODE": "1", "PATH": "/usr/bin:/bin"},
        timeout=10,
    )
    assert result.returncode != 0
