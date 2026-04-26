# Replay Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a JSONL telemetry capture + offline replay harness so navigation refactors can be validated against recorded yard runs before deployment. This plan implements §8 of `docs/major-architecture-and-code-improvement-plan.md`. Per the architecture plan's revised execution order, this work is a precondition for the navigation/localization refactor in Phase 2.

**Architecture:**

- A Pydantic `CaptureRecord` model wraps each `(SensorData input, NavigationStateSnapshot output)` pair produced by `NavigationService.update_navigation_state`.
- `TelemetryCapture` (writer) appends records as JSONL — one JSON object per line, append-only, no rotation in this plan.
- `ReplayLoader` (reader) yields records back via an iterator.
- `NavigationService` gains an optional `attach_capture(...)` method. When attached, every call to `update_navigation_state` records one line. When not attached (default), navigation behavior is unchanged.
- `scripts/replay_navigation.py` reads a captured JSONL, replays each record through a fresh `NavigationService` in `SIM_MODE=1`, and reports per-step deltas vs. the recorded ground truth. Exits non-zero when deltas exceed configurable thresholds.
- A small synthetic golden fixture is committed under `tests/fixtures/navigation/` and validated by an integration test that runs the replay harness against current code and asserts parity within tight tolerances.

**Tech Stack:**

- Python 3.11
- Pydantic v2 (`>=2.8.0`, already a dependency) for `model_dump_json` / `model_validate_json`
- pytest + pytest-asyncio (existing test infrastructure)
- Standard library `pathlib`, `argparse`, `json`, `asyncio`
- No new third-party dependencies

**Out of scope for this plan:**

- Rotation/retention of capture files (will be addressed alongside §12 runtime budget work).
- UI integration (toggling capture from the frontend, viewing replay results) — belongs to §9 observability work.
- Frontend changes — none.
- Modifying `NavigationService` internals beyond the capture hook. The point of replay is to validate future changes; this plan must not change navigation behavior.

---

## File Structure

**Created:**

- `backend/src/diagnostics/__init__.py` — exports `TelemetryCapture`, `ReplayLoader`.
- `backend/src/diagnostics/capture.py` — `TelemetryCapture` JSONL writer (≤120 lines).
- `backend/src/diagnostics/replay.py` — `ReplayLoader` JSONL reader (≤80 lines).
- `backend/src/models/diagnostics_capture.py` — `CaptureRecord` and `NavigationStateSnapshot` Pydantic models (≤80 lines).
- `scripts/replay_navigation.py` — CLI replay harness (≤180 lines).
- `tests/unit/test_diagnostics_capture.py` — writer round-trip tests.
- `tests/unit/test_diagnostics_replay.py` — reader round-trip tests.
- `tests/integration/test_navigation_replay.py` — golden-fixture parity test.
- `tests/fixtures/__init__.py` — empty.
- `tests/fixtures/navigation/__init__.py` — empty.
- `tests/fixtures/navigation/build_synthetic_fixture.py` — fixture generator (run once; output committed).
- `tests/fixtures/navigation/synthetic_straight_drive.jsonl` — committed golden fixture (~5 KB).
- `docs/diagnostics-replay.md` — operator/developer doc for the capture/replay workflow.

**Modified:**

- `backend/src/services/navigation_service.py` — add `attach_capture(...)` method, call `_capture.record(...)` inside `update_navigation_state`. **No other behavior changes.**
- `backend/src/main.py` — at startup, if `LAWNBERRY_CAPTURE_PATH` env is set, attach a `TelemetryCapture(path)` to the navigation service.

---

## Pre-flight

The implementer must have:

- A working SIM_MODE Python environment for this repo (`SIM_MODE=1 pytest` runs against `backend.src...` imports — see `tests/conftest.py:28-32`).
- The current branch checked out: `feat/replay-harness` (worktree at `.worktrees/feat-replay-harness`).
- `pytest`, `pytest-asyncio` installed (already in dev deps).

If running tests fails with `ModuleNotFoundError: backend`, the project root must be on `sys.path` — `tests/conftest.py:28-32` adds it automatically when invoked as `pytest` from the repo root.

---

### Task 1: Add CaptureRecord and NavigationStateSnapshot models

**Files:**
- Create: `backend/src/models/diagnostics_capture.py`
- Test: `tests/unit/test_diagnostics_capture.py`

**Why:** The capture format is the contract between writer and reader. A typed Pydantic model gives us round-trip serialization for free and pins the schema to a versioned `capture_version` field.

`NavigationStateSnapshot` is a *trimmed* projection of `NavigationState` containing only the dynamic fields useful for parity comparison. It deliberately excludes `planned_path`, `obstacle_map`, `coverage_grid`, and `safety_boundaries` — those are slow-changing or structural and would balloon the capture file. They can be added later if needed.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_diagnostics_capture.py` with this exact content:

```python
"""Unit tests for diagnostics capture record models."""
from __future__ import annotations

from datetime import UTC, datetime

from backend.src.models.diagnostics_capture import (
    CaptureRecord,
    NavigationStateSnapshot,
    CAPTURE_SCHEMA_VERSION,
)
from backend.src.models.navigation_state import NavigationMode, PathStatus, Position
from backend.src.models.sensor_data import GpsReading, ImuReading, SensorData


def _sample_sensor_data() -> SensorData:
    return SensorData(
        gps=GpsReading(latitude=42.0, longitude=-83.0, accuracy=0.5, satellites=12),
        imu=ImuReading(yaw=90.0, calibration_status="calibrated"),
    )


def _sample_snapshot() -> NavigationStateSnapshot:
    return NavigationStateSnapshot(
        current_position=Position(latitude=42.0, longitude=-83.0),
        heading=90.0,
        gps_cog=92.0,
        velocity=0.4,
        target_velocity=0.5,
        current_waypoint_index=0,
        path_status=PathStatus.EXECUTING,
        navigation_mode=NavigationMode.AUTO,
        dead_reckoning_active=False,
        dead_reckoning_drift=None,
        last_gps_fix=datetime(2026, 4, 26, tzinfo=UTC),
    )


def test_capture_record_round_trip_via_json():
    record = CaptureRecord(
        capture_version=CAPTURE_SCHEMA_VERSION,
        record_type="nav_step",
        sensor_data=_sample_sensor_data(),
        navigation_state_after=_sample_snapshot(),
    )
    line = record.model_dump_json()
    restored = CaptureRecord.model_validate_json(line)
    assert restored.capture_version == CAPTURE_SCHEMA_VERSION
    assert restored.record_type == "nav_step"
    assert restored.sensor_data.gps is not None
    assert restored.sensor_data.gps.latitude == 42.0
    assert restored.navigation_state_after.heading == 90.0
    assert restored.navigation_state_after.path_status == "executing"


def test_capture_record_rejects_unknown_record_type():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CaptureRecord(
            capture_version=CAPTURE_SCHEMA_VERSION,
            record_type="not_a_real_type",
            sensor_data=_sample_sensor_data(),
            navigation_state_after=_sample_snapshot(),
        )


