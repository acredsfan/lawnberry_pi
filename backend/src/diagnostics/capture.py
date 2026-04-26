"""JSONL telemetry capture writer.

Append-only. One JSON record per line. Flushes after each record so a process
crash mid-mission leaves a valid prefix on disk (every complete line is a
parseable record).

Synchronous file I/O is used deliberately: at ≤10 Hz capture rates the cost is
negligible on a Pi 4/5, and async I/O would introduce ordering complexity for
no practical benefit. If capture is ever called from a hot loop, batching can
be added later.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import IO

from backend.src.models.diagnostics_capture import CaptureRecord

logger = logging.getLogger(__name__)


class TelemetryCapture:
    """Append-only JSONL writer for CaptureRecord."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._fp: IO[str] | None = None

    def _ensure_open(self) -> IO[str]:
        if self._fp is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._fp = self._path.open("a", encoding="utf-8")
            logger.info("Telemetry capture opened: %s", self._path)
        return self._fp

    def record(self, record: CaptureRecord) -> None:
        """Append one record. Caller-side errors propagate; we do not swallow."""
        fp = self._ensure_open()
        fp.write(record.model_dump_json())
        fp.write("\n")
        fp.flush()

    def close(self) -> None:
        if self._fp is not None:
            try:
                self._fp.close()
            finally:
                self._fp = None
                logger.info("Telemetry capture closed: %s", self._path)

    @property
    def path(self) -> Path:
        return self._path
