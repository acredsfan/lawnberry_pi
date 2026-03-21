import json
import time
import types

import pytest

from backend.src.services import robohat_service as robohat_module
from backend.src.services.robohat_service import RoboHATService


class _StubSerial:
    def __init__(self):
        self.is_open = True
        self.in_waiting = 0


class _ResponsiveSerial(_StubSerial):
    def __init__(self, lines: list[str]):
        super().__init__()
        self._lines = [line.encode("utf-8") + b"\n" for line in lines]
        self.writes: list[bytes] = []
        self.write_timeout = 1.0

    @property
    def in_waiting(self):
        return int(bool(self._lines))

    @in_waiting.setter
    def in_waiting(self, _value):
        return None

    def write(self, payload: bytes):
        self.writes.append(payload)
        return len(payload)

    def flush(self):
        return None

    def readline(self):
        if self._lines:
            return self._lines.pop(0)
        return b""

    def close(self):
        self.is_open = False


class _DelayedResponsiveSerial(_ResponsiveSerial):
    def __init__(self, lines: list[str], ready_after_checks: int):
        super().__init__(lines)
        self._ready_after_checks = ready_after_checks
        self._checks = 0

    @property
    def in_waiting(self):
        self._checks += 1
        if self._checks <= self._ready_after_checks:
            return 0
        return int(bool(self._lines))

    @in_waiting.setter
    def in_waiting(self, _value):
        return None


@pytest.mark.asyncio
async def test_send_motor_command_forces_rc_disable(monkeypatch):
    svc = RoboHATService()
    svc.serial_conn = _StubSerial()
    svc.running = True
    svc._rc_enabled = True
    calls: list[str] = []

    async def fake_send_line(line: str) -> bool:
        calls.append(line)
        return True

    async def fake_wait_for_usb_control(timeout: float = 0.75) -> bool:  # noqa: ARG001
        svc._pending_rc_state = None
        svc._rc_enabled = False
        return True

    # Prevent the maintain loop from interfering
    svc._usb_control_requested = True
    monkeypatch.setattr(svc, "_send_line", fake_send_line)
    monkeypatch.setattr(svc, "_wait_for_usb_control", fake_wait_for_usb_control)

    ok = await svc.send_motor_command(0.1, 0.1)

    assert ok is True
    assert calls[0] == "rc=disable"
    assert any(call.startswith("pwm,") for call in calls[1:])


@pytest.mark.asyncio
async def test_ensure_usb_control_retries_and_marks_error(monkeypatch):
    svc = RoboHATService()
    svc.serial_conn = _StubSerial()
    svc.running = True
    svc._rc_enabled = True
    attempts: list[tuple[bool, bool]] = []

    async def fake_set_rc(enabled: bool, *, force: bool = False) -> None:
        attempts.append((enabled, force))

    async def fake_wait_for_usb_control(timeout: float = 0.75) -> bool:  # noqa: ARG001
        return False

    monkeypatch.setattr(svc, "_set_rc_enabled", fake_set_rc)
    monkeypatch.setattr(svc, "_wait_for_usb_control", fake_wait_for_usb_control)

    ok = await svc._ensure_usb_control(timeout=0.01, retries=2)

    assert ok is False
    assert svc.status.motor_controller_ok is False
    assert svc.status.last_error == "usb_control_unavailable"
    # Should attempt initial disable plus forced retries
    assert attempts == [(False, False), (False, True), (False, True)]


@pytest.mark.asyncio
async def test_ensure_usb_control_succeeds_after_retry(monkeypatch):
    svc = RoboHATService()
    svc.serial_conn = _StubSerial()
    svc.running = True
    svc._rc_enabled = True
    svc._pending_rc_state = True
    attempts: list[tuple[bool, bool]] = []

    async def fake_set_rc(enabled: bool, *, force: bool = False) -> None:
        attempts.append((enabled, force))

    calls = 0

    async def fake_wait_for_usb_control(timeout: float = 0.75) -> bool:  # noqa: ARG001
        nonlocal calls
        calls += 1
        if calls < 2:
            return False
        svc._pending_rc_state = None
        svc._rc_enabled = False
        return True

    monkeypatch.setattr(svc, "_set_rc_enabled", fake_set_rc)
    monkeypatch.setattr(svc, "_wait_for_usb_control", fake_wait_for_usb_control)

    ok = await svc._ensure_usb_control(timeout=0.01, retries=2)

    assert ok is True
    assert svc._rc_enabled is False
    assert attempts == [(False, False), (False, True)]


@pytest.mark.asyncio
async def test_process_line_timeout_marks_rc_enabled():
    svc = RoboHATService()
    svc._rc_enabled = False

    svc._process_line("[USB] Timeout – back to RC mode: manual")

    assert svc._rc_enabled is True


