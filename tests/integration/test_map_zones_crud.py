"""Integration tests for per-zone CRUD endpoints (T5).

Tests:
- GET /api/v2/map/zones/{id} — single-zone fetch
- PUT /api/v2/map/zones/{id} — update one zone without touching others
- DELETE /api/v2/map/zones/{id} — delete one zone
- POST /api/v2/map/zones — still works (bulk replace) and emits WS event
- WS event emission on mutations
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
# Shared runtime fixture with a real in-memory MapRepository
# ---------------------------------------------------------------------------

@pytest.fixture
def map_repo(tmp_path: Path) -> MapRepository:
    return MapRepository(db_path=tmp_path / "test_zones.db")


@pytest.fixture
def ws_hub() -> MagicMock:
    hub = MagicMock(name="websocket_hub")
    hub.broadcast_to_topic = AsyncMock()
    return hub


@pytest.fixture(autouse=True)
def _override_runtime(map_repo: MapRepository, ws_hub: MagicMock):
    """Set dependency_overrides[get_runtime] before the integration conftest autouse sees it.

    Because this is a module-level autouse fixture, it runs before the conftest autouse fixture
    checks whether get_runtime is already overridden. That means the conftest fixture skips
    injecting its own (repo-less) runtime and ours wins.
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
        websocket_hub=ws_hub,
        persistence=MagicMock(),
        command_gateway=_gw,
        map_repository=map_repo,
    )
    app.dependency_overrides[get_runtime] = lambda: runtime
    yield runtime
    # conftest's reset_app_state_runtime_and_overrides clears dependency_overrides after test


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _poly(lat_offset: float = 0.0) -> list[dict]:
    base = 40.7128
    return [
        {"latitude": base + lat_offset, "longitude": -74.0060},
        {"latitude": base + lat_offset + 0.0001, "longitude": -74.0060},
        {"latitude": base + lat_offset + 0.0001, "longitude": -74.0059},
        {"latitude": base + lat_offset, "longitude": -74.0059},
    ]


def _zone_payload(zone_id: str, name: str, priority: int = 0, lat_offset: float = 0.0) -> dict:
    return {
        "id": zone_id,
        "name": name,
        "polygon": _poly(lat_offset),
        "priority": priority,
        "exclusion_zone": False,
    }


async def _post_zones(client: httpx.AsyncClient, *zone_payloads: dict) -> httpx.Response:
    return await client.post("/api/v2/map/zones?bulk=true", json=list(zone_payloads))


# ---------------------------------------------------------------------------
# GET /api/v2/map/zones/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_single_zone_returns_correct_zone():
    """GET /api/v2/map/zones/{id} returns exactly the zone with that id."""
    zone_a_id = str(uuid.uuid4())
    zone_b_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        post_resp = await _post_zones(
            client,
            _zone_payload(zone_a_id, "Zone A"),
            _zone_payload(zone_b_id, "Zone B", lat_offset=0.001),
        )
        assert post_resp.status_code == 200

        get_resp = await client.get(f"/api/v2/map/zones/{zone_a_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == zone_a_id
        assert data["name"] == "Zone A"


@pytest.mark.asyncio
async def test_get_single_zone_not_found_returns_404():
    """GET /api/v2/map/zones/{id} for unknown id returns 404."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        get_resp = await client.get("/api/v2/map/zones/does-not-exist")
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/v2/map/zones/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_zone_updates_single_record_without_replacing_all():
    """PUT /api/v2/map/zones/{id} updates one zone; the sibling is unchanged."""
    zone_a_id = str(uuid.uuid4())
    zone_b_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        post_resp = await _post_zones(
            client,
            _zone_payload(zone_a_id, "Zone A"),
            _zone_payload(zone_b_id, "Zone B", lat_offset=0.001),
        )
        assert post_resp.status_code == 200

        updated_payload = _zone_payload(zone_a_id, "Zone A Updated", lat_offset=0.002)
        put_resp = await client.put(f"/api/v2/map/zones/{zone_a_id}", json=updated_payload)
        assert put_resp.status_code == 200
        updated = put_resp.json()
        assert updated["id"] == zone_a_id
        assert updated["name"] == "Zone A Updated"

        # GET all zones — still 2 zones
        list_resp = await client.get("/api/v2/map/zones")
        assert list_resp.status_code == 200
        zones = list_resp.json()
        assert len(zones) == 2

        zone_a = next((z for z in zones if z["id"] == zone_a_id), None)
        assert zone_a is not None
        assert zone_a["name"] == "Zone A Updated"

        zone_b = next((z for z in zones if z["id"] == zone_b_id), None)
        assert zone_b is not None
        assert zone_b["name"] == "Zone B"


@pytest.mark.asyncio
async def test_put_zone_not_found_returns_404():
    """PUT /api/v2/map/zones/{id} for unknown id returns 404."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        put_resp = await client.put(
            "/api/v2/map/zones/no-such-zone",
            json=_zone_payload("no-such-zone", "Ghost"),
        )
        assert put_resp.status_code == 404


