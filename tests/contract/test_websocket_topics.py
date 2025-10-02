"""Contract tests for WebSocket handshake and metadata across v2 topics."""

import base64
import os

import pytest
import httpx

from backend.src.main import app


BASE_URL = "http://test"


def _websocket_headers(extra: dict | None = None) -> dict:
    key = base64.b64encode(os.urandom(16)).decode()
    headers = {
        "Connection": "Upgrade",
        "Upgrade": "websocket",
        "Sec-WebSocket-Key": key,
        "Sec-WebSocket-Version": "13",
        "Authorization": "Bearer test-token",
        "Sec-WebSocket-Protocol": "telemetry.v1",
    }
    if extra:
        headers.update(extra)
    return headers


@pytest.mark.asyncio
async def test_telemetry_websocket_handshake_includes_latency_budget():
    """/api/v2/ws/telemetry must upgrade with latency budget and schema headers."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        headers = _websocket_headers()
        response = await client.get("/api/v2/ws/telemetry", headers=headers)

        assert response.status_code == 101, response.text
        accept = response.headers.get("sec-websocket-accept")
        assert accept, "Missing Sec-WebSocket-Accept header"
        latency_budget = int(response.headers.get("x-latency-budget-ms", "0"))
        assert latency_budget <= 250
        assert response.headers.get("sec-websocket-protocol") == "telemetry.v1"
        assert response.headers.get("x-payload-schema") == "#/components/schemas/HardwareTelemetryStream"


@pytest.mark.asyncio
async def test_telemetry_websocket_requires_bearer_auth():
    """Telemetry channel should reject unauthenticated connections."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        headers = _websocket_headers({"Authorization": None})
        headers.pop("Authorization", None)

        response = await client.get("/api/v2/ws/telemetry", headers=headers)

        assert response.status_code == 401, response.text
        body = response.json()
        assert body.get("detail") == "Unauthorized"


@pytest.mark.asyncio
async def test_control_websocket_requires_bearer_auth():
    """/api/v2/ws/control should reject connections without Authorization header."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        headers = _websocket_headers({"Authorization": None, "Sec-WebSocket-Protocol": "control.v1"})
        headers.pop("Authorization", None)

        response = await client.get("/api/v2/ws/control", headers=headers)

        assert response.status_code == 401, response.text
        body = response.json()
        assert body.get("detail") == "Unauthorized"


@pytest.mark.asyncio
async def test_control_websocket_handshake_includes_latency_and_schema():
    """Control channel handshake must advertise latency budget and payload schema."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        headers = _websocket_headers({"Sec-WebSocket-Protocol": "control.v1"})
        response = await client.get("/api/v2/ws/control", headers=headers)

        assert response.status_code == 101, response.text
        assert response.headers.get("sec-websocket-protocol") == "control.v1"
        assert response.headers.get("sec-websocket-accept")
        latency_budget = int(response.headers.get("x-latency-budget-ms", "0"))
        assert latency_budget <= 200
        assert response.headers.get("x-payload-schema") == "#/components/schemas/ControlCommandResponse"


@pytest.mark.asyncio
async def test_settings_websocket_announces_payload_schema():
    """Settings WebSocket handshake should surface payload schema reference."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        headers = _websocket_headers({"Sec-WebSocket-Protocol": "settings.v1"})
        response = await client.get("/api/v2/ws/settings", headers=headers)

        assert response.status_code == 101, response.text
        assert response.headers.get("sec-websocket-protocol") == "settings.v1"
        assert response.headers.get("sec-websocket-accept")
        schema_ref = response.headers.get("x-payload-schema")
        assert schema_ref == "#/components/schemas/SettingsProfile"


@pytest.mark.asyncio
async def test_settings_websocket_requires_bearer_auth():
    """Settings channel should require Authorization header."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        headers = _websocket_headers({"Authorization": None, "Sec-WebSocket-Protocol": "settings.v1"})
        headers.pop("Authorization", None)

        response = await client.get("/api/v2/ws/settings", headers=headers)

        assert response.status_code == 401, response.text
        body = response.json()
        assert body.get("detail") == "Unauthorized"


@pytest.mark.asyncio
async def test_notifications_websocket_includes_latency_and_schema():
    """Notifications channel must advertise latency budget and schema metadata."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        headers = _websocket_headers({"Sec-WebSocket-Protocol": "notifications.v1"})
        response = await client.get("/api/v2/ws/notifications", headers=headers)

        assert response.status_code == 101, response.text
        assert response.headers.get("sec-websocket-protocol") == "notifications.v1"
        assert response.headers.get("sec-websocket-accept")
        latency_budget = int(response.headers.get("x-latency-budget-ms", "0"))
        assert latency_budget <= 500
        assert response.headers.get("x-payload-schema") == "#/components/schemas/NotificationEvent"


@pytest.mark.asyncio
async def test_notifications_websocket_requires_bearer_auth():
    """Notifications channel should reject unauthenticated connections."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        headers = _websocket_headers({"Authorization": None, "Sec-WebSocket-Protocol": "notifications.v1"})
        headers.pop("Authorization", None)

        response = await client.get("/api/v2/ws/notifications", headers=headers)

        assert response.status_code == 401, response.text
        body = response.json()
        assert body.get("detail") == "Unauthorized"