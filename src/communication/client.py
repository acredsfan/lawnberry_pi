"""
MQTT Client with Advanced Features
Provides robust MQTT client with reconnection, QoS management, and message handling
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Callable, List, Set
from datetime import datetime
from collections import defaultdict, deque
import threading
from dataclasses import is_dataclass, asdict
import math


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from .message_protocols import MessageProtocol, MessageType, Priority, MessageValidator


class MQTTClient:
    """Advanced MQTT client with reliability features"""
    
    def __init__(self, client_id: str, config: Dict[str, Any] = None):
        self.client_id = client_id
        self.logger = logging.getLogger(f"{__name__}.{client_id}")
        # Deep-merge provided config with defaults so missing keys (e.g. queue_size) don't raise KeyError
        if config:
            self.config = self._merge_config(self._default_config(), config)
        else:
            self.config = self._default_config()
        
        # MQTT client
        self.client: Optional[mqtt.Client] = None
        self._connected = False
        self._connection_lock = asyncio.Lock()
        
        # Message handling
        self._message_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._command_handlers: Dict[str, Callable] = {}
        self._pending_responses: Dict[str, asyncio.Future] = {}
        
        # Quality of Service management
        self._qos_map = {
            Priority.LOW: 0,
            Priority.NORMAL: 1, 
            Priority.HIGH: 1,
            Priority.CRITICAL: 2
        }
        
        # Connection resilience
        self._reconnect_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._last_heartbeat = time.time()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Message queuing and retry
        self._message_queue = deque()
        self._failed_messages = deque()
        self._retry_counts: Dict[str, int] = {}
        self._max_retries = 3
        
        # Performance monitoring
        self._message_stats = {
            'sent': 0,
            'received': 0,
            'failed': 0,
            'reconnections': 0
        }
        
        # Rate limiting
        self._rate_limiter = defaultdict(deque)
        self._rate_limits = {
            # Allow higher throughput for sensor_data to reduce warning noise; service-level throttles still apply
            'sensor_data': 600,  # messages per minute
            'commands': 60,
            # Increase status to support periodic heartbeats and service status updates
            'status': 120
        }
    
    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge override into base (non-destructive for unspecified keys)"""
        for k, v in override.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                base[k] = self._merge_config(base[k], v)
            else:
                base[k] = v
        return base

    def _default_config(self) -> Dict[str, Any]:
        """Default client configuration"""
        return {
            'broker_host': 'localhost',
            'broker_port': 1883,
            'keepalive': 60,
            'clean_session': True,
            'reconnect_delay': 5,
            'max_reconnect_delay': 300,
            'reconnect_backoff': 2.0,
            'message_timeout': 30,
            'queue_size': 1000,
            'compression_enabled': True,
            'auth': {
                'enabled': False,
                'username': None,
                'password': None
            },
            'tls': {
                'enabled': False,
                'ca_certs': None,
                'certfile': None,
                'keyfile': None
            }
        }
    
    async def initialize(self) -> bool:
        """Initialize MQTT client"""
        if mqtt is None:
            self.logger.error("paho-mqtt not installed")
            return False
        
        try:
            self.logger.info(f"Initializing MQTT client: {self.client_id}")
            # Capture current running loop for cross-thread scheduling
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
            
            # Create client (paho-mqtt v2.x) with v1-style callbacks
            # Use keyword args to avoid positional misbinding across versions
            self.client = mqtt.Client(
                client_id=self.client_id,
                clean_session=self.config['clean_session'],
                callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
            )
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            self.client.on_publish = self._on_publish
            
            # Configure authentication
            if self.config['auth']['enabled']:
                self.client.username_pw_set(
                    self.config['auth']['username'],
                    self.config['auth']['password']
                )
            
            # Configure TLS
            if self.config['tls']['enabled']:
                self.client.tls_set(
                    ca_certs=self.config['tls']['ca_certs'],
                    certfile=self.config['tls']['certfile'],
                    keyfile=self.config['tls']['keyfile']
                )
            
            # Start connection
            await self._connect()
            
            if self._connected:
                # Start background tasks
                self._reconnect_task = asyncio.create_task(self._connection_monitor())
                self.logger.info("MQTT client initialized successfully")
                return True
            else:
                self.logger.error("Failed to establish initial connection")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to initialize MQTT client: {e}")
            return False
    
    async def connect(self) -> bool:
        """Public method to connect to MQTT broker"""
        return await self._connect()
    
    async def disconnect(self):
        """Public method to disconnect from MQTT broker"""
        if self.client and self._connected:
            self.client.loop_stop()
            self.client.disconnect()
            self._connected = False
            self.logger.info("MQTT client disconnected")
    
    def is_connected(self) -> bool:
        """Check if client is connected"""
        return self._connected
    
    async def shutdown(self):
        """Shutdown client gracefully"""
        self.logger.info("Shutting down MQTT client...")
        
        self._shutdown_event.set()
        
        # Cancel background tasks
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect client
        if self.client and self._connected:
            self.client.loop_stop()
            self.client.disconnect()
        
        self.logger.info("MQTT client shut down")
    
    async def _connect(self) -> bool:
        """Connect to MQTT broker"""
        async with self._connection_lock:
            if self._connected:
                return True
            
            try:
                self.logger.info(f"Connecting to MQTT broker at {self.config['broker_host']}:{self.config['broker_port']}")
                
                # Connect
                self.client.connect(
                    self.config['broker_host'],
                    self.config['broker_port'],
                    self.config['keepalive']
                )
                
                # Start network loop
                self.client.loop_start()
                
                # Wait for connection
                for _ in range(100):  # 10 second timeout
                    if self._connected:
                        break
                    await asyncio.sleep(0.1)
                
                if self._connected:
                    self.logger.info("Connected to MQTT broker")
                    return True
                else:
                    self.logger.error("Connection timeout")
                    return False
                    
            except Exception as e:
                self.logger.error(f"Connection failed: {e}")
                return False
    
    def _on_connect(self, client, userdata, flags, rc):
        """Handle connection event"""
        if rc == 0:
            self._connected = True
            self._last_heartbeat = time.time()
            self._message_stats['reconnections'] += 1
            self.logger.info(f"Connected to MQTT broker (rc={rc})")
        else:
            self.logger.error(f"Connection failed (rc={rc})")
    
    def _on_disconnect(self, client, userdata, rc):
        """Handle disconnection event"""
        self._connected = False
        if rc != 0:
            self.logger.warning(f"Unexpected disconnection (rc={rc})")
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming message"""
        try:
            # Update stats
            self._message_stats['received'] += 1
            self._last_heartbeat = time.time()
            
            # Decode message
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            self.logger.debug(f"Received message on {topic}: {len(payload)} bytes")
            
            # Parse message if it's a protocol message
            try:
                message = MessageProtocol.from_json(payload)
                if MessageValidator.validate_message(message):
                    self._schedule_coroutine(self._handle_protocol_message(topic, message))
                else:
                    self.logger.warning(f"Invalid protocol message on {topic}")
            except (json.JSONDecodeError, KeyError):
                # Handle as raw message
                self._schedule_coroutine(self._handle_raw_message(topic, payload))
                
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
    
    def _on_publish(self, client, userdata, mid):
        """Handle publish confirmation"""
        self.logger.debug(f"Message published (mid={mid})")

    def _schedule_coroutine(self, coro):
        """Schedule coroutine safely from non-async threads into the captured event loop."""
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(coro, self._loop)
            else:
                # As a fallback (shouldn't happen in normal service runtime), attempt to get a loop
                loop = None
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass
                if loop and loop.is_running():
                    loop.create_task(coro)
                else:
                    self.logger.error("No running event loop to schedule coroutine")
        except Exception as e:
            self.logger.error(f"Failed to schedule coroutine: {e}")
    
    async def _handle_protocol_message(self, topic: str, message: MessageProtocol):
        """Handle structured protocol message"""
        try:
            msg_type = message.metadata.message_type
            
            # Handle responses
            if msg_type == MessageType.RESPONSE and message.metadata.correlation_id:
                correlation_id = message.metadata.correlation_id
                if correlation_id in self._pending_responses:
                    future = self._pending_responses.pop(correlation_id)
                    if not future.done():
                        future.set_result(message.payload)
            
            # Handle commands
            elif msg_type == MessageType.COMMAND:
                await self._handle_command_message(message)
            
            # Call registered handlers (supports wildcard patterns like + and #)
            for pattern, handlers in list(self._message_handlers.items()):
                if self._topic_matches(pattern, topic):
                    for handler in list(handlers):
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(topic, message)
                            else:
                                # Support handlers that are regular functions but return a coroutine
                                result = handler(topic, message)
                                if asyncio.iscoroutine(result):
                                    self._schedule_coroutine(result)
                        except Exception as e:
                            self.logger.error(f"Handler error for {topic}: {e}")
                        
        except Exception as e:
            self.logger.error(f"Error handling protocol message: {e}")
    
    async def _handle_raw_message(self, topic: str, payload: str):
        """Handle raw message with wildcard-aware dispatch"""
        for pattern, handlers in list(self._message_handlers.items()):
            if self._topic_matches(pattern, topic):
                for handler in list(handlers):
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(topic, payload)
                        else:
                            # Support regular functions that return a coroutine
                            result = handler(topic, payload)
                            if asyncio.iscoroutine(result):
                                self._schedule_coroutine(result)
                    except Exception as e:
                        self.logger.error(f"Handler error for {topic}: {e}")

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        """Check if MQTT topic matches subscription pattern with + and # wildcards."""
        # Exact match fast-path
        if pattern == topic:
            return True
        p_parts = pattern.split('/')
        t_parts = topic.split('/')
        for i, p in enumerate(p_parts):
            if p == '#':
                return True
            if i >= len(t_parts):
                return False
            if p == '+':
                continue
            if p != t_parts[i]:
                return False
        return len(t_parts) == len(p_parts)
    
    async def _handle_command_message(self, message: MessageProtocol):
        """Handle command message"""
        try:
            command = message.payload.get('command')
            target = message.payload.get('target')
            
            if target == self.client_id and command in self._command_handlers:
                handler = self._command_handlers[command]
                
                try:
                    if asyncio.iscoroutinefunction(handler):
                        result = await handler(message.payload.get('parameters', {}))
                    else:
                        result = handler(message.payload.get('parameters', {}))
                    
                    # Send response
                    from .message_protocols import ResponseMessage
                    response = ResponseMessage.create(
                        sender=self.client_id,
                        correlation_id=message.metadata.correlation_id,
                        success=True,
                        result=result
                    )
                    
                    response_topic = f"lawnberry/responses/{message.metadata.sender}"
                    await self.publish(response_topic, response)
                    
                except Exception as e:
                    # Send error response
                    from .message_protocols import ResponseMessage
                    response = ResponseMessage.create(
                        sender=self.client_id,
                        correlation_id=message.metadata.correlation_id,
                        success=False,
                        error=str(e)
                    )
                    
                    response_topic = f"lawnberry/responses/{message.metadata.sender}"
                    await self.publish(response_topic, response)
                    
        except Exception as e:
            self.logger.error(f"Error handling command: {e}")
    
    async def _connection_monitor(self):
        """Monitor connection and handle reconnections"""
        reconnect_delay = self.config['reconnect_delay']
        
        while not self._shutdown_event.is_set():
            try:
                if not self._connected:
                    self.logger.info(f"Attempting reconnection in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    
                    if await self._connect():
                        reconnect_delay = self.config['reconnect_delay']  # Reset delay
                    else:
                        # Exponential backoff
                        reconnect_delay = min(
                            reconnect_delay * self.config['reconnect_backoff'],
                            self.config['max_reconnect_delay']
                        )
                
                # Process queued messages
                await self._process_message_queue()
                
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Connection monitor error: {e}")
                await asyncio.sleep(5)
    
    async def _process_message_queue(self):
        """Process queued messages"""
        if not self._connected or not self._message_queue:
            return
        
        processed = 0
        while self._message_queue and processed < 10:  # Process max 10 per cycle
            try:
                topic, message, qos = self._message_queue.popleft()
                result = self.client.publish(topic, message, qos=qos)
                
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    self._message_stats['sent'] += 1
                else:
                    # Re-queue on failure
                    self._message_queue.appendleft((topic, message, qos))
                    break
                
                processed += 1
                
            except Exception as e:
                self.logger.error(f"Error processing queued message: {e}")
                break
    
    def _check_rate_limit(self, category: str) -> bool:
        """Check if rate limit allows message"""
        if category not in self._rate_limits:
            return True
        
        now = time.time()
        minute_ago = now - 60
        
        # Clean old entries
        queue = self._rate_limiter[category]
        while queue and queue[0] < minute_ago:
            queue.popleft()
        
        # Check limit
        if len(queue) >= self._rate_limits[category]:
            return False
        
        # Add current message
        queue.append(now)
        return True
    
    async def publish(self, topic: str, message: Any, qos: int = 1, retain: bool = False) -> bool:
        """Publish message with reliability features"""
        try:
            # Helper: sanitize objects so JSON never contains NaN/Infinity (invalid per RFC 8259)
            def _sanitize_for_json(obj: Any):
                try:
                    # Replace non-finite floats with None
                    if isinstance(obj, float):
                        return obj if math.isfinite(obj) else None
                    # ints are always fine
                    if isinstance(obj, (int, str, bool)) or obj is None:
                        return obj
                    if isinstance(obj, list):
                        return [_sanitize_for_json(i) for i in obj]
                    if isinstance(obj, dict):
                        return {k: _sanitize_for_json(v) for k, v in obj.items()}
                    # Dataclasses converted above; for unknown objects, string-coerce
                    return obj
                except Exception:
                    # Fallback: string representation
                    try:
                        return str(obj)
                    except Exception:
                        return None

            # Serialize message
            if isinstance(message, MessageProtocol):
                payload = message.to_json()
                category = message.metadata.message_type.value
                qos = self._qos_map.get(message.metadata.priority, qos)
                # Sanitize MessageProtocol JSON payload to remove NaN/Infinity
                try:
                    parsed = json.loads(payload)
                    parsed = _sanitize_for_json(parsed)
                    payload = json.dumps(parsed, cls=DateTimeEncoder, default=str, allow_nan=False)
                except Exception:
                    # If parsing fails, keep original payload (best effort)
                    pass
            else:
                # Convert dataclass instances
                if is_dataclass(message):
                    message = asdict(message)
                # Objects with to_dict support
                elif hasattr(message, 'to_dict') and callable(getattr(message, 'to_dict')):
                    try:
                        message = message.to_dict()
                    except Exception:
                        pass
                # Ensure datetime objects inside structures become ISO strings
                def _convert(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    if isinstance(obj, list):
                        return [_convert(i) for i in obj]
                    if isinstance(obj, dict):
                        return {k: _convert(v) for k, v in obj.items()}
                    return obj
                if isinstance(message, (dict, list)):
                    message = _convert(message)
                    # Sanitize numbers to avoid NaN/Infinity in JSON
                    message = _sanitize_for_json(message)
                payload = message if isinstance(message, str) else json.dumps(message, cls=DateTimeEncoder, default=str, allow_nan=False)
                category = 'general'
            
            # Check rate limiting
            if not self._check_rate_limit(category):
                self.logger.warning(f"Rate limit exceeded for {category}")
                return False
            
            # Publish or queue
            if self._connected:
                result = self.client.publish(topic, payload, qos=qos, retain=retain)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    self._message_stats['sent'] += 1
                    self.logger.debug(f"Published to {topic}: {len(payload)} bytes")
                    return True
                else:
                    self.logger.warning(f"Publish failed (rc={result.rc}), queuing message")
            
            # Queue message if not connected or publish failed
            if len(self._message_queue) < self.config['queue_size']:
                self._message_queue.append((topic, payload, qos))
                return True
            else:
                self.logger.error("Message queue full, dropping message")
                self._message_stats['failed'] += 1
                return False
                
        except Exception as e:
            self.logger.error(f"Publish error: {e}")
            self._message_stats['failed'] += 1
            return False
    
    async def subscribe(self, topic: str, qos: int = 1) -> bool:
        """Subscribe to topic"""
        if not self._connected:
            self.logger.warning(f"Not connected, cannot subscribe to {topic}")
            return False
        
        try:
            result, mid = self.client.subscribe(topic, qos)
            if result == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"Subscribed to {topic} (qos={qos})")
                return True
            else:
                self.logger.error(f"Subscribe failed (rc={result})")
                return False
        except Exception as e:
            self.logger.error(f"Subscribe error: {e}")
            return False
    
    def add_message_handler(self, topic: str, handler: Callable):
        """Add message handler for topic"""
        self._message_handlers[topic].append(handler)
        self.logger.debug(f"Added handler for {topic}")
    
    def add_command_handler(self, command: str, handler: Callable):
        """Add command handler"""
        self._command_handlers[command] = handler
        self.logger.debug(f"Added command handler for {command}")
    
    async def send_command(self, target: str, command: str, parameters: Dict[str, Any] = None, timeout: float = 30) -> Any:
        """Send command and wait for response"""
        from .message_protocols import CommandMessage
        
        cmd_msg = CommandMessage.create(self.client_id, target, command, parameters)
        correlation_id = cmd_msg.metadata.correlation_id
        
        # Create response future
        future = asyncio.Future()
        self._pending_responses[correlation_id] = future
        
        try:
            # Publish command
            cmd_topic = f"lawnberry/commands/{target}"
            await self.publish(cmd_topic, cmd_msg)
            
            # Wait for response
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
            
        except asyncio.TimeoutError:
            self._pending_responses.pop(correlation_id, None)
            raise
        except Exception as e:
            self._pending_responses.pop(correlation_id, None)
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        return {
            'connected': self._connected,
            'client_id': self.client_id,
            'last_heartbeat': self._last_heartbeat,
            'message_stats': self._message_stats.copy(),
            'queue_size': len(self._message_queue),
            'pending_responses': len(self._pending_responses),
            'handlers': {
                'message_handlers': len(self._message_handlers),
                'command_handlers': len(self._command_handlers)
            }
        }
