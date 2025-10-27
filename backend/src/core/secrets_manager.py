"""Secrets management utilities.

Lightweight secrets manager for Pi deployment:
- Sources: environment variables, then file-based store at config/secrets.json
- File store permissions are enforced (0600)
- Audit logs for access and rotation, without logging values
- Simple rotation API to update and version secrets
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .context import get_correlation_id

_log = logging.getLogger(__name__)


@dataclass
class SecretRecord:
    value: str
    updated_at: str
    version: int


class SecretsManager:
    def __init__(self, store_path: Optional[str] = None) -> None:
        # Default to project config directory
        default_path = "./config/secrets.json"
        self._path = Path(store_path or os.getenv("LAWN_SECRETS_PATH", default_path))
        self._cache: Dict[str, SecretRecord] = {}
        self._loaded = False

    def _ensure_permissions(self) -> None:
        if not self._path.exists():
            return
        st = self._path.stat()
        # must be 0600
        if stat.S_IMODE(st.st_mode) != 0o600:
            os.chmod(self._path, 0o600)

    def _load(self) -> None:
        if self._loaded:
            return
        try:
            if self._path.exists():
                with self._path.open("r") as f:
                    raw = json.load(f)
                for k, meta in raw.items():
                    self._cache[k] = SecretRecord(
                        value=str(meta.get("value", "")),
                        updated_at=str(meta.get("updated_at", "")),
                        version=int(meta.get("version", 1)),
                    )
                self._ensure_permissions()
            self._loaded = True
        except Exception:
            _log.exception("Failed to load secrets file")
            self._loaded = True

    def get(self, key: str, *, default: Optional[str] = None, purpose: str = "") -> Optional[str]:
        # Prefer environment variables to allow containerization and CI
        env_key = os.getenv(key)
        if env_key is not None:
            self._audit("get", key, source="env", purpose=purpose)
            return env_key

        self._load()
        rec = self._cache.get(key)
        if rec is not None:
            self._audit("get", key, source="file", purpose=purpose)
            return rec.value

        # If a JWT secret is missing, generate and save one.
        if key == "JWT_SECRET":
            _log.warning("JWT_SECRET not found. Generating a new one.")
            new_secret = secrets.token_hex(32)
            self.set(key, new_secret)
            self._audit("generate", key, source="internal", purpose=purpose)
            return new_secret

        self._audit("miss", key, source="none", purpose=purpose)
        return default

    def set(self, key: str, value: str) -> None:
        self._load()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        rec = self._cache.get(key)
        version = 1 if rec is None else rec.version + 1
        self._cache[key] = SecretRecord(value=value, updated_at=now, version=version)
        self._persist()
        self._audit("set", key, source="file")

    def rotate(self, key: str, new_value: str) -> None:
        self.set(key, new_value)
        self._audit("rotate", key, source="file")

    def validate_required(self, keys: list[str]) -> dict:
        missing: dict[str, bool] = {}
        for k in keys:
            v = self.get(k, default=None, purpose="validate")
            if not v:
                missing[k] = True
        if missing:
            _log.error("Missing required secrets: %s", ", ".join(missing.keys()))
        return missing

    def _persist(self) -> None:
        try:
            data = {
                k: {"value": v.value, "updated_at": v.updated_at, "version": v.version} for k, v in self._cache.items()
            }
            tmp = self._path.with_suffix(".tmp")
            with tmp.open("w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self._path)
            os.chmod(self._path, 0o600)
        except Exception:
            _log.exception("Failed to persist secrets file")

    def _audit(self, action: str, key: str, *, source: str, purpose: str = "") -> None:
        _log.info(
            "secrets.%s key=%s source=%s purpose=%s corr=%s",
            action,
            key,
            source,
            purpose,
            get_correlation_id(),
        )
