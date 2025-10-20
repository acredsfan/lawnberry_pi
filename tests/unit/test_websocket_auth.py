import pytest
from starlette.requests import Request
from fastapi.testclient import TestClient

from backend.src.api import rest
from backend.src.main import app


def build_request(headers=None, client_host="127.0.0.1"):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/ws/telemetry",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (client_host, 12345),
    }
    return Request(scope)


def test_require_bearer_auth_allows_loopback_without_header():
    request = build_request()
    # Should not raise for loopback clients even without token
    rest._require_bearer_auth(request)


def test_require_bearer_auth_rejects_public_client_without_header():
    request = build_request(client_host="8.8.8.8")
    with pytest.raises(rest.HTTPException) as exc:
        rest._require_bearer_auth(request)
    assert exc.value.status_code == 401


def test_require_bearer_auth_accepts_bearer_token():
    request = build_request(headers={"Authorization": "Bearer test-token"}, client_host="8.8.8.8")
    rest._require_bearer_auth(request)


def test_handshake_allows_missing_subprotocol_header():
    client = TestClient(app)
    response = client.get(
        "/api/v2/ws/telemetry",
        headers={
            "connection": "Upgrade",
            "upgrade": "websocket",
            "sec-websocket-version": "13",
            "sec-websocket-key": "dGhlIHNhbXBsZSBub25jZQ==",
        },
    )
    assert response.status_code == 101
    assert response.headers["sec-websocket-protocol"] == "telemetry.v1"


def test_legacy_handshake_works_without_subprotocol_header():
    client = TestClient(app)
    response = client.get(
        "/ws/telemetry",
        headers={
            "connection": "Upgrade",
            "upgrade": "websocket",
            "sec-websocket-version": "13",
            "sec-websocket-key": "dGhlIHNhbXBsZSBub25jZQ==",
        },
    )
    assert response.status_code == 101
    assert response.headers["sec-websocket-protocol"] == "telemetry.v1"


def test_websocket_accepts_requested_subprotocol():
    client = TestClient(app)
    with client.websocket_connect(
        "/api/v2/ws/telemetry",
        headers={"sec-websocket-protocol": "telemetry.v1"},
    ) as websocket:
        assert websocket.accepted_subprotocol == "telemetry.v1"


def test_legacy_websocket_accepts_requested_subprotocol():
    client = TestClient(app)
    with client.websocket_connect(
        "/ws/telemetry",
        headers={"sec-websocket-protocol": "telemetry.v1"},
    ) as websocket:
        assert websocket.accepted_subprotocol == "telemetry.v1"
