"""Contract: the navigation tick wall-time metric is exposed on /metrics."""

import pytest

from backend.src.api.metrics import metrics
from backend.src.core.observability import observability
from backend.src.models import GpsReading, SensorData
from backend.src.services.navigation_service import NavigationService


@pytest.mark.asyncio
async def test_navigation_tick_duration_appears_in_metrics_endpoint():
    observability.reset_events_for_testing()
    nav = NavigationService()

    await nav.update_navigation_state(
        SensorData(gps=GpsReading(latitude=1.0, longitude=1.0, accuracy=0.5))
    )

    body = metrics().body.decode()

    assert "lawnberry_timer_navigation_tick_duration_count 1" in body
    assert "lawnberry_timer_navigation_tick_duration_avg_ms" in body
    assert "lawnberry_timer_navigation_tick_duration_min_ms" in body
    assert "lawnberry_timer_navigation_tick_duration_max_ms" in body
