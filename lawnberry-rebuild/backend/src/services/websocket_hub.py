import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
from ..models.sensor_data import SensorData
from ..models.alert import Alert


class WebSocketHub:
    """Centralized WebSocket hub for real-time communication."""
    
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self.subscriptions: Dict[str, Set[str]] = {}  # topic -> client_ids
        self.telemetry_cadence_hz = 5.0
        self._telemetry_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def connect(self, websocket: WebSocket, client_id: str):
        """Connect a new WebSocket client."""
        await websocket.accept()
        self.connections[client_id] = websocket
        
        # Send connection confirmation
        await self._send_to_client(client_id, {
            "event": "connection.established",
            "client_id": client_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
    def disconnect(self, client_id: str):
        """Disconnect a WebSocket client."""
        if client_id in self.connections:
            del self.connections[client_id]
            
        # Remove from all subscriptions
        for topic, subscribers in self.subscriptions.items():
            subscribers.discard(client_id)
            
    async def subscribe(self, client_id: str, topic: str):
        """Subscribe client to a topic."""
        if topic not in self.subscriptions:
            self.subscriptions[topic] = set()
        self.subscriptions[topic].add(client_id)
        
        # Send confirmation
        await self._send_to_client(client_id, {
            "event": "subscription.confirmed",
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
    async def unsubscribe(self, client_id: str, topic: str):
        """Unsubscribe client from a topic."""
        if topic in self.subscriptions:
            self.subscriptions[topic].discard(client_id)
            
        await self._send_to_client(client_id, {
            "event": "subscription.cancelled", 
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
    async def set_cadence(self, client_id: str, cadence_hz: float):
        """Set telemetry cadence (1-10 Hz)."""
        cadence_hz = max(1.0, min(10.0, cadence_hz))
        self.telemetry_cadence_hz = cadence_hz
        
        await self._send_to_client(client_id, {
            "event": "cadence.updated",
            "cadence_hz": cadence_hz,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
    async def broadcast_to_topic(self, topic: str, data: Any):
        """Broadcast data to all subscribers of a topic."""
        if topic not in self.subscriptions or not self.subscriptions[topic]:
            return
            
        message = {
            "event": "telemetry.data",
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        
        message_json = json.dumps(message)
        disconnected_clients = []
        
        for client_id in self.subscriptions[topic].copy():
            if client_id in self.connections:
                try:
                    await self.connections[client_id].send_text(message_json)
                except Exception:
                    disconnected_clients.append(client_id)
                    
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)
            
    async def broadcast_alert(self, alert: Alert):
        """Broadcast system alert to all connected clients."""
        await self.broadcast_to_topic("alerts/system", alert.dict())
        
    async def start_telemetry_loop(self):
        """Start the telemetry broadcast loop."""
        if self._telemetry_task is not None:
            return
            
        self._running = True
        self._telemetry_task = asyncio.create_task(self._telemetry_loop())
        
    async def stop_telemetry_loop(self):
        """Stop the telemetry broadcast loop."""
        self._running = False
        if self._telemetry_task:
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass
            self._telemetry_task = None
            
    async def _telemetry_loop(self):
        """Main telemetry broadcast loop."""
        while self._running:
            try:
                # Generate telemetry data
                telemetry_data = await self._generate_telemetry()
                
                # Broadcast to different topics
                await self.broadcast_to_topic("telemetry/state", telemetry_data)
                await self.broadcast_to_topic("telemetry/power", {
                    "battery_percentage": telemetry_data.get("battery", {}).get("percentage", 0),
                    "battery_voltage": telemetry_data.get("battery", {}).get("voltage"),
                    "charging": telemetry_data.get("charging", False)
                })
                
                # Wait based on cadence
                await asyncio.sleep(1.0 / self.telemetry_cadence_hz)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error and continue
                print(f"Telemetry loop error: {e}")
                await asyncio.sleep(1.0)
                
    async def _generate_telemetry(self) -> dict:
        """Generate telemetry data (placeholder implementation)."""
        # This would integrate with real sensor services
        return {
            "source": "simulated",
            "battery": {"percentage": 85.2, "voltage": 12.6},
            "position": {"latitude": 40.7128, "longitude": -74.0060},
            "navigation_mode": "idle",
            "motor_status": "idle",
            "safety_state": "safe",
            "uptime_seconds": 3600,
        }
        
    async def _send_to_client(self, client_id: str, message: dict):
        """Send message to specific client."""
        if client_id in self.connections:
            try:
                await self.connections[client_id].send_text(json.dumps(message))
            except Exception:
                self.disconnect(client_id)


# Global instance
websocket_hub = WebSocketHub()