@pytest.mark.asyncio
async def test_put_zone_id_mismatch_returns_422():
    """PUT /api/v2/map/zones/{id} where body id != path id returns 422."""
    zone_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await _post_zones(client, _zone_payload(zone_id, "Some Zone"))

        bad_payload = _zone_payload("different-id", "Name")
        put_resp = await client.put(f"/api/v2/map/zones/{zone_id}", json=bad_payload)
        assert put_resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/v2/map/zones/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_zone_removes_only_targeted_zone():
    """DELETE /api/v2/map/zones/{id} removes exactly that zone; sibling survives."""
    zone_a_id = str(uuid.uuid4())
    zone_b_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        post_resp = await _post_zones(
            client,
            _zone_payload(zone_a_id, "Zone A"),
            _zone_payload(zone_b_id, "Zone B", lat_offset=0.001),
        )
        assert post_resp.status_code == 200

        del_resp = await client.delete(f"/api/v2/map/zones/{zone_a_id}")
        assert del_resp.status_code == 204

        list_resp = await client.get("/api/v2/map/zones")
        zones = list_resp.json()
        assert len(zones) == 1
        assert zones[0]["id"] == zone_b_id


@pytest.mark.asyncio
async def test_delete_zone_not_found_returns_404():
    """DELETE /api/v2/map/zones/{id} for unknown id returns 404."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        del_resp = await client.delete("/api/v2/map/zones/no-such-zone")
        assert del_resp.status_code == 404


# ---------------------------------------------------------------------------
# WS event emission
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zone_change_emits_ws_event_on_post(ws_hub: MagicMock):
    """POST /api/v2/map/zones emits planning.zone.changed on the WS hub."""
    zone_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await _post_zones(client, _zone_payload(zone_id, "Test Zone"))
        assert resp.status_code == 200

    # broadcast_to_topic is awaited directly in the async handler — no sleep needed
    ws_hub.broadcast_to_topic.assert_awaited()
    call_args = ws_hub.broadcast_to_topic.call_args
    assert call_args[0][0] == "planning.zone.changed"


@pytest.mark.asyncio
async def test_zone_change_emits_ws_event_on_put(ws_hub: MagicMock):
    """PUT /api/v2/map/zones/{id} emits planning.zone.changed on the WS hub."""
    zone_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await _post_zones(client, _zone_payload(zone_id, "Original"))
        ws_hub.broadcast_to_topic.reset_mock()

        resp = await client.put(
            f"/api/v2/map/zones/{zone_id}", json=_zone_payload(zone_id, "Updated")
        )
        assert resp.status_code == 200

    ws_hub.broadcast_to_topic.assert_awaited()
    assert ws_hub.broadcast_to_topic.call_args[0][0] == "planning.zone.changed"


@pytest.mark.asyncio
async def test_zone_change_emits_ws_event_on_delete(ws_hub: MagicMock):
    """DELETE /api/v2/map/zones/{id} emits planning.zone.changed on the WS hub."""
    zone_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await _post_zones(client, _zone_payload(zone_id, "ToDelete"))
        ws_hub.broadcast_to_topic.reset_mock()

        resp = await client.delete(f"/api/v2/map/zones/{zone_id}")
        assert resp.status_code == 204

    ws_hub.broadcast_to_topic.assert_awaited()
    assert ws_hub.broadcast_to_topic.call_args[0][0] == "planning.zone.changed"


# ---------------------------------------------------------------------------
# Verify _zones_store is gone (no fallback to in-memory)
# ---------------------------------------------------------------------------

def test_zones_store_global_is_removed():
    """_zones_store should no longer exist in rest.py."""
    import backend.src.api.rest as rest_module
    assert not hasattr(rest_module, "_zones_store"), (
        "_zones_store global still present in rest.py — must be removed"
    )
