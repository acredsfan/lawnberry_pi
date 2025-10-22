from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.src.middleware.sanitization import register_sanitization_middleware


def create_app():
    app = FastAPI()
    register_sanitization_middleware(app)

    @app.get("/secrets")
    def secrets():
        return {"token": "secret-token", "nested": {"password": "p@ss"}, "ok": True}

    return app


def test_sanitizes_sensitive_fields():
    app = create_app()
    client = TestClient(app)
    r = client.get("/secrets")
    assert r.status_code == 200
    data = r.json()
    assert data["token"] == "***REDACTED***"
    assert data["nested"]["password"] == "***REDACTED***"
    assert data["ok"] is True
