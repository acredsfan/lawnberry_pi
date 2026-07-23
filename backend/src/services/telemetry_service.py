import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from ..core.state_manager import AppState
from ..models.sensor_data import SensorData
from ..nav.geoutils import body_offset_to_north_east, offset_lat_lon
from ..utils.battery import voltage_current_to_soc

logger = logging.getLogger(__name__)

_service_start_time: float = time.time()

# Module-level lock: guarantees only one sensor init across all TelemetryService
# instances, even when multiple are created before the first finishes.
_sensor_init_lock: asyncio.Lock | None = None


def _get_sensor_init_lock() -> asyncio.Lock:
    """Lazily create the init lock bound to the current event loop."""
    global _sensor_init_lock
    if _sensor_init_lock is None:
        _sensor_init_lock = asyncio.Lock()
    return _sensor_init_lock


class TelemetryService:
    def __init__(self):
        self.app_state = AppState.get_instance()
        self._last_position: dict[str, Any] = {}
        self._last_position_observed_at: datetime | None = None
        self._gps_warm_done = False

    @staticmethod
    def _numeric(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @staticmethod
    def _as_utc(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @classmethod
    def _sample_metadata(
        cls,
        observed_at: Any,
        *,
        source: str,
        freshness_seconds: float = 2.0,
    ) -> dict[str, Any]:
        timestamp = cls._as_utc(observed_at)
        age_seconds = (
            max(0.0, (datetime.now(UTC) - timestamp).total_seconds())
            if timestamp is not None
            else None
        )
        return {
            "source": source,
            "observed_at": timestamp.isoformat() if timestamp is not None else None,
            "age_seconds": age_seconds,
            "fresh": bool(age_seconds is not None and age_seconds <= freshness_seconds),
        }

    def _get_navigation_heading(self) -> float | None:
        try:
            from .navigation_service import NavigationService

            nav_svc = NavigationService.get_instance()
            nav_state = getattr(nav_svc, "navigation_state", None)
            heading = getattr(nav_state, "heading", None) if nav_state is not None else None
            return float(heading) if isinstance(heading, (int, float)) else None
        except Exception:
            return None

    def _get_canonical_pose(self) -> Any | None:
        try:
            from .navigation_service import NavigationService

            nav_svc = NavigationService.get_instance()
            localization = getattr(nav_svc, "_localization", None)
            canonical_pose = getattr(localization, "canonical_pose", None)
            if callable(canonical_pose):
                return canonical_pose()
        except Exception:
            return None
        return None

    def _get_motor_status(self) -> str:
        try:
            from . import mission_service as _ms_mod
            mission = getattr(_ms_mod, "_mission_service_instance", None)
            if mission is None:
                raise LookupError("no mission instance")
            status = getattr(mission, "status", None) or getattr(mission, "_status", None)
            if status is not None:
                status_str = str(status.value if hasattr(status, "value") else status).lower()
                # Normalize known mission states to dashboard-friendly strings
                _map = {
                    "running": "mowing",
                    "active": "mowing",
                    "mowing": "mowing",
                    "returning": "returning",
                    "paused": "paused",
                    "emergency_stop": "emergency_stop",
                    "idle": "idle",
                    "completed": "idle",
                    "failed": "idle",
                    "cancelled": "idle",
                }
                return _map.get(status_str, status_str)
        except Exception:
            pass
        try:
            # Check safety state for emergency stop override
            if self.app_state.safety_state.get("emergency_stop_active"):
                return "emergency_stop"
        except Exception:
            pass
        return "idle"

    def _apply_position_offsets(
        self,
        position: dict[str, Any],
        *,
        nav_heading: float | None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
        latitude = self._numeric(position.get("latitude"))
        longitude = self._numeric(position.get("longitude"))
        if latitude is None or longitude is None:
            return position, None, None

        hardware = getattr(self.app_state, "hardware_config", None)
        antenna_forward_m = float(getattr(hardware, "gps_antenna_offset_forward_m", 0.0) or 0.0)
        antenna_right_m = float(getattr(hardware, "gps_antenna_offset_right_m", 0.0) or 0.0)

        if antenna_forward_m == 0.0 and antenna_right_m == 0.0:
            return position, None, None

        corrected = dict(position)
        raw_position = dict(position)
        applied: list[str] = []
        pending: list[str] = []

        if antenna_forward_m != 0.0 or antenna_right_m != 0.0:
            if nav_heading is None:
                pending.append("gps_antenna_offset_heading_unavailable")
            else:
                antenna_north_m, antenna_east_m = body_offset_to_north_east(
                    forward_m=antenna_forward_m,
                    right_m=antenna_right_m,
                    heading_degrees=nav_heading,
                )
                latitude, longitude = offset_lat_lon(
                    latitude,
                    longitude,
                    north_m=-antenna_north_m,
                    east_m=-antenna_east_m,
                )
                applied.append("gps_antenna_offset")

        corrected["latitude"] = latitude
        corrected["longitude"] = longitude
        correction = {
            "applied": applied,
            "pending": pending,
            "antenna_offset_forward_m": antenna_forward_m,
            "antenna_offset_right_m": antenna_right_m,
        }
        return corrected, raw_position, correction

    async def initialize_sensors(self):
        """Initialize the sensor manager."""
        async with _get_sensor_init_lock():
            if self.app_state.sensor_manager is not None:
                return

            import os

            from ..models.hardware_config import GPSType
            from ..models.sensor_data import GpsMode
            from ..services.sensor_manager import SensorManager

            # Determine GPS Mode
            gps_mode = GpsMode.NEO8M_UART
            ntrip_enabled = False
            hw_cfg = self.app_state.hardware_config

            if hw_cfg and getattr(hw_cfg, "gps_type", None) in {
                GPSType.ZED_F9P_USB,
                GPSType.ZED_F9P_UART,
            }:
                gps_mode = (
                    GpsMode.F9P_USB
                    if getattr(hw_cfg, "gps_type", None) == GPSType.ZED_F9P_USB
                    else GpsMode.F9P_UART
                )
                ntrip_enabled = bool(getattr(hw_cfg, "gps_ntrip_enabled", False))

            # Hint GPS device — prefer explicit config, fall back to port scan
            gps_usb_device: str | None = None
            if hw_cfg:
                _usb = getattr(hw_cfg, "gps_usb_device", None)
                if isinstance(_usb, str) and _usb:
                    gps_usb_device = _usb
            if gps_usb_device:
                os.environ["GPS_DEVICE"] = gps_usb_device
            elif not os.environ.get("GPS_DEVICE"):
                for candidate in ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyAMA0", "/dev/ttyUSB0"]:
                    if os.path.exists(candidate):
                        os.environ["GPS_DEVICE"] = candidate
                        break

            # Config extraction
            tof_cfg = None
            power_cfg = None
            battery_cfg = None
            imu_cfg = None
            environmental_cfg = None
            if hw_cfg:
                try:
                    tc = getattr(hw_cfg, "tof_config", None)
                    if tc:
                        tof_cfg = tc.model_dump()

                    pc = getattr(hw_cfg, "ina3221_config", None)
                    victron = getattr(hw_cfg, "victron_config", None)
                    if pc or victron:
                        power_cfg = {}
                        if pc:
                            power_cfg["ina3221"] = pc.model_dump(exclude_none=True)
                        if victron:
                            power_cfg["victron"] = victron.model_dump(exclude_none=True)

                    battery_cfg = getattr(hw_cfg, "battery_config", None)

                    bme280 = getattr(hw_cfg, "bme280_config", None)
                    if bme280:
                        environmental_cfg = bme280.model_dump(exclude_none=True)

                    # IMU port/transport from hardware config (port overrides env
                    # var BNO085_PORT if set)
                    imu_port = getattr(hw_cfg, "imu_port", None)
                    imu_mode = getattr(hw_cfg, "imu_mode", None)
                    if imu_port or imu_mode:
                        imu_cfg = {}
                        if imu_port:
                            imu_cfg["port"] = imu_port
                        if imu_mode:
                            imu_cfg["mode"] = imu_mode
                except Exception:
                    pass

            manager = SensorManager(
                gps_mode=gps_mode,
                tof_config=tof_cfg,
                power_config=power_cfg,
                battery_config=battery_cfg,
                imu_config=imu_cfg,
                environmental_config=environmental_cfg,
                gps_usb_device=gps_usb_device,
            )
            await manager.initialize()
            self.app_state.sensor_manager = manager
            self.app_state.ntrip_forwarder = None
            # Sync the websocket_hub's cached reference so the health probe finds it.
            try:
                from ..services.websocket_hub import websocket_hub as _hub  # type: ignore

                _hub._sensor_manager = manager
            except Exception:
                pass

            if ntrip_enabled and os.getenv("SIM_MODE", "0") != "1":
                from ..services.ntrip_client import NtripForwarder

                forwarder = NtripForwarder.from_environment(gps_mode=gps_mode)
                if forwarder:
                    try:
                        await forwarder.start()
                        self.app_state.ntrip_forwarder = forwarder
                        gps_iface = getattr(manager, "gps", None)
                        if gps_iface is not None:
                            gps_iface._ntrip_forwarder = forwarder
                    except Exception as e:
                        logger.error(f"Failed to start NTRIP: {e}")

    async def get_telemetry(self, sim_mode: bool = False) -> dict[str, Any]:
        """Generate telemetry data from hardware or simulation."""

        if not sim_mode and self.app_state.sensor_manager is None:
            try:
                await self.initialize_sensors()
            except Exception as e:
                logger.warning(f"Lazy sensor init failed: {e}")

        manager = self.app_state.sensor_manager
        data = None

        if manager and getattr(manager, "initialized", False) and not sim_mode:
            try:
                # One-time warmup
                if not self._gps_warm_done:
                    await self._warmup_gps(manager)

                data = await manager.read_all_sensors()
                await self._update_navigation(data)
            except Exception as e:
                logger.warning(f"Sensor read failed: {e}")

        # If we have data, format it. If not (or if sim_mode), use simulation/fallback logic.
        # For now, we'll assume if data is None, we fall back to sim/defaults.

        return self._format_telemetry(data, sim_mode)

    async def _warmup_gps(self, manager):
        try:
            for _ in range(3):
                warm = await manager.read_all_sensors()
                if getattr(warm, "gps", None) and getattr(warm.gps, "latitude", None) is not None:
                    break
                await asyncio.sleep(0.2)
        finally:
            self._gps_warm_done = True

    async def _update_navigation(self, data: SensorData):
        try:
            # Local import to avoid circular dependency
            from ..services.navigation_service import NavigationService

            nav = NavigationService.get_instance()
            await nav.update_navigation_state(data)
        except Exception as e:
            logger.debug(f"Navigation update failed: {e}")

    def _format_telemetry(self, data: SensorData | None, sim_mode: bool) -> dict[str, Any]:
        """Format sensor data into the standard telemetry dictionary."""

        battery_pct: float | None = None
        batt_v: float | None = None

        if data and data.power:
            batt_v = self._numeric(data.power.battery_voltage)
            batt_cur = getattr(data.power, "battery_current", None)
            solar_cur = getattr(data.power, "solar_current", None)
            bc = getattr(getattr(self.app_state, "hardware_config", None), "battery_config", None)
            if batt_v is not None:
                battery_pct = voltage_current_to_soc(
                    batt_v,
                    battery_current_a=batt_cur,
                    solar_current_a=solar_cur,
                    min_voltage=bc.min_voltage if bc else None,
                    max_voltage=bc.max_voltage if bc else None,
                    chemistry=bc.chemistry if bc else "lifepo4",
                )

        # Position handling with caching
        pos = data.gps if data else None
        imu = data.imu if data else None

        # Merge with cache
        current_pos = {
            "latitude": getattr(pos, "latitude", None),
            "longitude": getattr(pos, "longitude", None),
            "altitude": getattr(pos, "altitude", None),
            "accuracy": getattr(pos, "accuracy", None),
            "gps_mode": getattr(pos, "mode", None),
            "satellites": getattr(pos, "satellites", None),
            "speed": getattr(pos, "speed", None),
            "heading": getattr(pos, "heading", None),
            "rtk_status": getattr(pos, "rtk_status", None),
            "hdop": getattr(pos, "hdop", None),
        }

        live_position = any(value is not None for value in current_pos.values())
        if live_position:
            self._last_position_observed_at = self._as_utc(getattr(pos, "timestamp", None))
        used_cached_position = False

        # Update cache and fill missing values while retaining the original
        # sample timestamp so consumers can see that a displayed fix is stale.
        for k, v in current_pos.items():
            if v is not None:
                self._last_position[k] = v
            elif k in self._last_position:
                current_pos[k] = self._last_position[k]
                used_cached_position = True

        nav_heading = self._get_navigation_heading()
        nav_heading_source = "localization"
        # Fall back to raw IMU yaw when localization hasn't established heading yet.
        # Only use IMU fallback when sensor is fully calibrated — not for safety/control,
        # but display layer must not be dark before first GPS COG alignment.
        if nav_heading is None and imu is not None:
            imu_cal = getattr(imu, "calibration_status", None)
            if imu_cal in {"fully_calibrated", "calibrated", "imu_calibrated"}:
                nav_heading = getattr(imu, "yaw", None)
                if nav_heading is not None:
                    nav_heading_source = "imu_raw"
        canonical_pose = self._get_canonical_pose()
        if canonical_pose is not None:
            pose_payload = canonical_pose.to_dict()
            body = pose_payload.get("body_center")
            antenna = pose_payload.get("antenna_position")
            if body is not None:
                current_pos.update(body)
                current_pos["position_role"] = "body_center"
            elif antenna is not None:
                current_pos.update(antenna)
                current_pos["position_role"] = "antenna"
            raw_position = antenna
            position_correction = {
                "applied": ["gps_antenna_offset"]
                if pose_payload.get("antenna_correction_state") == "applied"
                else [],
                "pending": ["gps_antenna_offset_heading_unavailable"]
                if pose_payload.get("antenna_correction_state") == "pending_heading"
                else [],
                "antenna_offset_forward_m": getattr(
                    getattr(self.app_state, "hardware_config", None),
                    "gps_antenna_offset_forward_m",
                    0.0,
                ),
                "antenna_offset_right_m": getattr(
                    getattr(self.app_state, "hardware_config", None),
                    "gps_antenna_offset_right_m",
                    0.0,
                ),
                "antenna_correction_state": pose_payload.get("antenna_correction_state"),
                "position_source": pose_payload.get("position_source"),
            }
            nav_heading = pose_payload.get("heading_deg")
            nav_heading_source = pose_payload.get("heading_source") or "localization"
        else:
            current_pos, raw_position, position_correction = self._apply_position_offsets(
                current_pos,
                nav_heading=nav_heading,
            )

        # IMU Calibration
        cal_status = getattr(imu, "calibration_status", None)
        cal_score: int | None = None
        if cal_status:
            _cal_map = {
                "fully_calibrated": 3,
                "calibrated": 3,
                "calibrating": 2,
                "partial": 2,
                "unknown": 1,
            }
            cal_score = _cal_map.get(cal_status, 1)

        source = "simulated" if sim_mode else "hardware" if data is not None else "unavailable"
        telemetry = {
            "source": source,
            "simulated": sim_mode,
            "timestamp": datetime.now(UTC).isoformat(),
            "sample": self._sample_metadata(
                getattr(data, "timestamp", None),
                source=source,
            ),
            "battery": {"percentage": battery_pct, "voltage": batt_v},
            "position": {
                **current_pos,
                "sample": self._sample_metadata(
                    getattr(self, "_last_position_observed_at", None),
                    source=(
                        "cached"
                        if used_cached_position or not live_position
                        else "gps"
                    )
                    if self._last_position
                    else "unavailable",
                ),
            },
            "imu": {
                "roll": getattr(imu, "roll", None),
                "pitch": getattr(imu, "pitch", None),
                "yaw": getattr(imu, "yaw", None),
                "gyro_z": getattr(imu, "gyro_z", None),
                "calibration": cal_score,
                "calibration_status": cal_status,
            },
            "velocity": {
                "linear": {
                    "x": current_pos.get("speed"),
                    "y": 0.0 if data is not None else None,
                    "z": 0.0 if data is not None else None,
                },
                "angular": {
                    "x": getattr(imu, "gyro_x", None),
                    "y": getattr(imu, "gyro_y", None),
                    "z": getattr(imu, "gyro_z", None),
                },
            },
            "motor_status": self._get_motor_status(),
            "safety_state": "emergency_stop"
            if self.app_state.safety_state.get("emergency_stop_active")
            else "nominal",
            "uptime_seconds": time.time() - _service_start_time,
        }

        # Add fused navigation heading from NavigationService (IMU yaw preferred, GPS COG fallback)
        telemetry["nav_heading"] = nav_heading
        telemetry["nav_heading_source"] = nav_heading_source
        if canonical_pose is not None:
            telemetry["canonical_pose"] = canonical_pose.to_dict()
        if raw_position is not None:
            telemetry["raw_position"] = raw_position
        if position_correction is not None:
            telemetry["position_correction"] = position_correction

        # Mission executor per-tick debug state (non-empty only during active navigation)
        try:
            from .navigation_service import NavigationService as _NavSvc
            _nav_dbg = _NavSvc.get_instance().nav_debug
            if _nav_dbg:
                telemetry["nav_debug"] = _nav_dbg
        except Exception:
            pass

        # Add Power Data — always present so WebSocket hub always broadcasts the topic
        if data and data.power:
            telemetry["power"] = self._format_power_data(data.power)
            telemetry["power_status"] = "ok"
        else:
            telemetry["power"] = self._empty_power_payload()
            telemetry["power_status"] = "unavailable"

        # Add Environmental Data
        if data and data.environmental:
            telemetry["environmental"] = {
                "temperature_c": getattr(data.environmental, "temperature", None),
                "humidity_percent": getattr(data.environmental, "humidity", None),
                "pressure_hpa": getattr(data.environmental, "pressure", None),
                "altitude_m": getattr(data.environmental, "altitude", None),
            }

        # Add ToF Data
        if data and (data.tof_left or data.tof_right):
            telemetry["tof"] = {
                "left": self._format_tof(data.tof_left),
                "right": self._format_tof(data.tof_right),
            }

        return telemetry

    def _format_power_data(self, power_data: Any) -> dict[str, Any]:
        """Format power specific data."""
        metadata = self._sample_metadata(
            getattr(power_data, "timestamp", None),
            source=(
                getattr(power_data, "battery_source", None)
                or getattr(power_data, "solar_source", None)
                or "hardware"
            ),
        )
        return {
            "battery_voltage": getattr(power_data, "battery_voltage", None),
            "battery_current": getattr(power_data, "battery_current", None),
            "battery_power": getattr(power_data, "battery_power", None),
            "solar_voltage": getattr(power_data, "solar_voltage", None),
            "solar_current": getattr(power_data, "solar_current", None),
            "solar_power": getattr(power_data, "solar_power", None),
            "solar_yield_today_wh": getattr(power_data, "solar_yield_today_wh", None),
            "battery_consumed_today_wh": getattr(power_data, "battery_consumed_today_wh", None),
            "load_current": getattr(power_data, "load_current", None),
            "timestamp": metadata["observed_at"],
            "source": metadata["source"],
            "sample_age_seconds": metadata["age_seconds"],
            "fresh": metadata["fresh"],
        }

    def _empty_power_payload(self) -> dict[str, Any]:
        """Return an all-null power payload when sensor data is unavailable."""
        return {
            "battery_voltage": None,
            "battery_current": None,
            "battery_power": None,
            "solar_voltage": None,
            "solar_current": None,
            "solar_power": None,
            "solar_yield_today_wh": None,
            "battery_consumed_today_wh": None,
            "load_current": None,
            "timestamp": None,
            "source": "unavailable",
            "sample_age_seconds": None,
            "fresh": False,
        }

    def _format_tof(self, tof_data: Any) -> dict[str, Any]:
        if not tof_data:
            return {"distance_mm": None, "range_status": None, "signal_strength": None}
        return {
            "distance_mm": getattr(tof_data, "distance", None),
            "range_status": getattr(tof_data, "range_status", None),
            "signal_strength": getattr(tof_data, "signal_strength", None),
        }


# Singleton
telemetry_service = TelemetryService()
