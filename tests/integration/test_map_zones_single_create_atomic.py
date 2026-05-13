"""Integration tests for atomic single-zone create endpoint (T3).

Tests:
- POST /map/zones/{id}  creates zone, returns 201
- POST /map/zones/{id}  with same id returns 409
- POST /map/zones       without ?bulk=true returns 400
- POST /map/zones?bulk=true  still works (returns 200)
- POST /map/zones/{id}  with id mismatch between body and path returns 422
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
    return MapRepository(db_path=tmp_path / "test_single_zone.db")


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


def _poly(lat_offset: float = 0.0) -> list[dict]:
    base = 40.7128
    return [
        {"latitude": base + lat_offset, "longitude": -74.0060},
        {"latitude": base + lat_offset + 0.0001, "longitude": -74.0060},
        {"latitude": base + lat_offset + 0.0001, "longitude": -74.0059},
        {"latitude": base + lat_offset, "longitude": -74.0059},
    ]


def _zone_payload(zone_id: str, *, lat_offset: float = 0.0, zone_kind: str = "boundary") -> dict:
    return {
        "id": zone_id,
        "name": f"Zone {zone_id[:8]}",
        "polygon": _poly(lat_offset),
        "priority": 0,
        "exclusion_zone": False,
        "zone_kind": zone_kind,
    }


# ---------------------------------------------------------------------------
# POST /map/zones/{id} — single create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_zone_create_returns_201():
    """POST /api/v2/map/zones/{id} creates a zone and returns 201."""
    zone_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post(
            f"/api/v2/map/zones/{zone_id}",
            json=_zone_payload(zone_id),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"] == zone_id
        assert body["zone_kind"] == "boundary"


@pytest.mark.asyncio
async def test_single_zone_create_conflict_returns_409():
    """POST /api/v2/map/zones/{id} with an already-existing id returns 409."""
    zone_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        first = await client.post(
            f"/api/v2/map/zones/{zone_id}",
            json=_zone_payload(zone_id),
        )
        assert first.status_code == 201, first.text

        second = await client.post(
            f"/api/v2/map/zones/{zone_id}",
            json=_zone_payload(zone_id),
        )
        assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_single_zone_create_id_mismatch_returns_422():
    """POST /api/v2/map/zones/{id} where body id != path id returns 422."""
    zone_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post(
            f"/api/v2/map/zones/{zone_id}",
            json=_zone_payload("different-id"),
        )
        assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_single_zone_create_zone_kind_mow():
    """POST /api/v2/map/zones/{id} with zone_kind='mow' round-trips correctly."""
    zone_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post(
            f"/api/v2/map/zones/{zone_id}",
            json=_zone_payload(zone_id, zone_kind="mow"),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["zone_kind"] == "mow"


@pytest.mark.asyncio
async def test_single_zone_create_emits_ws_event(ws_hub: MagicMock):
    """POST /api/v2/map/zones/{id} broadcasts a zone.changed WS event."""
    zone_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post(
            f"/api/v2/map/zones/{zone_id}",
            json=_zone_payload(zone_id),
        )
        assert resp.status_code == 201, resp.text

    ws_hub.broadcast_to_topic.assert_awaited()
    topic = ws_hub.broadcast_to_topic.call_args[0][0]
    assert topic == "planning.zone.changed"


# ---------------------------------------------------------------------------
# POST /map/zones — bulk guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_post_without_bulk_param_returns_400():
    """POST /api/v2/map/zones without ?bulk=true returns 400."""
    zone_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post(
            "/api/v2/map/zones",
            json=[_zone_payload(zone_id)],
        )
        assert resp.status_code == 400, resp.text
        assert "bulk=true" in resp.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_bulk_post_with_bulk_param_returns_200():
    """POST /api/v2/map/zones?bulk=true succeeds and returns the zones."""
    zone_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post(
            "/api/v2/map/zones?bulk=true",
            json=[_zone_payload(zone_id)],
        )
        assert resp.status_code == 200, resp.text
        zones = resp.json()
        assert any(z["id"] == zone_id for z in zones)
