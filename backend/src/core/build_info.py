"""Runtime build identity exposed to operators and diagnostics."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

APP_VERSION = "2.0.0"
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_STARTED_AT = datetime.now(UTC)


def _valid_sha(value: str | None) -> str | None:
    candidate = (value or "").strip()
    return candidate.lower() if _SHA_RE.fullmatch(candidate) else None


def _git_sha() -> str | None:
    """Resolve the checkout SHA without invoking a shell."""
    repository = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _valid_sha(result.stdout)


@lru_cache(maxsize=1)
def get_build_info() -> dict[str, Any]:
    """Return immutable process build metadata.

    Packaged deployments should set ``LAWNBERRY_BUILD_SHA``. A checkout falls
    back to ``git rev-parse``; failure remains explicit instead of inventing an
    identifier.
    """
    commit_sha = _valid_sha(os.getenv("LAWNBERRY_BUILD_SHA")) or _git_sha()
    return {
        "version": APP_VERSION,
        "commit_sha": commit_sha,
        "short_sha": commit_sha[:12] if commit_sha else None,
        "source": "environment" if _valid_sha(os.getenv("LAWNBERRY_BUILD_SHA")) else (
            "git" if commit_sha else "unavailable"
        ),
        "started_at": _STARTED_AT.isoformat(),
    }


__all__ = ["APP_VERSION", "get_build_info"]
