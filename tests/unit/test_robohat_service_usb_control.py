import time

import pytest

from backend.src.services.robohat_service import RoboHATService


class _StubSerial:
    def __init__(self):
        self.is_open = True
        self.in_waiting = 0


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