@pytest.mark.asyncio
async def test_process_line_rc_disabled_marks_controller_ready():
    svc = RoboHATService()
    svc._rc_enabled = True
    svc.status.last_error = "usb_control_unavailable"

    svc._process_line("[USB] RC disabled – USB control")

    assert svc._rc_enabled is False
    assert svc.status.motor_controller_ok is True
    assert svc.status.last_watchdog_echo == "rc_disable_ack"
    assert svc.status.last_error is None


@pytest.mark.asyncio
async def test_process_line_status_payload_accepts_python_dict_repr():
    svc = RoboHATService()
    svc._rc_enabled = False

    svc._process_line("[STATUS] {'rc_enabled': False, 'encoder': 42, 'uptime_seconds': 12}")

    assert svc.status.motor_controller_ok is True
    assert svc.status.encoder_feedback_ok is True
    assert svc.status.uptime_seconds == 12
    assert svc.status.last_error is None


@pytest.mark.asyncio
async def test_process_line_invalid_pwm_marks_rc_enabled():
    svc = RoboHATService()
    svc._rc_enabled = False

    svc._process_line("[USB] Invalid command: pwm,1500,1500")

    assert svc._rc_enabled is True
    assert svc.status.motor_controller_ok is False
    assert "pwm" in (svc.status.last_error or "").lower()


@pytest.mark.asyncio
async def test_maintain_usb_control_reacquires_control(monkeypatch):
    svc = RoboHATService()
    svc.serial_conn = _StubSerial()
    svc._usb_control_requested = True
    svc._rc_enabled = True
    svc._pending_rc_state = None
    calls: list[tuple[bool, bool]] = []

    async def fake_set_rc(enabled: bool, *, force: bool = False) -> None:
        calls.append((enabled, force))

    monkeypatch.setattr(svc, "_set_rc_enabled", fake_set_rc)

    await svc._maintain_usb_control()

    assert calls == [(False, False)]


@pytest.mark.asyncio
async def test_maintain_usb_control_retries_stale_pending_disable(monkeypatch):
    svc = RoboHATService()
    svc.serial_conn = _StubSerial()
    svc._usb_control_requested = True
    svc._rc_enabled = True
    svc._pending_rc_state = False
    svc._pending_rc_since = time.monotonic() - 2.0
    calls: list[tuple[bool, bool]] = []

    async def fake_set_rc(enabled: bool, *, force: bool = False) -> None:
        calls.append((enabled, force))

    monkeypatch.setattr(svc, "_set_rc_enabled", fake_set_rc)

    await svc._maintain_usb_control()

    assert calls == [(False, True)]


@pytest.mark.asyncio
async def test_maintain_usb_control_sends_keepalive(monkeypatch):
    svc = RoboHATService()
    svc.serial_conn = _StubSerial()
    svc._usb_control_requested = True
    svc._rc_enabled = False
    svc._pending_rc_state = None
    sent: list[str] = []

    async def fake_send_line(line: str) -> bool:
        sent.append(line)
        return True

    monkeypatch.setattr(svc, "_send_line", fake_send_line)

    await svc._maintain_usb_control()

    assert sent == ["pwm,1500,1500"]


@pytest.mark.asyncio
async def test_probe_firmware_response_accepts_robohat_lines():
    svc = RoboHATService()
    svc.serial_conn = _ResponsiveSerial(["[USB] RC disabled – USB control"])
    svc._PROBE_STARTUP_SETTLE_SECONDS = 0.01

    ok = await svc._probe_firmware_response(timeout=0.1)

    assert ok is True
    assert svc.status.motor_controller_ok is True
    assert svc.status.last_error is None
    assert svc.serial_conn.writes == [b"rc=disable\n"]


@pytest.mark.asyncio
async def test_probe_firmware_response_accepts_delayed_startup_heartbeat():
    svc = RoboHATService()
    svc.serial_conn = _DelayedResponsiveSerial(["[RC] steer=1500 µs thr=1500 µs enc=0"], ready_after_checks=2)
    svc._PROBE_STARTUP_SETTLE_SECONDS = 0.12

    ok = await svc._probe_firmware_response(timeout=0.05)

    assert ok is True
    assert svc.status.last_watchdog_echo.startswith("[RC]")
    assert svc.status.last_error is None


@pytest.mark.asyncio
async def test_probe_firmware_response_rejects_silent_device():
    svc = RoboHATService()
    svc.serial_conn = _ResponsiveSerial([])
    svc._PROBE_STARTUP_SETTLE_SECONDS = 0.01

    ok = await svc._probe_firmware_response(timeout=0.05)

    assert ok is False
    assert svc.status.last_error == "robohat_unresponsive"


@pytest.mark.asyncio
async def test_process_line_legacy_timeout_marks_rc_enabled():
    svc = RoboHATService()
    svc._rc_enabled = False

    svc._process_line("[USB] Timeout → back to RC")

    assert svc._rc_enabled is True


