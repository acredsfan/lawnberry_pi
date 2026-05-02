"""Integration tests for scripts/replay_navigation.py --compare mode.

compare-run replays the same JSONL fixture through both the legacy path
(LAWN_LEGACY_NAV=1) and the refactored path (LAWN_LEGACY_NAV=0) and reports
per-step divergence in heading, position, and velocity.

These tests use subprocess so they exercise the real CLI arg parsing and
the real env-var branch inside NavigationService — no mocking of internals.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "replay_navigation.py"
FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "navigation" / "synthetic_straight_drive.jsonl"
)


def _run_compare(extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT), str(FIXTURE), "--compare"]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"SIM_MODE": "1", "PATH": "/usr/bin:/bin"},
        timeout=60,
    )


def test_compare_flag_is_accepted() -> None:
    """--compare must not produce an unrecognised-argument error."""
    result = _run_compare()
    assert result.returncode in {0, 1}, (
        f"unexpected exit code {result.returncode}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "unrecognized" not in result.stderr.lower(), result.stderr


def test_compare_exits_zero_when_paths_are_identical() -> None:
    """On the synthetic fixture both paths are identical, so exit code must be 0."""
    result = _run_compare()
    assert result.returncode == 0, (
        f"compare exited {result.returncode} unexpectedly\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_compare_output_contains_summary_line() -> None:
    """stdout must contain a line that names both paths and step count."""
    result = _run_compare()
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "compare" in combined.lower(), (
        f"expected 'compare' in output:\n{combined}"
    )
    assert "steps" in combined.lower(), (
        f"expected 'steps' in output:\n{combined}"
    )


def test_compare_output_contains_no_divergence_message() -> None:
    """When both paths agree, stdout must confirm zero divergence."""
    result = _run_compare()
    assert result.returncode == 0
    assert "no divergence" in result.stdout.lower() or "identical" in result.stdout.lower(), (
        f"expected 'no divergence' or 'identical' in stdout:\n{result.stdout}"
    )


def test_compare_json_report_flag() -> None:
    """--compare --report-json <path> writes a machine-readable divergence report."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        report_path = tf.name
    try:
        cmd = [
            sys.executable, str(SCRIPT), str(FIXTURE),
            "--compare", "--report-json", report_path,
        ]
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env={"SIM_MODE": "1", "PATH": "/usr/bin:/bin"},
            timeout=60,
        )
        assert result.returncode == 0, (
            f"exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert Path(report_path).exists(), "report JSON file was not created"
        with open(report_path) as f:
            report = json.load(f)
        assert "steps" in report, f"missing 'steps' key: {report}"
        assert "divergences" in report, f"missing 'divergences' key: {report}"
        assert "summary" in report, f"missing 'summary' key: {report}"
    finally:
        if os.path.exists(report_path):
            os.unlink(report_path)


def test_compare_missing_fixture_exits_nonzero(tmp_path: Path) -> None:
    """--compare on a nonexistent fixture must exit non-zero."""
    cmd = [
        sys.executable, str(SCRIPT),
        str(tmp_path / "no-such.jsonl"), "--compare",
    ]
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"SIM_MODE": "1", "PATH": "/usr/bin:/bin"},
        timeout=10,
    )
    assert result.returncode != 0
