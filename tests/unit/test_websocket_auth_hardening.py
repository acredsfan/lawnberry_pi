from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.src.api.routers import auth as auth_router
from backend.src.models.user_session import UserSession


@pytest.mark.asyncio
async def test_production_loopback_websocket_requires_signed_proof(monkeypatch):
    monkeypatch.setenv("SIM_MODE", "0")
    websocket = SimpleNamespace(
        headers={},
        client=("127.0.0.1", 12345),
        query_params={},
    )

    with pytest.raises(HTTPException) as exc:
        await auth_router._authorize_websocket(websocket)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_websocket_subprotocol_authenticates_without_url_credential(monkeypatch):
    monkeypatch.setenv("SIM_MODE", "0")
    session = UserSession.create_operator_session()
    verify_token = AsyncMock(return_value=session)
    monkeypatch.setattr(auth_router.primary_auth_service, "verify_token", verify_token)
    websocket = SimpleNamespace(
        headers={"Sec-WebSocket-Protocol": "telemetry.v1, lawnberry.jwt.signed-token"},
        client=("127.0.0.1", 12345),
        query_params={},
    )

    authorized = await auth_router._authorize_websocket(websocket)

    assert authorized is session
    verify_token.assert_awaited_once_with("signed-token")


@pytest.mark.asyncio
async def test_websocket_query_token_is_not_an_authentication_channel(monkeypatch):
    monkeypatch.setenv("SIM_MODE", "0")
    websocket = SimpleNamespace(
        headers={},
        client=("127.0.0.1", 12345),
        query_params={"access_token": "would-leak-in-access-log"},
    )

    with pytest.raises(HTTPException) as exc:
        await auth_router._authorize_websocket(websocket)

    assert exc.value.status_code == 401
