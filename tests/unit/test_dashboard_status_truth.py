from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.src.api.routers.sensors import dashboard_status


class _Hub:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def get_cached_telemetry(self) -> dict:
        return self.payload


class _EnergyService:
    def current_state(self) -> SimpleNamespace:
        return SimpleNamespace(
            soc_percent=72.5,
            available=True,
            fresh=True,
            charging_confirmed=False,
            source="ina3221",
            sample_age_seconds=0.4,
            reason_code=None,
        )


@pytest.mark.asyncio
async def test_dashboard_status_uses_canonical_cached_runtime_truth() -> None:
    observed_at = datetime.now(UTC)
    runtime = SimpleNamespace(
        websocket_hub=_Hub(
            {
                "source": "hardware",
                "sample": {
                    "source": "hardware",
                    "observed_at": observed_at.isoformat(),
                    "age_seconds": 0.2,
                    "fresh": True,
                },
                "position": {"latitude": 39.1, "longitude": -84.2, "accuracy": 0.03},
            }
        ),
        navigation=SimpleNamespace(
            navigation_state=SimpleNamespace(navigation_mode=SimpleNamespace(value="auto"))
        ),
        safety_state={"emergency_stop_active": False},
        blade_state={"active": True},
        energy_service=_EnergyService(),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=runtime)))

    status = await dashboard_status(request)

    assert status.source == "hardware"
    assert status.fresh is True
    assert status.sample_age_seconds == pytest.approx(0.2)
    assert status.last_updated == observed_at
    assert status.battery_percentage == pytest.approx(72.5)
    assert status.power_source == "ina3221"
    assert status.power_fresh is True
    assert status.navigation_state == "auto"
    assert status.position is not None
    assert status.position.latitude == pytest.approx(39.1)
    assert status.blade_active is True


@pytest.mark.asyncio
async def test_dashboard_status_keeps_missing_values_unknown(monkeypatch) -> None:
    from backend.src.api.routers import sensors

    monkeypatch.setattr(sensors, "websocket_hub", _Hub({"source": "unavailable"}))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    status = await dashboard_status(request)

    assert status.source == "unavailable"
    assert status.fresh is False
    assert status.battery_percentage is None
    assert status.position is None
    assert status.navigation_state == "UNKNOWN"
    assert status.power_mode == "UNKNOWN"
    assert status.last_updated is None
    assert status.reason_code == "POWER_SERVICE_UNAVAILABLE"
