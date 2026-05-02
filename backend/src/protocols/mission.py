"""Protocols for mission–navigation boundary.

Using a structural Protocol breaks the circular import between
MissionService and NavigationService without requiring any changes
to MissionService's implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from backend.src.models import Position


@runtime_checkable
class MissionStatusReader(Protocol):
    """Minimal interface NavigationService needs from MissionService."""

    mission_statuses: Mapping[str, Any]  # read-only access: mission_id → MissionStatus

    async def update_waypoint_progress(self, mission_id: str, waypoint_index: int) -> None: ...


@runtime_checkable
class LocalizationProvider(Protocol):
    """Minimal pose interface consumed by MissionExecutor.

    Structural: any object with these attributes satisfies the protocol.
    """

    @property
    def current_position(self) -> Position | None: ...

    @property
    def heading(self) -> float | None: ...

    @property
    def dead_reckoning_active(self) -> bool: ...

    @property
    def last_gps_fix(self) -> datetime | None: ...
