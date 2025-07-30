# MQTT Communication System

A comprehensive MQTT-based communication infrastructure for the Lawnberry autonomous mower, enabling reliable microservices coordination with <50ms message latency and full offline operation capability.

## Overview

The communication system provides:
- **Local MQTT Broker**: Mosquitto-based broker with no external dependencies
- **Hierarchical Topics**: Organized topic structure for all system components
- **Message Protocols**: Standardized JSON message formats with validation
- **Service Coordination**: Automatic service discovery and health monitoring
- **Reliability Features**: Auto-reconnection, message queuing, and error handling
- **Performance Optimization**: Message compression, rate limiting, and QoS management

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web UI/API    │    │  Navigation     │    │  Safety System  │
│   Service       │    │  Service        │    │  Service        │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────┴─────────────┐
                    │   MQTT Broker (Local)     │
                    │   Topic Manager           │
                    │   Message Protocols       │
                    └─────────────┬─────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
┌─────────┴───────┐    ┌─────────┴───────┐    ┌─────────┴───────┐
│   Hardware      │    │   Power Mgmt    │    │   Vision        │
│   Interface     │    │   Service       │    │   Service       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Quick Start

### Installation

```bash
# Install dependencies
pip install paho-mqtt pyyaml

# Install Mosquitto broker (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install mosquitto mosquitto-clients

# For other systems, see: https://mosquitto.org/download/
```

### Basic Usage

```python
import asyncio
from src.communication import MQTTBroker, ServiceManager

async def main():
    # Start local MQTT broker
    broker = MQTTBroker()
    await broker.start()
    
    # Create service
    service = ServiceManager("my_service", "sensor")
    await service.initialize()
    
    # Emit events
    await service.emit_event("sensor_reading", {"temperature": 25.5})
    
    # Send commands
    result = await service.send_command("target_service", "get_status")
    
    # Cleanup
    await service.shutdown()
    await broker.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### Run the Demo

```bash
cd examples
python communication_demo.py
```

## Core Components

### 1. MQTT Broker (MQTTBroker)

Manages the local Mosquitto MQTT broker instance.

```python
from src.communication import MQTTBroker

# Create and configure broker
broker = MQTTBroker({
    'port': 1883,
    'websockets': {'enabled': True, 'port': 9001},
    'persistence': True
})

# Start broker
await broker.start()

# Check status
status = await broker.get_status()
print(f"Broker running: {status['running']}")

# Stop broker
await broker.stop()
```

**Features:**
- Automatic configuration file generation
- WebSocket support for web UI
- Message persistence
- Authentication and TLS support
- Health monitoring

### 2. MQTT Client (MQTTClient)

Advanced MQTT client with reliability and performance features.

```python
from src.communication import MQTTClient

# Create client
client = MQTTClient("my_client", {
    'broker_host': 'localhost',
    'reconnect_delay': 5,
    'queue_size': 1000
})

await client.initialize()

# Subscribe to topics
await client.subscribe("sensors/+/data")

# Add message handler
def handle_sensor_data(topic, message):
    print(f"Received: {topic} -> {message}")

client.add_message_handler("sensors/+/data", handle_sensor_data)

# Publish messages
await client.publish("sensors/temp1/data", {"temperature": 25.5})

# Send commands with response
result = await client.send_command("target_service", "get_reading")
```

**Features:**
- Automatic reconnection with exponential backoff
- Message queuing during disconnections
- Rate limiting and QoS management
- Command/response pattern
- Performance monitoring

### 3. Service Manager (ServiceManager)

Coordinates microservices with automatic discovery and health monitoring.

```python
from src.communication import ServiceManager

# Create service
service = ServiceManager("sensor_service", "sensors")

# Initialize with dependencies
await service.initialize(
    dependencies=["hardware_interface"],
    endpoints={"data": "sensors/temp/data"},
    metadata={"sensor_type": "temperature"}
)

# Service discovery
services = service.discover_services("navigation")
print(f"Found navigation services: {[s.service_id for s in services]}")

# Event handling
def handle_emergency(event_data):
    print(f"Emergency: {event_data}")

service.add_event_handler("emergency_stop", handle_emergency)

# Emit events and alerts
await service.emit_event("sensor_reading", {"value": 25.5})
await service.emit_alert("high_temperature", "Temperature > 40°C", "warning")
```

**Features:**
- Automatic service discovery
- Dependency resolution
- Health monitoring with heartbeats
- Event system
- Graceful shutdown handling

### 4. Message Protocols

Standardized message formats for reliable communication.

```python
from src.communication import SensorData, CommandMessage, EventMessage

