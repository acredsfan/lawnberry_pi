# backend/src/repositories/calibration_repository.py
"""CalibrationRepository: single owner of IMU alignment and tunable parameters.

Storage backend: a human-editable JSON file (default: data/calibration.json).
Writes are atomic: write to a .tmp file, then rename to replace the target.
Read errors (missing or corrupt file) return safe defaults and log a warning.

This is intentionally NOT SQLite so operators can edit calibration values by
hand during field bring-up without a database client.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_IMU_ALIGNMENT: dict[str, Any] = {
    "session_heading_alignment": 0.0,
    "sample_count": 0,
    "source": "default",
    "last_updated": None,
}

_DEFAULT_TUNABLES: dict[str, Any] = {}


class CalibrationRepository:
    """Owns IMU alignment offset and operator-editable calibration tunables.

    The file schema is::

        {
          "imu": {
            "session_heading_alignment": <float degrees>,
            "sample_count": <int>,
            "source": <str>,
            "last_updated": <ISO-8601 str>
          },
          "tunables": {
            "<key>": <value>,
            ...
          }
        }
    """

    def __init__(self, calibration_path: Path | None = None) -> None:
        if calibration_path is None:
            calibration_path = Path("data") / "calibration.json"
        self._calibration_path = calibration_path
        self._calibration_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_alignment_file()

    # ------------------------------------------------------------------
    # IMU alignment
    # ------------------------------------------------------------------
    def load_imu_alignment(self) -> dict[str, Any]:
        """Return saved alignment or safe defaults if file is absent/corrupt."""
        data = self._load_file()
        imu = data.get("imu", {})
        result = dict(_DEFAULT_IMU_ALIGNMENT)
        result.update(imu)
        return result

    def save_imu_alignment(
        self, heading_deg: float, sample_count: int, source: str
    ) -> None:
        """Persist current IMU heading alignment atomically.

        Silently swallows I/O errors so a filesystem issue never crashes navigation.
        """
        try:
            data = self._load_file()
            data["imu"] = {
                "session_heading_alignment": round(heading_deg % 360.0, 3),
                "sample_count": sample_count,
                "source": source,
                "last_updated": datetime.now(UTC).isoformat(),
            }
            self._write_file(data)
            logger.info(
                "CalibrationRepository: IMU alignment saved %.1f° (source=%s, samples=%d)",
                heading_deg,
                source,
                sample_count,
            )
        except Exception as exc:
            logger.warning("CalibrationRepository: could not save IMU alignment: %s", exc)

    # ------------------------------------------------------------------
    # Tunables
    # ------------------------------------------------------------------
    def load_tunables(self) -> dict[str, Any]:
        """Return the tunables dict (empty dict if absent)."""
        data = self._load_file()
        return dict(data.get("tunables", _DEFAULT_TUNABLES))

    def save_tunables(self, tunables: dict[str, Any]) -> None:
        """Replace the entire tunables section."""
        data = self._load_file()
        data["tunables"] = tunables
        self._write_file(data)
        logger.debug("CalibrationRepository: saved tunables: %s", list(tunables.keys()))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_file(self) -> dict[str, Any]:
        if not self._calibration_path.exists():
            return {}
        try:
            return json.loads(self._calibration_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "CalibrationRepository: could not read %s: %s", self._calibration_path, exc
            )
            return {}

    def _write_file(self, data: dict[str, Any]) -> None:
        """Atomic write: write to .tmp then rename."""
        tmp = self._calibration_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._calibration_path)

    def _migrate_legacy_alignment_file(self) -> None:
        """One-time migration: if data/imu_alignment.json exists and calibration.json does not, import it."""
        legacy = self._calibration_path.parent / "imu_alignment.json"
        if legacy.exists() and not self._calibration_path.exists():
            try:
                data = json.loads(legacy.read_text(encoding="utf-8"))
                self.save_imu_alignment(
                    heading_deg=float(data.get("session_heading_alignment", 0.0)),
                    sample_count=int(data.get("sample_count", 0)),
                    source="migrated_from_legacy",
                )
                logger.info("CalibrationRepository: migrated imu_alignment.json -> calibration.json")
            except Exception as exc:
                logger.warning("CalibrationRepository: legacy migration failed: %s", exc)
