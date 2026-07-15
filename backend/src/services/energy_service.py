"""Canonical battery state, reserve policy, and mission energy forecasts.

The service consumes only the cached reading owned by ``SensorManager``.  It
never opens or polls power hardware, so admission, runtime policy, history, and
the API all reason from the same timestamped sample and SOC algorithm.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..models import Position
from ..models.hardware_config import BatteryConfig
from ..nav.path_planner import PathPlanner
from ..utils.battery import voltage_current_to_soc


class EnergyReturnRequired(RuntimeError):
    """Raised after a safe hold when a mowing mission must return to dock."""


class EnergyCriticalStop(RuntimeError):
    """Raised after a hard safety stop when energy is below the critical floor."""


class EnergyState(BaseModel):
    available: bool
    fresh: bool
    reason_code: str | None = None
    source: str | None = None
    sampled_at: datetime | None = None
    sample_age_seconds: float | None = None
    voltage: float | None = None
    battery_current: float | None = None
    battery_power: float | None = None
    solar_current: float | None = None
    solar_power: float | None = None
    load_power: float | None = None
    soc_percent: float | None = None
    capacity_wh: float
    remaining_wh: float | None = None
    return_reserve_percent: float
    return_reserve_wh: float
    critical_soc_percent: float
    charging_confirmed: bool = False


class MissionEnergyForecast(BaseModel):
    mission_distance_m: float = 0.0
    return_distance_m: float = 0.0
    mission_energy_wh: float = 0.0
    return_energy_wh: float = 0.0
    reserve_floor_wh: float = 0.0
    required_energy_wh: float = 0.0
    is_return_mission: bool = False
    assumptions: list[str] = Field(default_factory=list)


class RuntimeEnergyPolicy(BaseModel):
    action: Literal["continue", "continue_return", "return_home", "stop", "critical_stop"]
    reason_code: str
    state: EnergyState


class EnergyService:
    """Single owner of energy truth and conservative mission reserve policy."""

    def __init__(
        self,
        *,
        sensor_manager_provider: Callable[[], Any],
        battery_config: BatteryConfig,
        position_provider: Callable[[], Any] | None = None,
        home_position_provider: Callable[[], Any] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._sensor_manager_provider = sensor_manager_provider
        self._battery = battery_config
        self._position_provider = position_provider
        self._home_position_provider = home_position_provider
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    @staticmethod
    def _as_position(value: Any) -> Position | None:
        if value is None:
            return None
        latitude = getattr(value, "latitude", getattr(value, "lat", None))
        longitude = getattr(value, "longitude", getattr(value, "lon", None))
        if latitude is None or longitude is None:
            return None
        try:
            return Position(latitude=float(latitude), longitude=float(longitude))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_return_mission(mission: Any) -> bool:
        name = str(getattr(mission, "name", "")).strip().lower()
        if name == "return to home":
            return True
        waypoints = list(getattr(mission, "waypoints", []) or [])
        if not waypoints:
            return False
        leg_type = getattr(waypoints[-1], "leg_type", None)
        return getattr(leg_type, "value", leg_type) == "dock"

    def _cached_power_reading(self) -> Any | None:
        try:
            sensor_manager = self._sensor_manager_provider()
            power_interface = getattr(sensor_manager, "power", None)
            return getattr(power_interface, "last_reading", None)
        except Exception:
            return None

    def current_state(self) -> EnergyState:
        reading = self._cached_power_reading()
        reserve_wh = self._battery.capacity_wh * self._battery.return_reserve_percent / 100.0
        common = {
            "capacity_wh": self._battery.capacity_wh,
            "return_reserve_percent": self._battery.return_reserve_percent,
            "return_reserve_wh": reserve_wh,
            "critical_soc_percent": self._battery.critical_soc_percent,
        }
        if reading is None:
            return EnergyState(
                available=False,
                fresh=False,
                reason_code="POWER_SAMPLE_UNAVAILABLE",
                **common,
            )

        sampled_at = getattr(reading, "timestamp", None)
        if sampled_at is not None and sampled_at.tzinfo is None:
            sampled_at = sampled_at.replace(tzinfo=UTC)
        age_seconds = None
        if sampled_at is not None:
            age_seconds = max(0.0, (self._now_provider() - sampled_at).total_seconds())
        source = getattr(reading, "battery_source", None)
        voltage = getattr(reading, "battery_voltage", None)
        available = voltage is not None and bool(source)
        fresh = bool(
            available
            and age_seconds is not None
            and age_seconds <= self._battery.max_sample_age_seconds
        )
        battery_current = getattr(reading, "battery_current", None)
        solar_current = getattr(reading, "solar_current", None)
        soc = voltage_current_to_soc(
            voltage,
            battery_current_a=battery_current,
            solar_current_a=solar_current,
            chemistry=self._battery.chemistry,
            min_voltage=self._battery.min_voltage,
            max_voltage=self._battery.max_voltage,
        )
        remaining_wh = None if soc is None else self._battery.capacity_wh * soc / 100.0
        solar_power = getattr(reading, "solar_power", None)
        load_power = getattr(reading, "load_power", None)
        if load_power is None:
            load_current = getattr(reading, "load_current", None)
            if load_current is not None and voltage is not None:
                load_power = float(load_current) * float(voltage)
        reason_code = None
        if not available:
            reason_code = "POWER_SOURCE_OR_VOLTAGE_UNAVAILABLE"
        elif not fresh:
            reason_code = "POWER_SAMPLE_STALE"
        return EnergyState(
            available=available,
            fresh=fresh,
            reason_code=reason_code,
            source=source,
            sampled_at=sampled_at,
            sample_age_seconds=age_seconds,
            voltage=voltage,
            battery_current=battery_current,
            battery_power=getattr(reading, "battery_power", None),
            solar_current=solar_current,
            solar_power=solar_power,
            load_power=load_power,
            soc_percent=soc,
            remaining_wh=remaining_wh,
            charging_confirmed=bool(
                battery_current is not None
                and float(battery_current) > 0.05
                and solar_power is not None
                and float(solar_power) > 0.5
            ),
            **common,
        )

    def estimate_mission(self, mission: Any) -> MissionEnergyForecast:
        waypoints = list(getattr(mission, "waypoints", []) or [])
        current = self._as_position(
            self._position_provider() if self._position_provider is not None else None
        )
        home = self._as_position(
            self._home_position_provider() if self._home_position_provider is not None else None
        )
        points = [
            Position(latitude=float(wp.lat), longitude=float(wp.lon))
            for wp in waypoints
        ]
        mission_distance = 0.0
        previous = current
        for point in points:
            if previous is not None:
                mission_distance += PathPlanner.calculate_distance(previous, point)
            previous = point
        return_distance = 0.0
        if previous is not None and home is not None and not self._is_return_mission(mission):
            return_distance = PathPlanner.calculate_distance(previous, home)

        fixed = self._battery.mission_fixed_overhead_wh
        rate = self._battery.mission_wh_per_meter
        mission_energy = fixed + mission_distance * rate
        return_energy = 0.0 if return_distance <= 0 else fixed + return_distance * rate
        reserve_floor = self._battery.capacity_wh * self._battery.return_reserve_percent / 100.0
        is_return = self._is_return_mission(mission)
        if is_return:
            required = mission_energy
        else:
            required = mission_energy + max(reserve_floor, return_energy)
        assumptions = [
            f"{rate:.3f} Wh per path metre",
            f"{fixed:.2f} Wh fixed mission overhead",
        ]
        if current is None:
            assumptions.append("current position unavailable; first-leg distance omitted")
        if home is None and not is_return:
            assumptions.append("home position unavailable; configured reserve floor used")
        return MissionEnergyForecast(
            mission_distance_m=mission_distance,
            return_distance_m=return_distance,
            mission_energy_wh=mission_energy,
            return_energy_wh=return_energy,
            reserve_floor_wh=reserve_floor,
            required_energy_wh=required,
            is_return_mission=is_return,
            assumptions=assumptions,
        )

    def admission_snapshot(self, *, mission: Any) -> dict[str, Any]:
        state = self.current_state()
        forecast = self.estimate_mission(mission)
        reasons: list[str] = []
        if not state.available:
            reasons.append(state.reason_code or "ENERGY_STATE_UNAVAILABLE")
        elif not state.fresh:
            reasons.append(state.reason_code or "POWER_SAMPLE_STALE")
        if state.soc_percent is None:
            reasons.append("SOC_UNAVAILABLE")
        elif state.soc_percent <= state.critical_soc_percent:
            reasons.append("SOC_AT_OR_BELOW_CRITICAL")
        if (
            state.remaining_wh is None
            or state.remaining_wh < forecast.required_energy_wh
        ):
            reasons.append("MISSION_RETURN_RESERVE_INSUFFICIENT")
        return {
            "admitted": not reasons,
            "reason_codes": list(dict.fromkeys(reasons)),
            "state": state.model_dump(mode="json"),
            "forecast": forecast.model_dump(mode="json"),
        }

    def _live_return_energy_wh(self) -> float:
        current = self._as_position(
            self._position_provider() if self._position_provider is not None else None
        )
        home = self._as_position(
            self._home_position_provider() if self._home_position_provider is not None else None
        )
        if current is None or home is None:
            return 0.0
        distance = PathPlanner.calculate_distance(current, home)
        return (
            self._battery.mission_fixed_overhead_wh
            + distance * self._battery.mission_wh_per_meter
        )

    def runtime_policy(self, mission: Any) -> RuntimeEnergyPolicy:
        state = self.current_state()
        if not state.available or not state.fresh or state.soc_percent is None:
            return RuntimeEnergyPolicy(
                action="stop",
                reason_code=state.reason_code or "ENERGY_STATE_UNAVAILABLE",
                state=state,
            )
        if state.soc_percent <= state.critical_soc_percent:
            return RuntimeEnergyPolicy(
                action="critical_stop",
                reason_code="ENERGY_CRITICAL_STOP",
                state=state,
            )
        if self._is_return_mission(mission):
            return RuntimeEnergyPolicy(
                action="continue_return",
                reason_code="RETURN_MISSION_ABOVE_CRITICAL_FLOOR",
                state=state,
            )
        live_return_floor = max(state.return_reserve_wh, self._live_return_energy_wh())
        if state.remaining_wh is None or state.remaining_wh <= live_return_floor:
            return RuntimeEnergyPolicy(
                action="return_home",
                reason_code="ENERGY_RETURN_RESERVE_REACHED",
                state=state,
            )
        return RuntimeEnergyPolicy(
            action="continue",
            reason_code="ENERGY_RESERVE_AVAILABLE",
            state=state,
        )


__all__ = [
    "EnergyCriticalStop",
    "EnergyReturnRequired",
    "EnergyService",
    "EnergyState",
    "MissionEnergyForecast",
    "RuntimeEnergyPolicy",
]