def test_navigation_state_snapshot_excludes_path_lists():
    snap = _sample_snapshot()
    dumped = snap.model_dump()
    assert "planned_path" not in dumped
    assert "obstacle_map" not in dumped
    assert "coverage_grid" not in dumped
    assert "safety_boundaries" not in dumped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/pi/lawnberry/.worktrees/feat-replay-harness && SIM_MODE=1 pytest tests/unit/test_diagnostics_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.src.models.diagnostics_capture'`.

- [ ] **Step 3: Create the model file**

Create `backend/src/models/diagnostics_capture.py` with this exact content:

```python
"""Telemetry capture record models.

These types define the on-disk format used by the replay harness. The format is
JSONL (one JSON object per line). See docs/diagnostics-replay.md.

`NavigationStateSnapshot` is a trimmed projection of NavigationState. It
deliberately omits planned_path, obstacle_map, coverage_grid, and
safety_boundaries because those are large and slow-changing. Replay parity is
checked against the dynamic fields below, which is sufficient to detect
behavior changes in update_navigation_state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.src.models.navigation_state import NavigationMode, PathStatus, Position
from backend.src.models.sensor_data import SensorData

CAPTURE_SCHEMA_VERSION: int = 1

RecordType = Literal["nav_step"]


class NavigationStateSnapshot(BaseModel):
    """Trimmed projection of NavigationState for replay parity comparison."""

    current_position: Position | None = None
    heading: float | None = None
    gps_cog: float | None = None
    velocity: float | None = None
    target_velocity: float | None = None
    current_waypoint_index: int = 0
    path_status: PathStatus = PathStatus.PLANNING
    navigation_mode: NavigationMode = NavigationMode.IDLE
    dead_reckoning_active: bool = False
    dead_reckoning_drift: float | None = None
    last_gps_fix: datetime | None = None
    timestamp: datetime | None = None

    model_config = ConfigDict(use_enum_values=True)


class CaptureRecord(BaseModel):
    """One captured navigation step.

    The pair (sensor_data, navigation_state_after) is sufficient to replay
    a step: feed sensor_data into a fresh NavigationService, then compare its
    produced navigation_state against navigation_state_after.
    """

    capture_version: int
    record_type: RecordType
    sensor_data: SensorData
    navigation_state_after: NavigationStateSnapshot

    model_config = ConfigDict(use_enum_values=True)


__all__ = [
    "CAPTURE_SCHEMA_VERSION",
    "CaptureRecord",
    "NavigationStateSnapshot",
    "RecordType",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `SIM_MODE=1 pytest tests/unit/test_diagnostics_capture.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/src/models/diagnostics_capture.py tests/unit/test_diagnostics_capture.py
git commit -m "feat(diagnostics): add CaptureRecord and NavigationStateSnapshot models"
```

---

### Task 2: Implement TelemetryCapture (JSONL writer)

**Files:**
- Create: `backend/src/diagnostics/__init__.py`
- Create: `backend/src/diagnostics/capture.py`
- Modify (extend): `tests/unit/test_diagnostics_capture.py`

**Why:** A focused JSONL appender. Writes one record per line. Opens the file lazily on first record and flushes after each line so a crash mid-mission still leaves a valid prefix on disk. No background threads — synchronous fs writes are fine at the rates we expect (typically ≤10 Hz).

- [ ] **Step 1: Append the failing tests for TelemetryCapture**

Append to `tests/unit/test_diagnostics_capture.py`:

```python
import json
from pathlib import Path

from backend.src.diagnostics.capture import TelemetryCapture


def test_telemetry_capture_writes_one_line_per_record(tmp_path: Path):
    capture = TelemetryCapture(tmp_path / "run.jsonl")
    record = CaptureRecord(
        capture_version=CAPTURE_SCHEMA_VERSION,
        record_type="nav_step",
        sensor_data=_sample_sensor_data(),
        navigation_state_after=_sample_snapshot(),
    )
    capture.record(record)
    capture.record(record)
    capture.close()

    lines = (tmp_path / "run.jsonl").read_text().splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["capture_version"] == CAPTURE_SCHEMA_VERSION
    assert parsed[0]["record_type"] == "nav_step"


def test_telemetry_capture_creates_parent_directory(tmp_path: Path):
    target = tmp_path / "nested" / "dir" / "run.jsonl"
    capture = TelemetryCapture(target)
    capture.record(
        CaptureRecord(
            capture_version=CAPTURE_SCHEMA_VERSION,
            record_type="nav_step",
            sensor_data=_sample_sensor_data(),
            navigation_state_after=_sample_snapshot(),
        )
    )
    capture.close()
    assert target.exists()
    assert target.parent.is_dir()


def test_telemetry_capture_flushes_each_record(tmp_path: Path):
    """A crash between records must leave a valid prefix on disk."""
    target = tmp_path / "run.jsonl"
    capture = TelemetryCapture(target)
    capture.record(
        CaptureRecord(
            capture_version=CAPTURE_SCHEMA_VERSION,
            record_type="nav_step",
            sensor_data=_sample_sensor_data(),
            navigation_state_after=_sample_snapshot(),
        )
    )
    # Without close(), the bytes should still be on disk because we flush per record.
    contents = target.read_text()
    assert contents.endswith("\n")
    json.loads(contents.strip())  # parses cleanly
    capture.close()


def test_telemetry_capture_close_is_idempotent(tmp_path: Path):
    capture = TelemetryCapture(tmp_path / "run.jsonl")
    capture.close()
    capture.close()  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `SIM_MODE=1 pytest tests/unit/test_diagnostics_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.src.diagnostics'`.

- [ ] **Step 3: Create the diagnostics package**

Create `backend/src/diagnostics/__init__.py` with this exact content:

```python
"""Diagnostics utilities: telemetry capture and replay."""
from backend.src.diagnostics.capture import TelemetryCapture
from backend.src.diagnostics.replay import ReplayLoader

__all__ = ["ReplayLoader", "TelemetryCapture"]
```

Create `backend/src/diagnostics/capture.py` with this exact content:

```python
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
```

Note: `replay.py` does not exist yet — Task 3 creates it. The `__init__.py` import of `ReplayLoader` will fail until Task 3. To keep Task 2 testable in isolation, change the `__init__.py` import to lazy form for now:

Replace the contents of `backend/src/diagnostics/__init__.py` with:

```python
"""Diagnostics utilities: telemetry capture and replay."""
from backend.src.diagnostics.capture import TelemetryCapture

__all__ = ["TelemetryCapture"]
```

Task 3 will re-add the `ReplayLoader` export.

- [ ] **Step 4: Run tests to verify they pass**

Run: `SIM_MODE=1 pytest tests/unit/test_diagnostics_capture.py -v`
Expected: PASS — 7 tests (3 model + 4 capture).

- [ ] **Step 5: Commit**

```bash
git add backend/src/diagnostics/__init__.py backend/src/diagnostics/capture.py tests/unit/test_diagnostics_capture.py
git commit -m "feat(diagnostics): add TelemetryCapture JSONL writer"
```

---

### Task 3: Implement ReplayLoader (JSONL reader)

