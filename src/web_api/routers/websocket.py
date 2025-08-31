"""
WebSocket Router
Real-time communication via WebSocket connections.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Request
from datetime import datetime
import weakref

from ..models import WebSocketMessage, WebSocketCommand
from ..auth import get_current_user_optional
from ..mqtt_bridge import MQTTBridge


router = APIRouter()
logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manage WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = weakref.WeakSet()
        self.connection_info: Dict[WebSocket, Dict[str, Any]] = {}
        self.subscriptions: Dict[WebSocket, Set[str]] = {}
        
    async def connect(self, websocket: WebSocket, user_info: Dict[str, Any] = None):
        """Accept WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.connection_info[websocket] = {
            "connected_at": datetime.utcnow(),
            "user": user_info,
            "last_ping": datetime.utcnow()
        }
        self.subscriptions[websocket] = set()
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.active_connections.discard(websocket)
        self.connection_info.pop(websocket, None)
        self.subscriptions.pop(websocket, None)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """Send message to specific WebSocket"""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: Dict[str, Any], topic: str = None):
        """Broadcast message to all connected clients or topic subscribers"""
        if not self.active_connections:
            return
        
        message_json = json.dumps(message)
        disconnected = set()
        
        for websocket in self.active_connections:
            try:
                # Check if client is subscribed to this topic
                if topic and topic not in self.subscriptions.get(websocket, set()):
                    continue
                
                await websocket.send_text(message_json)
            except Exception as e:
                logger.debug(f"WebSocket connection error during broadcast: {e}")
                disconnected.add(websocket)
        
        # Clean up disconnected connections
        for websocket in disconnected:
            self.disconnect(websocket)
    
    def subscribe(self, websocket: WebSocket, topic: str):
        """Subscribe WebSocket to topic"""
        if websocket in self.subscriptions:
            self.subscriptions[websocket].add(topic)
            logger.debug(f"WebSocket subscribed to topic: {topic}")
    
    def unsubscribe(self, websocket: WebSocket, topic: str):
        """Unsubscribe WebSocket from topic"""
        if websocket in self.subscriptions:
            self.subscriptions[websocket].discard(topic)
            logger.debug(f"WebSocket unsubscribed from topic: {topic}")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            "total_connections": len(self.active_connections),
            "subscriptions": sum(len(subs) for subs in self.subscriptions.values()),
            "uptime": datetime.utcnow().isoformat()
        }


# Global WebSocket manager
ws_manager = WebSocketManager()


