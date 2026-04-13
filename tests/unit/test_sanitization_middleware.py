import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.src.middleware.sanitization import register_sanitization_middleware, _redact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_app():
    app = FastAPI()
    register_sanitization_middleware(app)

    @app.get("/secrets")
    def secrets():
        return {"token": "secret-token", "nested": {"password": "p@ss"}, "ok": True}

    return app


def _check_content_length(resp) -> None:
    """Assert that the declared Content-Length matches the actual body length."""
    declared = int(resp.headers.get("content-length", -1))
    actual = len(resp.content)
    assert declared == actual, (
        f"Content-Length mismatch: declared={declared}, actual={actual}"
    )


# ---------------------------------------------------------------------------
# Existing redaction test
# ---------------------------------------------------------------------------

def test_sanitizes_sensitive_fields():
    app = create_app()
    client = TestClient(app)
    r = client.get("/secrets")
    assert r.status_code == 200
    data = r.json()
    assert data["token"] == "***REDACTED***"
    assert data["nested"]["password"] == "***REDACTED***"
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# Content-Length correctness tests — these guard against the ASGI error
# "Response content longer/shorter than Content-Length" that occurs when
# the body iterator is exhausted before the response is fully sent.
# ---------------------------------------------------------------------------

def test_content_length_correct_after_redaction_enlarges_body():
    """Redacting short values (e.g. 'x') produces a LONGER body; Content-Length must match."""
    app = FastAPI()
    register_sanitization_middleware(app)

    @app.get("/short-token")
    def short_token():
        # 'token': 'x' → 'token': '***REDACTED***' increases body size
        return {"token": "x", "data": "ok"}

    client = TestClient(app)
    r = client.get("/short-token")
    assert r.status_code == 200
    _check_content_length(r)
    assert r.json()["token"] == "***REDACTED***"


def test_content_length_correct_for_large_body_passthrough():
    """Bodies > 256 KB are passed through without redaction; Content-Length must still match.

    Before the fix, draining body_iterator and then returning the exhausted
    _StreamingResponse caused Content-Length=N but body=0 bytes.
    """
    app = FastAPI()
    register_sanitization_middleware(app)

    large_payload = {"data": "x" * 300_000}

    @app.get("/large")
    def large():
        return large_payload

    client = TestClient(app)
    r = client.get("/large")
    assert r.status_code == 200
    _check_content_length(r)
    # Body must contain the actual data (not be empty or truncated)
    assert len(r.content) > 256_000


def test_content_length_correct_for_invalid_json_passthrough():
    """application/json response whose body is not valid JSON is passed through verbatim.

    Before the fix, draining body_iterator on an invalid-JSON body and then
    returning the exhausted _StreamingResponse caused Content-Length mismatch.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Route
    from backend.src.middleware.sanitization import SanitizationMiddleware

    raw_body = b"not valid json at all"

    async def bad_json(request: Request):
        return Response(content=raw_body, media_type="application/json")

    starlette_app = Starlette(
        routes=[Route("/bad", bad_json)],
        middleware=[Middleware(SanitizationMiddleware)],
    )

    client = TestClient(starlette_app, raise_server_exceptions=True)
    r = client.get("/bad")
    assert r.status_code == 200
    _check_content_length(r)
    assert r.content == raw_body


def test_content_length_correct_for_non_json_passthrough():
    """Non-JSON responses are passed through with correct Content-Length."""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Route
    from backend.src.middleware.sanitization import SanitizationMiddleware

    async def plain(request: Request):
        return Response(content=b"plain text response", media_type="text/plain")

    starlette_app = Starlette(
        routes=[Route("/plain", plain)],
        middleware=[Middleware(SanitizationMiddleware)],
    )

    client = TestClient(starlette_app)
    r = client.get("/plain")
    assert r.status_code == 200
    _check_content_length(r)
    assert r.text == "plain text response"


def test_security_headers_always_present():
    """X-Content-Type-Options and X-Frame-Options must be set on every response."""
    app = create_app()
    client = TestClient(app)
    r = client.get("/secrets")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"


# ---------------------------------------------------------------------------
# Unit tests for the pure _redact helper
# ---------------------------------------------------------------------------

def test_redact_dict_sensitive_keys():
    result = _redact({"token": "abc", "ok": 1})
    assert result == {"token": "***REDACTED***", "ok": 1}


def test_redact_nested():
    result = _redact({"user": {"password": "pw", "name": "alice"}})
    assert result["user"]["password"] == "***REDACTED***"
    assert result["user"]["name"] == "alice"


def test_redact_list():
    result = _redact([{"api_key": "k"}, {"other": "v"}])
    assert result[0]["api_key"] == "***REDACTED***"
    assert result[1]["other"] == "v"


def test_redact_non_collection_passthrough():
    assert _redact(42) == 42
    assert _redact("hello") == "hello"
    assert _redact(None) is None
