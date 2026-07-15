"""Executable autonomous-mission integration scenarios."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.models.mission import MissionLegType
from backend.src.repositories.map_repository import MapRepository
from backend.src.repositories.mission_repository import MissionRepository
from backend.src.services.mission_service import MissionService, MissionValidationError
from backend.src.services.planning_service import PlanningService


@pytest.mark.asyncio
async def test_saved_zone_plans_and_starts_a_typed_coverage_mission(tmp_path) -> None:
    db_path = tmp_path / "autonomous-operation.db"
    map_repository = MapRepository(db_path=db_path)
    mission_repository = MissionRepository(db_path=db_path)
    map_repository.save_zones(
        [
            {
                "id": "front-lawn",
                "name": "Front Lawn",
                "polygon": [
                    [37.000000, -122.000000],
                    [37.000018, -122.000000],
                    [37.000018, -122.000024],
                    [37.000000, -122.000024],
                ],
                "priority": 1,
                "exclusion_zone": False,
            }
        ]
    )
    planning = PlanningService()
    planning.set_map_repository(map_repository)

    navigation = MagicMock()
    navigation.navigation_state = SimpleNamespace(
        safety_boundaries=[],
        planned_path=[],
        current_waypoint_index=0,
    )
    navigation.execute_mission = AsyncMock()
    mission_service = MissionService(
        navigation_service=navigation,
        websocket_hub=None,
        mission_repository=mission_repository,
    )

    with patch(
        "backend.src.services.mission_service.get_planning_service",
        return_value=planning,
    ):
        mission = await mission_service.create_mission(
            "Front lawn autonomous coverage",
            zone_id="front-lawn",
            pattern="parallel",
            pattern_params={"spacing_m": 0.5, "endpoint_clearance_m": 0.15},
        )
        assert mission.waypoints == []

        started = await mission_service.start_mission(mission.id)
        await asyncio.sleep(0)

    planned = mission_service.missions[mission.id].waypoints
    assert started.status == "running"
    assert len(planned) >= 2
    assert any(waypoint.leg_type is MissionLegType.MOW for waypoint in planned)
    assert all(
        not waypoint.blade_on or waypoint.leg_type is MissionLegType.MOW
        for waypoint in planned
    )
    navigation.execute_mission.assert_awaited_once()


@pytest.mark.asyncio
async def test_unsupported_coverage_pattern_fails_before_motion(tmp_path) -> None:
    mission_repository = MissionRepository(db_path=tmp_path / "unsupported-pattern.db")
    navigation = MagicMock()
    navigation.navigation_state = SimpleNamespace(
        safety_boundaries=[],
        planned_path=[],
        current_waypoint_index=0,
    )
    navigation.execute_mission = AsyncMock()
    mission_service = MissionService(
        navigation_service=navigation,
        websocket_hub=None,
        mission_repository=mission_repository,
    )
    planning = MagicMock()
    planning.plan_path_for_zone = AsyncMock(
        side_effect=NotImplementedError("pattern not implemented: 'spiral'")
    )

    with patch(
        "backend.src.services.mission_service.get_planning_service",
        return_value=planning,
    ):
        mission = await mission_service.create_mission(
            "Unsupported pattern",
            zone_id="front-lawn",
            pattern="spiral",
        )
        with pytest.raises(MissionValidationError, match="Failed to generate waypoints"):
            await mission_service.start_mission(mission.id)

    navigation.execute_mission.assert_not_awaited()