@router.websocket("/realtime")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time communication"""
    user_info = None
    # Obtain MQTT bridge from application state so we can access cached data
    mqtt_bridge = getattr(websocket.app.state, 'mqtt_bridge', None)
    
    try:
        # Get MQTT bridge from app state (we'll handle this in the connection)
        await ws_manager.connect(websocket, user_info)

        # Register this websocket with the MQTT bridge so MQTTBridge can broadcast directly
        try:
            if mqtt_bridge and hasattr(mqtt_bridge, 'add_websocket_connection'):
                mqtt_bridge.add_websocket_connection(websocket)
        except Exception:
            logger.debug("Failed to register websocket with MQTT bridge; continuing")
        
        # Send welcome message
        welcome_message = {
            "type": "connection",
            "message": "Connected to Lawnberry API",
            "timestamp": datetime.utcnow().isoformat(),
            "server_time": datetime.utcnow().isoformat()
        }
        await ws_manager.send_personal_message(welcome_message, websocket)
        
        # Message handling loop
        while True:
            try:
                # Set timeout for receiving messages
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # 30 second timeout
                )
                
                # Parse message
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    await ws_manager.send_personal_message({
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": datetime.utcnow().isoformat()
                    }, websocket)
                    continue
                
                # Handle message
                await handle_websocket_message(websocket, message, mqtt_bridge)
                
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                ping_message = {
                    "type": "ping",
                    "timestamp": datetime.utcnow().isoformat()
                }
                await ws_manager.send_personal_message(ping_message, websocket)
                
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Unregister websocket from MQTT bridge (if previously registered)
        try:
            if mqtt_bridge and hasattr(mqtt_bridge, 'remove_websocket_connection'):
                mqtt_bridge.remove_websocket_connection(websocket)
        except Exception:
            logger.debug("Failed to unregister websocket from MQTT bridge; continuing")

        ws_manager.disconnect(websocket)


async def handle_websocket_message(websocket: WebSocket, message: Dict[str, Any], mqtt_bridge: MQTTBridge):
    """Handle incoming WebSocket messages"""
    message_type = message.get("type", "")
    
    try:
        if message_type == "subscribe":
            # Subscribe to topic updates
            topic = message.get("topic", "")
            if topic:
                ws_manager.subscribe(websocket, topic)
                
                # Send subscription confirmation
                await ws_manager.send_personal_message({
                    "type": "subscription_confirmed",
                    "topic": topic,
                    "timestamp": datetime.utcnow().isoformat()
                }, websocket)
                
                # Send current data if available and mqtt_bridge exists
                if mqtt_bridge:
                    cached_data = mqtt_bridge.get_cached_data(topic)
                    if cached_data:
                        await ws_manager.send_personal_message({
                            "type": "data",
                            "topic": topic,
                            "data": cached_data,
                            "timestamp": datetime.utcnow().isoformat()
                        }, websocket)
        
        elif message_type == "unsubscribe":
            # Unsubscribe from topic updates
            topic = message.get("topic", "")
            if topic:
                ws_manager.unsubscribe(websocket, topic)
                await ws_manager.send_personal_message({
                    "type": "unsubscription_confirmed",
                    "topic": topic,
                    "timestamp": datetime.utcnow().isoformat()
                }, websocket)
        
        elif message_type == "command":
            # Execute command via MQTT
            if not mqtt_bridge or not mqtt_bridge.is_connected():
                await ws_manager.send_personal_message({
                    "type": "error",
                    "message": "MQTT bridge not available",
                    "timestamp": datetime.utcnow().isoformat()
                }, websocket)
                return
            
            command = message.get("command", "")
            parameters = message.get("parameters", {})
            request_id = message.get("request_id", "")
            
            # Send command via MQTT
            result = await mqtt_bridge.send_command(command, parameters)
            
            # Send response
            response = {
                "type": "command_response",
                "request_id": request_id,
                "command": command,
                "success": result is not None,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            }
            await ws_manager.send_personal_message(response, websocket)
        
        elif message_type == "pong":
            # Handle pong response
            ws_manager.connection_info[websocket]["last_ping"] = datetime.utcnow()
        
        elif message_type == "get_status":
            # Send current system status
            status_data = {}
            if mqtt_bridge:
                status_data = mqtt_bridge.get_all_cached_data()
            
            await ws_manager.send_personal_message({
                "type": "status",
                "data": status_data,
                "timestamp": datetime.utcnow().isoformat()
            }, websocket)
        
        else:
            # Unknown message type
            await ws_manager.send_personal_message({
                "type": "error",
                "message": f"Unknown message type: {message_type}",
                "timestamp": datetime.utcnow().isoformat()
            }, websocket)
    
    except Exception as e:
        logger.error(f"Error handling WebSocket message: {e}")
        await ws_manager.send_personal_message({
            "type": "error",
            "message": "Error processing message",
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)


@router.get("/connections")
async def get_websocket_connections():
    """Get WebSocket connection statistics"""
    return ws_manager.get_connection_stats()


@router.post("/broadcast")
async def broadcast_message(
    message: Dict[str, Any],
    topic: str = None
):
    """Broadcast message to all WebSocket connections"""
    broadcast_msg = {
        "type": "broadcast",
        "data": message,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await ws_manager.broadcast(broadcast_msg, topic)
    
    return {
        "success": True,
        "message": "Message broadcasted",
        "connections": len(ws_manager.active_connections)
    }


# Function to integrate with MQTT bridge
def setup_websocket_mqtt_integration(mqtt_bridge: MQTTBridge):
    """Setup integration between WebSocket and MQTT bridge"""
    # Add WebSocket manager to MQTT bridge
    if hasattr(mqtt_bridge, 'add_websocket_connection'):
        # This would be called when connections are established
        pass
    
    # Setup message forwarding from MQTT to WebSocket
    async def mqtt_to_websocket_handler(topic: str, data: Dict[str, Any]):
        """Forward MQTT messages to WebSocket clients"""
        message = {
            "type": "mqtt_data",
            "topic": topic,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        await ws_manager.broadcast(message, topic)
    
    # Subscribe to relevant MQTT topics
    topics_to_forward = [
        "system/status",
    "system/health",
    "system/tof_status",
        "sensors/+/data",
        "navigation/position",
        "power/battery",
        "weather/current",
    # Forward safety status frames to the UI
    "safety/status",
    "safety/alerts/+",
    # RC control status topics (exact match required by MQTTBridge handler)
    "rc/status",
    "hardware/rc/status"
    ]
    
    for topic in topics_to_forward:
        mqtt_bridge.subscribe_to_topic(topic, mqtt_to_websocket_handler)


# Export WebSocket manager for use in main app
def get_websocket_manager() -> WebSocketManager:
    """Get the global WebSocket manager"""
    return ws_manager
