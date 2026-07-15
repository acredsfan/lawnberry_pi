import os
import subprocess
import sys
from pathlib import Path


def test_camera_unit_uses_canonical_pi_paths_env_and_shared_socket():
    unit = Path("systemd/lawnberry-camera.service").read_text(encoding="utf-8")

    assert "WorkingDirectory=/home/pi/lawnberry" in unit
    assert "EnvironmentFile=-/home/pi/lawnberry/.env" in unit
    assert "Environment=LAWNBERRY_CAMERA_SOCKET=/run/lawnberry/camera.sock" in unit
    assert "RuntimeDirectory=lawnberry" in unit
    assert "RuntimeDirectoryMode=0755" in unit
    assert "ReadWritePaths=/home/pi/lawnberry /var/lib/lawnberry /run/lawnberry" in unit
    assert (
        "ExecStart=/usr/bin/env SIM_MODE=0 "
        "LAWNBERRY_CAMERA_SOCKET=/run/lawnberry/camera.sock "
        "/home/pi/lawnberry/.venv/bin/python "
        "-m backend.src.services.camera_stream_service"
    ) in unit
    assert "/bin/bash" not in unit
    assert "/apps/lawnberry-pi" not in unit

    backend_unit = Path("systemd/lawnberry-backend.service").read_text(encoding="utf-8")
    assert "After=network-online.target lawnberry-camera.service" in backend_unit
    assert "Wants=network-online.target lawnberry-camera.service" in backend_unit
    assert "PartOf=lawnberry-backend.service" in unit
    assert (
        "ExecStart=/usr/bin/env SIM_MODE=0 "
        "LAWNBERRY_CAMERA_SOCKET=/run/lawnberry/camera.sock "
        "/home/pi/lawnberry/.venv/bin/uvicorn"
    ) in backend_unit


def test_frontend_unit_uses_the_canonical_workspace_tree():
    unit = Path("systemd/lawnberry-frontend.service").read_text(encoding="utf-8")

    assert "WorkingDirectory=/home/pi/lawnberry/frontend" in unit
    assert "ExecStart=/usr/bin/node /home/pi/lawnberry/frontend/server.mjs" in unit
    assert "ReadWritePaths=/home/pi/lawnberry/frontend" in unit
    assert "/apps/lawnberry-pi" not in unit


def test_live_camera_runtime_imports_client_without_embedded_owner():
    """Hardware-mode FastAPI imports must not create a second camera singleton."""
    env = os.environ.copy()
    env["SIM_MODE"] = "0"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from backend.src.services.camera_runtime import camera_service; "
                "assert type(camera_service).__name__ == 'CameraClient'; "
                "assert 'backend.src.services.camera_stream_service' not in sys.modules"
            ),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
