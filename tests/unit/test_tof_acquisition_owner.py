import asyncio

import pytest
from pydantic import ValidationError

from backend.src.models.sensor_data import SensorStatus
from backend.src.services.sensor_manager import SensorCoordinator, ToFSensorInterface


class FakeToFDriver:
    def __init__(self, distance: int = 500, *, fail: bool = False):
        self.distance = distance
        self.fail = fail
        self.calls = 0
        self.initialized = False
        self.running = False
        self._driver_backend = "fake"
        self._last_error = None
        self._xshut_gpio = None

    async def initialize(self):
        self.initialized = True

    async def start(self):
        self.running = True

    async def stop(self):
        self.running = False

    async def read_distance_mm(self):
        self.calls += 1
        if self.fail:
            raise OSError("simulated I2C failure")
        return self.distance


def _interface(left: FakeToFDriver, right: FakeToFDriver) -> ToFSensorInterface:
    interface = ToFSensorInterface(SensorCoordinator(), tof_config={"timing_budget_us": 1})
    interface._left = left
    interface._right = right
    return interface


@pytest.mark.asyncio
async def test_consumers_only_read_owner_cache_and_samples_are_immutable():
    left = FakeToFDriver(400)
    right = FakeToFDriver(600)
    interface = _interface(left, right)
    assert await interface.initialize()
    await asyncio.sleep(0.02)
    await interface.shutdown()
    owner_calls = (left.calls, right.calls)

    first = await interface.read_tof_sensors()
    second = await interface.read_tof_sensors()

    assert (left.calls, right.calls) == owner_calls
    assert first[0] is not second[0]
    assert first[0].sample_id is not None
    assert first[0].monotonic_received_s is not None
    with pytest.raises(ValidationError):
        first[0].distance = 1.0


@pytest.mark.asyncio
async def test_owner_tracks_bounded_per_sensor_failure_rate():
    interface = _interface(FakeToFDriver(fail=True), FakeToFDriver(700))
    interface.status = SensorStatus.ONLINE

    for _ in range(5):
        await interface._acquire_pair_once()

    health = interface.health_snapshot()
    assert health["left"]["window_samples"] == 5
    assert health["left"]["failure_rate"] == 1.0
    assert health["left"]["sample_age_s"] is None
    assert health["right"]["failure_rate"] == 0.0
    assert health["right"]["sample_id"] is not None


@pytest.mark.asyncio
async def test_cached_sample_keeps_original_timestamp_between_consumers():
    interface = _interface(FakeToFDriver(450), FakeToFDriver(550))
    interface.status = SensorStatus.ONLINE
    await interface._acquire_pair_once()

    first = await interface.read_tof_sensors()
    await asyncio.sleep(0)
    second = await interface.read_tof_sensors()

    assert first[0].sample_id == second[0].sample_id
    assert first[0].monotonic_received_s == second[0].monotonic_received_s
