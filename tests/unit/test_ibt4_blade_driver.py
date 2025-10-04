import pytest
import asyncio

from backend.src.drivers.blade.ibt4_gpio import IBT4BladeDriver, _GPIOAdapter


class DummyGPIO(_GPIOAdapter):
    def __init__(self, in1: int, in2: int):
        super().__init__(in1, in2)
        self.setup_called = False
        self.cleanup_called = False

    def setup(self) -> None:
        self.setup_called = True
        super().setup()

    def cleanup(self) -> None:
        self.cleanup_called = True
        super().cleanup()


@pytest.mark.asyncio
async def test_ibt4_initialize_and_toggle_in_sim_mode(monkeypatch):
    # Force SIM_MODE for test safety
    monkeypatch.setenv("SIM_MODE", "1")

    gpio = DummyGPIO(24, 25)
    drv = IBT4BladeDriver(config={"pins": {"in1": 24, "in2": 25}}, gpio_adapter=gpio)

    await drv.initialize()
    assert drv.initialized

    await drv.start()
    assert drv.running

    # Should be off by default
    hc = await drv.health_check()
    assert not hc["active"]

    # Toggle on
    ok = await drv.set_active(True)
    assert ok
    hc = await drv.health_check()
    assert hc["active"]

    # E-stop blocks activation
    await drv.set_estop(True)
    ok = await drv.set_active(True)
    assert not ok

    # Stop driver
    await drv.stop()
    assert not (await drv.health_check())["active"]
