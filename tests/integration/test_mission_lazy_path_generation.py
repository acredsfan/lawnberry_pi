"""Integration tests for T8: lazy waypoint generation via zone_id.

Tests verify that:
  1. A mission created with zone_id generates waypoints at start_mission time.
  2. start_mission raises MissionValidationError when the planner returns empty waypoints.
  3. The explicit-waypoints path still works unchanged (regression).
  4. MissionCreationRequest rejects requests missing both waypoints and zone_id (model level).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.src.models.mission import MissionCreationRequest, MissionWaypoint
from backend.src.repositories.mission_repository import MissionRepository
from backend.src.repositories.map_repository import MapRepository
from backend.src.services.mission_service import (
    MissionService,
    MissionValidationError,
)
from backend.src.services.planning_service import PlannedPath, PlanningService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def mission_repo(tmp_db: Path) -> MissionRepository:
    return MissionRepository(db_path=tmp_db)


@pytest.fixture()
def map_repo(tmp_db: Path) -> MapRepository:
    return MapRepository(db_path=tmp_db)


@pytest.fixture()
def nav_service_mock() -> MagicMock:
    """Minimal NavigationService stub."""
    nav = MagicMock()
    nav.navigation_state = MagicMock()
    nav.navigation_state.safety_boundaries = []  # no geofence → skip validation
    nav.execute_mission = AsyncMock()
    return nav


@pytest.fixture()
def mission_service(nav_service_mock: MagicMock, mission_repo: MissionRepository) -> MissionService:
    return MissionService(
        navigation_service=nav_service_mock,
        websocket_hub=None,
        mission_repository=mission_repo,
    )


# Small rectangular zone polygon (lat/lon pairs) that fits within a 0.35 m grid step.
# Approximately 1 m × 1 m centred at (37.0, -122.0).
_ZONE_POLYGON = [
    [37.000000, -122.000000],
    [37.000009, -122.000000],
    [37.000009, -122.000012],
    [37.000000, -122.000012],
]

_ZONE_ID = "zone-abc-123"


def _make_zone(zone_id: str = _ZONE_ID, exclusion: bool = False) -> dict:
    return {
        "id": zone_id,
        "name": "Test Zone",
        "polygon": _ZONE_POLYGON,
        "priority": 1,
        "exclusion_zone": exclusion,
    }


def _make_planning_service_with_zone(map_repo: MapRepository) -> PlanningService:
    """Return a real PlanningService wired to map_repo containing one zone."""
    map_repo.save_zones([_make_zone()])
    ps = PlanningService()
    ps.set_map_repository(map_repo)
    return ps


# ---------------------------------------------------------------------------
# T1: zone_id mission generates waypoints at start_mission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_mission_with_zone_id_generates_waypoints(
    mission_service: MissionService,
    map_repo: MapRepository,
):
    """Waypoints must be non-empty on the stored mission after start_mission."""
    ps = _make_planning_service_with_zone(map_repo)

    with patch(
        "backend.src.services.mission_service.get_planning_service",
        return_value=ps,
    ):
        mission = await mission_service.create_mission(
            "lazy-test",
            zone_id=_ZONE_ID,
            pattern="parallel",
            pattern_params={"spacing_m": 0.5},
        )

        assert mission.waypoints == [], "Waypoints should be empty before start_mission"
        assert mission_service._planning_intents.get(mission.id) is not None

        await mission_service.start_mission(mission.id)

    stored = mission_service.missions[mission.id]
    assert len(stored.waypoints) > 0, "Waypoints must be populated after start_mission"


# ---------------------------------------------------------------------------
# T2: start_mission raises when planner returns empty list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_mission_rejects_empty_planned_path(
    mission_service: MissionService,
):
    """If PlanningService returns no waypoints, start_mission must raise MissionValidationError."""
    empty_plan = PlannedPath(waypoints=[], length_m=0.0, est_duration_s=0.0)
    mock_ps = MagicMock()
    mock_ps.plan_path_for_zone = AsyncMock(return_value=empty_plan)

    with patch(
        "backend.src.services.mission_service.get_planning_service",
        return_value=mock_ps,
    ):
        mission = await mission_service.create_mission(
            "empty-zone-test",
            zone_id="some-zone",
            pattern="parallel",
        )

        with pytest.raises(MissionValidationError, match="no waypoints"):
            await mission_service.start_mission(mission.id)

    # Mission should NOT be RUNNING after failure
    status = mission_service.mission_statuses[mission.id]
    from backend.src.models.mission import MissionLifecycleStatus
    assert status.status == MissionLifecycleStatus.IDLE


# ---------------------------------------------------------------------------
# T3: Explicit waypoints path works unchanged (regression)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_waypoints_still_work_unchanged(
    mission_service: MissionService,
):
    """Creating and starting a mission with explicit waypoints must still work."""
    waypoints = [
        MissionWaypoint(lat=37.0, lon=-122.0),
        MissionWaypoint(lat=37.0001, lon=-122.0001),
    ]

    mission = await mission_service.create_mission("explicit-wp", waypoints)
    assert len(mission.waypoints) == 2
    assert mission_service._planning_intents.get(mission.id) is None

    await mission_service.start_mission(mission.id)

    # Nav service should have been called
    mission_service.nav_service.execute_mission.assert_called_once()
    stored = mission_service.missions[mission.id]
    assert len(stored.waypoints) == 2


# ---------------------------------------------------------------------------
# T4: MissionCreationRequest rejects neither waypoints nor zone_id
# ---------------------------------------------------------------------------


def test_creation_rejected_when_neither_waypoints_nor_zone_id():
    """Pydantic must raise ValidationError when both waypoints and zone_id are absent."""
    import pydantic

    with pytest.raises(pydantic.ValidationError, match="zone_id"):
        MissionCreationRequest(name="bad-mission")


def test_creation_rejected_when_both_waypoints_and_zone_id():
    """Pydantic must raise ValidationError when both waypoints and zone_id are present."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        MissionCreationRequest(
            name="bad-mission",
            waypoints=[MissionWaypoint(lat=37.0, lon=-122.0)],
            zone_id="some-zone",
        )


def test_creation_accepted_with_waypoints_only():
    """Explicit waypoints with no zone_id should be accepted."""
    req = MissionCreationRequest(
        name="ok-mission",
        waypoints=[MissionWaypoint(lat=37.0, lon=-122.0)],
    )
    assert len(req.waypoints) == 1
    assert req.zone_id is None


def test_creation_accepted_with_zone_id_only():
    """zone_id with no waypoints should be accepted."""
    req = MissionCreationRequest(
        name="ok-zone-mission",
        zone_id="my-zone",
        pattern="parallel",
    )
    assert req.zone_id == "my-zone"
    assert req.waypoints is None
