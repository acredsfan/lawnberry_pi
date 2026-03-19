from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


class _DummyFrame:
    def __init__(self, raw_bytes: bytes):
        self._raw_bytes = raw_bytes
        self.data = "this-should-not-be-served-directly"
        self.metadata = SimpleNamespace(timestamp=datetime.now(timezone.utc))

    def get_frame_data(self) -> bytes:
        return self._raw_bytes


class _DummyCameraService:
    def __init__(self, raw_bytes: bytes):
        self.running = True
        self.sim_mode = False
        self.stream = SimpleNamespace(
            last_frame_time=datetime.now(timezone.utc),
            mode=SimpleNamespace(value="streaming"),
            client_count=1,
            is_active=True,
        )
        self._frame = _DummyFrame(raw_bytes)

    async def get_stream_statistics(self):
        return SimpleNamespace(
            frames_captured=12,
            frames_processed=11,
            current_fps=14.5,
            average_fps=13.2,
        )

    async def get_current_frame(self):
        return self._frame

    async def initialize(self):
        return True

    async def start_streaming(self):
        return True


@pytest.mark.asyncio
async def test_camera_frame_endpoint_returns_raw_jpeg_bytes(test_client, monkeypatch):
    from backend.src.api.routers import camera as camera_router

    raw_bytes = b"\xff\xd8\xff\xe0mock-jpeg-data\xff\xd9"
    monkeypatch.setattr(camera_router, "camera_service", _DummyCameraService(raw_bytes))

    response = await test_client.get("/api/v2/camera/frame")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.content == raw_bytes


@pytest.mark.asyncio
async def test_camera_status_reports_current_fps(test_client, monkeypatch):
    from backend.src.api.routers import camera as camera_router

    monkeypatch.setattr(camera_router, "camera_service", _DummyCameraService(b"\xff\xd8\xff\xd9"))

    response = await test_client.get("/api/v2/camera/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["fps"] == pytest.approx(14.5)
    assert payload["statistics"]["fps"] == pytest.approx(14.5)
    assert payload["statistics"]["average_fps"] == pytest.approx(13.2)