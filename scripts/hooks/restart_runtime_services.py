#!/usr/bin/env python3
"""Stop hook that restarts LawnBerry backend/frontend services after completed work."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
RESTART_RELEVANT_PREFIXES = (
    "backend/",
    "frontend/",
    "config/",
    "systemd/",
    "scripts/",
    ".env",
    "pyproject.toml",
)
SERVICE_UNITS = (
    "lawnberry-backend.service",
    "lawnberry-frontend.service",
)
RESTART_TIMEOUT_SECONDS = 40


def _run_git(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _get_changed_paths() -> list[str]:
    changed: set[str] = set()
    for args in (
        ("diff", "--name-only", "--cached", "--diff-filter=ACMR"),
        ("diff", "--name-only", "--diff-filter=ACMR"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        changed.update(_run_git(*args))
    return sorted(changed)


def _matches_any(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def _emit(payload: dict[str, object], *, exit_code: int = 0) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    raise SystemExit(exit_code)


def _restart_services() -> tuple[bool, str]:
    attempts: list[list[str]] = []

    if shutil.which("sudo"):
        attempts.append(["sudo", "-n", "systemctl", "restart", *SERVICE_UNITS])
    if shutil.which("systemctl"):
        attempts.append(["systemctl", "restart", *SERVICE_UNITS])

    if not attempts:
        return False, "No supported restart command found (`systemctl` unavailable)."

    errors: list[str] = []
    for command in attempts:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=RESTART_TIMEOUT_SECONDS,
        )
        if completed.returncode == 0:
            return True, " ".join(command)
        stderr = (completed.stderr or completed.stdout or "unknown error").strip()
        errors.append(f"{' '.join(command)} -> {stderr}")

    return False, "; ".join(errors)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}

    if payload.get("hookEventName") != "Stop":
        _emit({"continue": True})

    if payload.get("stop_hook_active"):
        _emit({"continue": True})

    try:
        changed_paths = _get_changed_paths()
    except Exception as exc:  # pragma: no cover - hook should stay best-effort
        _emit(
            {
                "continue": True,
                "systemMessage": (
                    "Runtime restart hook could not inspect Git changes, so it skipped the restart. "
                    f"Details: {exc}"
                ),
            }
        )

    if not changed_paths:
        _emit({"continue": True})

    relevant_paths = [
        path for path in changed_paths if _matches_any(path, RESTART_RELEVANT_PREFIXES)
    ]
    if not relevant_paths:
        _emit(
            {
                "continue": True,
                "systemMessage": (
                    "Runtime restart hook skipped service restart because only non-runtime files changed."
                ),
            }
        )

    try:
        restarted, details = _restart_services()
    except subprocess.TimeoutExpired:
        _emit(
            {
                "continue": True,
                "systemMessage": (
                    "Runtime restart hook timed out while restarting LawnBerry services. "
                    f"Changed files included: {', '.join(relevant_paths[:5])}"
                ),
            }
        )

    if restarted:
        _emit(
            {
                "continue": True,
                "systemMessage": (
                    "Runtime restart hook restarted LawnBerry backend/frontend services after task completion "
                    f"using `{details}`."
                ),
            }
        )

    _emit(
        {
            "continue": True,
            "systemMessage": (
                "Runtime restart hook detected runtime-affecting changes but could not restart services automatically. "
                f"Details: {details}"
            ),
        }
    )


if __name__ == "__main__":
    main()
