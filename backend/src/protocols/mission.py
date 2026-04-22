"""Protocols for mission–navigation boundary.

Using a structural Protocol breaks the circular import between
MissionService and NavigationService without requiring any changes
to MissionService's implementation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MissionStatusReader(Protocol):
    """Minimal interface NavigationService needs from MissionService."""

    mission_statuses: dict  # read-only access to status dict

    async def update_waypoint_progress(
        self, mission_id: str, waypoint_index: int
    ) -> None: ...

    async def mark_mission_complete(self, mission_id: str) -> None: ...

    async def mark_mission_failed(self, mission_id: str, reason: str) -> None: ...
