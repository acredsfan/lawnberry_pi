"""Unit tests for MissionExecutor.

All tests use fake localization (FakeLocalization) and fake gateway (FakeGateway)
so no hardware, RoboHAT, or NavigationService instance is required.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.src.models import NavigationMode, PathStatus, Position
from backend.src.models.mission import MissionLifecycleStatus


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class FakeLocalization:
    """Minimal LocalizationProvider for testing."""

    def __init__(
        self,
        *,
        position: Position | None = None,
        heading: float | None = 0.0,
        dead_reckoning_active: bool = False,
        last_gps_fix: datetime | None = None,
    ):
        self._position = position
        self._heading = heading
        self._dead_reckoning_active = dead_reckoning_active
        self._last_gps_fix = last_gps_fix or datetime.now(UTC)

    @property
    def current_position(self) -> Position | None:
        return self._position

    @property
    def heading(self) -> float | None:
        return self._heading

    @property
    def dead_reckoning_active(self) -> bool:
        return self._dead_reckoning_active

    @property
    def last_gps_fix(self) -> datetime | None:
        return self._last_gps_fix


class FakeGateway:
    """Minimal gateway stub — records drive calls, never errors."""

    def __init__(self):
        self.drive_calls: list[tuple[float, float]] = []
        self._emergency = False

    def is_emergency_active(self) -> bool:
        return self._emergency

    async def dispatch_drive_speeds(self, left: float, right: float) -> bool:
        self.drive_calls.append((left, right))
        return True


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

def test_mission_executor_constructs():
    from backend.src.services.mission_executor import MissionExecutor

    loc = FakeLocalization()
    gw = FakeGateway()
    executor = MissionExecutor(localization=loc, gateway=gw)
    assert executor is not None
