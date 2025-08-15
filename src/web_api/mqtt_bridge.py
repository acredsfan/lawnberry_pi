"""
MQTT Bridge
Bridges MQTT communication with the web API, handling real-time data flow.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable, Set
from datetime import datetime
import weakref

from communication.client import MQTTClient
from .models import WebSocketMessage


class MQTTBridge:
    """Bridge between MQTT system and web API"""
    
    def __init__(self, mqtt_config: Dict[str, Any]):
        self.logger = logging.getLogger(__name__)
        self.config = mqtt_config
        self.mqtt_client: Optional[MQTTClient] = None
        self._connected = False
        
        # WebSocket connection management
        self._websocket_connections: Set[Any] = weakref.WeakSet()
        self._subscription_handlers: Dict[str, Set[Callable]] = {}
        
        # Data caching for quick API responses
        self._cached_data: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._cache_ttl = 60  # seconds
        
        # Topic mapping for API endpoints
        self._topic_mappings = {
            'system/status': 'system_status',
            'system/services/+/status': 'service_status',
            'sensors/+/data': 'sensor_data',
            'sensors/+/status': 'sensor_status',
            'navigation/position': 'navigation_position',
            'navigation/status': 'navigation_status',
            'navigation/path': 'navigation_path',
            'power/battery': 'battery_status',
            'power/solar': 'solar_status',
            'weather/current': 'weather_current',
            'weather/forecast': 'weather_forecast',
            'safety/alerts/+': 'safety_alert',
            'safety/emergency_stop': 'emergency_stop',
            'maps/boundaries': 'map_boundaries',
            'maps/coverage': 'map_coverage',
            'deployment/events': 'deployment_event',
            'deployment/status': 'deployment_status'
        }
    
    async def connect(self) -> bool:
        """Connect to MQTT broker"""
        try:
            self.mqtt_client = MQTTClient(
                client_id=self.config.client_id,
                config={
                    'broker_host': self.config.broker_host,
                    'broker_port': self.config.broker_port,
                    'keepalive': self.config.keepalive,
                    'clean_session': True,
                    'reconnect_delay': self.config.reconnect_delay,
                    'max_reconnect_delay': self.config.max_reconnect_delay,
                    'message_timeout': self.config.message_timeout,
                    'auth': {
                        'enabled': bool(self.config.username),
                        'username': self.config.username,
                        'password': self.config.password
                    },
                    'tls': {
                        'enabled': self.config.use_tls,
                        'ca_certs': self.config.ca_certs,
                        'certfile': self.config.cert_file,
                        'keyfile': self.config.key_file
                    }
                }
            )
            
            # Connect to MQTT
            initialized = await self.mqtt_client.initialize()
            if not initialized:
                raise ConnectionError("Failed to initialize MQTT client")
            
            # Subscribe to all relevant topics
            await self._setup_subscriptions()
            
            self._connected = True
            self.logger.info("MQTT bridge connected successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect MQTT bridge: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.mqtt_client:
            await self.mqtt_client.disconnect()
        self._connected = False
        self.logger.info("MQTT bridge disconnected")
    
    def is_connected(self) -> bool:
        """Check if MQTT bridge is connected"""
        return self._connected and self.mqtt_client and self.mqtt_client.is_connected()
    
    async def _setup_subscriptions(self):
        """Setup MQTT topic subscriptions"""
        if not self.mqtt_client:
            return
        
        # Subscribe to all mapped topics
        for topic in self._topic_mappings.keys():
            full_topic = f"lawnberry/{topic}"
            await self.mqtt_client.subscribe(full_topic)
            # Add message handler for this topic
            self.mqtt_client.add_message_handler(full_topic, self._handle_mqtt_message)
            self.logger.debug(f"Subscribed to {full_topic}")
    
    async def _handle_mqtt_message(self, topic: str, payload: Any):
        """Handle incoming MQTT messages. Accepts raw string or dict payloads and parses JSON if needed."""
        try:
            # Remove namespace prefix
            clean_topic = topic.replace("lawnberry/", "")
            
            # Ensure payload is a dictionary
            data: Dict[str, Any]
            if isinstance(payload, str):
                try:
                    data = json.loads(payload)
                except Exception:
                    # If not JSON, wrap as text
                    data = {"text": payload}
            elif isinstance(payload, bytes):
                try:
                    data = json.loads(payload.decode("utf-8"))
                except Exception:
                    data = {"text": payload.decode("utf-8", errors="ignore")}
            elif isinstance(payload, dict):
                data = payload
            else:
                # Attempt generic conversion
                try:
                    data = json.loads(json.dumps(payload, default=str))
                except Exception:
                    data = {"value": str(payload)}

            # Update cache
            self._cached_data[clean_topic] = data
            self._cache_timestamps[clean_topic] = datetime.now()
            
            # Find matching topic pattern
            message_type = self._get_message_type(clean_topic)
            if not message_type:
                return
            
            # Create WebSocket message
            ws_message = WebSocketMessage(
                type=message_type,
                topic=clean_topic,
                data=data
            )
            
            # Broadcast to WebSocket connections
            await self._broadcast_to_websockets(ws_message)
            
            # Notify subscription handlers
            await self._notify_handlers(clean_topic, data)
            
        except Exception as e:
            self.logger.error(f"Error handling MQTT message from {topic}: {e}")
    
    def _get_message_type(self, topic: str) -> Optional[str]:
        """Get message type from topic pattern"""
        for pattern, msg_type in self._topic_mappings.items():
            if self._topic_matches(topic, pattern):
                return msg_type
        return None
    
    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """Check if topic matches pattern with wildcards"""
        topic_parts = topic.split('/')
        pattern_parts = pattern.split('/')
        
        if len(topic_parts) != len(pattern_parts):
            return False
        
        for topic_part, pattern_part in zip(topic_parts, pattern_parts):
            if pattern_part == '+':
                continue
            elif pattern_part == '#':
                return True
            elif topic_part != pattern_part:
                return False
        
        return True
    
    async def _broadcast_to_websockets(self, message: WebSocketMessage):
        """Broadcast message to all WebSocket connections"""
        if not self._websocket_connections:
            return
        
        message_json = message.json()
        disconnected = set()
        
        for ws in self._websocket_connections:
            try:
                await ws.send_text(message_json)
            except Exception as e:
                self.logger.debug(f"WebSocket connection error: {e}")
                disconnected.add(ws)
        
        # Clean up disconnected connections
        for ws in disconnected:
            self._websocket_connections.discard(ws)
    
    async def _notify_handlers(self, topic: str, data: Dict[str, Any]):
        """Notify subscription handlers"""
        handlers = self._subscription_handlers.get(topic, set())
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(topic, data)
                else:
                    handler(topic, data)
            except Exception as e:
                self.logger.error(f"Error in subscription handler: {e}")
    
    def add_websocket_connection(self, websocket):
        """Add WebSocket connection for broadcasting"""
        self._websocket_connections.add(websocket)
        self.logger.debug(f"Added WebSocket connection. Total: {len(self._websocket_connections)}")
    
    def remove_websocket_connection(self, websocket):
        """Remove WebSocket connection"""
        self._websocket_connections.discard(websocket)
        self.logger.debug(f"Removed WebSocket connection. Total: {len(self._websocket_connections)}")
    
    def subscribe_to_topic(self, topic: str, handler: Callable):
        """Subscribe to specific topic updates"""
        if topic not in self._subscription_handlers:
            self._subscription_handlers[topic] = set()
        self._subscription_handlers[topic].add(handler)
    
    def unsubscribe_from_topic(self, topic: str, handler: Callable):
        """Unsubscribe from topic updates"""
        if topic in self._subscription_handlers:
            self._subscription_handlers[topic].discard(handler)
            if not self._subscription_handlers[topic]:
                del self._subscription_handlers[topic]
    
    async def publish_message(self, topic: str, data: Dict[str, Any], qos: int = 1) -> bool:
        """Publish message to MQTT"""
        if not self.mqtt_client or not self.is_connected():
            self.logger.error("MQTT client not connected")
            return False
        
        try:
            full_topic = f"lawnberry/{topic}"
            await self.mqtt_client.publish(full_topic, data, qos=qos)
            return True
        except Exception as e:
            self.logger.error(f"Error publishing to {topic}: {e}")
            return False
    
    def get_cached_data(self, topic: str) -> Optional[Dict[str, Any]]:
        """Get cached data for topic"""
        if topic not in self._cached_data:
            return None
        
        # Check if cache is still valid
        timestamp = self._cache_timestamps.get(topic)
        if timestamp and (datetime.now() - timestamp).total_seconds() > self._cache_ttl:
            # Cache expired
            self._cached_data.pop(topic, None)
            self._cache_timestamps.pop(topic, None)
            return None
        
        return self._cached_data[topic]
    
    def get_all_cached_data(self) -> Dict[str, Any]:
        """Get all cached data"""
        current_time = datetime.now()
        valid_data = {}
        
        for topic, data in self._cached_data.items():
            timestamp = self._cache_timestamps.get(topic)
            if timestamp and (current_time - timestamp).total_seconds() <= self._cache_ttl:
                valid_data[topic] = data
        
        return valid_data
    
    async def send_command(self, command: str, parameters: Dict[str, Any] = None, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """Send command and wait for response"""
        if not self.mqtt_client or not self.is_connected():
            return None
        
        try:
            command_data = {
                'command': command,
                'parameters': parameters or {},
                'timestamp': datetime.now().isoformat(),
                'request_id': f"api_{int(datetime.now().timestamp() * 1000)}"
            }
            
            # Publish command
            success = await self.publish_message('commands/execute', command_data, qos=2)
            if not success:
                return None
            
            # Wait for response (simplified - in production, use proper request/response correlation)
            await asyncio.sleep(0.1)  # Give some time for response
            return {'success': True, 'message': 'Command sent'}
            
        except Exception as e:
            self.logger.error(f"Error sending command {command}: {e}")
            return None
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            'connected': self.is_connected(),
            'websocket_connections': len(self._websocket_connections),
            'cached_topics': len(self._cached_data),
            'subscription_handlers': sum(len(handlers) for handlers in self._subscription_handlers.values())
        }