# Create sensor data message
sensor_msg = SensorData.create(
    sender="temp_sensor",
    sensor_type="temperature",
    data={"temperature": 25.5, "units": "celsius"}
)

# Create command message
cmd_msg = CommandMessage.create(
    sender="controller",
    target="sensor",
    command="calibrate",
    parameters={"offset": 1.5}
)

# Serialize for transmission
json_str = sensor_msg.to_json()

# Deserialize received message
received_msg = MessageProtocol.from_json(json_str)
```

**Message Types:**
- **SensorData**: Sensor readings and measurements
- **CommandMessage**: Service commands with parameters
- **ResponseMessage**: Command responses
- **StatusMessage**: Service health and status
- **EventMessage**: System events and notifications
- **AlertMessage**: Safety alerts and warnings

### 5. Topic Manager

Manages hierarchical MQTT topic structure and routing.

```python
from src.communication import topic_manager

# Get full topic with namespace
topic = topic_manager.get_full_topic("sensors/temp/data")
# Returns: "lawnberry/sensors/temp/data"

# Find topic definition
definition = topic_manager.find_topic_definition("sensors/temp/data")
print(f"QoS: {definition.qos}, Retained: {definition.retained}")

# Get recommended settings
qos = topic_manager.get_recommended_qos("commands/navigation")
should_retain = topic_manager.should_retain("system/health")

# Service-specific topics
topics = topic_manager.get_topics_for_service("navigation")
```

## Topic Hierarchy

### Sensor Topics
- `lawnberry/sensors/{sensor_id}/data` - Sensor readings (QoS 1)
- `lawnberry/sensors/{sensor_id}/status` - Sensor health (QoS 1, retained)

### Navigation Topics
- `lawnberry/navigation/position` - Current position (QoS 1, retained)
- `lawnberry/navigation/path` - Current path (QoS 1, retained)
- `lawnberry/navigation/status` - Navigation status (QoS 1, retained)

### Safety Topics
- `lawnberry/safety/alerts/{type}` - Safety alerts (QoS 2, retained)
- `lawnberry/safety/emergency_stop` - Emergency stop (QoS 2, retained)
- `lawnberry/safety/hazards` - Detected hazards (QoS 2)

### Power Topics
- `lawnberry/power/battery` - Battery status (QoS 1, retained)
- `lawnberry/power/solar` - Solar charging (QoS 1, retained)
- `lawnberry/power/consumption` - Power usage (QoS 1)

### Command Topics
- `lawnberry/commands/{service}` - Service commands (QoS 2)
- `lawnberry/responses/{service}` - Command responses (QoS 2)

### System Topics
- `lawnberry/system/health` - Overall health (QoS 1, retained)
- `lawnberry/system/services/{service}/status` - Service status (QoS 1, retained)
- `lawnberry/system/events/{type}` - System events (QoS 1)

## Configuration

Configuration is managed through `config/communication.yaml`:

```yaml
# MQTT Broker
broker:
  port: 1883
  websockets:
    enabled: true
    port: 9001

# Performance tuning
client:
  reconnect_delay: 5
  queue_size: 1000
  rate_limits:
    sensor_data: 100  # messages per minute

# Service coordination
services:
  heartbeat_interval: 30
  heartbeat_timeout: 90
```

## Performance Features

### Rate Limiting
Prevents message flooding with configurable limits per topic type:
```python
# Automatic rate limiting based on topic
client.publish("sensors/temp/data", data)  # Limited to 100/min
client.publish("commands/navigation", cmd)  # Limited to 60/min
```

### Message Compression
Automatic compression for large payloads:
```python
# Messages > 1KB are automatically compressed
large_data = {"readings": [i for i in range(1000)]}
await client.publish("sensors/bulk_data", large_data)
```

### QoS Management
Automatic QoS selection based on message importance:
- **QoS 0**: Non-critical data (vision frame analysis)
- **QoS 1**: Important data (sensor readings, status)
- **QoS 2**: Critical commands (safety alerts, emergency stop)

### Connection Resilience
- Exponential backoff reconnection
- Message queuing during disconnections
- Automatic subscription restoration
- Connection health monitoring

## Integration Examples

### Hardware Interface Service

```python
from src.communication import ServiceManager, SensorData

