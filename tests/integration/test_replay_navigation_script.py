"""Smoke tests for scripts/replay_navigation.py."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "replay_navigation.py"
FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "navigation" / "synthetic_straight_drive.jsonl"
)


@pytest.fixture(autouse=True)
def isolate_alignment_file():
    alignment_file = REPO_ROOT / "data" / "imu_alignment.json"
    backup_file = REPO_ROOT / "data" / "imu_alignment.json.testbackup"

    has_alignment = alignment_file.exists()
    if has_alignment:
        shutil.move(str(alignment_file), str(backup_file))

    yield

    if has_alignment:
        if alignment_file.exists():
            alignment_file.unlink()
        shutil.move(str(backup_file), str(alignment_file))


def test_replay_script_exits_zero_on_synthetic_fixture():
    assert SCRIPT.exists()
    assert FIXTURE.exists()
    env = os.environ.copy()
    env["SIM_MODE"] = "1"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"replay script exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "OK" in result.stdout or "PASS" in result.stdout.upper()


def test_replay_script_exits_nonzero_on_missing_fixture(tmp_path: Path):
    env = os.environ.copy()
    env["SIM_MODE"] = "1"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "no-such.jsonl")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode != 0


