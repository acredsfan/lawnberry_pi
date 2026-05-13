"""Contract tests for the navigation coverage plan endpoint.

T4: Coverage plan reads from map_zones table (via map_repository), not the config envelope.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from backend.src.control.command_gateway import MotorCommandGateway
from backend.src.core import globals as _g
from backend.src.core.runtime import RuntimeContext, get_runtime
from backend.src.main import app
from backend.src.repositories.map_repository import MapRepository

BASE_URL = "http://test"


def _boundary_zone_repo() -> dict:
    """A boundary zone in MapRepository format (polygon list of dicts)."""
    return {
        "id": "boundary-1",
        "name": "Boundary",
        "polygon": [
            {"latitude": 40.7128, "longitude": -74.0060},
            {"latitude": 40.7132, "longitude": -74.0060},
            {"latitude": 40.7132, "longitude": -74.0056},
            {"latitude": 40.7128, "longitude": -74.0056},
        ],
        "priority": 0,
        "exclusion_zone": False,
        "zone_kind": "boundary",
    }


@pytest.fixture
def map_repo(tmp_path: Path) -> MapRepository:
    return MapRepository(db_path=tmp_path / "coverage_contract.db")


@pytest.fixture(autouse=True)
def _override_runtime_with_repo(map_repo: MapRepository):
    """Provide a runtime with a real MapRepository so coverage-plan can find zones.

    This fixture unconditionally sets the override so it wins over the conftest
    default (which provides a runtime without map_repository=None).
    """
    _gw = MotorCommandGateway(
        safety_state=_g._safety_state,
        blade_state=_g._blade_state,
        client_emergency=_g._client_emergency,
        robohat=MagicMock(status=MagicMock(serial_connected=False)),
        persistence=MagicMock(),
    )
    runtime = RuntimeContext(
        config_loader=MagicMock(),
        hardware_config=MagicMock(),
        safety_limits=MagicMock(),
        navigation=MagicMock(),
        mission_service=MagicMock(),
        safety_state=_g._safety_state,
        blade_state=_g._blade_state,
        robohat=MagicMock(),
        websocket_hub=MagicMock(),
        persistence=MagicMock(),
        command_gateway=_gw,
        map_repository=map_repo,
    )
    # Unconditionally override so this module's fixture wins over the conftest default.
    prev = app.dependency_overrides.get(get_runtime)
    app.dependency_overrides[get_runtime] = lambda: runtime
    yield
    if prev is None:
        app.dependency_overrides.pop(get_runtime, None)
    else:
        app.dependency_overrides[get_runtime] = prev


@pytest.mark.asyncio
async def test_get_coverage_plan_returns_linestring_for_saved_boundary(map_repo: MapRepository):
    """Coverage plan succeeds when a boundary zone exists in map_zones."""
    map_repo.save_zones([_boundary_zone_repo()])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get(
            "/api/v2/nav/coverage-plan",
            params={"config_id": "coverage-test", "spacing_m": 0.6},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        geometry = payload.get("plan", {}).get("geometry", {})
        properties = payload.get("plan", {}).get("properties", {})

        assert geometry.get("type") == "LineString"
        assert len(geometry.get("coordinates", [])) >= 2
        assert properties.get("config_id") == "coverage-test"
        assert properties.get("row_count", 0) > 0


@pytest.mark.asyncio
async def test_get_coverage_plan_requires_boundary_zone(map_repo: MapRepository):
    """Coverage plan returns 404 when no boundary zone is in map_zones."""
    # map_repo is empty
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get(
            "/api/v2/nav/coverage-plan",
            params={"config_id": "coverage-empty"},
        )

        assert response.status_code == 404, response.text
        assert "Boundary zone" in response.json().get("detail", "")
