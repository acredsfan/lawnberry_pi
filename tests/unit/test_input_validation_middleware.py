from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.src.middleware.input_validation import register_input_validation_middleware


def create_app():
    app = FastAPI()
    register_input_validation_middleware(app)

    @app.post("/echo")
    def echo(payload: dict):
        return payload

    return app


def test_rejects_non_json_content_type():
    app = create_app()
    client = TestClient(app)
    r = client.post(
        "/echo",
        data="x=1",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 415


def test_rejects_invalid_json():
    app = create_app()
    client = TestClient(app)
    r = client.post("/echo", data="{not json}", headers={"Content-Type": "application/json"})
    assert r.status_code == 400


def test_accepts_json_and_echoes():
    app = create_app()
    client = TestClient(app)
    r = client.post("/echo", json={"a": 1})
    assert r.status_code == 200
    assert r.json() == {"a": 1}
