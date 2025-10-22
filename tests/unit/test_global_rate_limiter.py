from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.src.middleware.rate_limiting import register_global_rate_limiter


def create_app():
    app = FastAPI()
    register_global_rate_limiter(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


def test_rate_limiter_allows_burst_then_limits(monkeypatch):
    monkeypatch.setenv("GLOBAL_RATE_LIMIT_RATE", "100")  # refill fast for test
    monkeypatch.setenv("GLOBAL_RATE_LIMIT_BURST", "3")
    monkeypatch.setenv("GLOBAL_RATE_LIMIT_EXEMPT", "/health")
    app = create_app()
    client = TestClient(app)

    # 3 allowed
    for _ in range(3):
        r = client.get("/ping")
        assert r.status_code == 200
    # 4th should be limited
    r = client.get("/ping")
    assert r.status_code == 429
    assert r.json()["detail"] == "Too many requests"
