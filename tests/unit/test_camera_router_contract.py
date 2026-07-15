import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.src.api.routers import camera as camera_router


def test_mjpeg_route_does_not_accept_manual_control_session_in_query() -> None:
    assert "session_id" not in inspect.signature(camera_router.stream_mjpeg).parameters


class _DummyFrame:
    def __init__(self, raw_bytes: bytes):
        self._raw_bytes = raw_bytes
        self.data = "this-should-not-be-served-directly"
        self.metadata = SimpleNamespace(timestamp=datetime.now(UTC))

    def get_frame_data(self) -> bytes:
        return self._raw_bytes


class _DummyCameraService:
    def __init__(self, raw_bytes: bytes):
        self.running = True
        self.sim_mode = False
        self.hardware_available = True
        self.stream = SimpleNamespace(
            last_frame_time=datetime.now(UTC),
            mode=SimpleNamespace(value="streaming"),
            client_count=1,
            is_active=True,
        )
        self._frame = _DummyFrame(raw_bytes)
        self.stop_calls = 0
        self.start_calls = 0

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
        self.start_calls += 1
        self.stream.is_active = True
        return True

    async def stop_streaming(self):
        self.stop_calls += 1
        self.stream.is_active = False


@pytest.mark.asyncio
async def test_camera_frame_endpoint_returns_raw_jpeg_bytes(test_client, monkeypatch):
    from backend.src.api.routers import camera as camera_router

    raw_bytes = b"\xff\xd8\xff\xe0mock-jpeg-data\xff\xd9"
    monkeypatch.setattr(camera_router, "camera_service", _DummyCameraService(raw_bytes))
    monkeypatch.setattr(camera_router, "get_power_manager", lambda: None)

    response = await test_client.get("/api/v2/camera/frame")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.content == raw_bytes


@pytest.mark.asyncio
async def test_camera_frame_endpoint_resumes_capture_for_active_viewer(test_client, monkeypatch):
    from backend.src.api.routers import camera as camera_router

    service = _DummyCameraService(b"\xff\xd8\xff\xd9")
    service.stream.is_active = False
    monkeypatch.setattr(camera_router, "camera_service", service)
    monkeypatch.setattr(camera_router, "get_power_manager", lambda: None)

    response = await test_client.get("/api/v2/camera/frame")

    assert response.status_code == 200
    assert service.start_calls == 1
    assert service.stream.is_active is True


@pytest.mark.asyncio
async def test_camera_viewer_wakes_capture_and_ai_through_power_manager(monkeypatch):
    power_manager = SimpleNamespace(wake_for_viewer=AsyncMock(return_value=True))
    service = _DummyCameraService(b"\xff\xd8\xff\xd9")
    service.stream.is_active = False
    monkeypatch.setattr(camera_router, "camera_service", service)
    monkeypatch.setattr(camera_router, "get_power_manager", lambda: power_manager)

    await camera_router._wake_camera_for_viewer()

    power_manager.wake_for_viewer.assert_awaited_once_with()
    assert service.start_calls == 0


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
    assert payload["sim_mode"] is False
    assert payload["hardware_available"] is True


@pytest.mark.asyncio
async def test_camera_status_exposes_owner_hardware_fallback(test_client, monkeypatch, tmp_path):
    from backend.src.api.routers import camera as camera_router
    from backend.src.services.camera_client import CameraClient
    from backend.src.services.camera_stream_service import CameraStreamService

    monkeypatch.setenv("SIM_MODE", "0")
    owner = CameraStreamService(sim_mode=False)
    owner.socket_path = str(tmp_path / "fallback-camera.sock")

    async def reject_hardware() -> bool:
        owner.hardware_available = False
        return False

    monkeypatch.setattr(owner, "_initialize_camera", reject_hardware)
    client = CameraClient(
        owner.socket_path,
        request_timeout_seconds=1.0,
        startup_timeout_seconds=0.0,
    )

    try:
        assert await owner.initialize() is True
        assert owner.sim_mode is True
        assert await client.initialize() is True
        monkeypatch.setattr(camera_router, "camera_service", client)

        response = await test_client.get("/api/v2/camera/status")

        assert response.status_code == 200
        payload = response.json()
        assert payload["sim_mode"] is True
        assert payload["hardware_available"] is False
        assert client.sim_mode is True
        assert client.hardware_available is False
    finally:
        await client.shutdown()
        await owner.shutdown()


@pytest.mark.asyncio
async def test_camera_stop_endpoint_awaits_service_stop(test_client, monkeypatch):
    from backend.src.api.routers import camera as camera_router

    service = _DummyCameraService(b"\xff\xd8\xff\xd9")
    monkeypatch.setattr(camera_router, "camera_service", service)

    response = await test_client.post("/api/v2/camera/stop")

    assert response.status_code == 200
    assert response.json()["streaming"] is False
    assert service.stop_calls == 1