class HardwareService:
    def __init__(self):
        self.service_manager = ServiceManager("hardware_interface", "hardware")
    
    async def initialize(self):
        await self.service_manager.initialize()
        
        # Add command handlers
        self.service_manager.mqtt_client.add_command_handler(
            "read_sensor", self.read_sensor
        )
    
    async def publish_sensor_data(self, sensor_type, data):
        """Publish sensor reading"""
        msg = SensorData.create("hardware_interface", sensor_type, data)
        topic = f"sensors/{sensor_type}/data"
        await self.service_manager.mqtt_client.publish(topic, msg)
    
    async def read_sensor(self, parameters):
        """Handle sensor read command"""
        sensor_id = parameters.get("sensor_id")
        # Read actual sensor...
        return {"value": 25.5, "timestamp": time.time()}
```

### Navigation Service

```python
class NavigationService:
    def __init__(self):
        self.service_manager = ServiceManager("navigation", "navigation")
    
    async def initialize(self):
        await self.service_manager.initialize(
            dependencies=["hardware_interface", "sensor_fusion"]
        )
        
        # Subscribe to sensor data
        await self.service_manager.mqtt_client.subscribe("sensors/+/data")
        self.service_manager.mqtt_client.add_message_handler(
            "sensors/+/data", self.handle_sensor_data
        )
    
    async def handle_sensor_data(self, topic, message):
        """Process incoming sensor data"""
        if message.payload["sensor_type"] == "gps":
            await self.update_position(message.payload["data"])
    
    async def update_position(self, gps_data):
        """Update current position"""
        position_msg = StatusMessage.create(
            "navigation",
            "moving", 
            {"position": gps_data}
        )
        await self.service_manager.mqtt_client.publish(
            "navigation/position", position_msg, retain=True
        )
```

### Safety Monitoring Service

```python
class SafetyService:
    def __init__(self):
        self.service_manager = ServiceManager("safety", "safety")
    
    async def initialize(self):
        await self.service_manager.initialize(
            dependencies=["hardware_interface", "vision_service"]
        )
        
        # Subscribe to all sensor data and vision detections
        topics = ["sensors/+/data", "vision/detections"]
        for topic in topics:
            await self.service_manager.mqtt_client.subscribe(topic)
            self.service_manager.mqtt_client.add_message_handler(
                topic, self.analyze_safety
            )
    
    async def analyze_safety(self, topic, message):
        """Analyze incoming data for safety hazards"""
        if "person_detected" in str(message.payload):
            await self.emergency_stop("Person detected in area")
    
    async def emergency_stop(self, reason):
        """Trigger emergency stop"""
        await self.service_manager.emit_alert(
            "emergency_stop", 
            f"Emergency stop: {reason}",
            "critical"
        )
        
        # Publish to emergency stop topic
        stop_msg = AlertMessage.create(
            "safety", "emergency_stop", reason, "critical"
        )
        await self.service_manager.mqtt_client.publish(
            "safety/emergency_stop", stop_msg, retain=True
        )
```

## External Integrations

### Web UI WebSocket Bridge

```python
import websockets
import json

class WebSocketBridge:
    def __init__(self):
        self.service_manager = ServiceManager("websocket_bridge", "web")
        self.clients = set()
    
    async def start_websocket_server(self):
        """Start WebSocket server for web UI"""
        async def handle_client(websocket, path):
            self.clients.add(websocket)
            try:
                async for message in websocket:
                    await self.handle_web_message(websocket, message)
            finally:
                self.clients.remove(websocket)
        
        server = await websockets.serve(handle_client, "localhost", 9002)
        return server
    
    async def forward_to_web_clients(self, topic, message):
        """Forward MQTT messages to web clients"""
        if self.clients:
            web_msg = {
                "topic": topic,
                "data": message.payload if hasattr(message, 'payload') else message
            }
            
            # Send to all connected web clients
            disconnected = set()
            for client in self.clients:
                try:
                    await client.send(json.dumps(web_msg))
                except:
                    disconnected.add(client)
            
            # Remove disconnected clients
            self.clients -= disconnected
```

### Home Assistant Integration

```python
class HomeAssistantIntegration:
    def __init__(self):
        self.service_manager = ServiceManager("ha_integration", "integration")
        self.discovery_prefix = "homeassistant"
    
    async def publish_discovery_config(self):
        """Publish Home Assistant MQTT discovery configuration"""
        
        # Battery sensor
        battery_config = {
            "name": "Lawnberry Battery",
            "device_class": "battery",
            "unit_of_measurement": "%",
            "state_topic": "lawnberry/power/battery",
            "value_template": "{{ value_json.charge_percentage }}",
            "unique_id": "lawnberry_battery",
            "device": {
                "identifiers": ["lawnberry_01"],
                "name": "Lawnberry Mower",
                "model": "Autonomous Mower v1.0"
            }
        }
        
        discovery_topic = f"{self.discovery_prefix}/sensor/lawnberry_battery/config"
        await self.service_manager.mqtt_client.publish(
            discovery_topic, json.dumps(battery_config), retain=True
        )
