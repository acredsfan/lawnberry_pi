"""WebSocket hub for real-time communication backbone.

This module implements the WebSocket event routing and client management system
as specified in T006. Provides telemetry streaming, command handling, and 
client connection management with <100ms telemetry latency requirements.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import structlog
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class WebSocketMessage(BaseModel):
    """Standard WebSocket message envelope."""
    type: str
    topic: str
    data: Dict[str, Any]
    timestamp: str
    message_id: str


class ClientConnection:
    """Represents a connected WebSocket client."""
    
    def __init__(self, websocket: WebSocket, client_id: str):
        self.websocket = websocket
        self.client_id = client_id
        self.connected_at = time.time()
        self.last_ping = time.time()
        self.subscriptions: Set[str] = set()
        
    async def send_message(self, message: WebSocketMessage) -> bool:
        """Send message to client, return success status."""
        try:
            await self.websocket.send_text(message.model_dump_json())
            return True
        except Exception as e:
            logger.warning("Failed to send message to client", 
                         client_id=self.client_id, error=str(e))
            return False
    
    async def ping(self) -> bool:
        """Send ping to client, return success status."""
        try:
            await self.websocket.send_text(json.dumps({"type": "ping", "timestamp": time.time()}))
            self.last_ping = time.time()
            return True
        except Exception:
            return False


class WebSocketHub:
    """Central WebSocket event routing and client management."""
    
    def __init__(self):
        self.clients: Dict[str, ClientConnection] = {}
        self.topics: Dict[str, Set[str]] = {}  # topic -> set of client_ids
        self.telemetry_cadence_hz = 5.0  # Default 5Hz as per spec
        self.max_cadence_hz = 10.0
        self.min_cadence_hz = 1.0
        self._telemetry_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
    async def connect_client(self, websocket: WebSocket) -> str:
        """Accept new client connection and return client ID."""
        await websocket.accept()
        client_id = str(uuid4())
        
        self.clients[client_id] = ClientConnection(websocket, client_id)
        logger.info("WebSocket client connected", client_id=client_id, 
                   total_clients=len(self.clients))
        
        # Send welcome message
        welcome = WebSocketMessage(
            type="connection",
            topic="system",
            data={
                "message": "Connected to LawnBerry WebSocket hub",
                "client_id": client_id,
                "server_time": datetime.utcnow().isoformat()
            },
            timestamp=datetime.utcnow().isoformat(),
            message_id=str(uuid4())
        )
        await self.clients[client_id].send_message(welcome)
        
        return client_id
    
    async def disconnect_client(self, client_id: str):
        """Remove client and clean up subscriptions."""
        if client_id in self.clients:
            # Remove from all topic subscriptions
            for topic_clients in self.topics.values():
                topic_clients.discard(client_id)
            
            del self.clients[client_id]
            logger.info("WebSocket client disconnected", client_id=client_id,
                       remaining_clients=len(self.clients))
    
    async def subscribe_client(self, client_id: str, topic: str):
        """Subscribe client to a topic.""" 
        if client_id not in self.clients:
            logger.warning("Cannot subscribe unknown client", client_id=client_id)
            return
            
        if topic not in self.topics:
            self.topics[topic] = set()
        
        self.topics[topic].add(client_id)
        self.clients[client_id].subscriptions.add(topic)
        
        logger.info("Client subscribed to topic", client_id=client_id, topic=topic)
    
    async def unsubscribe_client(self, client_id: str, topic: str):
        """Unsubscribe client from a topic."""
        if client_id in self.clients:
            self.clients[client_id].subscriptions.discard(topic)
        
        if topic in self.topics:
            self.topics[topic].discard(client_id)
            
        logger.info("Client unsubscribed from topic", client_id=client_id, topic=topic)
    
    async def broadcast_to_topic(self, topic: str, data: Dict[str, Any], 
                               message_type: str = "data") -> int:
        """Broadcast message to all clients subscribed to topic."""
        if topic not in self.topics:
            return 0
        
        message = WebSocketMessage(
            type=message_type,
            topic=topic,
            data=data,
            timestamp=datetime.utcnow().isoformat(),
            message_id=str(uuid4())
        )
        
        sent_count = 0
        failed_clients = []
        
        for client_id in self.topics[topic].copy():
            if client_id in self.clients:
                success = await self.clients[client_id].send_message(message)
                if success:
                    sent_count += 1
                else:
                    failed_clients.append(client_id)
        
        # Clean up failed clients
        for client_id in failed_clients:
            await self.disconnect_client(client_id)
        
        if sent_count > 0:
            logger.debug("Broadcasted to topic", topic=topic, clients=sent_count)
        
        return sent_count
    
    async def send_to_client(self, client_id: str, topic: str, data: Dict[str, Any],
                           message_type: str = "data") -> bool:
        """Send message to specific client."""
        if client_id not in self.clients:
            return False
        
        message = WebSocketMessage(
            type=message_type,
            topic=topic,
            data=data,
            timestamp=datetime.utcnow().isoformat(),
            message_id=str(uuid4())
        )
        
        return await self.clients[client_id].send_message(message)
    
    async def handle_client_message(self, client_id: str, message_data: str):
        """Process incoming message from client."""
        try:
            data = json.loads(message_data)
            message_type = data.get("type", "unknown")
            
            if message_type == "subscribe":
                topic = data.get("topic")
                if topic:
                    await self.subscribe_client(client_id, topic)
                    
            elif message_type == "unsubscribe":
                topic = data.get("topic")
                if topic:
                    await self.unsubscribe_client(client_id, topic)
                    
            elif message_type == "pong":
                # Update client ping time
                if client_id in self.clients:
                    self.clients[client_id].last_ping = time.time()
                    
            elif message_type == "set_cadence":
                # Handle telemetry cadence adjustment
                cadence = data.get("cadence_hz", self.telemetry_cadence_hz)
                await self.set_telemetry_cadence(cadence)
                
            else:
                logger.warning("Unknown message type", client_id=client_id, 
                             message_type=message_type)
                
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from client", client_id=client_id)
        except Exception as e:
            logger.error("Error handling client message", client_id=client_id, error=str(e))
    
    async def set_telemetry_cadence(self, cadence_hz: float):
        """Update telemetry broadcast cadence within limits."""
        cadence_hz = max(self.min_cadence_hz, min(self.max_cadence_hz, cadence_hz))
        
        if cadence_hz != self.telemetry_cadence_hz:
            self.telemetry_cadence_hz = cadence_hz
            logger.info("Telemetry cadence updated", cadence_hz=cadence_hz)
            
            # Broadcast cadence update to settings topic
            await self.broadcast_to_topic("settings/cadence", {
                "cadence_hz": cadence_hz,
                "updated_at": datetime.utcnow().isoformat()
            }, "cadence_update")
    
    async def start_telemetry_loop(self):
        """Start background telemetry broadcasting."""
        if self._telemetry_task is not None:
            return
            
        self._telemetry_task = asyncio.create_task(self._telemetry_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info("WebSocket hub telemetry loops started")
    
    async def stop_telemetry_loop(self):
        """Stop background tasks."""
        if self._telemetry_task:
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass
            self._telemetry_task = None
            
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        
        logger.info("WebSocket hub telemetry loops stopped")
    
    async def _telemetry_loop(self):
        """Background task for telemetry broadcasting."""
        while True:
            try:
                # Generate sample telemetry data
                telemetry_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "battery_voltage": 12.8,  # Simulated data
                    "position": {"lat": 0.0, "lon": 0.0},
                    "motor_status": "idle",
                    "safety_state": "safe",
                    "uptime_seconds": time.time()
                }
                
                await self.broadcast_to_topic("telemetry/updates", telemetry_data)
                
                # Wait for next broadcast based on cadence
                await asyncio.sleep(1.0 / self.telemetry_cadence_hz)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in telemetry loop", error=str(e))
                await asyncio.sleep(1.0)  # Brief pause on error
    
    async def _heartbeat_loop(self):
        """Background task for client heartbeat/ping."""
        while True:
            try:
                current_time = time.time()
                stale_clients = []
                
                for client_id, client in self.clients.items():
                    # Ping clients every 30 seconds
                    if current_time - client.last_ping > 30:
                        success = await client.ping()
                        if not success:
                            stale_clients.append(client_id)
                
                # Clean up stale clients
                for client_id in stale_clients:
                    await self.disconnect_client(client_id)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in heartbeat loop", error=str(e))
                await asyncio.sleep(5.0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get hub statistics."""
        return {
            "total_clients": len(self.clients),
            "active_topics": len(self.topics),
            "telemetry_cadence_hz": self.telemetry_cadence_hz,
            "uptime_seconds": time.time()
        }


# Global hub instance
websocket_hub = WebSocketHub()