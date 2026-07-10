from datetime import UTC, datetime, timedelta

import pytest

from backend.src.models.sensor_data import GpsReading
from backend.src.services.stationary_rtk_averaging import (
    collect_live_stationary_rtk_average,
    compute_stationary_rtk_average,
)


def _sample(
    index: int,
    *,
    lat_offset: float = 0.0,
    lon_offset: float = 0.0,
    rtk_status: str = "RTK_FIXED",
    cached: bool = False,
    speed: float = 0.0,
    accuracy: float = 0.02,
) -> GpsReading:
    return GpsReading(
        latitude=40.0 + lat_offset,
        longitude=-75.0 + lon_offset,
        altitude=200.0,
        accuracy=accuracy,
        speed=speed,
        rtk_status=rtk_status,
        cached=cached,
        sample_id=index,
        timestamp=datetime(2026, 6, 24, tzinfo=UTC) + timedelta(milliseconds=200 * index),
    )


def test_stationary_rtk_average_accepts_uncached_rtk_fixed_samples():
    samples = [_sample(i, lat_offset=i * 1e-9, lon_offset=-i * 1e-9) for i in range(20)]

    result = compute_stationary_rtk_average(samples, min_samples=20)

    assert result.accepted is True
    assert result.averaged_antenna_coordinate is not None
    assert result.averaged_antenna_coordinate["latitude"] == pytest.approx(40.0000000095)
    assert result.accepted_count == 20
    assert result.creates_global_offset is False
    assert result.rmse_m is not None and result.rmse_m < 0.01


def test_stationary_rtk_average_rejects_cached_moving_and_non_rtk_samples():
    samples = [
        *[_sample(i) for i in range(6)],
        _sample(6, cached=True),
        _sample(7, speed=0.2),
        _sample(8, rtk_status="RTK_FLOAT"),
        _sample(9, accuracy=0.4),
    ]

    result = compute_stationary_rtk_average(samples, min_samples=6)

    assert result.accepted is True
    assert result.accepted_count == 6
    assert result.rejected_reasons["cached"] == 1
    assert result.rejected_reasons["moving"] == 1
    assert result.rejected_reasons["not_rtk_fixed"] == 1
    assert result.rejected_reasons["accuracy"] == 1


def test_stationary_rtk_average_rejects_duplicate_sample_identity():
    samples = [_sample(index) for index in range(5)]
    duplicate = samples[-1].model_copy(
        update={"latitude": samples[-1].latitude + 0.000001}
    )

    result = compute_stationary_rtk_average(
        [*samples, duplicate],
        min_samples=6,
    )

    assert result.accepted is False
    assert result.accepted_count == 5
    assert result.rejected_reasons["duplicate_sample"] == 1


def test_stationary_rtk_average_rejects_spatial_outlier():
    samples = [_sample(i, lat_offset=i * 1e-9) for i in range(20)]
    samples.append(_sample(20, lat_offset=0.0001, lon_offset=0.0001))

    result = compute_stationary_rtk_average(samples, min_samples=20)

    assert result.accepted is True
    assert result.accepted_count == 20
    assert result.rejected_reasons["outlier"] == 1
    assert result.rmse_m is not None and result.rmse_m < 0.01


@pytest.mark.asyncio
async def test_live_collector_observes_owner_cache_and_counts_unique_samples_only():
    samples = [_sample(index, lat_offset=index * 1e-9) for index in range(3)]

    class OwnerCache:
        def __init__(self):
            self.index = 0

        @property
        def last_reading(self):
            sample = samples[min(self.index, len(samples) - 1)]
            self.index += 1
            return sample

        async def read_gps(self):
            raise AssertionError("collector must not read the GPS serial owner")

    result = await collect_live_stationary_rtk_average(
        OwnerCache(),
        duration_s=0.2,
        interval_s=0.01,
        min_samples=3,
    )

    assert result.accepted is True
    assert result.accepted_count == 3
