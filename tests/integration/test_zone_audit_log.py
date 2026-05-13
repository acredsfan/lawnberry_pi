"""Integration tests for per-zone audit logging (T5).

Verifies that each zone mutation endpoint records a structured entry
in the audit log via persistence.add_audit_log().

Tests:
1. POST /map/zones/{id}    → action="map.zone.created"
2. PUT  /map/zones/{id}    → action="map.zone.updated"
3. DELETE /map/zones/{id}  → action="map.zone.deleted"
4. POST /map/zones?bulk=true → action="map.zones.bulk_replace"
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.src.control.command_gateway import MotorCommandGateway
from backend.src.core import globals as _g
from backend.src.core.persistence import persistence
from backend.src.core.runtime import RuntimeContext, get_runtime
from backend.src.main import app
from backend.src.repositories.map_repository import MapRepository

BASE_URL = "http://test"


# ---------------------------------------------------------------------------
# Fixtures — real in-memory MapRepository; real persistence singleton for audit
# ---------------------------------------------------------------------------

@pytest.fixture
def map_repo(tmp_path: Path) -> MapRepository:
    return MapRepository(db_path=tmp_path / "zones_audit.db")


@pytest.fixture
def ws_hub() -> MagicMock:
    hub = MagicMock(name="websocket_hub")
    hub.broadcast_to_topic = AsyncMock()
    return hub


@pytest.fixture(autouse=True)
def _override_runtime(map_repo: MapRepository, ws_hub: MagicMock):
    """Inject a RuntimeContext with a real MapRepository before the conftest autouse fixture."""
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
        "zone_kind": "mow",
    }


def _find_audit_log(action: str, resource: str | None = None) -> list[dict]:
    """Return audit log entries matching action (and optionally resource)."""
    logs = persistence.load_audit_logs(limit=200)
    results = [log for log in logs if log["action"] == action]
    if resource is not None:
        results = [log for log in results if log.get("resource") == resource]
    return results


# ---------------------------------------------------------------------------
# 1. POST /map/zones/{id} → map.zone.created
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_zone_writes_audit_log():
    """POST /map/zones/{id} records a 'map.zone.created' audit entry."""
    zone_id = str(uuid.uuid4())
    payload = _zone_payload(zone_id, "Audit Create Zone")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post(f"/api/v2/map/zones/{zone_id}", json=payload)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    entries = _find_audit_log("map.zone.created", resource=zone_id)
    assert len(entries) >= 1, f"Expected at least 1 'map.zone.created' entry for {zone_id}, got {entries}"

    details = entries[0]["details"]
    assert details.get("name") == "Audit Create Zone"
    assert details.get("zone_kind") == "mow"
    assert details.get("priority") == 0
    assert details.get("exclusion_zone") is False
    assert isinstance(details.get("polygon"), list)
    assert len(details["polygon"]) == 4


# ---------------------------------------------------------------------------
# 2. PUT /map/zones/{id} → map.zone.updated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_zone_writes_audit_log():
    """PUT /map/zones/{id} records a 'map.zone.updated' audit entry."""
    zone_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Seed via bulk replace
        seed_resp = await client.post(
            "/api/v2/map/zones?bulk=true",
            json=[_zone_payload(zone_id, "Original Name")],
        )
        assert seed_resp.status_code == 200

        updated_payload = _zone_payload(zone_id, "Updated Name", priority=3, lat_offset=0.002)
        put_resp = await client.put(f"/api/v2/map/zones/{zone_id}", json=updated_payload)
        assert put_resp.status_code == 200, f"Expected 200, got {put_resp.status_code}: {put_resp.text}"

    entries = _find_audit_log("map.zone.updated", resource=zone_id)
    assert len(entries) >= 1, f"Expected at least 1 'map.zone.updated' entry for {zone_id}, got {entries}"

    details = entries[0]["details"]
    assert details.get("name") == "Updated Name"
    assert details.get("priority") == 3
    assert details.get("zone_kind") == "mow"
    assert isinstance(details.get("polygon"), list)


# ---------------------------------------------------------------------------
# 3. DELETE /map/zones/{id} → map.zone.deleted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_zone_writes_audit_log():
    """DELETE /map/zones/{id} records a 'map.zone.deleted' audit entry with zone details."""
    zone_id = str(uuid.uuid4())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        seed_resp = await client.post(
            "/api/v2/map/zones?bulk=true",
            json=[_zone_payload(zone_id, "Zone To Delete")],
        )
        assert seed_resp.status_code == 200

        del_resp = await client.delete(f"/api/v2/map/zones/{zone_id}")
        assert del_resp.status_code == 204, f"Expected 204, got {del_resp.status_code}: {del_resp.text}"

    entries = _find_audit_log("map.zone.deleted", resource=zone_id)
    assert len(entries) >= 1, f"Expected at least 1 'map.zone.deleted' entry for {zone_id}, got {entries}"

    # Details should include pre-deletion zone data (id at minimum)
    details = entries[0]["details"]
    assert details  # non-empty


# ---------------------------------------------------------------------------
# 4. POST /map/zones?bulk=true → map.zones.bulk_replace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_replace_writes_audit_log():
    """POST /map/zones?bulk=true records a 'map.zones.bulk_replace' audit entry."""
    zone_id_a = str(uuid.uuid4())
    zone_id_b = str(uuid.uuid4())

    zones = [
        _zone_payload(zone_id_a, "Bulk Zone A"),
        _zone_payload(zone_id_b, "Bulk Zone B", lat_offset=0.001),
    ]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.post("/api/v2/map/zones?bulk=true", json=zones)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    entries = _find_audit_log("map.zones.bulk_replace")
    assert len(entries) >= 1, f"Expected at least 1 'map.zones.bulk_replace' entry, got {entries}"

    # Find the entry that matches our zone ids
    matching = [e for e in entries if set(e["details"].get("ids", [])) == {zone_id_a, zone_id_b}]
    assert len(matching) >= 1, (
        f"No 'map.zones.bulk_replace' entry with ids={[zone_id_a, zone_id_b]}. "
        f"Entries found: {entries}"
    )

    details = matching[0]["details"]
    assert details["count"] == 2
    assert set(details["ids"]) == {zone_id_a, zone_id_b}
