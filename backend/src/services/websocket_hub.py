import asyncio
import json
import logging
import os
import time
import inspect
import math
from datetime import datetime, timezone
from typing import Any, Optional, Mapping

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder

from ..models.sensor_data import GpsMode
from ..models.hardware_config import GPSType
from ..services.ntrip_client import NtripForwarder
from ..services.weather_service import weather_service
from ..services.remote_access_service import (
    STATUS_PATH as REMOTE_ACCESS_STATUS_PATH,
    RemoteAccessService,
    RemoteAccessStatus,
)

# We need to import _remote_access_settings from somewhere or pass it in.
# In rest.py it was a global. We should probably make WebSocketHub self-contained or
# pass dependencies in `__init__` or `bind_app_state`.
# For now, I will assume we can access it via app_state or similar, or I'll need to refactor how it's accessed.
# Actually, looking at rest.py, `_remote_access_settings` is a global loaded from disk.
# I'll duplicate the loading logic here or better, make it a property of the hub that loads it?
# Or maybe just import the service and load it when needed.

# Also `_safety_state` is a global in rest.py.
# This is tricky. Globals are bad.
# I should probably move `_safety_state` to a service or a shared module.
# For now, I'll define it here as well, but this effectively duplicates state if not careful.
# Wait, `rest.py` uses `_safety_state` in `_generate_telemetry`.
# If I move `_generate_telemetry` to `WebSocketHub`, I need access to `_safety_state`.
# I should probably create a `SafetyService` or similar.
# But to avoid over-engineering right now, I might just have to pass it in or keep it in a shared place.
# Let's look at where `_safety_state` is defined. Line 2255 in rest.py.
# It's just a dict.

# I'll create a `backend/src/core/state.py` to hold these shared globals if they are truly global.
# Or I can put them in `backend/src/services/safety_service.py`?
# Let's check if there is a safety service.
# `backend/src/safety/safety_triggers.py` exists.

# Let's create `backend/src/core/globals.py` for now to hold these shared states to avoid circular imports and duplication.

logger = logging.getLogger(__name__)

