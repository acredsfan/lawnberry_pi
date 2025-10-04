import pytest

from backend.src.drivers.motor.robohat_rp2040 import RoboHATRP2040Driver


@pytest.mark.asyncio
async def test_robohat_driver_sim_mode_initialize_and_send_drive(monkeypatch):
    monkeypatch.setenv("SIM_MODE", "1")
    drv = RoboHATRP2040Driver()
    await drv.initialize()
    assert drv.initialized is True
    assert drv.status.serial_connected is False

    await drv.start()
    ok = await drv.send_drive(0.5, -0.25)
    assert ok is True

    health = await drv.health_check()
    assert health["driver"] == "robohat_rp2040"
    assert health["serial_connected"] is False

    await drv.stop()


@pytest.mark.asyncio
async def test_robohat_driver_emergency_stop_sim(monkeypatch):
    monkeypatch.setenv("SIM_MODE", "1")
    drv = RoboHATRP2040Driver()
    await drv.initialize()
    ok = await drv.emergency_stop()
    assert ok is True


class _FakeSerial:
    def __init__(self, lines: list[bytes]):
        self._lines = lines
        self.is_open = True
        self.written = []

    def write(self, payload: bytes) -> int:  # pragma: no cover - tiny wrapper
        self.written.append(payload)
        return len(payload)

    def flush(self) -> None:  # pragma: no cover
        return

    def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        return b""


@pytest.mark.asyncio
async def test_robohat_driver_ack_handling_success(monkeypatch):
    # Force non-SIM path but replace serial with fake
    monkeypatch.delenv("SIM_MODE", raising=False)
    drv = RoboHATRP2040Driver()
    drv._ser = _FakeSerial([b"{\"status\":\"ok\"}\n", b"ACK\n"])  # two ACKs for two commands

    # Pretend as if serial is open and initialized
    drv.initialized = True
    drv.status.serial_connected = True

    ok = await drv.send_drive(1.0, -1.0)
    assert ok is True

    ok2 = await drv.emergency_stop()
    assert ok2 is True


@pytest.mark.asyncio
async def test_robohat_driver_ack_handling_timeout(monkeypatch):
    monkeypatch.delenv("SIM_MODE", raising=False)
    drv = RoboHATRP2040Driver()
    # No lines -> no ACK
    drv._ser = _FakeSerial([])
    drv.initialized = True
    drv.status.serial_connected = True

    ok = await drv.send_drive(0.0, 0.0)
    assert ok is False
    assert "No ACK" in (drv.status.last_error or "")
