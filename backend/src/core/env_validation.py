"""Environment and configuration validation on startup."""

from __future__ import annotations

import logging
import os
from typing import List

from .secrets_manager import SecretsManager

_log = logging.getLogger(__name__)


REQUIRED_SECRETS: List[str] = [
    "JWT_SECRET",
]


def validate_environment() -> bool:
    ok = True
    # Validate secrets
    sm = SecretsManager()
    missing = sm.validate_required(REQUIRED_SECRETS)
    if missing:
        ok = False

    # Validate API key if required
    if os.getenv("API_KEY_REQUIRED", "0") == "1" and not sm.get("API_KEY_SECRET", default=None, purpose="startup"):
        _log.error("API_KEY_REQUIRED=1 but API_KEY_SECRET is not configured")
        ok = False

    # Body size sanity
    try:
        _ = int(os.getenv("INPUT_MAX_BODY_BYTES", "1000000"))
    except ValueError:
        _log.error("INPUT_MAX_BODY_BYTES must be an integer")
        ok = False

    return ok
