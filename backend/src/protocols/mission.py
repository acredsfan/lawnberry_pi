"""Protocols for mission–navigation boundary.

Using a structural Protocol breaks the circular import between
MissionService and NavigationService without requiring any changes
to MissionService's implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MissionStatusReader(Protocol):
    """Minimal interface NavigationService needs from MissionService."""

    mission_statuses: Mapping[str, Any]  # read-only access: mission_id → MissionStatus

    async def update_waypoint_progress(self, mission_id: str, waypoint_index: int) -> None: ...