```

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
python -m pytest tests/test_communication_system.py -v

# Run specific test categories
python -m pytest tests/test_communication_system.py::TestMessageProtocols -v
python -m pytest tests/test_communication_system.py::TestMQTTClient -v
python -m pytest tests/test_communication_system.py::TestPerformance -v

# Run with coverage
pip install pytest-cov
python -m pytest tests/test_communication_system.py --cov=src.communication --cov-report=html
```

### Test Coverage

The test suite provides comprehensive coverage:
- **Message Protocols**: Serialization, validation, type safety
- **MQTT Client**: Connection handling, message publishing, command/response
- **Service Manager**: Service discovery, health monitoring, event handling
- **Topic Manager**: Pattern matching, QoS recommendations, hierarchy
- **Performance**: Throughput, latency, topic matching efficiency
- **Integration**: End-to-end communication flows

## Monitoring and Debugging

### Performance Metrics

```python
# Get client statistics
stats = client.get_stats()
print(f"Messages sent: {stats['message_stats']['sent']}")
print(f"Queue size: {stats['queue_size']}")
print(f"Connected: {stats['connected']}")

# Get service statistics  
service_stats = service.get_stats()
print(f"Known services: {service_stats['known_services']}")
print(f"Uptime: {service_stats['uptime']:.1f}s")
```

### Debugging Tools

```python
# Enable debug logging
import logging
logging.getLogger("src.communication").setLevel(logging.DEBUG)

# Generate topic documentation
doc = topic_manager.generate_topic_documentation()
print(doc)

# Monitor all messages (development only)
def debug_handler(topic, message):
    print(f"DEBUG: {topic} -> {message}")

client.add_message_handler("#", debug_handler)  # Subscribe to all topics
```

### Health Monitoring

```python
# Check broker status
broker_status = await broker.get_status()
if not broker_status['running']:
    print("MQTT broker is not running!")

# Check service health
services = service_manager.discover_services()
for svc in services:
    if svc.state != ServiceState.HEALTHY:
        print(f"Service {svc.service_id} is {svc.state.value}")

# Monitor message latency
import time
start = time.time()
result = await client.send_command("target", "ping")
latency = (time.time() - start) * 1000
print(f"Command latency: {latency:.1f}ms")
```

## Troubleshooting

### Common Issues

**1. Broker won't start**
```bash
# Check if mosquitto is installed
which mosquitto

# Check if port is available
netstat -ln | grep :1883

# Check logs
tail -f /var/log/mosquitto/mosquitto.log
```

**2. Connection failures**
```python
# Check client logs
logging.getLogger("src.communication.client").setLevel(logging.DEBUG)

# Verify broker is running
broker_status = await broker.get_status()
print(f"Broker running: {broker_status['running']}")
```

**3. Message not received**
```python
# Check topic subscription
await client.subscribe("your/topic/here")

# Verify topic pattern matching
matched = topic_manager.match_topic_pattern("your/topic", "your/+")
print(f"Pattern matches: {matched}")

# Check rate limiting
rate_limit = topic_manager.get_rate_limit("your/topic")
print(f"Rate limit: {rate_limit} msg/min")
```

**4. High latency**
```python
# Check message queue size
stats = client.get_stats()
if stats['queue_size'] > 100:
    print("Message queue is building up - check network connectivity")

# Monitor broker resources
broker_status = await broker.get_status()
# Check CPU/memory usage of mosquitto process
```

## Security Considerations

### Authentication (Production)
```yaml
# config/communication.yaml
broker:
  auth:
    enabled: true
    username: "lawnberry_service"
    password: "secure_random_password"
```

### TLS Encryption (Production)
```yaml
broker:
  tls:
    enabled: true
    cert_file: "/path/to/server.crt"
    key_file: "/path/to/server.key"
    ca_file: "/path/to/ca.crt"
```

### Message Validation
All messages are automatically validated for:
- Required fields presence
- Data type correctness
- Payload size limits
- Message age limits

## Performance Specifications

- **Message Latency**: <50ms for local MQTT communication
- **Throughput**: >1000 messages/second for sensor data
- **Reliability**: Automatic reconnection with exponential backoff
- **Offline Operation**: Full functionality without internet connectivity
- **Memory Usage**: <100MB for complete communication system
- **CPU Usage**: <5% on Raspberry Pi 4 under normal load

## License

This communication system is part of the Lawnberry autonomous mower project.
