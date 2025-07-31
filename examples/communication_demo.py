"""
Communication System Demonstration
Shows MQTT-based microservices coordination in action
"""

import asyncio
import logging
import json
import time
from pathlib import Path
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add src to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from src.communication import (
    MQTTBroker, MQTTClient, ServiceManager, MessageProtocol,
    SensorData, CommandMessage, StatusMessage, EventMessage,
    topic_manager
)


class MockSensorService:
    """Mock sensor service for demonstration"""
    
    def __init__(self, service_id: str):
        self.service_id = service_id
        self.service_manager = ServiceManager(
            service_id=service_id,
            service_type="sensors"
        )
        self.running = False
        self._publish_task = None
    
    async def initialize(self):
        """Initialize service"""
        logger.info(f"Initializing {self.service_id}")
        
        success = await self.service_manager.initialize(
            dependencies=[],
            endpoints={"data": f"sensors/{self.service_id}/data"},
            metadata={"sensor_type": "temperature", "units": "celsius"}
        )
        
        if success:
            # Add command handler
            self.service_manager.mqtt_client.add_command_handler(
                "get_reading", self._handle_get_reading
            )
            
            self.running = True
            self._publish_task = asyncio.create_task(self._publish_sensor_data())
        
        return success
    
    async def shutdown(self):
        """Shutdown service"""
        self.running = False
        if self._publish_task:
            self._publish_task.cancel()
            try:
                await self._publish_task
            except asyncio.CancelledError:
                pass
        await self.service_manager.shutdown()
    
    async def _publish_sensor_data(self):
        """Publish mock sensor data"""
        while self.running:
            try:
                # Generate mock data
                temperature = 20 + (time.time() % 60) / 6  # Varies between 20-30°C
                
                sensor_msg = SensorData.create(
                    sender=self.service_id,
                    sensor_type="temperature",
                    data={
                        "temperature": round(temperature, 2),
                        "timestamp": time.time()
                    },
                    device_id=self.service_id
                )
                
                topic = f"sensors/{self.service_id}/data"
                await self.service_manager.mqtt_client.publish(
                    topic_manager.get_full_topic(topic),
                    sensor_msg
                )
                
                await asyncio.sleep(5)  # Publish every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error publishing sensor data: {e}")
                await asyncio.sleep(5)
    
    async def _handle_get_reading(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get reading command"""
        temperature = 20 + (time.time() % 60) / 6
        return {
            "temperature": round(temperature, 2),
            "units": "celsius",
            "timestamp": time.time()
        }


class MockNavigationService:
    """Mock navigation service for demonstration"""
    
    def __init__(self, service_id: str):
        self.service_id = service_id
        self.service_manager = ServiceManager(
            service_id=service_id,
            service_type="navigation"
        )
        self.position = {"x": 0, "y": 0, "heading": 0}
        self.running = False
        self._update_task = None
    
    async def initialize(self):
        """Initialize service"""
        logger.info(f"Initializing {self.service_id}")
        
        success = await self.service_manager.initialize(
            dependencies=["sensor_service"],
            endpoints={"position": "navigation/position"},
            metadata={"capabilities": ["path_planning", "obstacle_avoidance"]}
        )
        
        if success:
            # Subscribe to sensor data
            await self.service_manager.mqtt_client.subscribe(
                topic_manager.get_full_topic("sensors/+/data")
            )
            self.service_manager.mqtt_client.add_message_handler(
                topic_manager.get_full_topic("sensors/+/data"),
                self._handle_sensor_data
            )
            
            # Add command handlers
            self.service_manager.mqtt_client.add_command_handler(
                "get_position", self._handle_get_position
            )
            self.service_manager.mqtt_client.add_command_handler(
                "move_to", self._handle_move_to
            )
            
            self.running = True
            self._update_task = asyncio.create_task(self._update_position())
        
        return success
    
    async def shutdown(self):
        """Shutdown service"""
        self.running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        await self.service_manager.shutdown()
    
    async def _handle_sensor_data(self, topic: str, message: MessageProtocol):
        """Handle incoming sensor data"""
        try:
            sensor_data = message.payload.get('data', {})
            logger.debug(f"Navigation received sensor data: {sensor_data}")
            
            # Mock processing - could use temperature for decision making
            temperature = sensor_data.get('temperature')
            if temperature and temperature > 35:
                await self.service_manager.emit_alert(
                    "high_temperature",
                    f"High temperature detected: {temperature}°C",
                    severity="warning"
                )
        except Exception as e:
            logger.error(f"Error handling sensor data: {e}")
    
    async def _update_position(self):
        """Update position periodically"""
        while self.running:
            try:
                # Simulate movement
                self.position["x"] += 0.1
                self.position["y"] += 0.05
                self.position["heading"] = (self.position["heading"] + 1) % 360
                
                # Publish position
                status_msg = StatusMessage.create(
                    sender=self.service_id,
                    status="moving",
                    details={"position": self.position.copy()}
                )
                
                topic = "navigation/position"
                await self.service_manager.mqtt_client.publish(
                    topic_manager.get_full_topic(topic),
                    status_msg,
                    retain=True
                )
                
                await asyncio.sleep(10)  # Update every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating position: {e}")
                await asyncio.sleep(10)
    
    async def _handle_get_position(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get position command"""
        return self.position.copy()
    
    async def _handle_move_to(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle move to command"""
        target_x = parameters.get('x', 0)
        target_y = parameters.get('y', 0)
        
        logger.info(f"Moving to ({target_x}, {target_y})")
        
        # Simulate movement
        self.position["x"] = target_x
        self.position["y"] = target_y
        
        await self.service_manager.emit_event(
            "movement_completed",
            {"target": {"x": target_x, "y": target_y}}
        )
        
        return {"success": True, "position": self.position.copy()}


class CommunicationMonitor:
    """Monitor communication system performance"""
    
    def __init__(self):
        self.service_manager = ServiceManager(
            service_id="monitor",
            service_type="system"
        )
        self.message_count = 0
        self.start_time = time.time()
        self.services_seen = set()
    
    async def initialize(self):
        """Initialize monitor"""
        logger.info("Initializing communication monitor")
        
        success = await self.service_manager.initialize(
            metadata={"role": "system_monitor"}
        )
        
        if success:
            # Subscribe to all system topics
            topics = [
                "system/+",
                "sensors/+/+",
                "navigation/+",
                "safety/+",
                "power/+"
            ]
            
            for topic in topics:
                await self.service_manager.mqtt_client.subscribe(
                    topic_manager.get_full_topic(topic)
                )
                self.service_manager.mqtt_client.add_message_handler(
                    topic_manager.get_full_topic(topic),
                    self._handle_message
                )
        
        return success
    
    async def shutdown(self):
        """Shutdown monitor"""
        await self.service_manager.shutdown()
    
    async def _handle_message(self, topic: str, message):
        """Handle incoming messages"""
        self.message_count += 1
        
        # Track services
        if hasattr(message, 'metadata'):
            self.services_seen.add(message.metadata.sender)
        
        # Log statistics periodically
        if self.message_count % 50 == 0:
            elapsed = time.time() - self.start_time
            rate = self.message_count / elapsed
            logger.info(f"Monitor stats: {self.message_count} messages, "
                       f"{rate:.1f} msg/sec, {len(self.services_seen)} services")


async def demo_basic_communication():
    """Demonstrate basic MQTT communication"""
    logger.info("=== Basic Communication Demo ===")
    
    # Start broker
    broker = MQTTBroker()
    if not await broker.start():
        logger.error("Failed to start MQTT broker")
        return False
    
    try:
        # Create clients
        client1 = MQTTClient("client1")
        client2 = MQTTClient("client2")
        
        # Initialize clients
        await client1.initialize()
        await client2.initialize()
        
        # Setup message handler
        messages_received = []
        
        def handle_message(topic, message):
            messages_received.append((topic, message))
            logger.info(f"Client2 received: {topic} -> {message}")
        
        client2.add_message_handler("test/topic", handle_message)
        await client2.subscribe("test/topic")
        
        # Wait for subscription to take effect
        await asyncio.sleep(1)
        
        # Send test messages
        for i in range(3):
            await client1.publish("test/topic", f"Hello {i}")
            await asyncio.sleep(0.5)
        
        # Wait for messages
        await asyncio.sleep(2)
        
        logger.info(f"Received {len(messages_received)} messages")
        
        # Cleanup
        await client1.shutdown()
        await client2.shutdown()
        
        return True
        
    finally:
        await broker.stop()


async def demo_service_coordination():
    """Demonstrate service coordination"""
    logger.info("=== Service Coordination Demo ===")
    
    # Start broker
    broker = MQTTBroker()
    if not await broker.start():
        logger.error("Failed to start MQTT broker")
        return False
    
    try:
        # Create services
        sensor_service = MockSensorService("sensor_service")
        nav_service = MockNavigationService("nav_service")
        monitor = CommunicationMonitor()
        
        # Initialize services
        await sensor_service.initialize()
        await monitor.initialize()
        await asyncio.sleep(2)  # Let sensor service start
        await nav_service.initialize()
        
        # Let services run
        logger.info("Services running... watching for 30 seconds")
        await asyncio.sleep(30)
        
        # Test command functionality
        logger.info("Testing inter-service communication")
        
        # Send command to sensor service
        result = await nav_service.service_manager.send_command(
            "sensor_service", "get_reading", {}
        )
        logger.info(f"Sensor reading: {result}")
        
        # Send command to navigation service
        result = await monitor.service_manager.send_command(
            "nav_service", "move_to", {"x": 10, "y": 5}
        )
        logger.info(f"Move command result: {result}")
        
        # Wait a bit more
        await asyncio.sleep(10)
        
        # Show service discovery
        services = nav_service.service_manager.discover_services()
        logger.info(f"Discovered services: {[s.service_id for s in services]}")
        
        # Cleanup
        await sensor_service.shutdown()
        await nav_service.shutdown()
        await monitor.shutdown()
        
        return True
        
    finally:
        await broker.stop()


async def demo_message_protocols():
    """Demonstrate message protocols"""
    logger.info("=== Message Protocols Demo ===")
    
    # Create different message types
    sensor_msg = SensorData.create(
        sender="demo_sensor",
        sensor_type="temperature",
        data={"temperature": 25.5, "humidity": 60.0}
    )
    
    command_msg = CommandMessage.create(
        sender="demo_controller",
        target="demo_sensor",
        command="calibrate",
        parameters={"offset": 1.5}
    )
    
    status_msg = StatusMessage.create(
        sender="demo_service",
        status="healthy",
        details={"uptime": 3600, "cpu_usage": 15.2}
    )
    
    event_msg = EventMessage.create(
        sender="demo_service",
        event_type="startup_complete",
        event_data={"version": "1.0.0", "startup_time": 5.2}
    )
    
    # Show serialization
    logger.info("Message serialization examples:")
    logger.info(f"Sensor data: {sensor_msg.to_json()}")
    logger.info(f"Command: {command_msg.to_json()}")
    logger.info(f"Status: {status_msg.to_json()}")
    logger.info(f"Event: {event_msg.to_json()}")
    
    # Show topic organization
    logger.info("\nTopic hierarchy:")
    hierarchy = topic_manager.get_topic_hierarchy()
    logger.info(json.dumps(hierarchy, indent=2))
    
    return True


async def demo_performance_monitoring():
    """Demonstrate performance monitoring"""
    logger.info("=== Performance Monitoring Demo ===")
    
    broker = MQTTBroker()
    if not await broker.start():
        return False
    
    try:
        client = MQTTClient("perf_test")
        await client.initialize()
        
        # Performance test
        start_time = time.time()
        message_count = 100
        
        logger.info(f"Sending {message_count} messages...")
        
        for i in range(message_count):
            sensor_msg = SensorData.create(
                sender="perf_sensor",
                sensor_type="test",
                data={"value": i, "timestamp": time.time()}
            )
            await client.publish("test/performance", sensor_msg)
        
        end_time = time.time()
        duration = end_time - start_time
        rate = message_count / duration
        
        logger.info(f"Performance: {rate:.1f} messages/second")
        
        # Show client stats
        stats = client.get_stats()
        logger.info(f"Client stats: {json.dumps(stats, indent=2)}")
        
        await client.shutdown()
        return True
        
    finally:
        await broker.stop()


async def main():
    """Main demonstration function"""
    logger.info("Starting Communication System Demonstration")
    
    demos = [
        ("Basic Communication", demo_basic_communication),
        ("Message Protocols", demo_message_protocols),
        ("Performance Monitoring", demo_performance_monitoring),
        ("Service Coordination", demo_service_coordination),
    ]
    
    for name, demo_func in demos:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {name}")
        logger.info(f"{'='*50}")
        
        try:
            success = await demo_func()
            if success:
                logger.info(f"✓ {name} completed successfully")
            else:
                logger.error(f"✗ {name} failed")
        except Exception as e:
            logger.error(f"✗ {name} failed with error: {e}")
        
        # Brief pause between demos
        await asyncio.sleep(2)
    
    logger.info("\nCommunication system demonstration completed!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo failed: {e}")
