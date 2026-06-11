"""Integration test: recover legacy envelope zones into map_zones."""

from __future__ import annotations

import json
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


@pytest.fixture
def map_repo(tmp_path: Path) -> MapRepository:
    return MapRepository(db_path=tmp_path / "legacy-recovery.db")


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


@pytest.mark.asyncio
async def test_get_map_configuration_recovers_legacy_zones_into_map_repository(monkeypatch, map_repo):
    """Legacy envelope zones should be migrated into map_zones when DB is empty."""

    legacy_payload = {
        "provider": "google-maps",
        "zones": [
            {
                "zone_id": "legacy-boundary",
                "zone_type": "boundary",
                "name": "Legacy Boundary",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-84.2140, 39.0390],
                            [-84.2135, 39.0390],
                            [-84.2135, 39.0395],
                            [-84.2140, 39.0395],
                            [-84.2140, 39.0390],
                        ]
                    ],
                },
            }
        ],
    }

    async def _fake_load_map_configuration(config_id: str) -> str:
        assert config_id == "default"
        return json.dumps(legacy_payload)

    monkeypatch.setattr(
        "backend.src.api.rest.persistence.load_map_configuration",
        _fake_load_map_configuration,
    )

    assert map_repo.list_zones() == []

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/api/v2/map/configuration", params={"config_id": "default"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body.get("zones", [])) == 1
        assert body["zones"][0]["id"] == "legacy-boundary"
        assert body["zones"][0]["zone_kind"] == "boundary"

    persisted = map_repo.list_zones()
    assert len(persisted) == 1
    assert persisted[0]["id"] == "legacy-boundary"
