from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.src.models.hardware_config import BatteryConfig
from backend.src.models.mission import (
    Mission,
    MissionLegType,
    MissionLifecycleStatus,
    MissionStatus,
    MissionWaypoint,
)
from backend.src.models.navigation_state import Position
from backend.src.models.sensor_data import PowerReading
from backend.src.services.energy_service import (
    EnergyCriticalStop,
    EnergyReturnRequired,
    EnergyService,
)
from backend.src.services.mission_executor import MissionExecutor

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _mission(*, name: str = "Mow", leg_type: MissionLegType = MissionLegType.MOW) -> Mission:
    return Mission(
        name=name,
        created_at=NOW.isoformat(),
        waypoints=[
            MissionWaypoint(
                lat=40.0001,
                lon=-75.0,
                leg_type=leg_type,
                blade_on=leg_type == MissionLegType.MOW,
            )
        ],
    )


def _service(
    voltage: float,
    *,
    sampled_at: datetime = NOW,
    source: str | None = "ina3221",
    **config_overrides,
) -> EnergyService:
    reading = PowerReading(
        battery_voltage=voltage,
        battery_current=-1.0,
        battery_power=-voltage,
        solar_current=0.0,
        solar_power=0.0,
        battery_source=source,
        timestamp=sampled_at,
    )
    sensor_manager = SimpleNamespace(power=SimpleNamespace(last_reading=reading))
    config = BatteryConfig(capacity_wh=100.0, **config_overrides)
    return EnergyService(
        sensor_manager_provider=lambda: sensor_manager,
        battery_config=config,
        position_provider=lambda: Position(latitude=40.0, longitude=-75.0),
        home_position_provider=lambda: Position(latitude=40.0, longitude=-75.0),
        now_provider=lambda: NOW,
    )


def test_current_state_owns_source_freshness_and_soc() -> None:
    state = _service(13.2).current_state()

    assert state.available is True
    assert state.fresh is True
    assert state.source == "ina3221"
    assert state.soc_percent == 70.0
    assert state.remaining_wh == 70.0
    assert state.return_reserve_wh == 20.0


def test_stale_or_unproven_source_fails_admission_closed() -> None:
    stale = _service(13.2, sampled_at=NOW - timedelta(seconds=16))
    missing_source = _service(13.2, source=None)

    stale_snapshot = stale.admission_snapshot(mission=_mission())
    source_snapshot = missing_source.admission_snapshot(mission=_mission())

    assert stale_snapshot["admitted"] is False
    assert "POWER_SAMPLE_STALE" in stale_snapshot["reason_codes"]
    assert source_snapshot["admitted"] is False
    assert "POWER_SOURCE_OR_VOLTAGE_UNAVAILABLE" in source_snapshot["reason_codes"]


def test_mission_forecast_preserves_return_reserve() -> None:
    service = _service(13.2, mission_wh_per_meter=5.0)

    snapshot = service.admission_snapshot(mission=_mission())

    assert snapshot["admitted"] is False
    assert "MISSION_RETURN_RESERVE_INSUFFICIENT" in snapshot["reason_codes"]
    assert snapshot["forecast"]["required_energy_wh"] > snapshot["state"]["remaining_wh"]


def test_runtime_returns_before_critical_and_hard_stops_at_critical() -> None:
    reserve_policy = _service(12.88).runtime_policy(_mission())
    critical_policy = _service(12.0).runtime_policy(_mission())
    return_policy = _service(12.88).runtime_policy(
        _mission(name="Return to home", leg_type=MissionLegType.DOCK)
    )

    assert reserve_policy.action == "return_home"
    assert critical_policy.action == "critical_stop"
    assert return_policy.action == "continue_return"


class _Gateway:
    def __init__(self) -> None:
        self.drive_calls: list[tuple[float, float]] = []
        self.blade_calls: list[bool] = []
        self.emergency_reasons: list[str] = []

    def is_emergency_active(self) -> bool:
        return False

    async def dispatch_drive_speeds(self, left: float, right: float) -> bool:
        self.drive_calls.append((left, right))
        return True

    async def dispatch_blade(self, active: bool) -> bool:
        self.blade_calls.append(active)
        return True

    async def trigger_emergency(self, trigger) -> object:
        self.emergency_reasons.append(trigger.reason)
        return object()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "error_type", "emergency"),
    [
        ("return_home", EnergyReturnRequired, False),
        ("critical_stop", EnergyCriticalStop, True),
    ],
)
async def test_executor_enters_hold_for_energy_policy(action, error_type, emergency) -> None:
    gateway = _Gateway()
    localization = SimpleNamespace(
        current_position=Position(latitude=40.0, longitude=-75.0, accuracy=0.1),
        heading=0.0,
        dead_reckoning_active=False,
        last_gps_fix=NOW,
    )
    policy = SimpleNamespace(action=action, reason_code=f"TEST_{action.upper()}")
    executor = MissionExecutor(
        localization=localization,
        gateway=gateway,
        energy_policy_provider=lambda _mission: policy,
    )
    mission = _mission()
    mission_service = SimpleNamespace(
        mission_statuses={mission.id: SimpleNamespace(status="running")}
    )

    with pytest.raises(error_type):
        await executor.go_to_waypoint(mission, mission.waypoints[0], mission_service)

    assert gateway.drive_calls[-1] == (0.0, 0.0)
    assert gateway.blade_calls[-1] is False
    assert bool(gateway.emergency_reasons) is emergency


@pytest.mark.asyncio
async def test_mission_service_schedules_canonical_return_after_energy_diversion(
    monkeypatch,
) -> None:
    from backend.src.services.mission_service import MissionService

    service = MissionService(navigation_service=SimpleNamespace())
    mission = _mission()
    service.missions[mission.id] = mission
    service.mission_statuses[mission.id] = MissionStatus(
        mission_id=mission.id,
        status=MissionLifecycleStatus.RUNNING,
        total_waypoints=1,
    )
    service._mission_terminal_events[mission.id] = asyncio.Event()
    monkeypatch.setattr(service, "_persist_mission_status", lambda _mission_id: None)
    scheduled: list[str] = []

    def capture_background(coroutine, *, name: str) -> None:
        scheduled.append(name)
        coroutine.close()

    monkeypatch.setattr(service, "_spawn_background", capture_background)

    class _FailedTask:
        @staticmethod
        def result() -> None:
            raise EnergyReturnRequired("ENERGY_RETURN_RESERVE_REACHED")

    service._mission_completed_callback(mission.id)(_FailedTask())
    await asyncio.sleep(0)

    assert service.mission_statuses[mission.id].status == MissionLifecycleStatus.FAILED
    assert scheduled == [f"energy-return:{mission.id}"]