**Files:**
- Create: `backend/src/diagnostics/replay.py`
- Modify: `backend/src/diagnostics/__init__.py`
- Create: `tests/unit/test_diagnostics_replay.py`

**Why:** The reader counterpart to TelemetryCapture. Yields `CaptureRecord` instances. Skips blank lines and surfaces the line number on parse errors so a corrupted capture is debuggable.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_diagnostics_replay.py` with this exact content:

```python
"""Unit tests for diagnostics replay loader."""
from __future__ import annotations

import pytest
from pathlib import Path

from backend.src.diagnostics.capture import TelemetryCapture
from backend.src.diagnostics.replay import ReplayLoader, ReplayLoadError
from backend.src.models.diagnostics_capture import (
    CAPTURE_SCHEMA_VERSION,
    CaptureRecord,
    NavigationStateSnapshot,
)
from backend.src.models.navigation_state import NavigationMode, PathStatus, Position
from backend.src.models.sensor_data import GpsReading, ImuReading, SensorData


def _record(seq: int = 0) -> CaptureRecord:
    return CaptureRecord(
        capture_version=CAPTURE_SCHEMA_VERSION,
        record_type="nav_step",
        sensor_data=SensorData(
            gps=GpsReading(latitude=42.0 + seq * 0.0001, longitude=-83.0),
            imu=ImuReading(yaw=90.0, calibration_status="calibrated"),
        ),
        navigation_state_after=NavigationStateSnapshot(
            current_position=Position(latitude=42.0 + seq * 0.0001, longitude=-83.0),
            heading=90.0,
            current_waypoint_index=0,
            path_status=PathStatus.EXECUTING,
            navigation_mode=NavigationMode.AUTO,
        ),
    )


def test_replay_loader_round_trips_through_capture(tmp_path: Path):
    target = tmp_path / "run.jsonl"
    capture = TelemetryCapture(target)
    for i in range(3):
        capture.record(_record(i))
    capture.close()

    records = list(ReplayLoader(target))
    assert len(records) == 3
    for i, rec in enumerate(records):
        assert rec.sensor_data.gps is not None
        assert rec.sensor_data.gps.latitude == pytest.approx(42.0 + i * 0.0001)


def test_replay_loader_skips_blank_lines(tmp_path: Path):
    target = tmp_path / "run.jsonl"
    capture = TelemetryCapture(target)
    capture.record(_record(0))
    capture.close()
    # Inject blank lines.
    with target.open("a", encoding="utf-8") as fp:
        fp.write("\n   \n")
    records = list(ReplayLoader(target))
    assert len(records) == 1


def test_replay_loader_surfaces_line_number_on_corrupt_record(tmp_path: Path):
    target = tmp_path / "run.jsonl"
    target.write_text(
        '{"capture_version":1,"record_type":"nav_step","sensor_data":{},'
        '"navigation_state_after":{}}\n'
        "this is not json\n",
        encoding="utf-8",
    )
    with pytest.raises(ReplayLoadError) as excinfo:
        list(ReplayLoader(target))
    assert "line 2" in str(excinfo.value)


