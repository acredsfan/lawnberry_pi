import logging
import time
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..core.state_manager import AppState
from ..models.sensor_data import SensorData
from ..utils.battery import voltage_to_soc

logger = logging.getLogger(__name__)

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
        self._last_position: Dict[str, Any] = {}
        self._gps_warm_done = False

    async def initialize_sensors(self):
        """Initialize the sensor manager."""
        async with _get_sensor_init_lock():
            if self.app_state.sensor_manager is not None:
                return

            from ..services.sensor_manager import SensorManager
            from ..models.hardware_config import GPSType
            from ..models.sensor_data import GpsMode
            import os

            # Determine GPS Mode
            gps_mode = GpsMode.NEO8M_UART
            ntrip_enabled = False
            hw_cfg = self.app_state.hardware_config
            
            if hw_cfg and getattr(hw_cfg, "gps_type", None) in {GPSType.ZED_F9P_USB, GPSType.ZED_F9P_UART}:
                gps_mode = GpsMode.F9P_USB if getattr(hw_cfg, "gps_type", None) == GPSType.ZED_F9P_USB else GpsMode.F9P_UART
                ntrip_enabled = bool(getattr(hw_cfg, "gps_ntrip_enabled", False))

            # Hint GPS device
            if not os.environ.get("GPS_DEVICE"):
                for candidate in ["/dev/ttyACM1", "/dev/ttyACM0", "/dev/ttyAMA0", "/dev/ttyUSB0"]:
                    if os.path.exists(candidate):
                        os.environ["GPS_DEVICE"] = candidate
                        break

            # Config extraction
            tof_cfg = None
            power_cfg = None
            battery_cfg = None
            imu_cfg = None
            if hw_cfg:
                try:
                    tc = getattr(hw_cfg, "tof_config", None)
                    if tc: tof_cfg = tc.model_dump()

                    pc = getattr(hw_cfg, "ina3221_config", None)
                    victron = getattr(hw_cfg, "victron_config", None)
                    if pc or victron:
                        power_cfg = {}
                        if pc: power_cfg["ina3221"] = pc.model_dump(exclude_none=True)
                        if victron: power_cfg["victron"] = victron.model_dump(exclude_none=True)

                    battery_cfg = getattr(hw_cfg, "battery_config", None)

                    # IMU port from hardware config (overrides env var BNO085_PORT if set)
                    imu_port = getattr(hw_cfg, "imu_port", None)
                    if imu_port:
                        imu_cfg = {"port": imu_port}
                except Exception:
                    pass

            manager = SensorManager(gps_mode=gps_mode, tof_config=tof_cfg, power_config=power_cfg, battery_config=battery_cfg, imu_config=imu_cfg)
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
                    except Exception as e:
                        logger.error(f"Failed to start NTRIP: {e}")

    async def get_telemetry(self, sim_mode: bool = False) -> Dict[str, Any]:
        """Generate telemetry data from hardware or simulation."""
        
        if self.app_state.sensor_manager is None:
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

    def _format_telemetry(self, data: Optional[SensorData], sim_mode: bool) -> Dict[str, Any]:
        """Format sensor data into the standard telemetry dictionary."""
        
        # Default/Fallback values
        battery_pct = 0.0
        batt_v = 0.0
        
        if data and data.power:
            batt_v = float(data.power.battery_voltage or 0.0)
            batt_cur = getattr(data.power, "battery_current", 0.0)
            bc = getattr(getattr(self.app_state, "hardware_config", None), "battery_config", None)
            soc = voltage_to_soc(
                batt_v,
                min_voltage=bc.min_voltage if bc else None,
                max_voltage=bc.max_voltage if bc else None,
                chemistry=bc.chemistry if bc else "lifepo4",
            ) or 0.0
            if isinstance(batt_cur, (int, float)) and batt_cur > 0.05:
                battery_pct = min(99.0, soc)
            else:
                battery_pct = soc

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
        
        # Update cache and fill missing values
        for k, v in current_pos.items():
            if v is not None:
                self._last_position[k] = v
            elif k in self._last_position:
                current_pos[k] = self._last_position[k]

        # IMU Calibration
        cal_status = getattr(imu, "calibration_status", None)
        cal_score = 0
        if cal_status:
             _cal_map = {"fully_calibrated": 3, "calibrated": 3, "calibrating": 2, "partial": 2, "unknown": 1}
             cal_score = _cal_map.get(cal_status, 1)

        telemetry = {
            "source": "hardware" if data else "simulated",
            "simulated": sim_mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "battery": {
                "percentage": battery_pct,
                "voltage": batt_v
            },
            "position": current_pos,
            "imu": {
                "roll": getattr(imu, "roll", None),
                "pitch": getattr(imu, "pitch", None),
                "yaw": getattr(imu, "yaw", None),
                "gyro_z": getattr(imu, "gyro_z", None),
                "calibration": cal_score,
                "calibration_status": cal_status,
            },
            "velocity": {
                "linear": {"x": current_pos.get("speed"), "y": None, "z": None},
                "angular": {"x": None, "y": None, "z": getattr(imu, "gyro_z", None)},
            },
            "motor_status": "idle", # Placeholder
            "safety_state": "emergency_stop" if self.app_state.safety_state.get("emergency_stop_active") else "nominal",
            "uptime_seconds": time.time(),
        }

        # Add fused navigation heading from NavigationService (IMU yaw preferred, GPS COG fallback)
        try:
            from .navigation_service import NavigationService
            nav_svc = NavigationService.get_instance()
            nav_state = getattr(nav_svc, "navigation_state", None)
            if nav_state is not None:
                telemetry["nav_heading"] = getattr(nav_state, "heading", None)
        except Exception:
            telemetry["nav_heading"] = None
        
        # Add Power Data
        if data and data.power:
            telemetry["power"] = self._format_power_data(data.power)
            
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

    def _format_power_data(self, power_data: Any) -> Dict[str, Any]:
        """Format power specific data."""
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
            "timestamp": getattr(power_data, "timestamp", None),
        }

    def _format_tof(self, tof_data: Any) -> Dict[str, Any]:
        if not tof_data:
            return {"distance_mm": None, "range_status": None, "signal_strength": None}
        return {
            "distance_mm": getattr(tof_data, "distance", None),
            "range_status": getattr(tof_data, "range_status", None),
            "signal_strength": getattr(tof_data, "signal_strength", None),
        }

# Singleton
telemetry_service = TelemetryService()
