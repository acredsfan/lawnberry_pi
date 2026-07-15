import asyncio
import json

import pytest

from backend.src.models.camera_stream import CameraFrame, CameraStream, FrameMetadata
from backend.src.services.camera_client import CameraClient


@pytest.mark.asyncio
async def test_camera_client_consumes_owner_status_and_annotated_frame(tmp_path):
    socket_path = tmp_path / "camera.sock"
    stream = CameraStream(is_active=True)
    frame = CameraFrame(
        metadata=FrameMetadata(
            frame_id="frame-owner-1",
            width=32,
            height=24,
            size_bytes=4,
        ),
        processed_for_ai=True,
        ai_annotations=[
            {
                "type": "obstacle_detection",
                "objects": [{"class": "obstacle", "confidence": 0.9}],
            }
        ],
    )
    frame.set_frame_data(b"jpeg")
    commands: list[str] = []

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while raw := await reader.readline():
                request = json.loads(raw)
                command = request["command"]
                commands.append(command)
                if command == "get_status":
                    status_payload = stream.model_dump(mode="json")
                    status_payload.update(
                        {
                            "sim_mode": False,
                            "hardware_available": True,
                        }
                    )
                    response = {
                        "status": "success",
                        "data": status_payload,
                    }
                elif command == "get_frame":
                    response = {
                        "status": "success",
                        "data": frame.model_dump(mode="json"),
                    }
                elif command == "start_streaming":
                    stream.is_active = True
                    response = {"status": "success", "message": "started"}
                elif command == "stop_streaming":
                    stream.is_active = False
                    response = {"status": "success", "message": "stopped"}
                else:
                    response = {"status": "error", "error": "unsupported"}
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle_client, path=str(socket_path))
    client = CameraClient(
        str(socket_path),
        request_timeout_seconds=1.0,
        startup_timeout_seconds=0.0,
    )
    try:
        assert await client.initialize() is True
        assert client.running is True
        assert client.stream.is_active is True
        assert client.sim_mode is False
        assert client.hardware_available is True

        received = await client.get_current_frame()
        assert received is not None
        assert received.metadata.frame_id == "frame-owner-1"
        assert received.get_frame_data() == b"jpeg"
        assert received.processed_for_ai is True
        assert received.ai_annotations[0]["objects"][0]["class"] == "obstacle"

        await client.stop_streaming()
        assert client.stream.is_active is False
        assert await client.start_streaming() is True
        assert client.stream.is_active is True

        await client.shutdown()
        assert client.running is False
        assert commands == [
            "get_status",
            "get_frame",
            "stop_streaming",
            "start_streaming",
        ]
    finally:
        await client.shutdown()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_camera_client_fails_fast_when_owner_socket_is_absent(tmp_path):
    client = CameraClient(
        str(tmp_path / "missing.sock"),
        request_timeout_seconds=0.1,
        startup_timeout_seconds=0.0,
    )

    assert await client.initialize() is False
    assert client.running is False
    assert client.sim_mode is True
    assert client.hardware_available is False


@pytest.mark.asyncio
async def test_camera_client_fails_closed_when_owner_omits_topology(tmp_path):
    socket_path = tmp_path / "legacy-camera.sock"
    stream = CameraStream(is_active=True)

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readline()
            writer.write(
                json.dumps(
                    {
                        "status": "success",
                        "data": stream.model_dump(mode="json"),
                    }
                ).encode()
                + b"\n"
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle_client, path=str(socket_path))
    client = CameraClient(
        str(socket_path),
        request_timeout_seconds=1.0,
        startup_timeout_seconds=0.0,
    )
    try:
        assert await client.initialize() is True
        assert client.sim_mode is True
        assert client.hardware_available is False
    finally:
        await client.shutdown()
        server.close()
        await server.wait_closed()