def test_replay_loader_rejects_mismatched_schema_version(tmp_path: Path):
    target = tmp_path / "run.jsonl"
    target.write_text(
        '{"capture_version":999,"record_type":"nav_step",'
        '"sensor_data":{},"navigation_state_after":{}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ReplayLoadError) as excinfo:
        list(ReplayLoader(target))
    assert "schema" in str(excinfo.value).lower()


def test_replay_loader_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        list(ReplayLoader(tmp_path / "does-not-exist.jsonl"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `SIM_MODE=1 pytest tests/unit/test_diagnostics_replay.py -v`
Expected: FAIL — `ImportError: cannot import name 'ReplayLoader' from 'backend.src.diagnostics.replay'`.

- [ ] **Step 3: Create the replay module**

Create `backend/src/diagnostics/replay.py` with this exact content:

```python
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
```

Update `backend/src/diagnostics/__init__.py` to re-export `ReplayLoader`:

```python
"""Diagnostics utilities: telemetry capture and replay."""
from backend.src.diagnostics.capture import TelemetryCapture
from backend.src.diagnostics.replay import ReplayLoader, ReplayLoadError

__all__ = ["ReplayLoadError", "ReplayLoader", "TelemetryCapture"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `SIM_MODE=1 pytest tests/unit/test_diagnostics_replay.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 5: Run all unit tests under tests/unit/test_diagnostics*.py**

Run: `SIM_MODE=1 pytest tests/unit/test_diagnostics_capture.py tests/unit/test_diagnostics_replay.py -v`
Expected: PASS — 12 tests total (3 model + 4 capture + 5 replay).

- [ ] **Step 6: Commit**

```bash
git add backend/src/diagnostics/replay.py backend/src/diagnostics/__init__.py tests/unit/test_diagnostics_replay.py
git commit -m "feat(diagnostics): add ReplayLoader JSONL reader"
```

---

### Task 4: Hook capture into NavigationService

**Files:**
- Modify: `backend/src/services/navigation_service.py`
- Create: `tests/unit/test_navigation_service_capture.py`

**Why:** Capture must run inside `update_navigation_state` so every navigation step is recorded with both its input (`SensorData`) and its output (the resulting `NavigationState`). The hook is opt-in: when no capture is attached, navigation behavior is byte-identical to today. **Do not change any other navigation behavior in this task.**

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_navigation_service_capture.py` with this exact content:

```python
"""Tests for the optional capture hook on NavigationService."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.src.diagnostics.capture import TelemetryCapture
from backend.src.diagnostics.replay import ReplayLoader
from backend.src.models.sensor_data import GpsReading, ImuReading, SensorData
from backend.src.services.navigation_service import NavigationService


@pytest.mark.asyncio
async def test_navigation_service_records_step_when_capture_attached(tmp_path: Path):
    capture_path = tmp_path / "nav.jsonl"
    capture = TelemetryCapture(capture_path)

    # Construct a fresh NavigationService (do not use the singleton; tests must
    # not pollute global state).
    nav = NavigationService()
    nav.attach_capture(capture)

    sensor_data = SensorData(
        gps=GpsReading(latitude=42.0, longitude=-83.0, accuracy=0.5, satellites=12),
        imu=ImuReading(yaw=90.0, calibration_status="calibrated"),
    )
    await nav.update_navigation_state(sensor_data)
    capture.close()

    records = list(ReplayLoader(capture_path))
    assert len(records) == 1
    assert records[0].record_type == "nav_step"
    assert records[0].sensor_data.gps is not None
    assert records[0].sensor_data.gps.latitude == 42.0


@pytest.mark.asyncio
async def test_navigation_service_records_nothing_without_capture(tmp_path: Path):
    """Behavior must be unchanged when no capture is attached."""
    nav = NavigationService()
    sensor_data = SensorData(
        gps=GpsReading(latitude=42.0, longitude=-83.0),
        imu=ImuReading(yaw=90.0, calibration_status="calibrated"),
    )
    # Should not raise, should not write anything.
    result = await nav.update_navigation_state(sensor_data)
    assert result is not None  # returns NavigationState as before


@pytest.mark.asyncio
async def test_navigation_service_capture_failure_does_not_break_navigation(
    tmp_path: Path, monkeypatch
):
    """If capture.record raises, navigation must still return a state."""
    nav = NavigationService()

    class BrokenCapture:
        def record(self, _record):
            raise OSError("simulated disk full")

        def close(self):
            pass

    nav.attach_capture(BrokenCapture())  # type: ignore[arg-type]
    sensor_data = SensorData(
        gps=GpsReading(latitude=42.0, longitude=-83.0),
        imu=ImuReading(yaw=90.0, calibration_status="calibrated"),
    )
    result = await nav.update_navigation_state(sensor_data)
    assert result is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SIM_MODE=1 pytest tests/unit/test_navigation_service_capture.py -v`
Expected: FAIL — `AttributeError: 'NavigationService' object has no attribute 'attach_capture'`.

- [ ] **Step 3: Modify NavigationService**

Open `backend/src/services/navigation_service.py`. Make exactly two changes.

**Change A — extend `__init__`:** Find the line at `__init__` (currently `backend/src/services/navigation_service.py:153` — verify by `grep -n "def __init__(self, weather=None):" backend/src/services/navigation_service.py`). Append a single line at the end of `__init__` (just before the line `_instance: NavigationService | None = None` at module level — i.e., still inside the method). Add this line right after `self._load_alignment_from_disk()`:

```python
        # Optional telemetry capture. Set via attach_capture(); default is no-op.
        self._capture = None
```

**Change B — add the `attach_capture` method.** Immediately after the `get_instance` classmethod block ends (around `backend/src/services/navigation_service.py:249`), insert this method into the class:

```python
    def attach_capture(self, capture) -> None:
        """Attach a TelemetryCapture for diagnostic replay.

        See backend/src/diagnostics/capture.py. Pass None to detach.
        """
        self._capture = capture
```

**Change C — record inside `update_navigation_state`.** Find the method definition (currently `backend/src/services/navigation_service.py:1153`). The method ends with `return self.navigation_state`. Replace that final `return` with the following block (locate the unique line — there is exactly one `return self.navigation_state` inside this method; verify with `grep -n "return self.navigation_state" backend/src/services/navigation_service.py`):

```python
        # Optional capture for replay diagnostics. Failures must never break
        # navigation, so swallow any exception and log at debug.
        if self._capture is not None:
            try:
                from backend.src.models.diagnostics_capture import (
                    CAPTURE_SCHEMA_VERSION,
                    CaptureRecord,
                    NavigationStateSnapshot,
                )

                snapshot = NavigationStateSnapshot(
                    current_position=self.navigation_state.current_position,
                    heading=self.navigation_state.heading,
                    gps_cog=self.navigation_state.gps_cog,
                    velocity=self.navigation_state.velocity,
                    target_velocity=self.navigation_state.target_velocity,
                    current_waypoint_index=self.navigation_state.current_waypoint_index,
                    path_status=self.navigation_state.path_status,
                    navigation_mode=self.navigation_state.navigation_mode,
                    dead_reckoning_active=self.navigation_state.dead_reckoning_active,
                    dead_reckoning_drift=self.navigation_state.dead_reckoning_drift,
                    last_gps_fix=self.navigation_state.last_gps_fix,
                    timestamp=self.navigation_state.timestamp,
                )
                self._capture.record(
                    CaptureRecord(
                        capture_version=CAPTURE_SCHEMA_VERSION,
                        record_type="nav_step",
                        sensor_data=sensor_data,
                        navigation_state_after=snapshot,
                    )
                )
            except Exception as exc:  # pragma: no cover - safety net
                logger.debug("Telemetry capture record failed: %s", exc)
        return self.navigation_state
```

The import is local (inside the `if` branch) to avoid coupling the navigation module's import time to the diagnostics package when capture is unused.

- [ ] **Step 4: Run tests to verify they pass**

Run: `SIM_MODE=1 pytest tests/unit/test_navigation_service_capture.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Run the existing navigation unit tests to verify no regressions**

Run: `SIM_MODE=1 pytest tests/unit/test_navigation_service.py -v`
Expected: PASS with the same count as on `main` (no new failures, no new skips).

- [ ] **Step 6: Commit**

```bash
git add backend/src/services/navigation_service.py tests/unit/test_navigation_service_capture.py
git commit -m "feat(navigation): optional telemetry capture hook in update_navigation_state"
```

---

### Task 5: Wire capture activation in main.py from env var

**Files:**
- Modify: `backend/src/main.py`
- Create: `tests/integration/test_main_capture_wiring.py`

**Why:** Without wiring, capture exists but never runs. The simplest activation path is an environment variable: `LAWNBERRY_CAPTURE_PATH=/path/to/run.jsonl` enables capture; absent or empty disables it. This follows existing patterns (`SIM_MODE`, `LAWN_HARDWARE_LOCAL_PATH`).

This wiring is intentionally minimal. It does **not** integrate with `RuntimeContext` (§1) — that's a follow-up plan. It does not add a runtime UI toggle.

- [ ] **Step 1: Locate the navigation construction site**

Run: `grep -n "NavigationService.get_instance" backend/src/main.py`
Expected: at least one match around line 145 (e.g., `NavigationService.get_instance(), websocket_hub=websocket_hub`). Read 20 lines of context around the match to find the lifespan startup block.

- [ ] **Step 2: Write the integration test**

Create `tests/integration/test_main_capture_wiring.py` with this exact content:

```python
"""Verify main.py attaches a TelemetryCapture when LAWNBERRY_CAPTURE_PATH is set."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_nav_singleton():
    """Force a fresh NavigationService for each wiring test."""
    from backend.src.services import navigation_service as ns_module

    ns_module.NavigationService._instance = None
    yield
    ns_module.NavigationService._instance = None


def test_capture_attached_when_env_var_set(tmp_path: Path, monkeypatch):
    target = tmp_path / "run.jsonl"
    monkeypatch.setenv("LAWNBERRY_CAPTURE_PATH", str(target))

    from backend.src.main import _maybe_attach_telemetry_capture
    from backend.src.services.navigation_service import NavigationService

    nav = NavigationService.get_instance()
    _maybe_attach_telemetry_capture(nav)
    assert nav._capture is not None
    assert nav._capture.path == target


def test_capture_not_attached_when_env_var_absent(monkeypatch):
    monkeypatch.delenv("LAWNBERRY_CAPTURE_PATH", raising=False)

    from backend.src.main import _maybe_attach_telemetry_capture
    from backend.src.services.navigation_service import NavigationService

    nav = NavigationService.get_instance()
    _maybe_attach_telemetry_capture(nav)
    assert nav._capture is None


def test_capture_not_attached_when_env_var_empty(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_CAPTURE_PATH", "")

    from backend.src.main import _maybe_attach_telemetry_capture
    from backend.src.services.navigation_service import NavigationService

    nav = NavigationService.get_instance()
    _maybe_attach_telemetry_capture(nav)
    assert nav._capture is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `SIM_MODE=1 pytest tests/integration/test_main_capture_wiring.py -v`
Expected: FAIL — `ImportError: cannot import name '_maybe_attach_telemetry_capture' from 'backend.src.main'`.

- [ ] **Step 4: Add the wiring helper to main.py**

Add this function near the top of `backend/src/main.py`, after the existing imports (place it before any FastAPI app definition):

```python
def _maybe_attach_telemetry_capture(nav_service) -> None:
    """If LAWNBERRY_CAPTURE_PATH is set, attach a JSONL telemetry capture.

    No-op when the env var is unset or empty. Errors during attach are logged
    but do not abort startup — capture is a diagnostic, not a safety dependency.
    """
    import logging
    import os

    path = os.environ.get("LAWNBERRY_CAPTURE_PATH", "").strip()
    if not path:
        return
    try:
        from backend.src.diagnostics.capture import TelemetryCapture

        capture = TelemetryCapture(path)
        nav_service.attach_capture(capture)
        logging.getLogger(__name__).info(
            "Telemetry capture enabled: %s", path
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Failed to enable telemetry capture at %s: %s", path, exc
        )
```

Then, in the lifespan startup block (find the existing call site around line 145 — search for `NavigationService.get_instance()`), add a single line **immediately after** the navigation service is fetched:

```python
            nav_service = NavigationService.get_instance()
            _maybe_attach_telemetry_capture(nav_service)
```

Adjust to match the exact existing variable pattern. If the existing line is e.g. `NavigationService.get_instance(), websocket_hub=websocket_hub`, refactor it to assign to a local first:

```python
            nav_service = NavigationService.get_instance()
            _maybe_attach_telemetry_capture(nav_service)
            # ... continue with the existing code that uses nav_service
```

Verify the existing code path still passes the navigation service into whatever consumer it had before.

- [ ] **Step 5: Run the wiring tests**

Run: `SIM_MODE=1 pytest tests/integration/test_main_capture_wiring.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 6: Run a smoke test to confirm main.py still imports cleanly**

Run: `SIM_MODE=1 python -c "import backend.src.main; print('OK')"`
Expected: prints `OK`.

- [ ] **Step 7: Commit**

```bash
git add backend/src/main.py tests/integration/test_main_capture_wiring.py
git commit -m "feat(diagnostics): wire LAWNBERRY_CAPTURE_PATH env var to attach capture"
```

---

### Task 6: Build the synthetic golden fixture

**Files:**
- Create: `tests/fixtures/__init__.py` (empty)
- Create: `tests/fixtures/navigation/__init__.py` (empty)
- Create: `tests/fixtures/navigation/build_synthetic_fixture.py`
- Create (generated): `tests/fixtures/navigation/synthetic_straight_drive.jsonl`

**Why:** The replay test needs a deterministic input/output fixture. Generating it programmatically (rather than recording from the field) keeps the test stable, fast, and free of GPS noise. The fixture represents a synthetic 5-step "straight drive": GPS marches forward in 0.0001° steps (~11 m/step at 42°N), IMU yaw stays at 90°, no waypoints.

The generator is committed alongside the fixture so anyone can regenerate it. The fixture itself is committed so tests do not depend on running the generator first.

Because `NavigationService.update_navigation_state` writes wall-clock timestamps into the snapshot, the generator wraps `TelemetryCapture` with a small `_DeterministicCapture` adapter that normalizes those fields to the synthetic step time. This is a generator-side workaround until §3 (real pose pipeline) lands and `NavigationService` accepts an injected clock.

- [ ] **Step 1: Create empty package markers**

Run:

```bash
touch tests/fixtures/__init__.py tests/fixtures/navigation/__init__.py
```

- [ ] **Step 2: Write the fixture generator**

Create `tests/fixtures/navigation/build_synthetic_fixture.py` with this exact content:

```python
"""Generate the synthetic_straight_drive.jsonl golden fixture.

Run with:

    SIM_MODE=1 python -m tests.fixtures.navigation.build_synthetic_fixture

This script constructs a fresh NavigationService in SIM_MODE, feeds it a
deterministic sequence of SensorData snapshots, and writes the resulting
CaptureRecord stream to synthetic_straight_drive.jsonl in this directory.

The fixture is committed to the repository. Tests load it via ReplayLoader and
replay through the current code path to verify parity. If a navigation change
intentionally alters the output for this scenario, regenerate the fixture and
review the diff carefully — every committed fixture change is a behavior change.

Determinism note: NavigationService writes wall-clock datetime.now(UTC) into
three fields that surface in the snapshot (NavigationState.timestamp,
NavigationState.last_gps_fix, and Position.timestamp via default factory).
For a fixture to be byte-reproducible, those fields must be normalized to a
deterministic clock before the record is written. The _DeterministicCapture
wrapper below does that. Until NavigationService accepts an injected clock
(see architecture plan §3 — real pose pipeline), this generator-side
normalization is the load-bearing contract for fixture reproducibility.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.src.diagnostics.capture import TelemetryCapture
from backend.src.models.diagnostics_capture import CaptureRecord
from backend.src.models.sensor_data import GpsReading, ImuReading, SensorData
from backend.src.services.navigation_service import NavigationService


FIXTURE_PATH = Path(__file__).parent / "synthetic_straight_drive.jsonl"
NUM_STEPS = 5
LAT_START = 42.0
LON_START = -83.0
LAT_STEP = 0.0001  # ~11 m at 42°N
YAW_DEG = 90.0


class _DeterministicCapture:
    """Wraps TelemetryCapture and rewrites snapshot timestamps to a fixed clock.

    NavigationService stamps wall-clock time into NavigationState.timestamp,
    NavigationState.last_gps_fix, and the default-factory timestamp on
    Position. For a reproducible fixture, those three fields must be replaced
    with the synthetic step time before the record hits disk.
    """

    def __init__(self, inner: TelemetryCapture) -> None:
        self._inner = inner
        self.next_ts: datetime | None = None

    def record(self, record: CaptureRecord) -> None:
        if self.next_ts is not None:
            snap = record.navigation_state_after
            snap.timestamp = self.next_ts
            if snap.current_position is not None:
                snap.current_position.timestamp = self.next_ts
            if snap.last_gps_fix is not None:
                snap.last_gps_fix = self.next_ts
        self._inner.record(record)

    def close(self) -> None:
        self._inner.close()


async def _build() -> None:
    # Force SIM mode so navigation does not attempt hardware access. Use a
    # hard set (not setdefault) because this is a fixture generator: an
    # external SIM_MODE=0 in the shell must not silently change what we
    # capture.
    os.environ["SIM_MODE"] = "1"

    # Fresh service — do not pollute the singleton.
    nav = NavigationService()
    capture = TelemetryCapture(FIXTURE_PATH)
    deterministic = _DeterministicCapture(capture)
    nav.attach_capture(deterministic)

    base_time = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
    for i in range(NUM_STEPS):
        ts = base_time + timedelta(seconds=i)
        deterministic.next_ts = ts
        sensor_data = SensorData(
            gps=GpsReading(
                latitude=LAT_START + i * LAT_STEP,
                longitude=LON_START,
                altitude=200.0,
                accuracy=0.5,
                heading=YAW_DEG,
                speed=0.5,
                satellites=12,
                hdop=0.8,
                timestamp=ts,
            ),
            imu=ImuReading(
                yaw=YAW_DEG,
                roll=0.0,
                pitch=0.0,
                calibration_status="calibrated",
                timestamp=ts,
            ),
            timestamp=ts,
        )
        await nav.update_navigation_state(sensor_data)
    capture.close()
    print(f"Wrote {NUM_STEPS} records to {FIXTURE_PATH}")


if __name__ == "__main__":
    asyncio.run(_build())
```

- [ ] **Step 3: Generate the fixture**

Run:

```bash
SIM_MODE=1 python -m tests.fixtures.navigation.build_synthetic_fixture
```

Expected: prints `Wrote 5 records to <abs path>/synthetic_straight_drive.jsonl`. Verify the file exists and has 5 non-empty lines:

```bash
wc -l tests/fixtures/navigation/synthetic_straight_drive.jsonl
```

Expected: `5 tests/fixtures/navigation/synthetic_straight_drive.jsonl`.

- [ ] **Step 4: Commit fixture and generator together**

```bash
git add tests/fixtures/__init__.py tests/fixtures/navigation/__init__.py \
        tests/fixtures/navigation/build_synthetic_fixture.py \
        tests/fixtures/navigation/synthetic_straight_drive.jsonl
git commit -m "test(diagnostics): add synthetic straight-drive replay fixture"
```

---

### Task 7: Replay parity integration test

**Files:**
- Create: `tests/integration/test_navigation_replay.py`

**Why:** This is the load-bearing test for the entire harness. It loads the committed golden fixture, replays each captured `SensorData` through a fresh `NavigationService`, and asserts the produced state matches the recorded ground truth within tight tolerances. If a future navigation refactor breaks behavior, this test fails — that is exactly the safety net the architecture plan calls for.

**Tolerances** (chosen to be tight on the synthetic fixture but allow for floating-point noise):

- heading: ±0.01°
- position lat/lon: ±1e-7 (~1 cm)
- velocity: ±0.001 m/s

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_navigation_replay.py` with this exact content:

```python
"""Replay-parity integration test.

Loads the committed golden fixture, replays each captured SensorData through a
fresh NavigationService, and asserts the produced state matches the recorded
state within tolerances. A failure here means navigation behavior has drifted
from the fixture — either an intentional change (regenerate the fixture) or a
regression (fix the code).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.src.diagnostics.replay import ReplayLoader
from backend.src.services.navigation_service import NavigationService

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "navigation"
    / "synthetic_straight_drive.jsonl"
)

HEADING_TOL_DEG = 0.01
LATLON_TOL = 1e-7
VELOCITY_TOL_MPS = 0.001


@pytest.mark.asyncio
async def test_synthetic_straight_drive_replays_with_parity():
    assert FIXTURE.exists(), f"missing golden fixture: {FIXTURE}"
    nav = NavigationService()

    deltas: list[str] = []
    step = 0
    for record in ReplayLoader(FIXTURE):
        result = await nav.update_navigation_state(record.sensor_data)
        expected = record.navigation_state_after

        if expected.heading is not None and result.heading is not None:
            d = abs(result.heading - expected.heading)
            if d > HEADING_TOL_DEG:
                deltas.append(
                    f"step {step} heading: got {result.heading:.6f}, "
                    f"expected {expected.heading:.6f}, delta={d:.6f}"
                )
        elif expected.heading != result.heading:
            deltas.append(
                f"step {step} heading nullness: got {result.heading}, "
                f"expected {expected.heading}"
            )

        if expected.current_position is not None and result.current_position is not None:
            dlat = abs(result.current_position.latitude - expected.current_position.latitude)
            dlon = abs(result.current_position.longitude - expected.current_position.longitude)
            if dlat > LATLON_TOL or dlon > LATLON_TOL:
                deltas.append(
                    f"step {step} position: got "
                    f"({result.current_position.latitude},{result.current_position.longitude}), "
                    f"expected "
                    f"({expected.current_position.latitude},{expected.current_position.longitude})"
                )
        elif (expected.current_position is None) != (result.current_position is None):
            deltas.append(
                f"step {step} position nullness mismatch: "
                f"got {result.current_position}, expected {expected.current_position}"
            )

        if expected.velocity is not None and result.velocity is not None:
            d = abs(result.velocity - expected.velocity)
            if d > VELOCITY_TOL_MPS:
                deltas.append(
                    f"step {step} velocity: got {result.velocity:.6f}, "
                    f"expected {expected.velocity:.6f}"
                )

        step += 1

    assert step == 5, f"expected 5 fixture records, got {step}"
    assert not deltas, "Replay parity broke:\n" + "\n".join(deltas)
```

- [ ] **Step 2: Run test to verify it passes**

Note: this test should pass on first run because the fixture was generated by the same code path the test replays through. If it fails, either the fixture is stale or the navigation code changed since the fixture was generated.

Run: `SIM_MODE=1 pytest tests/integration/test_navigation_replay.py -v`
Expected: PASS — 1 test.

- [ ] **Step 3: Verify the test actually exercises the harness (sanity check)**

Temporarily modify `tests/fixtures/navigation/synthetic_straight_drive.jsonl` — open it and change one captured `heading` field by 5 degrees on the first line. Run the test:

```bash
SIM_MODE=1 pytest tests/integration/test_navigation_replay.py -v
```

Expected: FAIL with a clear delta message including `step 0 heading`. **Then revert the edit** (`git checkout tests/fixtures/navigation/synthetic_straight_drive.jsonl`) and re-run to confirm PASS. This confirms the test is load-bearing.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_navigation_replay.py
git commit -m "test(diagnostics): replay-parity integration test for synthetic fixture"
```

---

### Task 8: CLI replay harness (`scripts/replay_navigation.py`)

**Files:**
- Create: `scripts/replay_navigation.py`
- Create: `tests/integration/test_replay_navigation_script.py`

**Why:** The CLI is the operator/developer-facing entry point. Given a captured JSONL, it replays the records and prints per-step deltas (heading, position, velocity) and a summary. Exits non-zero if any step exceeds the threshold. This is also what CI will eventually invoke against committed fixtures (covered by Task 7's pytest path; the CLI is for ad-hoc / yard-debug use).

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_replay_navigation_script.py` with this exact content:

```python
"""Smoke tests for scripts/replay_navigation.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "replay_navigation.py"
FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "navigation" / "synthetic_straight_drive.jsonl"
)


def test_replay_script_exits_zero_on_synthetic_fixture():
    assert SCRIPT.exists()
    assert FIXTURE.exists()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"SIM_MODE": "1", "PATH": "/usr/bin:/bin"},
        timeout=30,
    )
    assert result.returncode == 0, (
        f"replay script exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "OK" in result.stdout or "PASS" in result.stdout.upper()


def test_replay_script_exits_nonzero_on_missing_fixture(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "no-such.jsonl")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"SIM_MODE": "1", "PATH": "/usr/bin:/bin"},
        timeout=10,
    )
    assert result.returncode != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `SIM_MODE=1 pytest tests/integration/test_replay_navigation_script.py -v`
Expected: FAIL — `assert SCRIPT.exists()` fires, or the subprocess exits non-zero because the script doesn't exist.

- [ ] **Step 3: Create `scripts/replay_navigation.py`**

Create `scripts/replay_navigation.py` with this exact content:

```python
#!/usr/bin/env python3
"""Replay a captured navigation telemetry stream offline.

Usage:
    python scripts/replay_navigation.py <capture.jsonl> [--heading-tol 0.01]
                                        [--latlon-tol 1e-7]
                                        [--velocity-tol 0.001]
                                        [--quiet]

Reads a JSONL capture produced by TelemetryCapture, replays each captured
SensorData through a fresh NavigationService (in SIM_MODE), and reports
per-step deltas vs. the recorded ground truth. Exits 0 on parity, non-zero
on any threshold breach.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Repo root on sys.path so we can import backend.src.* without installing.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Default to SIM_MODE so the script never touches hardware.
os.environ.setdefault("SIM_MODE", "1")

from backend.src.diagnostics.replay import ReplayLoader  # noqa: E402
from backend.src.services.navigation_service import NavigationService  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="replay_navigation",
        description="Replay a captured navigation telemetry stream offline.",
    )
    p.add_argument("capture", type=Path, help="path to captured JSONL file")
    p.add_argument("--heading-tol", type=float, default=0.01, help="degrees")
    p.add_argument("--latlon-tol", type=float, default=1e-7, help="degrees")
    p.add_argument("--velocity-tol", type=float, default=0.001, help="m/s")
    p.add_argument(
        "--quiet", action="store_true", help="only print summary, suppress per-step output"
    )
    return p


async def _run(args: argparse.Namespace) -> int:
    if not args.capture.exists():
        print(f"error: capture file not found: {args.capture}", file=sys.stderr)
        return 2

    nav = NavigationService()
    deltas: list[str] = []
    step = 0
    for record in ReplayLoader(args.capture):
        result = await nav.update_navigation_state(record.sensor_data)
        expected = record.navigation_state_after

        if expected.heading is not None and result.heading is not None:
            d = abs(result.heading - expected.heading)
            if d > args.heading_tol:
                deltas.append(
                    f"step {step} heading: got {result.heading:.6f} "
                    f"expected {expected.heading:.6f} delta={d:.6f}"
                )

        if expected.current_position and result.current_position:
            dlat = abs(
                result.current_position.latitude - expected.current_position.latitude
            )
            dlon = abs(
                result.current_position.longitude - expected.current_position.longitude
            )
            if dlat > args.latlon_tol or dlon > args.latlon_tol:
                deltas.append(
                    f"step {step} position: dlat={dlat:.2e} dlon={dlon:.2e}"
                )

        if expected.velocity is not None and result.velocity is not None:
            d = abs(result.velocity - expected.velocity)
            if d > args.velocity_tol:
                deltas.append(
                    f"step {step} velocity: got {result.velocity:.6f} "
                    f"expected {expected.velocity:.6f}"
                )

        if not args.quiet:
            print(
                f"step {step}: heading={result.heading} "
                f"pos={result.current_position}"
            )
        step += 1

    print(f"replay complete: {step} steps")
    if deltas:
        print("DELTAS:")
        for d in deltas:
            print(f"  {d}")
        return 1
    print("OK — replay parity within tolerances")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
```

Make it executable:

```bash
chmod +x scripts/replay_navigation.py
```

- [ ] **Step 4: Run the smoke tests**

Run: `SIM_MODE=1 pytest tests/integration/test_replay_navigation_script.py -v`
Expected: PASS — 2 tests.

- [ ] **Step 5: Run the script manually**

Run: `SIM_MODE=1 python scripts/replay_navigation.py tests/fixtures/navigation/synthetic_straight_drive.jsonl`
Expected: prints 5 step lines, then `replay complete: 5 steps`, then `OK — replay parity within tolerances`. Exit code 0.

Run: `SIM_MODE=1 python scripts/replay_navigation.py /tmp/no-such-file.jsonl; echo "exit=$?"`
Expected: prints `error: capture file not found: ...`. Exit code 2.

- [ ] **Step 6: Commit**

```bash
git add scripts/replay_navigation.py tests/integration/test_replay_navigation_script.py
git commit -m "feat(diagnostics): add scripts/replay_navigation.py CLI harness"
```

---

### Task 9: Operator/developer documentation

**Files:**
- Create: `docs/diagnostics-replay.md`
- Modify: `AGENTS.md` (add a one-line pointer)

**Why:** Without docs the harness is undiscoverable. Keep it short — one page covering: how to enable capture, where files land, how to replay, how the synthetic fixture works, and how to add a new fixture from a real yard run.

- [ ] **Step 1: Create `docs/diagnostics-replay.md`**

Create `docs/diagnostics-replay.md` with this exact content:

````markdown
# Diagnostics: Telemetry Capture and Replay

The replay harness lets us capture a navigation session to disk and replay it
offline through current code. It is the regression net for navigation
refactors — when behavior unintentionally changes, the parity test fails
before the change reaches the mower.

## Enabling capture

Set `LAWNBERRY_CAPTURE_PATH` in the backend environment:

```bash
export LAWNBERRY_CAPTURE_PATH=data/captures/$(date +%Y%m%d-%H%M%S).jsonl
systemctl restart lawnberry-backend
```

When set, every call to `NavigationService.update_navigation_state` appends
one line to that file. Each line is a `CaptureRecord` (see
`backend/src/models/diagnostics_capture.py`) containing the input
`SensorData` and a trimmed `NavigationStateSnapshot` of the resulting state.

The format is JSONL — one JSON object per line, append-only, flushed after
each record. A crash or power loss leaves a valid prefix on disk.

Capture is opt-in. Unset or empty `LAWNBERRY_CAPTURE_PATH` disables it
entirely; navigation behavior is byte-identical to the no-capture path.

## Replaying a capture

```bash
SIM_MODE=1 python scripts/replay_navigation.py <capture.jsonl>
```

The script feeds each captured `SensorData` through a fresh
`NavigationService` and compares the produced state against the recorded
ground truth. Exits 0 on parity, non-zero on threshold breach.

Tolerances are tunable:

```bash
python scripts/replay_navigation.py run.jsonl \
    --heading-tol 0.05 --latlon-tol 1e-6 --velocity-tol 0.01
```

## The synthetic golden fixture

`tests/fixtures/navigation/synthetic_straight_drive.jsonl` is a 5-step
deterministic capture used by `tests/integration/test_navigation_replay.py`.
It is generated by `tests/fixtures/navigation/build_synthetic_fixture.py`
and committed to the repository.

To regenerate:

```bash
SIM_MODE=1 python -m tests.fixtures.navigation.build_synthetic_fixture
```

If you regenerate it, **review the diff carefully**: every committed change
to a fixture file is a navigation-behavior change. If the change is
intentional, document it in the commit message; if not, revert it and find
the regression.

## Adding a new fixture from a real yard run

1. Capture the session by setting `LAWNBERRY_CAPTURE_PATH` before the run.
2. After the run, copy the JSONL to `tests/fixtures/navigation/<scenario>.jsonl`.
3. Add an integration test that loads the new fixture and asserts parity (mirror
   `tests/integration/test_navigation_replay.py`).
4. Commit the fixture and the test in the same change.

Field-recorded fixtures may need looser tolerances than the synthetic one due
to GPS noise. Pick tolerances based on the scenario's expected variance.
````

- [ ] **Step 2: Add a pointer in AGENTS.md**

Open `AGENTS.md`. Find a sensible section (e.g., the "Repository Map" section). Add this single line at the end of that section:

```markdown
- `docs/diagnostics-replay.md` documents the telemetry capture + replay harness used to regression-check navigation refactors.
```

- [ ] **Step 3: Commit**

```bash
git add docs/diagnostics-replay.md AGENTS.md
git commit -m "docs(diagnostics): add capture/replay harness operator guide"
```

---

### Task 10: End-to-end verification and PR readiness

**Files:** none (verification only)

**Why:** Confirm the whole subsystem is working before opening the PR.

- [ ] **Step 1: Run the full diagnostics test set**

Run:

```bash
SIM_MODE=1 pytest tests/unit/test_diagnostics_capture.py \
                  tests/unit/test_diagnostics_replay.py \
                  tests/unit/test_navigation_service_capture.py \
                  tests/integration/test_main_capture_wiring.py \
                  tests/integration/test_navigation_replay.py \
                  tests/integration/test_replay_navigation_script.py \
                  -v
```

Expected: all PASS. No skips.

- [ ] **Step 2: Run the existing navigation/telemetry tests to confirm no regression**

Run:

```bash
SIM_MODE=1 pytest tests/unit/test_navigation_service.py \
                  tests/unit/test_telemetry_service.py -v
```

Expected: same pass/skip counts as on `main` before this branch. Compare with:

```bash
git stash && SIM_MODE=1 pytest tests/unit/test_navigation_service.py tests/unit/test_telemetry_service.py -v && git stash pop
```

(Only run the stash dance if you have local uncommitted changes — otherwise just `git checkout main` in a separate worktree.)

- [ ] **Step 3: Confirm the CLI works end-to-end**

Run: `SIM_MODE=1 python scripts/replay_navigation.py tests/fixtures/navigation/synthetic_straight_drive.jsonl`
Expected: exit 0, output ends with `OK — replay parity within tolerances`.

- [ ] **Step 4: Confirm capture wiring works under a fake live session**

Run:

```bash
SIM_MODE=1 LAWNBERRY_CAPTURE_PATH=/tmp/lb-replay-smoke.jsonl python -c "
import asyncio
from backend.src.main import _maybe_attach_telemetry_capture
from backend.src.services.navigation_service import NavigationService
from backend.src.models.sensor_data import SensorData, GpsReading, ImuReading

async def main():
    nav = NavigationService.get_instance()
    _maybe_attach_telemetry_capture(nav)
    for i in range(3):
        sd = SensorData(
            gps=GpsReading(latitude=42.0 + i * 0.0001, longitude=-83.0),
            imu=ImuReading(yaw=90.0, calibration_status='calibrated'),
        )
        await nav.update_navigation_state(sd)
    nav._capture.close()

asyncio.run(main())
print('captured 3 steps')
"
wc -l /tmp/lb-replay-smoke.jsonl
SIM_MODE=1 python scripts/replay_navigation.py /tmp/lb-replay-smoke.jsonl
rm /tmp/lb-replay-smoke.jsonl
```

Expected: `captured 3 steps`, then `3 /tmp/lb-replay-smoke.jsonl`, then the replay script reports OK with exit 0.

- [ ] **Step 5: Push the branch and open a PR**

Run:

```bash
git push -u origin feat/replay-harness
gh pr create --title "feat: telemetry capture + offline replay harness (§8)" \
             --body "$(cat <<'EOF'
## Summary
- Adds JSONL telemetry capture (`backend/src/diagnostics/capture.py`) and replay loader (`backend/src/diagnostics/replay.py`).
- Hooks an optional capture into `NavigationService.update_navigation_state` (no behavior change when unattached).
- Wires capture activation via `LAWNBERRY_CAPTURE_PATH` env var in `backend/src/main.py`.
- Adds CLI `scripts/replay_navigation.py` and a synthetic golden fixture.
- Implements §8 of the architecture plan; precondition for the navigation refactor in Phase 2.

## Test plan
- [ ] All new unit/integration tests pass under `SIM_MODE=1 pytest`.
- [ ] Existing navigation/telemetry test counts unchanged.
- [ ] Manual smoke: capture a 3-step session via env var, replay it, confirm exit 0.
- [ ] Documentation reviewed (`docs/diagnostics-replay.md`).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

---

## Self-review checklist

The plan author has run this checklist; the implementer should verify briefly before starting.

- **Spec coverage:** Every acceptance criterion in §8 of `docs/major-architecture-and-code-improvement-plan.md` maps to at least one task:
  - "captured GPS/IMU/encoder/command/mission state" → Tasks 1, 4, 6 (`SensorData` covers GPS/IMU; encoder/command capture is deferred per "Out of scope" note above and will land with the localization split).
  - "scripts/replay_navigation.py loads captures and runs localization offline" → Task 8.
  - "Golden replay fixtures under tests/fixtures/navigation/" → Tasks 6, 7.
  - "A failed yard run can become a replay fixture" → Task 9 (docs cover the workflow).
  - "HIL tests opt-in" → Out of scope for this plan; HIL belongs to Phase 4.
- **Placeholder scan:** No "TBD", no "implement appropriately", every step has either a command or a code block.
- **Type consistency:** `attach_capture`, `record`, `close`, `path`, `CaptureRecord`, `NavigationStateSnapshot`, `ReplayLoader`, `ReplayLoadError`, `CAPTURE_SCHEMA_VERSION` are spelled identically in every task.
- **TDD discipline:** Every implementation task starts with a failing test (verified by running and seeing the failure) before writing code.
- **Frequent commits:** 9 commits, one per task, each independently revertable.

## Known limitations of this plan

- **Encoder data is not captured** because `SensorData` does not yet include encoder ticks. This will be addressed when wheel encoder integration lands as part of §3 (real pose pipeline). The capture format's schema version (`CAPTURE_SCHEMA_VERSION = 1`) lets us add fields with a version bump without breaking old fixtures.
- **Motor commands are not captured.** This requires §4 (motor command gateway) to be in place — the gateway is the natural capture point for outgoing commands. Tracked as a follow-up.
- **Capture file rotation/retention is absent.** A long-running mission will produce a large file. Acceptable for Phase 1 because operators enable capture explicitly per session. Rotation belongs to §12 (runtime budget).
- **The plan does not change `RuntimeContext` (§1).** Capture is wired through the existing `NavigationService.get_instance()` singleton. When §1 lands, capture should be attached to the runtime context at startup; this plan's wiring helper (`_maybe_attach_telemetry_capture`) will move into the runtime context builder in that follow-up.
