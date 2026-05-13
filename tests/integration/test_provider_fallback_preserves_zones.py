"""Integration test: provider fallback does not wipe map_zones.

After POST /api/v2/map/provider-fallback, zones stored in map_zones table
must be unaffected. The narrow JSON_SET update in persistence must not
touch any zone data.
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
    return MapRepository(db_path=tmp_path / "test_fallback.db")


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
# Helper
# ---------------------------------------------------------------------------


def _zone(zone_id: str, zone_kind: str = "boundary") -> dict:
    return {
        "id": zone_id,
        "name": f"Zone-{zone_id[:8]}",
        "polygon": [
            {"latitude": 40.7128, "longitude": -74.0060},
            {"latitude": 40.7129, "longitude": -74.0060},
            {"latitude": 40.7129, "longitude": -74.0059},
            {"latitude": 40.7128, "longitude": -74.0059},
        ],
        "priority": 0,
        "exclusion_zone": False,
        "zone_kind": zone_kind,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_fallback_does_not_delete_zones(map_repo: MapRepository):
    """POST /map/provider-fallback must not remove zones from map_zones."""
    zone_id = str(uuid.uuid4())
    map_repo.save_zones([_zone(zone_id)])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post("/api/v2/map/provider-fallback")
        assert resp.status_code == 200, resp.text
        assert resp.json().get("provider") == "osm"

    # Zones in map_zones must be intact after fallback
    zones = map_repo.list_zones()
    assert len(zones) == 1, "Zone was deleted by provider fallback"
    assert zones[0]["id"] == zone_id


@pytest.mark.asyncio
async def test_provider_fallback_updates_provider_field(map_repo: MapRepository):
    """POST /map/provider-fallback must set provider to 'osm' in the response."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Set provider to google-maps first via non-spatial PUT
        put_resp = await client.put(
            "/api/v2/map/configuration",
            json={"provider": "google-maps"},
        )
        assert put_resp.status_code == 200, put_resp.text

        fallback_resp = await client.post("/api/v2/map/provider-fallback")
        assert fallback_resp.status_code == 200, fallback_resp.text
        body = fallback_resp.json()
        assert body.get("provider") == "osm"
        assert body.get("fallback", {}).get("active") is True


@pytest.mark.asyncio
async def test_provider_fallback_preserves_markers(map_repo: MapRepository):
    """POST /map/provider-fallback must not wipe markers from map_config."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Save markers via PUT
        put_resp = await client.put(
            "/api/v2/map/configuration",
            json={"markers": [{"id": "m1", "lat": 40.7, "lng": -74.0}], "provider": "google-maps"},
        )
        assert put_resp.status_code == 200, put_resp.text

        # Fallback to osm
        fallback_resp = await client.post("/api/v2/map/provider-fallback")
        assert fallback_resp.status_code == 200, fallback_resp.text

        # GET should still show markers
        get_resp = await client.get("/api/v2/map/configuration")
        assert get_resp.status_code == 200, get_resp.text
        payload = get_resp.json()
        markers = payload.get("markers", [])
        assert len(markers) == 1, f"Markers were wiped after fallback; got: {markers}"
        assert markers[0]["id"] == "m1"
