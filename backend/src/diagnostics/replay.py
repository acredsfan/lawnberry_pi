"""JSONL telemetry replay loader.

Reads the capture format produced by TelemetryCapture. Validates the schema
version on each record and surfaces line numbers on parse errors.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError

from backend.src.models.diagnostics_capture import (
    CAPTURE_SCHEMA_VERSION,
    CaptureRecord,
)


class ReplayLoadError(Exception):
    """Raised when a capture file cannot be parsed or the schema is incompatible."""


class ReplayLoader:
    """Iterate over CaptureRecord entries in a JSONL capture file."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def __iter__(self) -> Iterator[CaptureRecord]:
        with self._path.open("r", encoding="utf-8") as fp:
            for line_num, raw in enumerate(fp, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    record = CaptureRecord.model_validate_json(line)
                except ValidationError as exc:
                    raise ReplayLoadError(
                        f"Failed to parse record at {self._path}:line {line_num}: {exc}"
                    ) from exc
                if record.capture_version != CAPTURE_SCHEMA_VERSION:
                    raise ReplayLoadError(
                        f"Incompatible capture schema at {self._path}:line {line_num}: "
                        f"got version {record.capture_version}, "
                        f"expected {CAPTURE_SCHEMA_VERSION}"
                    )
                yield record

    @property
    def path(self) -> Path:
        return self._path


__all__ = ["ReplayLoader", "ReplayLoadError"]
