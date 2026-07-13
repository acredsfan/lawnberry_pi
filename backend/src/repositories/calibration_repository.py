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
import math
from datetime import UTC, datetime, timedelta
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

_REUSABLE_ALIGNMENT_SOURCES = {"gps_cog_snap", "stop_navigation"}
_MAX_FUTURE_SKEW_S = 30.0


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

    def __init__(
        self,
        calibration_path: Path | None = None,
        *,
        imu_epoch_id: str | None = None,
    ) -> None:
        if calibration_path is None:
            calibration_path = Path("data") / "calibration.json"
        self._calibration_path = calibration_path
        # Bound only after a genuinely fresh BNO085 report identifies the
        # current hardware reset generation. Process lifetime is not a safe
        # substitute because the driver can reinitialize in-process.
        self._imu_epoch_id = self._normalize_epoch_id(imu_epoch_id)
        self._calibration_path.parent.mkdir(parents=True, exist_ok=True)
        self._reconcile_legacy_alignment_file()

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

    @property
    def imu_epoch_id(self) -> str | None:
        return self._imu_epoch_id

    def bind_imu_epoch(self, imu_epoch_id: str) -> bool:
        """Bind persistence to the live BNO085 reset generation.

        Returns ``True`` when an already-bound sensor changed generation.
        Binding never edits or re-labels stored evidence; old records remain
        non-reusable until a fresh GPS COG snap is acquired in the new epoch.
        """
        normalized = self._normalize_epoch_id(imu_epoch_id)
        if normalized is None:
            raise ValueError("imu_epoch_id must be a non-empty string")
        changed = self._imu_epoch_id is not None and self._imu_epoch_id != normalized
        self._imu_epoch_id = normalized
        return changed

    def load_reusable_imu_alignment(self, *, max_age_s: float) -> dict[str, Any] | None:
        """Return current-epoch authoritative evidence within its age window."""
        alignment = self._authoritative_alignment(self.load_imu_alignment())
        if alignment is None or self._imu_epoch_id is None:
            return None
        record, timestamp = alignment
        if record.get("imu_epoch_id") != self._imu_epoch_id:
            return None
        age_s = (datetime.now(UTC) - timestamp).total_seconds()
        if age_s < -_MAX_FUTURE_SKEW_S or age_s > float(max_age_s):
            return None
        return record

    def save_imu_alignment(
        self,
        heading_deg: float,
        sample_count: int,
        source: str,
        *,
        imu_epoch_id: str | None = None,
    ) -> bool:
        """Persist current IMU heading alignment atomically.

        Silently swallows I/O errors so a filesystem issue never crashes navigation.
        """
        if not math.isfinite(float(heading_deg)):
            logger.warning("CalibrationRepository: rejected non-finite IMU alignment")
            return False
        evidence_epoch = self._normalize_epoch_id(imu_epoch_id)
        if source in _REUSABLE_ALIGNMENT_SOURCES and (
            self._imu_epoch_id is None
            or evidence_epoch is None
            or evidence_epoch != self._imu_epoch_id
            or int(sample_count) < 1
        ):
            logger.warning(
                "CalibrationRepository: rejected reusable alignment without "
                "current-epoch evidence (source=%s)",
                source,
            )
            return False
        try:
            data = self._load_file()
            record = {
                "session_heading_alignment": round(heading_deg % 360.0, 3),
                "sample_count": sample_count,
                "source": source,
                "last_updated": datetime.now(UTC).isoformat(),
            }
            if evidence_epoch is not None and evidence_epoch == self._imu_epoch_id:
                record["imu_epoch_id"] = evidence_epoch
            data["imu"] = record
            self._write_file(data)
            logger.info(
                "CalibrationRepository: IMU alignment saved %.1f° (source=%s, samples=%d)",
                heading_deg,
                source,
                sample_count,
            )
            return True
        except Exception as exc:
            logger.warning("CalibrationRepository: could not save IMU alignment: %s", exc)
            return False

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
    @staticmethod
    def _normalize_epoch_id(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

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

    @staticmethod
    def _alignment_timestamp(record: dict[str, Any]) -> datetime | None:
        value = record.get("last_updated")
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError:
            return None
        return timestamp.replace(tzinfo=timestamp.tzinfo or UTC)

    @classmethod
    def _authoritative_alignment(
        cls,
        record: dict[str, Any],
    ) -> tuple[dict[str, Any], datetime] | None:
        """Return a normalized, timestamped alignment safe to reuse."""
        try:
            source = str(record.get("source", "default")).strip()
            samples = int(record.get("sample_count", 0))
            heading = float(record.get("session_heading_alignment", 0.0)) % 360.0
        except (TypeError, ValueError):
            return None
        timestamp = cls._alignment_timestamp(record)
        if (
            samples < 1
            or source not in _REUSABLE_ALIGNMENT_SOURCES
            or not math.isfinite(heading)
            or timestamp is None
            or timestamp > datetime.now(UTC) + timedelta(seconds=_MAX_FUTURE_SKEW_S)
        ):
            return None
        normalized = {
            "session_heading_alignment": round(heading, 3),
            "sample_count": samples,
            "source": source,
            # Preserve acquisition time; migration must not make stale evidence fresh.
            "last_updated": str(record["last_updated"]),
        }
        epoch = record.get("imu_epoch_id")
        if isinstance(epoch, str) and epoch.strip():
            normalized["imu_epoch_id"] = epoch.strip()
        return normalized, timestamp

    def _reconcile_legacy_alignment_file(self) -> None:
        """Promote newer authoritative legacy evidence into canonical storage.

        Older releases let ``LocalizationService`` write ``imu_alignment.json``
        while mission admission read ``calibration.json``. Reconcile that split
        owner at startup without overwriting newer canonical evidence or changing
        the original acquisition timestamp.
        """
        legacy = self._calibration_path.parent / "imu_alignment.json"
        if not legacy.exists():
            return
        try:
            legacy_record = json.loads(legacy.read_text(encoding="utf-8"))
            legacy_alignment = self._authoritative_alignment(legacy_record)
            if legacy_alignment is None:
                logger.info(
                    "CalibrationRepository: ignored non-authoritative legacy IMU alignment"
                )
                return

            canonical_data = self._load_file()
            canonical_timestamp = self._alignment_timestamp(
                canonical_data.get("imu", {})
            )
            normalized_legacy, legacy_timestamp = legacy_alignment
            if canonical_timestamp is not None and canonical_timestamp >= legacy_timestamp:
                return

            canonical_data["imu"] = normalized_legacy
            self._write_file(canonical_data)
            logger.info(
                "CalibrationRepository: promoted newer authoritative legacy IMU alignment"
            )
            archive = legacy.with_suffix(".json.migrated")
            if not archive.exists():
                legacy.replace(archive)
                logger.info(
                    "CalibrationRepository: retired legacy IMU alignment as %s",
                    archive.name,
                )
        except Exception as exc:
            logger.warning("CalibrationRepository: legacy reconciliation failed: %s", exc)
