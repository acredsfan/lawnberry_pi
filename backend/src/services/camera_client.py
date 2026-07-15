"""IPC client for the camera-stream systemd service.

The live Raspberry Pi topology has one camera owner: ``lawnberry-camera.service``.
The FastAPI process uses this client instead of opening the device a second time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import suppress
from typing import Any

from ..models.camera_stream import CameraFrame, CameraStream, StreamStatistics

logger = logging.getLogger(__name__)


class CameraClientError(RuntimeError):
    """Raised when the camera IPC owner is unavailable or rejects a request."""


class CameraClient:
    """Async facade over the camera owner's newline-delimited JSON protocol."""

    def __init__(
        self,
        socket_path: str | None = None,
        *,
        request_timeout_seconds: float | None = None,
        startup_timeout_seconds: float | None = None,
    ) -> None:
        self.socket_path = socket_path or os.getenv(
            "LAWNBERRY_CAMERA_SOCKET",
            "/run/lawnberry/camera.sock",
        )
        self.request_timeout_seconds = self._bounded_float(
            request_timeout_seconds,
            env_name="CAMERA_IPC_REQUEST_TIMEOUT_SECONDS",
            default=2.0,
            minimum=0.1,
            maximum=10.0,
        )
        self.startup_timeout_seconds = self._bounded_float(
            startup_timeout_seconds,
            env_name="CAMERA_IPC_STARTUP_TIMEOUT_SECONDS",
            default=20.0,
            minimum=0.0,
            maximum=60.0,
        )
        self.stream = CameraStream()
        # Compatibility alias retained for older callers of the original stub.
        self.camera_stream = self.stream
        self.running = False
        # Treat an owner that has not yet reported its topology as unavailable,
        # never as confirmed live hardware.
        self.sim_mode = True
        self.hardware_available = False
        self.initialized = False
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_lock = asyncio.Lock()

    async def initialize(self) -> bool:
        """Wait briefly for the systemd owner and load its current state."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.startup_timeout_seconds
        last_error: Exception | None = None

        while True:
            try:
                await self._refresh_status()
                self.initialized = True
                self.running = True
                return True
            except (CameraClientError, OSError, TimeoutError, ValueError) as exc:
                last_error = exc
                if loop.time() >= deadline:
                    break
                await asyncio.sleep(min(0.25, max(0.0, deadline - loop.time())))

        self.initialized = False
        self.running = False
        logger.warning("Camera IPC owner unavailable at %s: %s", self.socket_path, last_error)
        return False

    async def get_camera_status(self) -> dict[str, Any]:
        """Return the camera owner's current serialized stream state."""
        await self._refresh_status()
        return self.stream.model_dump(mode="json")

    async def get_stream_statistics(self) -> StreamStatistics:
        """Refresh and return camera statistics from the owner process."""
        await self._refresh_status()
        return self.stream.statistics

    async def get_current_frame(self) -> CameraFrame | None:
        """Fetch the latest frame, including exact-frame AI annotations."""
        try:
            payload = await self._request("get_frame")
        except CameraClientError as exc:
            if "No frame available" in str(exc):
                return None
            raise
        if payload is None:
            return None
        return CameraFrame.model_validate(payload)

    async def start_streaming(self) -> bool:
        """Ask the canonical owner to start capture."""
        await self._request("start_streaming")
        self.stream.is_active = True
        self.running = True
        self.initialized = True
        return True

    async def stop_streaming(self) -> None:
        """Ask the canonical owner to stop capture."""
        await self._request("stop_streaming")
        self.stream.is_active = False

    async def update_configuration(self, config_data: dict[str, Any]) -> bool:
        """Apply camera configuration through the owner process."""
        await self._request("configure", configuration=config_data)
        await self._refresh_status()
        return True

    async def shutdown(self) -> None:
        """Close only this client connection; systemd owns service shutdown."""
        await self._close_connection()
        self.running = False
        self.initialized = False
        # Locks and streams are event-loop bound; a later app lifespan gets a
        # fresh lock after the previous TestClient/uvicorn loop is gone.
        self._request_lock = asyncio.Lock()

    async def _refresh_status(self) -> None:
        payload = await self._request("get_status")
        if not isinstance(payload, dict):
            raise CameraClientError("Camera owner returned an invalid status payload")
        reported_sim_mode = payload.get("sim_mode")
        reported_hardware = payload.get("hardware_available")
        # Missing/malformed metadata can occur during a rolling upgrade. Fail
        # closed so an old owner cannot be presented as confirmed hardware.
        self.sim_mode = reported_sim_mode if isinstance(reported_sim_mode, bool) else True
        self.hardware_available = (
            reported_hardware if isinstance(reported_hardware, bool) else False
        )
        self.stream = CameraStream.model_validate(payload)
        self.camera_stream = self.stream
        self.running = True

    async def _request(self, command: str, **payload: Any) -> Any:
        message = {"command": command, **payload}
        async with self._request_lock:
            for attempt in range(2):
                try:
                    await self._ensure_connection()
                    assert self._reader is not None
                    assert self._writer is not None
                    self._writer.write(json.dumps(message).encode("utf-8") + b"\n")
                    await asyncio.wait_for(
                        self._writer.drain(),
                        timeout=self.request_timeout_seconds,
                    )
                    raw = await asyncio.wait_for(
                        self._reader.readline(),
                        timeout=self.request_timeout_seconds,
                    )
                    if not raw:
                        raise CameraClientError("Camera owner closed the IPC connection")
                    response = json.loads(raw.decode("utf-8"))
                    if response.get("status") != "success":
                        raise CameraClientError(
                            str(response.get("error") or response.get("message") or command)
                        )
                    return response.get("data")
                except (OSError, TimeoutError, json.JSONDecodeError, CameraClientError):
                    await self._close_connection()
                    if attempt == 1:
                        raise
            raise CameraClientError(f"Camera IPC request failed: {command}")

    async def _ensure_connection(self) -> None:
        if self._writer is not None and not self._writer.is_closing() and self._reader is not None:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_unix_connection(
                    self.socket_path,
                    limit=16 * 1024 * 1024,
                ),
                timeout=self.request_timeout_seconds,
            )
        except (OSError, TimeoutError) as exc:
            raise CameraClientError(
                f"Unable to connect to camera owner at {self.socket_path}: {exc}"
            ) from exc

    async def _close_connection(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()

    @staticmethod
    def _bounded_float(
        explicit: float | None,
        *,
        env_name: str,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        raw: float | str = explicit if explicit is not None else os.getenv(env_name, str(default))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(value, maximum))


camera_client = CameraClient()
