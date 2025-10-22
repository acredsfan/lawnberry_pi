from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.src.middleware.api_key_auth import register_api_key_auth_middleware


def create_app():
    app = FastAPI()
    register_api_key_auth_middleware(app)

    @app.get("/api/v2/internal/status")
    def status():
        return {"ok": True}

    @app.get("/public")
    def public():
        return {"ok": True}

    return app


def test_api_key_required_on_protected_prefix(monkeypatch):
    monkeypatch.setenv("API_KEY_REQUIRED", "1")
    monkeypatch.setenv("API_KEY_PATH_PREFIXES", "/api/v2/internal")
    monkeypatch.setenv("API_KEY_SECRET", "abc123")

    app = create_app()
    client = TestClient(app)

    # Missing key
    r = client.get("/api/v2/internal/status")
    assert r.status_code == 401

    # Wrong key
    r = client.get("/api/v2/internal/status", headers={"X-API-Key": "nope"})
    assert r.status_code == 401

    # Correct key via header
    r = client.get("/api/v2/internal/status", headers={"X-API-Key": "abc123"})
    assert r.status_code == 200

    # Public path unaffected
    r = client.get("/public")
    assert r.status_code == 200