@pytest.mark.asyncio
async def test_maintain_usb_control_respects_disabled_request(monkeypatch):
    svc = RoboHATService()
    svc.serial_conn = _StubSerial()
    svc._usb_control_requested = False
    svc._rc_enabled = True
    svc._pending_rc_state = None

    async def fail_set_rc(*_args, **_kwargs):
        raise AssertionError("_set_rc_enabled should not be called when USB control not requested")

    async def fail_send_line(*_args, **_kwargs):
        raise AssertionError("_send_line should not be called when USB control not requested")

    monkeypatch.setattr(svc, "_set_rc_enabled", fail_set_rc)
    monkeypatch.setattr(svc, "_send_line", fail_send_line)

    await svc._maintain_usb_control()


@pytest.mark.asyncio
async def test_maintain_usb_control_waits_for_pending_ack(monkeypatch):
    svc = RoboHATService()
    svc.serial_conn = _StubSerial()
    svc._usb_control_requested = True
    svc._rc_enabled = False
    svc._pending_rc_state = False
    svc._pending_rc_since = time.monotonic()

    async def fail_send_line(*_args, **_kwargs):
        raise AssertionError("Keep-alive should not be sent while RC disable pending")

    async def fail_set_rc(*_args, **_kwargs):
        raise AssertionError("RC disable retry should not trigger before timeout expires")

    monkeypatch.setattr(svc, "_send_line", fail_send_line)
    monkeypatch.setattr(svc, "_set_rc_enabled", fail_set_rc)

    await svc._maintain_usb_control()


@pytest.mark.asyncio
async def test_emergency_stop_fails_closed_without_usb_control(monkeypatch):
    svc = RoboHATService()
    svc.serial_conn = _StubSerial()
    svc.running = True
    svc._last_pwm = (1600, 1400)
    svc._last_pwm_at = 123.0
    svc.status.last_watchdog_echo = "previous"

    async def fake_ensure_usb_control(*, timeout: float = 0.75, retries: int = 1) -> bool:  # noqa: ARG001
        return False

    async def fail_send_line(*_args, **_kwargs):
        raise AssertionError("Emergency stop should not send commands without USB control")

    monkeypatch.setattr(svc, "_ensure_usb_control", fake_ensure_usb_control)
    monkeypatch.setattr(svc, "_send_line", fail_send_line)

    ok = await svc.emergency_stop()

    assert ok is False
    assert svc._last_pwm == (1600, 1400)
    assert svc._last_pwm_at == 123.0
    assert svc.status.last_watchdog_echo == "previous"


def test_candidate_serial_ports_prioritize_env_and_settings(monkeypatch, tmp_path):
    env_port = "/dev/env-robohat"
    profile_port = "/dev/profile-robohat"
    monkeypatch.setenv("ROBOHAT_PORT", env_port)

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.json").write_text(
        json.dumps({"hardware": {"robohat_port": profile_port}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("LAWN_SETTINGS_DIR", str(config_dir))

    class DummyPort:
        def __init__(self, device: str, description: str = "", manufacturer: str = "", product: str = "", vid: int | None = None):
            self.device = device
            self.description = description
            self.manufacturer = manufacturer
            self.product = product
            self.vid = vid

    fake_ports = [
        DummyPort(
            "/dev/match0",
            description="CircuitPython RoboHAT",
            manufacturer="LawnBerry",
            vid=0x2E8A,
        ),
        DummyPort(
            "/dev/other",
            description="u-blox GNSS",
            manufacturer="u-blox",
            vid=0x1546,
        ),
    ]

    monkeypatch.setattr(robohat_module, "list_ports", types.SimpleNamespace(comports=lambda: fake_ports))
    monkeypatch.setattr(robohat_module.glob, "glob", lambda pattern: [])
    monkeypatch.setattr(robohat_module.os.path, "exists", lambda _path: True)

    candidates = robohat_module._candidate_serial_ports()

    assert candidates[0] == env_port
    assert profile_port in candidates
    assert "/dev/match0" in candidates


@pytest.mark.asyncio
async def test_initialize_robohat_service_attempts_candidates(monkeypatch):
    attempts: list[str] = []

    async def fake_initialize(self):  # noqa: ANN001
        attempts.append(self.serial_port)
        if self.serial_port == "/dev/ttyACM1":
            self.status.serial_connected = True
            self.running = True
            return True
        return False

    monkeypatch.setattr(robohat_module, "_candidate_serial_ports", lambda explicit=None: ["/dev/ttyACM0", "/dev/ttyACM1"])
    monkeypatch.setattr(robohat_module.RoboHATService, "initialize", fake_initialize)
    monkeypatch.setattr(robohat_module, "robohat_service", None)

    ok = await robohat_module.initialize_robohat_service()

    assert ok is True
    assert attempts == ["/dev/ttyACM0", "/dev/ttyACM1"]
    assert robohat_module.robohat_service is not None
    assert robohat_module.robohat_service.serial_port == "/dev/ttyACM1"
