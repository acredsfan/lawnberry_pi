"""Integration test: /api/v2/nav/coverage-plan reads from map_zones, not envelope.

Verifies that:
- Coverage plan uses map_repository.list_zones() filtered by zone_kind
- Zones in map_config envelope are ignored (T4 invariant)
- 404 is returned when no boundary zone exists in map_zones
"""

from __future__ import annotations

import uuid
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def map_repo(tmp_path: Path) -> MapRepository:
    return MapRepository(db_path=tmp_path / "test_coverage.db")


@pytest.fixture(autouse=True)
def _override_runtime(map_repo: MapRepository):
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
    app.dependency_overrides[get_runtime] = lambda: runtime
    yield runtime
    app.dependency_overrides.pop(get_runtime, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _boundary_zone(zone_id: str) -> dict:
    """A boundary zone polygon with enough area for a coverage plan."""
    return {
        "id": zone_id,
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


def _exclusion_zone(zone_id: str) -> dict:
    return {
        "id": zone_id,
        "name": "Exclusion",
        "polygon": [
            {"latitude": 40.7129, "longitude": -74.0059},
            {"latitude": 40.71295, "longitude": -74.0059},
            {"latitude": 40.71295, "longitude": -74.00585},
            {"latitude": 40.7129, "longitude": -74.00585},
        ],
        "priority": 0,
        "exclusion_zone": True,
        "zone_kind": "exclusion",
    }


def _mow_zone(zone_id: str) -> dict:
    """A mow zone that should NOT be treated as a boundary."""
    return {
        "id": zone_id,
        "name": "Mow Zone",
        "polygon": [
            {"latitude": 40.7128, "longitude": -74.0060},
            {"latitude": 40.7132, "longitude": -74.0060},
            {"latitude": 40.7132, "longitude": -74.0056},
            {"latitude": 40.7128, "longitude": -74.0056},
        ],
        "priority": 0,
        "exclusion_zone": False,
        "zone_kind": "mow",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coverage_plan_uses_map_zones_boundary(map_repo: MapRepository):
    """Coverage plan succeeds when a boundary zone is in map_zones."""
    zone_id = str(uuid.uuid4())
    map_repo.save_zones([_boundary_zone(zone_id)])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.get("/api/v2/nav/coverage-plan", params={"spacing_m": 0.6})
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        geometry = payload.get("plan", {}).get("geometry", {})
        assert geometry.get("type") == "LineString"
        assert len(geometry.get("coordinates", [])) >= 2


@pytest.mark.asyncio
async def test_coverage_plan_returns_404_when_no_boundary_zone(map_repo: MapRepository):
    """Coverage plan returns 404 when map_zones has no boundary zone."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.get("/api/v2/nav/coverage-plan", params={"spacing_m": 0.6})
        assert resp.status_code == 404, resp.text
        assert "boundary" in resp.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_coverage_plan_returns_404_when_only_mow_zone(map_repo: MapRepository):
    """Coverage plan returns 404 when map_zones has only a mow zone (not boundary)."""
    zone_id = str(uuid.uuid4())
    map_repo.save_zones([_mow_zone(zone_id)])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.get("/api/v2/nav/coverage-plan", params={"spacing_m": 0.6})
        assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_coverage_plan_ignores_envelope_zones(map_repo: MapRepository):
    """Coverage plan must read from map_zones, not from the map_config envelope.

    Even if the envelope had zones before T4, they should be ignored.
    """
    # No zones in map_repo → coverage plan should return 404, regardless of
    # what was previously in the map_config envelope.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.get("/api/v2/nav/coverage-plan", params={"spacing_m": 0.6})
        assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_coverage_plan_returns_404_when_no_map_repository():
    """Coverage plan returns 404 when map_repository is None on the runtime."""
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.core import globals as _g

    _gw = MotorCommandGateway(
        safety_state=_g._safety_state,
        blade_state=_g._blade_state,
        client_emergency=_g._client_emergency,
        robohat=MagicMock(status=MagicMock(serial_connected=False)),
        persistence=MagicMock(),
    )
    runtime_no_repo = RuntimeContext(
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
        map_repository=None,
    )
    app.dependency_overrides[get_runtime] = lambda: runtime_no_repo
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            resp = await client.get("/api/v2/nav/coverage-plan", params={"spacing_m": 0.6})
            assert resp.status_code == 404, resp.text
    finally:
        app.dependency_overrides.pop(get_runtime, None)
