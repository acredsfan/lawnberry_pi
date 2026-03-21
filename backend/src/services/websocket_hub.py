import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Mapping

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder

from ..core.state_manager import AppState
from ..services.telemetry_service import telemetry_service

logger = logging.getLogger(__name__)

class WebSocketHub:
    def __init__(self):
        self.clients: dict[str, WebSocket] = {}
        self.subscriptions: dict[str, set[str]] = {}  # topic -> client_ids
        self.telemetry_cadence_hz = 5.0
        self._telemetry_task: Optional[asyncio.Task] = None
        self.app_state = AppState.get_instance()
        self._app_state = self.app_state
        self._sensor_manager: Optional[Any] = None
        self._ntrip_forwarder: Optional[Any] = None
        self._calibration_lock = asyncio.Lock()

    def bind_app_state(self, state: Any) -> None:
        """Expose app.state to the hub."""
        self._app_state = self.app_state
        hardware_config = getattr(state, "hardware_config", None)
        if hardware_config is not None:
            self._app_state.hardware_config = hardware_config
        sensor_manager = getattr(state, "sensor_manager", None)
        if sensor_manager is not None:
            self._app_state.sensor_manager = sensor_manager
            self._sensor_manager = sensor_manager
        ntrip_forwarder = getattr(state, "ntrip_forwarder", None)
        if ntrip_forwarder is not None:
            self._app_state.ntrip_forwarder = ntrip_forwarder
            self._ntrip_forwarder = ntrip_forwarder
        setattr(state, "websocket_hub", self)

    async def _ensure_sensor_manager(self):
        manager = self._app_state.sensor_manager
        if manager is None:
            await telemetry_service.initialize_sensors()
            manager = self._app_state.sensor_manager
        self._sensor_manager = manager
        self._ntrip_forwarder = getattr(self._app_state, "ntrip_forwarder", None)
        return manager

    async def connect(self, websocket: WebSocket, client_id: str):
        subprotocol = None
        header_value = None
        try:
            headers = getattr(websocket, "headers", None)
            if headers is not None:
                getter = getattr(headers, "get", None)
                if callable(getter):
                    value = getter("sec-websocket-protocol")
                    if hasattr(value, "__await__"): # Check awaitable
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
        try:
            await websocket.send_text(json.dumps({
                "event": "connection.established",
                "client_id": client_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
        except Exception:
            self.disconnect(client_id)

    async def broadcast(self, message: str):
        disconnected_clients = []
        for client_id, websocket in list(self.clients.items()):
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected_clients.append(client_id)

        for client_id in disconnected_clients:
            self.disconnect(client_id)
        
    def disconnect(self, client_id: str):
        if client_id in self.clients:
            del self.clients[client_id]
        for _topic, subscribers in self.subscriptions.items():
            subscribers.discard(client_id)
            
    async def subscribe(self, client_id: str, topic: str):
        if topic not in self.subscriptions:
            self.subscriptions[topic] = set()
        self.subscriptions[topic].add(client_id)
        
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps({
                "event": "subscription.confirmed",
                "topic": topic,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
    async def unsubscribe(self, client_id: str, topic: str):
        if topic in self.subscriptions:
            self.subscriptions[topic].discard(client_id)
            
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps({
                "event": "unsubscription.confirmed", 
                "topic": topic,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
    async def set_cadence(self, client_id: str, cadence_hz: float):
        cadence_hz = max(1.0, min(10.0, cadence_hz))
        self.telemetry_cadence_hz = cadence_hz
        
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps({
                "event": "cadence.updated",
                "cadence_hz": cadence_hz,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
    async def broadcast_to_topic(self, topic: str, data: dict):
        if topic not in self.subscriptions:
            return
        
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
        import os
        while True:
            try:
                sim_mode = os.getenv("SIM_MODE", "0") != "0"
                telemetry_data = await telemetry_service.get_telemetry(sim_mode=sim_mode)
                
                # Broadcast topics
                await self._broadcast_telemetry_topics(telemetry_data)
                
                await asyncio.sleep(1.0 / self.telemetry_cadence_hz)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telemetry loop error: {e}")
                await asyncio.sleep(1.0)
                
    async def _broadcast_telemetry_topics(self, telemetry_data: dict):
        """Broadcast telemetry data to appropriate topics."""
        
        # Power
        if "power" in telemetry_data:
            await self.broadcast_to_topic("telemetry.power", {
                "power": telemetry_data["power"],
                "battery": telemetry_data.get("battery"),
                "source": telemetry_data.get("source")
            })

        # Navigation
        if "position" in telemetry_data:
            await self.broadcast_to_topic("telemetry.navigation", {
                "position": telemetry_data["position"],
                "velocity": telemetry_data.get("velocity"),
                "source": telemetry_data.get("source")
            })
            
        # Sensors (IMU)
        if "imu" in telemetry_data:
            await self.broadcast_to_topic("telemetry.sensors", {
                "imu": telemetry_data["imu"],
                "source": telemetry_data.get("source")
            })

        # Environmental
        if "environmental" in telemetry_data:
            await self.broadcast_to_topic("telemetry.environmental", {
                "environmental": telemetry_data["environmental"],
                "source": telemetry_data.get("source")
            })

        # ToF
        if "tof" in telemetry_data:
            await self.broadcast_to_topic("telemetry.tof", {
                "tof": telemetry_data["tof"],
                "source": telemetry_data.get("source")
            })
            
        # System
        system_data = {
            "safety_state": telemetry_data.get("safety_state"),
            "uptime_seconds": telemetry_data.get("uptime_seconds"),
            "source": telemetry_data.get("source")
        }
        await self.broadcast_to_topic("telemetry.system", system_data)
        await self.broadcast_to_topic("system.health", system_data)
        
        # Legacy full update
        await self.broadcast_to_topic("telemetry/updates", telemetry_data)

    # Helper for legacy external access if needed (e.g. by routers)
    async def _generate_telemetry(self) -> dict:
        import os
        sim_mode = os.getenv("SIM_MODE", "0") != "0"
        return await telemetry_service.get_telemetry(sim_mode=sim_mode)

# Singleton
websocket_hub = WebSocketHub()