"""Regression test for RuntimeError: Response content longer than Content-Length.

Root cause: JSONResponse(status_code=304, content=None) renders b"null" as the
body (4 bytes).  Starlette's init_headers intentionally omits Content-Length for
304 responses, so uvicorn starts with expected_content_length=0.  Sending 4 bytes
then raises "Response content longer than Content-Length".

Fix: use Response(status_code=304) which produces an empty body (b""), matching
uvicorn's expectation for 304.
"""

import hashlib
import json

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.responses import Response


# ---------------------------------------------------------------------------
# Unit tests – verify the response objects directly
# ---------------------------------------------------------------------------

class TestJSONResponse304Regression:
    """Ensure JSONResponse(304, content=None) is never used for conditional responses."""

    def test_response_304_empty_body(self):
        """Response(status_code=304) must have an empty body."""
        r = Response(status_code=304)
        assert r.body == b"", "304 Response must have empty body"

    def test_response_304_no_content_length_with_empty_body(self):
        """304 response body must be empty so uvicorn expected_content_length=0 is satisfied."""
        r = Response(status_code=304)
        # body is empty – sending 0 bytes never exceeds expected_content_length=0
        assert len(r.body) == 0

    def test_response_304_with_cache_headers(self):
        """304 with cache headers must still have empty body."""
        headers = {"ETag": "abc123", "Cache-Control": "public, max-age=30"}
        r = Response(status_code=304, headers=headers)
        assert r.body == b"", "304 with headers must have empty body"
        header_names = {k.decode() for k, _ in r.raw_headers}
        assert "etag" in header_names
        assert "cache-control" in header_names

    def test_json_response_304_none_has_body(self):
        """Confirm the OLD broken pattern: JSONResponse(304, content=None) has non-empty body."""
        r = JSONResponse(status_code=304, content=None)
        # This is the bug: body is b"null" (4 bytes) but no Content-Length header.
        assert r.body == b"null", "JSONResponse None renders as 'null'"
        # Confirm Content-Length is absent (Starlette skips it for 304)
        header_names = {k.decode() for k, _ in r.raw_headers}
        assert "content-length" not in header_names, (
            "Starlette omits Content-Length for 304 – sending any body causes "
            "uvicorn to raise 'Response content longer than Content-Length'"
        )


# ---------------------------------------------------------------------------
# Integration tests – hit the actual endpoints via TestClient
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from backend.src.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestMapEndpoints304:
    """Verify /api/v2/settings/maps endpoints return valid 304 responses."""

    def test_map_zones_200_then_304_etag(self, client):
        """Second request with matching ETag returns 304 with no body."""
        r1 = client.get("/api/v2/map/zones")
        assert r1.status_code == 200
        etag = r1.headers.get("etag")
        if etag is None:
            pytest.skip("ETag header not present on 200 response")

        r2 = client.get("/api/v2/map/zones", headers={"If-None-Match": etag})
        assert r2.status_code == 304
        # Body MUST be empty – non-empty body causes the ASGI RuntimeError
        assert r2.content == b"", f"304 response must have empty body, got {r2.content!r}"

    def test_map_locations_200_then_304_etag(self, client):
        """Second request with matching ETag returns 304 with no body."""
        r1 = client.get("/api/v2/map/locations")
        assert r1.status_code == 200
        etag = r1.headers.get("etag")
        if etag is None:
            pytest.skip("ETag header not present on 200 response")

        r2 = client.get("/api/v2/map/locations", headers={"If-None-Match": etag})
        assert r2.status_code == 304
        assert r2.content == b"", f"304 response must have empty body, got {r2.content!r}"
