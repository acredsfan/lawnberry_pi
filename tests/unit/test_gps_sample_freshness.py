from datetime import UTC, datetime

import pytest

from backend.src.models.sensor_data import GpsReading, SensorData
from backend.src.services.localization_service import LocalizationService


@pytest.mark.asyncio
async def test_cached_gps_sample_does_not_refresh_last_fix():
    svc = LocalizationService(alignment_file=None)
    ts = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)

    await svc.update(
        SensorData(
            gps=GpsReading(
                latitude=39.0,
                longitude=-84.0,
                accuracy=0.05,
                timestamp=ts,
                sample_id=1,
            )
        )
    )
    first_fix = svc.last_gps_fix

    await svc.update(
        SensorData(
            gps=GpsReading(
                latitude=39.0,
                longitude=-84.0,
                accuracy=0.05,
                timestamp=ts,
                sample_id=1,
                cached=True,
            )
        )
    )

    assert svc.last_gps_fix == first_fix


@pytest.mark.asyncio
async def test_new_gps_sample_refreshes_last_fix():
    svc = LocalizationService(alignment_file=None)
    ts = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)

    await svc.update(
        SensorData(gps=GpsReading(latitude=39.0, longitude=-84.0, sample_id=1, timestamp=ts))
    )
    first_fix = svc.last_gps_fix

    await svc.update(
        SensorData(gps=GpsReading(latitude=39.0001, longitude=-84.0, sample_id=2, timestamp=ts))
    )

    assert svc.last_gps_fix is not None
    assert first_fix is not None
    assert svc.last_gps_fix >= first_fix

