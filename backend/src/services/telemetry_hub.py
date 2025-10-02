"""
TelemetryHubService for LawnBerry Pi v2
WebSocket telemetry publishing and client management
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Set, List, Optional, Any
from uuid import uuid4

from ..models import (
    TelemetryExchange, TelemetryHub, TelemetryMessage, StreamConfiguration,
    ClientSubscription, StreamStatistics, TelemetryTopic, MessagePriority, StreamStatus,
    HardwareTelemetryStream, ComponentId, ComponentStatus
)
from ..core.persistence import persistence

logger = logging.getLogger(__name__)


class WebSocketClient:
    """Individual WebSocket client management"""
    
    def __init__(self, client_id: str, websocket):
        self.client_id = client_id
        self.websocket = websocket
        self.connected_at = datetime.now(timezone.utc)
        self.last_ping = None
        self.last_pong = None
        self.subscriptions: Set[TelemetryTopic] = set()
        self.message_count = 0
        self.error_count = 0
        
    async def send_message(self, message: str) -> bool:
        """Send message to client"""
        try:
            await self.websocket.send_text(message)
            self.message_count += 1
            return True
        except Exception as e:
            logger.error(f"Failed to send message to client {self.client_id}: {e}")
            self.error_count += 1
            return False
    
    async def ping(self) -> bool:
        """Send ping to client"""
        try:
            await self.websocket.ping()
            self.last_ping = datetime.now(timezone.utc)
            return True
        except Exception as e:
            logger.error(f"Failed to ping client {self.client_id}: {e}")
            return False
    
    def is_healthy(self) -> bool:
        """Check if client connection is healthy"""
        if self.last_ping and not self.last_pong:
            # No pong response within reasonable time
            time_since_ping = (datetime.now(timezone.utc) - self.last_ping).total_seconds()
            if time_since_ping > 30:  # 30 second timeout
                return False
        
        return self.error_count < 5  # Allow some errors before considering unhealthy


class TelemetryPublisher:
    """Handles telemetry data publishing"""
    
    def __init__(self, telemetry_hub: TelemetryHub):
        self.hub = telemetry_hub
        self.publish_tasks: Dict[TelemetryTopic, asyncio.Task] = {}
        self.running = False
        
    async def start_publishing(self):
        """Start telemetry publishing loops"""
        self.running = True
        
        # Start publishing task for each configured stream
        for topic, config in self.hub.streams.items():
            if config.enabled:
                task = asyncio.create_task(self._publish_loop(topic, config))
                self.publish_tasks[topic] = task
                logger.info(f"Started publishing loop for {topic} at {config.cadence_hz} Hz")
    
    async def stop_publishing(self):
        """Stop all publishing loops"""
        self.running = False
        
        for task in self.publish_tasks.values():
            task.cancel()
        
        await asyncio.gather(*self.publish_tasks.values(), return_exceptions=True)
        self.publish_tasks.clear()
        logger.info("Stopped all telemetry publishing loops")
    
    async def _publish_loop(self, topic: TelemetryTopic, config: StreamConfiguration):
        """Publishing loop for a specific topic"""
        interval = 1.0 / config.cadence_hz
        
        while self.running:
            try:
                # Generate telemetry data based on topic
                telemetry_data = await self._generate_telemetry_data(topic)
                
                if telemetry_data:
                    message = TelemetryMessage(
                        message_id=str(uuid4()),
                        topic=topic,
                        data=telemetry_data,
                        priority=MessagePriority.NORMAL,
                        source_service="telemetry_hub"
                    )
                    
                    # Publish to hub
                    self.hub.publish_message(message)
                
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in {topic} publishing loop: {e}")
                await asyncio.sleep(interval)
    
    async def _generate_telemetry_data(self, topic: TelemetryTopic) -> Optional[Dict[str, Any]]:
        """Generate telemetry data for a topic"""
        
        if topic == TelemetryTopic.TELEMETRY_UPDATES:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "battery": {"percentage": 85.2, "voltage": 12.6},
                "position": {"latitude": 40.7128, "longitude": -74.0060},
                "motor_status": "idle",
                "safety_state": "safe",
                "uptime_seconds": time.time()
            }
        
        elif topic == TelemetryTopic.SYSTEM_STATUS:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_state": "idle",
                "cpu_usage": 25.0,
                "memory_usage": 45.0,
                "disk_usage": 60.0,
                "temperature": 42.5
            }
        
        elif topic == TelemetryTopic.SENSOR_DATA:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "gps": {"latitude": 40.7128, "longitude": -74.0060, "accuracy": 2.5},
                "imu": {"roll": 0.5, "pitch": 1.2, "yaw": 45.0},
                "tof": {"left": 1250, "right": 2100},
                "environmental": {"temperature": 22.5, "humidity": 65.0, "pressure": 1013.25}
            }
        
        elif topic == TelemetryTopic.POWER_STATUS:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "battery": {
                    "voltage": 12.6,
                    "current": -2.5,
                    "percentage": 85.2,
                    "charging": False
                },
                "solar": {
                    "voltage": 14.2,
                    "current": 1.8,
                    "power": 25.6
                }
            }
        
        elif topic == TelemetryTopic.NAVIGATION_STATE:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "idle",
                "position": {"latitude": 40.7128, "longitude": -74.0060},
                "heading": 45.0,
                "velocity": 0.0,
                "waypoints_total": 0,
                "waypoints_completed": 0
            }
        
        return None


class TelemetryHubService:
    """Main telemetry hub service managing WebSocket connections and data flow"""
    
    def __init__(self):
        self.telemetry_exchange = TelemetryExchange.create_default_exchange()
        self.hub = self.telemetry_exchange.hub
        self.publisher = TelemetryPublisher(self.hub)
        
        # Client management
        self.clients: Dict[str, WebSocketClient] = {}
        self.client_subscriptions: Dict[str, List[ClientSubscription]] = {}
        
        # Service state
        self.running = False
        self.health_check_task: Optional[asyncio.Task] = None
        self.message_dispatch_task: Optional[asyncio.Task] = None
        
    async def start_service(self) -> bool:
        """Start the telemetry hub service"""
        try:
            logger.info("Starting telemetry hub service")
            
            self.running = True
            self.hub.hub_status = StreamStatus.ACTIVE
            
            # Start publisher
            await self.publisher.start_publishing()
            
            # Start message dispatch loop
            self.message_dispatch_task = asyncio.create_task(self._message_dispatch_loop())
            
            # Start health check loop
            self.health_check_task = asyncio.create_task(self._health_check_loop())
            
            logger.info("Telemetry hub service started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start telemetry hub service: {e}")
            return False
    
    async def stop_service(self):
        """Stop the telemetry hub service"""
        logger.info("Stopping telemetry hub service")
        
        self.running = False
        self.hub.hub_status = StreamStatus.STOPPED
        
        # Stop publisher
        await self.publisher.stop_publishing()
        
        # Cancel tasks
        if self.message_dispatch_task:
            self.message_dispatch_task.cancel()
        if self.health_check_task:
            self.health_check_task.cancel()
        
        # Disconnect all clients
        for client in list(self.clients.values()):
            await self.disconnect_client(client.client_id)
        
        logger.info("Telemetry hub service stopped")
    
    async def connect_client(self, websocket, client_id: str = None) -> str:
        """Connect a new WebSocket client"""
        if not client_id:
            client_id = f"client_{int(time.time())}_{len(self.clients)}"
        
        if len(self.clients) >= self.hub.max_concurrent_clients:
            logger.warning(f"Max clients reached, rejecting {client_id}")
            raise Exception("Maximum clients reached")
        
        # Accept WebSocket connection
        await websocket.accept()
        
        # Create client object
        client = WebSocketClient(client_id, websocket)
        self.clients[client_id] = client
        self.client_subscriptions[client_id] = []
        
        # Send connection confirmation
        connection_msg = {
            "event": "connection.established",
            "client_id": client_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "available_topics": [topic.value for topic in TelemetryTopic]
        }
        
        await client.send_message(json.dumps(connection_msg))
        
        logger.info(f"Client {client_id} connected ({len(self.clients)} total clients)")
        return client_id
    
    async def disconnect_client(self, client_id: str):
        """Disconnect a client"""
        if client_id not in self.clients:
            return
        
        client = self.clients[client_id]
        
        # Remove from all subscriptions
        self.hub.unsubscribe_client(client_id)
        
        # Close WebSocket
        try:
            await client.websocket.close()
        except:
            pass
        
        # Clean up
        del self.clients[client_id]
        if client_id in self.client_subscriptions:
            del self.client_subscriptions[client_id]
        
        logger.info(f"Client {client_id} disconnected ({len(self.clients)} total clients)")
    
    async def handle_client_message(self, client_id: str, message: str):
        """Handle message from client"""
        if client_id not in self.clients:
            return
        
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "subscribe":
                topic_str = data.get("topic")
                if topic_str:
                    try:
                        topic = TelemetryTopic(topic_str)
                        await self.subscribe_client_to_topic(client_id, topic)
                    except ValueError:
                        logger.warning(f"Invalid topic from client {client_id}: {topic_str}")
            
            elif message_type == "unsubscribe":
                topic_str = data.get("topic")
                if topic_str:
                    try:
                        topic = TelemetryTopic(topic_str)
                        await self.unsubscribe_client_from_topic(client_id, topic)
                    except ValueError:
                        logger.warning(f"Invalid topic from client {client_id}: {topic_str}")
            
            elif message_type == "set_cadence":
                cadence_hz = data.get("cadence_hz", 5.0)
                await self.set_client_cadence(client_id, cadence_hz)
            
            elif message_type == "ping":
                # Respond with pong
                pong_msg = {
                    "event": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await self.clients[client_id].send_message(json.dumps(pong_msg))
            
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from client {client_id}")
        except Exception as e:
            logger.error(f"Error handling message from client {client_id}: {e}")
    
    async def subscribe_client_to_topic(self, client_id: str, topic: TelemetryTopic):
        """Subscribe client to a telemetry topic"""
        if client_id not in self.clients:
            return False
        
        success = self.hub.subscribe_client(client_id, topic)
        
        if success:
            self.clients[client_id].subscriptions.add(topic)
            
            # Send confirmation
            confirm_msg = {
                "event": "subscription.confirmed",
                "topic": topic.value,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.clients[client_id].send_message(json.dumps(confirm_msg))
            
            logger.info(f"Client {client_id} subscribed to {topic}")
        
        return success
    
    async def unsubscribe_client_from_topic(self, client_id: str, topic: TelemetryTopic):
        """Unsubscribe client from a topic"""
        if client_id not in self.clients:
            return
        
        self.hub.unsubscribe_client(client_id, topic)
        self.clients[client_id].subscriptions.discard(topic)
        
        # Send confirmation
        confirm_msg = {
            "event": "unsubscription.confirmed",
            "topic": topic.value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.clients[client_id].send_message(json.dumps(confirm_msg))
        
        logger.info(f"Client {client_id} unsubscribed from {topic}")
    
    async def set_client_cadence(self, client_id: str, cadence_hz: float):
        """Set telemetry cadence for client"""
        # Clamp cadence between 1-10 Hz
        cadence_hz = max(1.0, min(10.0, cadence_hz))
        
        if client_id not in self.clients:
            return
        
        # Update hub cadence (simplified - would be per-client in real implementation)
        self.hub.global_rate_limit_hz = cadence_hz
        
        # Send confirmation
        confirm_msg = {
            "event": "cadence.updated",
            "cadence_hz": cadence_hz,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.clients[client_id].send_message(json.dumps(confirm_msg))
        
        logger.info(f"Client {client_id} cadence set to {cadence_hz} Hz")
    
    async def _message_dispatch_loop(self):
        """Main message dispatch loop"""
        while self.running:
            try:
                # Process pending messages
                messages_to_send = self.hub.pending_messages.copy()
                self.hub.pending_messages.clear()
                
                for message in messages_to_send:
                    await self._dispatch_message(message)
                
                await asyncio.sleep(0.01)  # 100 Hz dispatch rate
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message dispatch loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _dispatch_message(self, message: TelemetryMessage):
        """Dispatch message to subscribed clients"""
        subscribers = self.hub.get_topic_subscribers(message.topic)
        
        if not subscribers:
            return
        
        # Convert to WebSocket message format
        ws_message = message.to_websocket_message()
        
        # Send to all subscribers
        failed_clients = []
        for subscription in subscribers:
            client_id = subscription.client_id
            
            if client_id in self.clients:
                success = await self.clients[client_id].send_message(ws_message)
                if success:
                    subscription.messages_sent += 1
                    subscription.last_message_time = message.timestamp
                else:
                    subscription.messages_dropped += 1
                    failed_clients.append(client_id)
        
        # Disconnect failed clients
        for client_id in failed_clients:
            await self.disconnect_client(client_id)
        
        # Update statistics
        if message.topic in self.hub.stream_statistics:
            stats = self.hub.stream_statistics[message.topic]
            stats.messages_delivered += len(subscribers) - len(failed_clients)
            stats.messages_dropped += len(failed_clients)
    
    async def _health_check_loop(self):
        """Health check loop for connected clients"""
        while self.running:
            try:
                unhealthy_clients = []
                
                for client_id, client in self.clients.items():
                    if not client.is_healthy():
                        unhealthy_clients.append(client_id)
                    else:
                        # Send periodic ping
                        await client.ping()
                
                # Disconnect unhealthy clients
                for client_id in unhealthy_clients:
                    logger.info(f"Disconnecting unhealthy client {client_id}")
                    await self.disconnect_client(client_id)
                
                # Update hub health check timestamp
                self.hub.last_health_check = datetime.now(timezone.utc)
                
                await asyncio.sleep(self.hub.health_check_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(10)
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Get current service status"""
        return {
            "running": self.running,
            "hub_status": self.hub.hub_status,
            "connected_clients": len(self.clients),
            "max_clients": self.hub.max_concurrent_clients,
            "active_streams": len([s for s in self.hub.streams.values() if s.enabled]),
            "total_messages_sent": sum(
                stats.messages_delivered for stats in self.hub.stream_statistics.values()
            ),
            "pending_messages": len(self.hub.pending_messages),
            "last_health_check": self.hub.last_health_check
        }