class WebSocketHub:
    def __init__(self):
        self.clients: dict[str, WebSocket] = {}
        self.subscriptions: dict[str, set[str]] = {}  # topic -> client_ids
        self.telemetry_cadence_hz = 5.0
        self._telemetry_task: Optional[asyncio.Task] = None
        # Hardware integration
        self._sensor_manager = None  # lazy init to avoid hardware deps on CI
        self._gps_warm_done = False
        # Cache last known position to smooth fields missing on alternating NMEA sentences
        self._last_position: dict[str, Any] = {}
        # Optional link back to FastAPI app state so other endpoints can reuse services
        self._app_state: Any | None = None
        # Prevent concurrent calibration runs
        self._calibration_lock = asyncio.Lock()
        # Optional NTRIP bridge for RTK corrections
        self._ntrip_forwarder: NtripForwarder | None = None
        # Simulation helpers for deterministic synthetic telemetry
        self._sim_cycle: int = 0

    def bind_app_state(self, state: Any) -> None:
        """Expose app.state to the hub so lazily-created services can be shared."""
        self._app_state = state
        if state is not None:
            try:
                state.websocket_hub = self
            except Exception:
                pass

    async def _ensure_sensor_manager(self):
        """Lazy-create the SensorManager with appropriate GPS configuration."""
        if self._sensor_manager is not None:
            return self._sensor_manager

        from ..services.sensor_manager import SensorManager  # type: ignore

        gps_mode = GpsMode.NEO8M_UART
        ntrip_enabled = False
        if self._app_state is not None:
            try:
                hw_cfg = getattr(self._app_state, "hardware_config", None)
            except Exception:
                hw_cfg = None
            if hw_cfg and getattr(hw_cfg, "gps_type", None) in {GPSType.ZED_F9P_USB, GPSType.ZED_F9P_UART}:
                gps_mode = GpsMode.F9P_USB if getattr(hw_cfg, "gps_type", None) == GPSType.ZED_F9P_USB else GpsMode.F9P_UART
                ntrip_enabled = bool(getattr(hw_cfg, "gps_ntrip_enabled", False))

        # Hint GPS device if a common device node is present
        try:
            if not os.environ.get("GPS_DEVICE"):
                candidates = [
                    "/dev/ttyACM1",
                    "/dev/ttyACM0",
                    "/dev/ttyAMA0",
                    "/dev/ttyUSB0",
                ]
                for candidate in candidates:
                    if os.path.exists(candidate):
                        os.environ["GPS_DEVICE"] = candidate
                        break
        except Exception:
            pass

        logger.info(
            "Initializing SensorManager with GPS mode %s (NTRIP %s)",
            gps_mode.value,
            "enabled" if ntrip_enabled else "disabled",
        )

        # Extract typed ToF configuration from app.state.hardware_config
        tof_cfg: dict | None = None
        power_cfg: dict | None = None
        if self._app_state and getattr(self._app_state, "hardware_config", None):
            try:
                hwc = self._app_state.hardware_config
                tc = getattr(hwc, "tof_config", None)
                if tc is not None:
                    # Convert to dict for SensorManager
                    tof_cfg = tc.model_dump()
                power_cfg = {}
                pc = getattr(hwc, "ina3221_config", None)
                if pc is not None:
                    power_cfg["ina3221"] = pc.model_dump(exclude_none=True)
                victron = getattr(hwc, "victron_config", None)
                if victron is not None:
                    power_cfg["victron"] = victron.model_dump(exclude_none=True)
                if not power_cfg:
                    power_cfg = None
            except Exception:
                tof_cfg = None
                power_cfg = None

        self._sensor_manager = SensorManager(gps_mode=gps_mode, tof_config=tof_cfg, power_config=power_cfg)
        await self._sensor_manager.initialize()
        if ntrip_enabled:
            await self._ensure_ntrip_forwarder(gps_mode)
        if self._app_state is not None:
            try:
                setattr(self._app_state, "sensor_manager", self._sensor_manager)
            except Exception:
                pass
        return self._sensor_manager

    async def _ensure_ntrip_forwarder(self, gps_mode: GpsMode) -> None:
        """Start the NTRIP client when hardware requests RTK corrections."""
        if self._ntrip_forwarder is not None:
            return
        if os.getenv("SIM_MODE", "0") == "1":
            return
        forwarder = NtripForwarder.from_environment(gps_mode=gps_mode)
        if forwarder is None:
            logger.warning("NTRIP forwarding requested but configuration is incomplete; set NTRIP_* env vars")
            return
        try:
            await forwarder.start()
        except Exception as exc:
            logger.error("Failed to start NTRIP forwarder: %s", exc)
            return
        self._ntrip_forwarder = forwarder

    async def connect(self, websocket: WebSocket, client_id: str):
        subprotocol = None
        header_value = None
        try:
            headers = getattr(websocket, "headers", None)
            if headers is not None:
                getter = getattr(headers, "get", None)
                if callable(getter):
                    value = getter("sec-websocket-protocol")
                    if inspect.isawaitable(value):
                        value = await value
                    header_value = value
                elif isinstance(headers, Mapping):
                    header_value = headers.get("sec-websocket-protocol")
        except Exception:
            header_value = None
        if header_value:
            protocols = [token.strip() for token in str(header_value).split(",") if token.strip()]
            if protocols:
                subprotocol = protocols[0]

        await websocket.accept(subprotocol=subprotocol)
        self.clients[client_id] = websocket
        await websocket.send_text(json.dumps({
            "event": "connection.established",
            "client_id": client_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))
        
    def disconnect(self, client_id: str):
        if client_id in self.clients:
            del self.clients[client_id]
        # Remove from all subscriptions
        for _topic, subscribers in self.subscriptions.items():
            subscribers.discard(client_id)
            
    async def subscribe(self, client_id: str, topic: str):
        if topic not in self.subscriptions:
            self.subscriptions[topic] = set()
        self.subscriptions[topic].add(client_id)
        
        # Send confirmation
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps({
                "event": "subscription.confirmed",
                "topic": topic,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
    async def unsubscribe(self, client_id: str, topic: str):
        if topic in self.subscriptions:
            self.subscriptions[topic].discard(client_id)
            
        # Send confirmation
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps({
                "event": "unsubscription.confirmed", 
                "topic": topic,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
    async def set_cadence(self, client_id: str, cadence_hz: float):
        # Clamp cadence between 1-10 Hz
        cadence_hz = max(1.0, min(10.0, cadence_hz))
        self.telemetry_cadence_hz = cadence_hz
        
        # Send confirmation
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps({
                "event": "cadence.updated",
                "cadence_hz": cadence_hz,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
    async def broadcast_to_topic(self, topic: str, data: dict):
        if topic not in self.subscriptions:
            return
        
        # Use FastAPI's encoder to safely handle datetimes and Pydantic models
        payload = {
            "event": "telemetry.data",
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        message = json.dumps(jsonable_encoder(payload), default=str)
        
        disconnected_clients = []
        for client_id in self.subscriptions[topic]:
            if client_id in self.clients:
                try:
                    await self.clients[client_id].send_text(message)
                except Exception:
                    disconnected_clients.append(client_id)
                    
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)
            
    async def start_telemetry_loop(self):
        if self._telemetry_task is not None:
            return
        self._telemetry_task = asyncio.create_task(self._telemetry_loop())
        
    async def stop_telemetry_loop(self):
        if self._telemetry_task:
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass
            self._telemetry_task = None
            
    async def _telemetry_loop(self):
        while True:
            try:
                telemetry_data = await self._generate_telemetry()
                # Broadcast to topic-specific channels immediately
                await self._broadcast_telemetry_topics(telemetry_data)
                
                # Wait based on cadence
                await asyncio.sleep(1.0 / self.telemetry_cadence_hz)
                
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)
                
    async def _broadcast_telemetry_topics(self, telemetry_data: dict):
        """Broadcast telemetry data to appropriate topics."""
        # Extract data for specific topics
        if "battery" in telemetry_data or "power" in telemetry_data:
            power_payload = telemetry_data.get("power") if isinstance(telemetry_data.get("power"), dict) else None
            message: dict[str, Any] = {
                "source": telemetry_data.get("source", "unknown"),
            }
            battery_block = telemetry_data.get("battery") if isinstance(telemetry_data.get("battery"), dict) else None
            if battery_block is not None:
                # We'll enrich this after we know power payload details
                message["battery"] = dict(battery_block)
            if power_payload is not None:
                # Work on a shallow copy to avoid mutating shared state
                pp = dict(power_payload)
                message["power"] = pp
                # Battery metrics (augment battery block and provide default if absent)
                battery_voltage = power_payload.get("battery_voltage")
                battery_current = power_payload.get("battery_current")
                battery_power = power_payload.get("battery_power")
                # Charging state derived from current direction when available
                charging_state = None
                try:
                    if isinstance(battery_current, (int, float)):
                        if battery_current > 0.05:
                            charging_state = "charging"
                        elif battery_current < -0.05:
                            charging_state = "discharging"
                        else:
                            charging_state = "idle"
                except Exception:
                    charging_state = None

                if "battery" not in message:
                    message["battery"] = {}
                if battery_voltage is not None:
                    message["battery"].setdefault("voltage", battery_voltage)
                if battery_current is not None:
                    message["battery"]["current"] = battery_current
                if battery_power is not None:
                    message["battery"]["power"] = battery_power
                if charging_state is not None:
                    message["battery"]["charging_state"] = charging_state

                solar_voltage = pp.get("solar_voltage")
                solar_current = pp.get("solar_current")
                solar_power = pp.get("solar_power")
                # Ensure solar current/power are non-negative for display semantics
                if isinstance(solar_voltage, (int, float)):
                    solar_voltage = abs(float(solar_voltage))
                if isinstance(solar_current, (int, float)):
                    solar_current = abs(float(solar_current))
                if isinstance(solar_power, (int, float)):
                    solar_power = abs(float(solar_power))
                # Reflect normalization in the power payload for consumer consistency
                if "solar_voltage" in pp and solar_voltage is not None:
                    pp["solar_voltage"] = solar_voltage
                if "solar_current" in pp and solar_current is not None:
                    pp["solar_current"] = solar_current
                if "solar_power" in pp and solar_power is not None:
                    pp["solar_power"] = solar_power
                if any(value is not None for value in (solar_voltage, solar_current, solar_power)):
                    message["solar"] = {
                        "voltage": solar_voltage,
                        "current": solar_current,
                        "power": solar_power,
                        "timestamp": power_payload.get("timestamp"),
                    }

                # Load output (state/current/power) when available
                load_current = pp.get("load_current")
                load_power = None
                if isinstance(load_current, (int, float)) and isinstance(battery_voltage, (int, float)):
                    try:
                        load_power = float(battery_voltage) * float(load_current)
                    except Exception:
                        load_power = None
                load_state = None
                if isinstance(load_current, (int, float)):
                    load_state = "on" if abs(load_current) > 0.05 else "off"
                if any(v is not None for v in (load_current, load_power, load_state)):
                    message["load"] = {
                        "state": load_state,
                        "current": load_current,
                        "power": load_power,
                    }
                # Surface derived fields back into power payload for convenience
                if load_power is not None:
                    pp["load_power"] = load_power
                if load_state is not None:
                    pp["load_state"] = load_state
                timestamp = pp.get("timestamp")
                if timestamp is not None:
                    message["timestamp"] = timestamp
            await self.broadcast_to_topic("telemetry.power", message)
            
        if "position" in telemetry_data:
            # Ensure shallow copy to avoid mutation races
            pos = telemetry_data.get("position") or {}
            # Merge with last known values to avoid transient None for fields (e.g., altitude/accuracy)
            cached = self._last_position
            def _merge_field(key: str):
                v = pos.get(key) if isinstance(pos, dict) else None
                return v if v is not None else cached.get(key)
            merged = {
                "latitude": _merge_field("latitude"),
                "longitude": _merge_field("longitude"),
                "altitude": _merge_field("altitude"),
                "accuracy": _merge_field("accuracy"),
                "gps_mode": _merge_field("gps_mode"),
                "hdop": _merge_field("hdop"),
                "speed": _merge_field("speed"),
                "rtk_status": _merge_field("rtk_status"),
                "satellites": _merge_field("satellites"),
            }
            # Update cache with any newly provided non-None values
            for k, v in merged.items():
                if v is not None:
                    self._last_position[k] = v
            nav_payload = {
                "position": merged,
                "source": telemetry_data.get("source", "unknown"),
            }
            speed_val = merged.get("speed")
            if isinstance(speed_val, (int, float)):
                nav_payload["speed_mps"] = speed_val
            accuracy_val = merged.get("accuracy")
            if isinstance(accuracy_val, (int, float)):
                nav_payload["accuracy_m"] = accuracy_val
            hdop_val = merged.get("hdop")
            if isinstance(hdop_val, (int, float)):
                nav_payload["hdop"] = hdop_val
            await self.broadcast_to_topic("telemetry.navigation", nav_payload)
            
        if "imu" in telemetry_data:
            await self.broadcast_to_topic("telemetry.sensors", {
                "imu": telemetry_data["imu"],
                "source": telemetry_data.get("source", "unknown")
            })

        if "environmental" in telemetry_data:
            await self.broadcast_to_topic("telemetry.environmental", {
                "environmental": telemetry_data["environmental"],
                "source": telemetry_data.get("source", "unknown")
            })

        if "tof" in telemetry_data:
            await self.broadcast_to_topic("telemetry.tof", {
                "tof": telemetry_data["tof"],
                "source": telemetry_data.get("source", "unknown")
            })
            
        if "motor_status" in telemetry_data:
            await self.broadcast_to_topic("telemetry.motors", {
                "motor_status": telemetry_data["motor_status"],
                "source": telemetry_data.get("source", "unknown")
            })
            
        # System status
        system_data = {
            "safety_state": telemetry_data.get("safety_state", "unknown"),
            "uptime_seconds": telemetry_data.get("uptime_seconds", 0),
            "source": telemetry_data.get("source", "unknown")
        }
        await self.broadcast_to_topic("telemetry.system", system_data)
        await self.broadcast_to_topic("system.health", system_data)
        
        # Legacy support: broadcast full data to general telemetry topic
        await self.broadcast_to_topic("telemetry/updates", telemetry_data)
        
        # Additional topics (hardware when available, otherwise simulated)
        await self._broadcast_additional_topics(telemetry_data)
        
    async def _broadcast_additional_topics(self, telemetry_data: Optional[dict] = None):
        """Broadcast supplemental topics, preferring hardware readings when present."""
        import random

        weather_data: Optional[dict[str, Any]] = None
        env = (telemetry_data or {}).get("environmental") if telemetry_data else None

        if isinstance(env, dict) and any(env.get(key) is not None for key in ("temperature_c", "humidity_percent", "pressure_hpa")):
            weather_data = {
                "temperature_c": env.get("temperature_c"),
                "humidity_percent": env.get("humidity_percent"),
                "pressure_hpa": env.get("pressure_hpa"),
                "altitude_m": env.get("altitude_m"),
                "wind_speed_ms": None,
                "precipitation_mm": None,
                "source": telemetry_data.get("source", "hardware") if telemetry_data else "hardware"
            }

        if weather_data is None and self._sensor_manager is not None:
            env_iface = getattr(self._sensor_manager, "environmental", None)
            if env_iface is not None:
                try:
                    reading = await env_iface.read_environmental()
                except Exception:
                    reading = None
                if reading is not None:
                    weather_data = {
                        "temperature_c": getattr(reading, "temperature", None),
                        "humidity_percent": getattr(reading, "humidity", None),
                        "pressure_hpa": getattr(reading, "pressure", None),
                        "altitude_m": getattr(reading, "altitude", None),
                        "wind_speed_ms": None,
                        "precipitation_mm": None,
                        "source": "hardware"
                    }

        if weather_data is None:
            try:
                snapshot = await weather_service.get_current_async()
            except Exception:
                snapshot = None
            if snapshot and any(snapshot.get(key) is not None for key in ("temperature_c", "humidity_percent", "pressure_hpa")):
                weather_data = {
                    "temperature_c": snapshot.get("temperature_c"),
                    "humidity_percent": snapshot.get("humidity_percent"),
                    "pressure_hpa": snapshot.get("pressure_hpa"),
                    "altitude_m": snapshot.get("altitude_m"),
                    "wind_speed_ms": snapshot.get("wind_speed_ms") if snapshot.get("wind_speed_ms") is not None else None,
                    "precipitation_mm": snapshot.get("precipitation_mm") if snapshot.get("precipitation_mm") is not None else None,
                    "source": snapshot.get("source", "simulated")
                }

        if weather_data is None:
            weather_data = {
                "temperature_c": None,
                "humidity_percent": None,
                "pressure_hpa": None,
                "altitude_m": None,
                "wind_speed_ms": None,
                "precipitation_mm": None,
                "source": "unavailable"
            }

        await self.broadcast_to_topic("telemetry.weather", weather_data)
        
        # Job status (simulated)
        job_data = {
            "current_job": "mowing_zone_1",
            "progress_percent": round(random.uniform(0, 100), 1),
            "remaining_time_min": random.randint(5, 60),
            "status": random.choice(["running", "paused", "idle"]),
            "source": "simulated"
        }
        await self.broadcast_to_topic("jobs.progress", job_data)
        
    # System performance
        perf_data = {
            "cpu_usage_percent": round(random.uniform(10, 60), 1),
            "memory_usage_percent": round(random.uniform(20, 70), 1),
            "disk_usage_percent": round(random.uniform(30, 80), 1),
            "temperature_c": round(random.uniform(35, 65), 1),
            "source": "simulated"
        }
        await self.broadcast_to_topic("system.performance", perf_data)
        
        # Connectivity status
        # FIXME: This relies on _remote_access_settings being available.
        # For now, I'll load it here to be safe.
        from ..services.remote_access_service import CONFIG_PATH as REMOTE_ACCESS_CONFIG_PATH
        try:
             _remote_access_settings = RemoteAccessService.load_config_from_disk(REMOTE_ACCESS_CONFIG_PATH)
        except Exception:
             # Fallback
             from ..models.remote_access_config import RemoteAccessConfig
             _remote_access_settings = RemoteAccessConfig()

        try:
            ra_status = RemoteAccessService.load_status_from_disk(
                REMOTE_ACCESS_STATUS_PATH,
                configured_provider=_remote_access_settings.provider,
                enabled=_remote_access_settings.enabled,
            )
        except Exception:  # pragma: no cover - defensive
            ra_status = RemoteAccessStatus(
                provider=_remote_access_settings.provider,
                configured_provider=_remote_access_settings.provider,
                enabled=_remote_access_settings.enabled,
                active=False,
                message="unavailable",
            )
        conn_data = {
            "wifi_signal_strength": random.randint(-80, -30),
            "internet_connected": random.choice([True, False]),
            "mqtt_connected": random.choice([True, False]),
            "remote_access_active": ra_status.active,
            "remote_access_provider": ra_status.provider,
            "remote_access_url": ra_status.url,
            "remote_access_health": ra_status.health,
            "remote_access_message": ra_status.message,
            "source": "live" if ra_status.last_checked else "simulated",
        }
        await self.broadcast_to_topic("system.connectivity", conn_data)

    async def _generate_telemetry(self) -> dict:
        """Generate telemetry from hardware when SIM_MODE=0, otherwise simulated.

        Safe on CI: imports and hardware init are lazy and wrapped in try/except.
        """
        sim_mode = os.getenv("SIM_MODE", "0") != "0"

        manager: Any | None = None
        try:
            manager = await self._ensure_sensor_manager()
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("SensorManager initialization failed: %s", exc)
            manager = None
        
        # Access shared state for safety
        from ..core.globals import _safety_state, _debug_overrides

        if manager and getattr(manager, "initialized", False):
            try:
                # One-time warmup to allow GPS first fix to populate
                if not self._gps_warm_done:
                    try:
                        for _ in range(3):
                            warm = await manager.read_all_sensors()
                            if getattr(warm, "gps", None) and getattr(warm.gps, "latitude", None) is not None:
                                break
                            await asyncio.sleep(0.2)
                    finally:
                        self._gps_warm_done = True

                data = await manager.read_all_sensors()
                try:
                    # Feed fresh sensor data into NavigationService for closed-loop control
                    from ..services.navigation_service import NavigationService as _NavSvc  # local import to avoid cycles
                    nav = _NavSvc.get_instance()
                    await nav.update_navigation_state(data)
                except Exception as exc:
                    # Non-fatal: navigation state updates should not break telemetry
                    logger.debug("Navigation state update failed: %s", exc)
            except Exception as exc:
                logger.warning("SensorManager telemetry read failed: %s", exc)
            else:
                battery_pct = None
                batt_v = None
                if data.power and data.power.battery_voltage is not None:
                    batt_v = float(data.power.battery_voltage)
                    estimate = None
                    try:
                        estimate = manager._estimate_battery_soc(batt_v)
                    except Exception:
                        estimate = None
                    if estimate is None:
                        estimate = max(0.0, min(100.0, (batt_v - 11.0) / (13.0 - 11.0) * 100.0))
                    # If the battery is actively charging, avoid pegging at 100% just due to surface charge
                    batt_cur = getattr(data.power, "battery_current", None)
                    if isinstance(batt_cur, (int, float)) and batt_cur > 0.05:
                        battery_pct = float(min(99.0, estimate))
                    else:
                        battery_pct = float(estimate)

                pos = data.gps
                imu = data.imu
                speed_mps = getattr(pos, "speed", None) if pos else None
                accuracy_m = getattr(pos, "accuracy", None) if pos else None
                hdop = getattr(pos, "hdop", None) if pos else None
                if accuracy_m is None and hdop is not None:
                    try:
                        accuracy_m = float(hdop)
                    except Exception:
                        accuracy_m = None

                cal_status = getattr(imu, "calibration_status", None)
                _cal_map = {
                    "fully_calibrated": 3,
                    "calibrated": 3,
                    "calibrating": 2,
                    "partial": 2,
                    "unknown": 1,
                    None: 0,
                }
                cal_score = _cal_map.get(cal_status, 1 if cal_status else 0)

                telemetry: dict[str, Any] = {
                    "source": "hardware",
                    "simulated": bool(sim_mode),
                    "battery": {"percentage": battery_pct, "voltage": batt_v},
                    "position": {
                        "latitude": getattr(pos, "latitude", None),
                        "longitude": getattr(pos, "longitude", None),
                        "altitude": getattr(pos, "altitude", None),
                        "accuracy": accuracy_m,
                        "gps_mode": getattr(pos, "mode", None) if pos else None,
                        "satellites": getattr(pos, "satellites", None) if pos else None,
                        "speed": speed_mps,
                        "rtk_status": getattr(pos, "rtk_status", None) if pos else None,
                        "hdop": hdop,
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
                        "linear": {"x": speed_mps, "y": None, "z": None},
                        "angular": {"x": None, "y": None, "z": getattr(imu, "gyro_z", None)},
                    },
                    "motor_status": "idle",
                    "safety_state": "emergency_stop" if _safety_state.get("emergency_stop_active", False) else "nominal",
                    "uptime_seconds": time.time(),
                }

                power = getattr(data, "power", None)
                if power is not None:
                    telemetry["power"] = {
                        "battery_voltage": getattr(power, "battery_voltage", None),
                        "battery_current": getattr(power, "battery_current", None),
                        "battery_power": getattr(power, "battery_power", None),
                        "solar_voltage": getattr(power, "solar_voltage", None),
                        "solar_current": getattr(power, "solar_current", None),
                        "solar_power": getattr(power, "solar_power", None),
                        "solar_yield_today_wh": getattr(power, "solar_yield_today_wh", None),
                        "load_current": getattr(power, "load_current", None),
                        "timestamp": getattr(power, "timestamp", None),
                    }
                    # Derived load power/state for convenience
                    try:
                        cur = getattr(power, "load_current", None)
                        if cur is not None and batt_v is not None:
                            telemetry["power"]["load_power"] = round(float(batt_v) * float(cur), 3)
                        if isinstance(cur, (int, float)):
                            telemetry["power"]["load_state"] = "on" if abs(cur) > 0.05 else "off"
                    except Exception:
                        pass
                    if telemetry["battery"].get("voltage") is None and getattr(power, "battery_voltage", None) is not None:
                        telemetry["battery"]["voltage"] = float(getattr(power, "battery_voltage"))
                    # Surface a charging_state hint for the UI
                    bc = getattr(power, "battery_current", None)
                    if isinstance(bc, (int, float)):
                        telemetry["battery"]["charging_state"] = "charging" if bc > 0.05 else ("discharging" if bc < -0.05 else "idle")

                env = getattr(data, "environmental", None)
                if env:
                    environmental_payload = {
                        "temperature_c": getattr(env, "temperature", None),
                        "humidity_percent": getattr(env, "humidity", None),
                        "pressure_hpa": getattr(env, "pressure", None),
                        "altitude_m": getattr(env, "altitude", None),
                    }
                    if any(v is not None for v in environmental_payload.values()):
                        telemetry["environmental"] = environmental_payload

                tof_left = getattr(data, "tof_left", None)
                tof_right = getattr(data, "tof_right", None)
                tof_payload: dict[str, Any] = {}
                if tof_left is not None:
                    tof_payload["left"] = {
                        "distance_mm": getattr(tof_left, "distance", None),
                        "range_status": getattr(tof_left, "range_status", None),
                        "signal_strength": getattr(tof_left, "signal_strength", None),
                    }
                if tof_right is not None:
                    tof_payload["right"] = {
                        "distance_mm": getattr(tof_right, "distance", None),
                        "range_status": getattr(tof_right, "range_status", None),
                        "signal_strength": getattr(tof_right, "signal_strength", None),
                    }
                if tof_payload:
                    telemetry["tof"] = tof_payload

                if "environmental" not in telemetry:
                    telemetry["environmental"] = {
                        "temperature_c": None,
                        "humidity_percent": None,
                        "pressure_hpa": None,
                        "altitude_m": None,
                    }
                if "tof" not in telemetry:
                    telemetry["tof"] = {
                        "left": {"distance_mm": None, "range_status": None, "signal_strength": None},
                        "right": {"distance_mm": None, "range_status": None, "signal_strength": None},
                    }

                try:
                    from ..services.camera_stream_service import camera_service
                    camera_frame = await camera_service.get_current_frame()
                    if camera_frame and camera_service.stream:
                        telemetry["camera"] = {
                            "active": camera_service.stream.is_active,
                            "mode": camera_service.stream.mode,
                            "fps": camera_service.stream.statistics.current_fps,
                            "frame_count": camera_service.stream.statistics.frames_captured,
                            "client_count": camera_service.stream.client_count,
                            "last_frame": camera_frame.metadata.timestamp.isoformat() if camera_frame else None,
                        }
                    else:
                        telemetry["camera"] = {
                            "active": False,
                            "mode": "offline",
                            "fps": 0.0,
                            "frame_count": 0,
                            "client_count": 0,
                            "last_frame": None,
                        }
                except Exception:
                    telemetry["camera"] = {"active": False, "mode": "error"}

                return telemetry

        # Simulated data
        telemetry = {
            "source": "simulated",
            "battery": {"percentage": None, "voltage": None},
            "position": {"latitude": None, "longitude": None, "accuracy": None, "gps_mode": None, "hdop": None},
            "imu": {"roll": None, "pitch": None, "yaw": None, "gyro_z": None, "calibration": 0, "calibration_status": None},
            "velocity": {
                "linear": {"x": None, "y": None, "z": None},
                "angular": {"x": None, "y": None, "z": None},
            },
            "motor_status": "idle",
            "safety_state": "emergency_stop" if _safety_state.get("emergency_stop_active", False) else "nominal",
            "uptime_seconds": time.time(),
        }
        telemetry["environmental"] = {
            "temperature_c": None,
            "humidity_percent": None,
            "pressure_hpa": None,
            "altitude_m": None,
        }
        cycle = self._sim_cycle
        self._sim_cycle = (self._sim_cycle + 1) % 10000
        left_distance = 1200 + 250 * math.sin(cycle / 6.0)
        right_distance = 1180 + 220 * math.cos((cycle + 3) / 5.0)
        left_status = "valid"
        right_status = "valid"
        if cycle % 24 == 12:
            left_distance = 160.0
            left_status = "obstacle"
        if cycle % 32 == 16:
            right_distance = 180.0
            right_status = "obstacle"
        telemetry["tof"] = {
            "left": {
                "distance_mm": round(left_distance, 1),
                "range_status": left_status,
                "signal_strength": 1400 + 100 * math.sin(cycle / 4.0),
            },
            "right": {
                "distance_mm": round(right_distance, 1),
                "range_status": right_status,
                "signal_strength": 1350 + 90 * math.cos(cycle / 4.0),
            },
        }
        
        # Add simulated camera data
        try:
            from ..services.camera_stream_service import camera_service
            if camera_service.stream and camera_service.stream.is_active:
                telemetry["camera"] = {
                    "active": True,
                    "mode": "streaming",
                    "fps": 15.0,
                    "frame_count": int(time.time() * 15) % 10000,  # Simulated counter
                    "client_count": len(camera_service.clients),
                    "last_frame": datetime.now(timezone.utc).isoformat()
                }
            else:
                telemetry["camera"] = {
                    "active": False,
                    "mode": "offline",
                    "fps": 0.0,
                    "frame_count": 0,
                    "client_count": 0,
                    "last_frame": None
                }
        except Exception:
            telemetry["camera"] = {"active": False, "mode": "error"}
        
        return telemetry

# Global WebSocket hub instance
websocket_hub = WebSocketHub()
weather_service.register_sensor_manager(lambda: websocket_hub._sensor_manager)