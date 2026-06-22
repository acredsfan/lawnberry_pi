import sys
import types

import pytest

from backend.src.drivers.sensors import vl53l0x_driver
from backend.src.drivers.sensors.vl53l0x_driver import VL53L0XDriver
from backend.src.models import SensorStatus
from backend.src.services.sensor_manager import SensorCoordinator, ToFSensorInterface


@pytest.mark.asyncio
async def test_vl53l0x_pair_init_failure_releases_xshut_pins_high(monkeypatch):
    """Regression: failed pair init must not leave a ToF sensor held in reset."""
    gpio_writes: list[tuple[int, int]] = []

    async def fake_provider():
        return "fake"

    def fake_gpio_set(pin: int, value: int) -> None:
        gpio_writes.append((pin, value))

    async def no_sleep(_seconds: float) -> None:
        return None

    class FailingSensor:
        def __init__(self, _i2c):
            raise OSError("i2c address assignment failed")

    fake_adafruit = types.SimpleNamespace(VL53L0X=FailingSensor)
    fake_board = types.SimpleNamespace(SCL=object(), SDA=object())
    fake_busio = types.SimpleNamespace(I2C=lambda _scl, _sda: object())

    monkeypatch.setattr(vl53l0x_driver, "_pair_initialized", False)
    monkeypatch.setattr(vl53l0x_driver, "_adafruit_i2c", None)
    monkeypatch.setattr(vl53l0x_driver, "_ensure_gpio_provider", fake_provider)
    monkeypatch.setattr(vl53l0x_driver, "_gpio_set", fake_gpio_set)
    monkeypatch.setattr(vl53l0x_driver.asyncio, "sleep", no_sleep)
    monkeypatch.setitem(sys.modules, "adafruit_vl53l0x", fake_adafruit)
    monkeypatch.setitem(sys.modules, "board", fake_board)
    monkeypatch.setitem(sys.modules, "busio", fake_busio)

    ok = await vl53l0x_driver.ensure_pair_addressing(22, 23, 0x30)

    assert ok is False
    assert gpio_writes[:3] == [(22, 0), (23, 0), (23, 1)]
    assert gpio_writes[-2:] == [(22, 1), (23, 1)]
    assert gpio_writes.count((22, 1)) == vl53l0x_driver._XSHUT_PAIR_INIT_ATTEMPTS
    assert gpio_writes.count((23, 1)) == vl53l0x_driver._XSHUT_PAIR_INIT_ATTEMPTS * 2
    assert vl53l0x_driver._pair_initialized is False


def test_tof_interface_passes_timing_budget_to_both_drivers():
    interface = ToFSensorInterface(
        SensorCoordinator(),
        tof_config={
            "bus": 1,
            "left_address": 0x29,
            "right_address": 0x30,
            "left_shutdown_gpio": 22,
            "right_shutdown_gpio": 23,
            "ranging_mode": "best_accuracy",
            "timing_budget_us": 66000,
        },
    )

    assert interface._left._timing_budget_us == 66000
    assert interface._right._timing_budget_us == 66000


@pytest.mark.asyncio
async def test_tof_interface_reports_error_when_driver_backend_missing():
    """Regression: no hardware backend must not be reported as ONLINE."""
    interface = ToFSensorInterface.__new__(ToFSensorInterface)
    interface.coordinator = SensorCoordinator()
    interface.left_reading = None
    interface.right_reading = None
    interface.status = SensorStatus.OFFLINE

    class MissingBackendDriver:
        initialized = False
        running = False
        _driver_backend = None
        _last_error = "No VL53L0X Python binding available"
        _xshut_gpio = None

        async def initialize(self):
            self.initialized = False

        async def start(self):
            self.running = False

    interface._left = MissingBackendDriver()
    interface._right = MissingBackendDriver()

    ok = await interface.initialize()

    assert ok is False
    assert interface.status == SensorStatus.ERROR


@pytest.mark.asyncio
async def test_reinit_failure_preserves_existing_backend(monkeypatch):
    """No-target streaks must not downgrade a previously working ToF backend."""
    driver = VL53L0XDriver("left")
    old_backend = object()
    driver._driver = old_backend
    driver._driver_backend = "adafruit"
    driver.initialized = True
    driver.running = True
    driver._fail_count = 3
    driver._last_init_attempt = None

    async def fail_adafruit(_driver):
        _driver._last_error = "temporary i2c failure"
        return False

    async def fail_pololu(_driver):
        _driver._driver_backend = None
        _driver._last_error = "No VL53L0X Python binding available"
        return False

    monkeypatch.setenv("SIM_MODE", "0")
    monkeypatch.setattr(vl53l0x_driver, "_try_init_adafruit", fail_adafruit)
    monkeypatch.setattr(vl53l0x_driver, "_try_init_pololu_like", fail_pololu)

    await vl53l0x_driver._reinit_if_needed(driver)

    assert driver._driver is old_backend
    assert driver._driver_backend == "adafruit"
    assert driver.initialized is True
    assert driver.running is True
    assert "preserving existing backend" in (driver._last_error or "")
