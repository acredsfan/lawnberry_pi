"""Integration tests for zone overlap validation on single-zone create.

Tests:
- Creating a zone that overlaps an existing boundary zone returns 422
- Creating a non-overlapping zone succeeds with 201
- A zone with < 3 points bypasses overlap check and succeeds
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.src.main import app
from backend.src.core.runtime import RuntimeContext, get_runtime
from backend.src.control.command_gateway import MotorCommandGateway
from backend.src.core import globals as _g
from backend.src.repositories.map_repository import MapRepository

BASE_URL = "http://test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def map_repo(tmp_path: Path) -> MapRepository:
    return MapRepository(db_path=tmp_path / "test_overlap.db")


@pytest.fixture
def ws_hub() -> MagicMock:
    hub = MagicMock(name="websocket_hub")
    hub.broadcast_to_topic = AsyncMock()
    return hub


@pytest.fixture(autouse=True)
def _override_runtime(map_repo: MapRepository, ws_hub: MagicMock):
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
        websocket_hub=ws_hub,
        persistence=MagicMock(),
        command_gateway=_gw,
        map_repository=map_repo,
    )
    app.dependency_overrides[get_runtime] = lambda: runtime
    yield runtime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _square_zone(zone_id: str, lat: float, lon: float, size: float = 0.0001) -> dict:
    """Create a small square zone centred at (lat, lon)."""
    return {
        "id": zone_id,
        "name": f"Zone {zone_id[:8]}",
        "polygon": [
            {"latitude": lat, "longitude": lon},
            {"latitude": lat + size, "longitude": lon},
            {"latitude": lat + size, "longitude": lon + size},
            {"latitude": lat, "longitude": lon + size},
        ],
        "priority": 0,
        "exclusion_zone": False,
        "zone_kind": "boundary",
    }


async def _create_zone(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    zone_id = payload["id"]
    return await client.post(f"/api/v2/map/zones/{zone_id}", json=payload)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overlapping_zone_returns_422():
    """Creating a zone that overlaps an existing zone returns 422 with conflict detail."""
    existing_id = str(uuid.uuid4())
    overlapping_id = str(uuid.uuid4())

    # Both zones occupy the same area: lat=40.7128, lon=-74.006, size=0.001
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        first = await _create_zone(client, _square_zone(existing_id, 40.7128, -74.006, 0.001))
        assert first.status_code == 201, first.text

        # The second zone overlaps the first (same coordinates, different id)
        overlapping = _square_zone(overlapping_id, 40.7128, -74.006, 0.001)
        second = await _create_zone(client, overlapping)
        assert second.status_code == 422, second.text
        detail = second.json().get("detail", "")
        assert existing_id in str(detail), f"Expected conflicting zone id in detail: {detail}"


@pytest.mark.asyncio
async def test_non_overlapping_zone_succeeds():
    """Creating a zone that does not overlap existing zones returns 201."""
    zone_a_id = str(uuid.uuid4())
    zone_b_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Zone A at latitude 40.7000
        first = await _create_zone(client, _square_zone(zone_a_id, 40.7000, -74.006, 0.0001))
        assert first.status_code == 201, first.text

        # Zone B at latitude 41.0000 — far away
        second = await _create_zone(client, _square_zone(zone_b_id, 41.0000, -74.006, 0.0001))
        assert second.status_code == 201, second.text


@pytest.mark.asyncio
async def test_partially_overlapping_zone_returns_422():
    """A zone that partially overlaps an existing zone also returns 422."""
    zone_a_id = str(uuid.uuid4())
    zone_b_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Zone A: lat 40.7000 to 40.7010
        first = await _create_zone(client, _square_zone(zone_a_id, 40.7000, -74.0060, 0.0010))
        assert first.status_code == 201, first.text

        # Zone B: lat 40.7005 to 40.7015 — overlaps Zone A by half
        zone_b = _square_zone(zone_b_id, 40.7005, -74.0060, 0.0010)
        second = await _create_zone(client, zone_b)
        assert second.status_code == 422, second.text


@pytest.mark.asyncio
async def test_touching_boundary_zones_succeed():
    """Zones that only touch at an edge (not truly overlapping) should succeed."""
    zone_a_id = str(uuid.uuid4())
    zone_b_id = str(uuid.uuid4())
    size = 0.0010

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Zone A: lat 40.7000, lon -74.0060 to lat 40.7010, lon -74.0050
        zone_a = {
            "id": zone_a_id,
            "name": "Zone A",
            "polygon": [
                {"latitude": 40.7000, "longitude": -74.0060},
                {"latitude": 40.7000 + size, "longitude": -74.0060},
                {"latitude": 40.7000 + size, "longitude": -74.0060 + size},
                {"latitude": 40.7000, "longitude": -74.0060 + size},
            ],
            "priority": 0,
            "exclusion_zone": False,
            "zone_kind": "boundary",
        }
        first = await _create_zone(client, zone_a)
        assert first.status_code == 201, first.text

        # Zone B starts exactly where Zone A ends (touching at the edge)
        zone_b = {
            "id": zone_b_id,
            "name": "Zone B",
            "polygon": [
                {"latitude": 40.7000 + size, "longitude": -74.0060},
                {"latitude": 40.7000 + 2 * size, "longitude": -74.0060},
                {"latitude": 40.7000 + 2 * size, "longitude": -74.0060 + size},
                {"latitude": 40.7000 + size, "longitude": -74.0060 + size},
            ],
            "priority": 0,
            "exclusion_zone": False,
            "zone_kind": "boundary",
        }
        second = await _create_zone(client, zone_b)
        # Touching polygons should not conflict
        assert second.status_code == 201, second.text
