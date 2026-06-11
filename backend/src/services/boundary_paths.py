"""Shared file paths for boundary helper runtime data."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    raw = os.getenv("LAWN_DATA_DIR", "").strip()
    return Path(raw) if raw else Path(os.getcwd()) / "data"


def boundary_file(name: str) -> Path:
    return data_dir() / name


PROPERTY_BOUNDARY_IMPORTED = "property_boundary_imported.json"
MOWING_BOUNDARY_CONFIRMED = "mowing_boundary_user_confirmed.json"
MOWING_BOUNDARY_SAFE = "mowing_boundary_safe.json"
BOUNDARY_CAPTURE_SESSION = "boundary_capture_session.json"
BOUNDARY_VERIFICATION_SESSION = "boundary_verification_session.json"
