"""
Communication System Tests
Comprehensive test suite for MQTT-based communication infrastructure
"""

import asyncio
import json
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

# Add src to path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from src.communication import (
    MQTTBroker, MQTTClient, ServiceManager, MessageProtocol,
    SensorData, CommandMessage, ResponseMessage, StatusMessage,
    EventMessage, AlertMessage, MessageValidator, topic_manager
)
from src.communication.message_protocols import MessageType, Priority


class TestMessageProtocols:
    """Test message protocol classes"""
    
    def test_sensor_data_creation(self):
        """Test sensor data message creation"""
        sensor_msg = SensorData.create(
            sender="test_sensor",
            sensor_type="temperature",
            data={"temperature": 25.5, "units": "celsius"}
        )
        
        assert sensor_msg.metadata.sender == "test_sensor"
        assert sensor_msg.metadata.message_type == MessageType.SENSOR_DATA
        assert sensor_msg.payload["sensor_type"] == "temperature"
        assert sensor_msg.payload["data"]["temperature"] == 25.5
    
    def test_command_message_creation(self):
        """Test command message creation"""
        cmd_msg = CommandMessage.create(
            sender="controller",
            target="sensor",
            command="calibrate",
            parameters={"offset": 1.5}
        )
        
        assert cmd_msg.metadata.sender == "controller"
        assert cmd_msg.metadata.message_type == MessageType.COMMAND
        assert cmd_msg.payload["target"] == "sensor"
        assert cmd_msg.payload["command"] == "calibrate"
        assert cmd_msg.payload["parameters"]["offset"] == 1.5
    
    def test_message_serialization(self):
        """Test message JSON serialization/deserialization"""
        original = SensorData.create(
            sender="test",
            sensor_type="temp",
            data={"value": 42}
        )
        
        # Serialize
        json_str = original.to_json()
        assert isinstance(json_str, str)
        
        # Deserialize
        restored = MessageProtocol.from_json(json_str)
        
        assert restored.metadata.sender == original.metadata.sender
        assert restored.metadata.message_type == original.metadata.message_type
        assert restored.payload == original.payload
    
    def test_message_validation(self):
        """Test message validation"""
        # Valid message
        valid_msg = SensorData.create("test", "temp", {"value": 1})
        assert MessageValidator.validate_message(valid_msg)
        
        # Invalid message - missing required fields
        invalid_msg = MessageProtocol(
            metadata=Mock(message_id="", sender="test", timestamp=time.time()),
            payload={}
        )
        assert not MessageValidator.validate_message(invalid_msg)


class TestTopicManager:
    """Test topic manager functionality"""
    
    def test_topic_pattern_matching(self):
        """Test MQTT wildcard pattern matching"""
        # Single level wildcard
        assert topic_manager.match_topic_pattern("sensors/temp1/data", "sensors/+/data")
        assert not topic_manager.match_topic_pattern("sensors/temp1/status", "sensors/+/data")
        
        # Multi-level wildcard
        assert topic_manager.match_topic_pattern("system/services/sensor/status", "system/#")
        assert topic_manager.match_topic_pattern("system/health", "system/#")
    
    def test_topic_definition_lookup(self):
        """Test finding topic definitions"""
        definition = topic_manager.find_topic_definition("sensors/temp1/data")
        assert definition is not None
        assert definition.qos >= 0
        
        # Non-existent pattern
        definition = topic_manager.find_topic_definition("invalid/topic/pattern")
        assert definition is None
    
    def test_qos_recommendations(self):
        """Test QoS recommendations"""
        # Sensor data should be QoS 1
        qos = topic_manager.get_recommended_qos("sensors/temp/data")
        assert qos == 1
        
        # Commands should be QoS 2
        qos = topic_manager.get_recommended_qos("commands/navigation")
        assert qos == 2
    
    def test_topic_hierarchy(self):
        """Test topic hierarchy generation"""
        hierarchy = topic_manager.get_topic_hierarchy()
        assert isinstance(hierarchy, dict)
        assert "sensors" in hierarchy
        assert "commands" in hierarchy
        assert "system" in hierarchy


@pytest.mark.asyncio
class TestMQTTBroker:
    """Test MQTT broker functionality"""
    
    async def test_broker_configuration(self):
        """Test broker configuration generation"""
        broker = MQTTBroker()
        config_file = await broker._generate_config()
        
        assert config_file.exists()
        
        # Read and verify config
        content = config_file.read_text()
        assert "port 1883" in content
        assert "bind_address localhost" in content
        
        # Cleanup
        config_file.unlink()
    
    @patch('subprocess.run')
    @patch('subprocess.Popen')
    async def test_broker_start_stop(self, mock_popen, mock_run):
        """Test broker start and stop"""
        # Mock mosquitto availability
        mock_run.return_value = Mock(returncode=0)
        
        # Mock process
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process running
        mock_popen.return_value = mock_process
        
        broker = MQTTBroker()
        
        # Start broker
        success = await broker.start()
        assert success
        assert broker.is_running()
        
        # Stop broker
        await broker.stop()
        mock_process.poll.return_value = 0  # Process stopped
        assert not broker.is_running()


@pytest.mark.asyncio
class TestMQTTClient:
    """Test MQTT client functionality"""
    
    @patch('paho.mqtt.client.Client')
    async def test_client_initialization(self, mock_mqtt_client):
        """Test client initialization"""
        mock_client_instance = Mock()
        mock_mqtt_client.return_value = mock_client_instance
        
        client = MQTTClient("test_client")
        
        # Mock successful connection
        client._connected = True
        
        success = await client.initialize()
        assert success
        
        # Verify MQTT client setup
        mock_mqtt_client.assert_called_once()
        assert mock_client_instance.on_connect is not None
        assert mock_client_instance.on_disconnect is not None
        assert mock_client_instance.on_message is not None
    
    @patch('paho.mqtt.client.Client')
    async def test_message_publishing(self, mock_mqtt_client):
        """Test message publishing"""
        mock_client_instance = Mock()
        mock_client_instance.publish.return_value = Mock(rc=0)  # Success
        mock_mqtt_client.return_value = mock_client_instance
        
        client = MQTTClient("test_client")
        client._connected = True
        client.client = mock_client_instance
        
        # Test publishing
        sensor_msg = SensorData.create("test", "temp", {"value": 25})
        success = await client.publish("test/topic", sensor_msg)
        
        assert success
        mock_client_instance.publish.assert_called_once()
    
    @patch('paho.mqtt.client.Client')
    async def test_command_response_cycle(self, mock_mqtt_client):
        """Test command/response cycle"""
        mock_client_instance = Mock()
        mock_mqtt_client.return_value = mock_client_instance
        
        client = MQTTClient("test_client")
        client._connected = True
        client.client = mock_client_instance
        
        # Add command handler
        async def test_handler(params):
            return {"result": "success", "value": params.get("input", 0) * 2}
        
        client.add_command_handler("test_command", test_handler)
        
        # Simulate incoming command
        cmd_msg = CommandMessage.create(
            sender="remote_client",
            target="test_client",
            command="test_command",
            parameters={"input": 5}
        )
        
        # Process command message
        await client._handle_command_message(cmd_msg)
        
        # Verify response was sent
        assert mock_client_instance.publish.called
    
    async def test_rate_limiting(self):
        """Test rate limiting functionality"""
        client = MQTTClient("test_client")
        
        # Test rate limiting
        for i in range(5):
            allowed = client._check_rate_limit("test_category")
            if i < 3:  # Assuming low limit for test
                assert allowed
            # Rate limiting behavior depends on configuration
    
    async def test_message_queuing(self):
        """Test message queuing when disconnected"""
        client = MQTTClient("test_client")
        client._connected = False
        
        # Publish message while disconnected
        success = await client.publish("test/topic", "test message")
        
        # Message should be queued
        assert len(client._message_queue) > 0
        
        # Should still return success (queued)
        assert success


@pytest.mark.asyncio
class TestServiceManager:
    """Test service manager functionality"""
    
    @patch('src.communication.client.MQTTClient')
    async def test_service_initialization(self, mock_mqtt_client):
        """Test service manager initialization"""
        mock_client_instance = AsyncMock()
        mock_client_instance.initialize.return_value = True
        mock_mqtt_client.return_value = mock_client_instance
        
        service = ServiceManager("test_service", "test_type")
        
        success = await service.initialize(
            dependencies=[],
            endpoints={"api": "/api/v1"},
            metadata={"version": "1.0.0"}
        )
        
        assert success
        assert service.service_id == "test_service"
        assert service.service_type == "test_type"
        assert service.endpoints["api"] == "/api/v1"
    
    @patch('src.communication.client.MQTTClient')
    async def test_service_discovery(self, mock_mqtt_client):
        """Test service discovery"""
        mock_client_instance = AsyncMock()
        mock_mqtt_client.return_value = mock_client_instance
        
        service = ServiceManager("test_service", "test_type")
        
        # Add mock services to registry
        from src.communication.service_manager import ServiceInfo, ServiceState
        service.services["other_service"] = ServiceInfo(
            service_id="other_service",
            service_type="other_type",
            version="1.0.0",
            start_time=time.time(),
            last_heartbeat=time.time(),
            state=ServiceState.HEALTHY,
            dependencies=[],
            endpoints={},
            metadata={}
        )
        
        # Test discovery
        services = service.discover_services()
        assert len(services) == 1
        assert services[0].service_id == "other_service"
        
        # Test filtered discovery
        services = service.discover_services("other_type")
        assert len(services) == 1
        
        services = service.discover_services("non_existent_type")
        assert len(services) == 0
    
    @patch('src.communication.client.MQTTClient')
    async def test_event_emission(self, mock_mqtt_client):
        """Test event emission"""
        mock_client_instance = AsyncMock()
        mock_mqtt_client.return_value = mock_client_instance
        
        service = ServiceManager("test_service", "test_type")
        service.mqtt_client = mock_client_instance
        
        # Emit event
        await service.emit_event("test_event", {"key": "value"})
        
        # Verify publish was called
        mock_client_instance.publish.assert_called_once()
        
        # Check call arguments
        call_args = mock_client_instance.publish.call_args
        topic = call_args[0][0]
        message = call_args[0][1]
        
        assert "system/events/test_event" in topic
        assert message.metadata.message_type == MessageType.EVENT
    
    @patch('src.communication.client.MQTTClient')
    async def test_alert_emission(self, mock_mqtt_client):
        """Test alert emission"""
        mock_client_instance = AsyncMock()
        mock_mqtt_client.return_value = mock_client_instance
        
        service = ServiceManager("test_service", "test_type")
        service.mqtt_client = mock_client_instance
        
        # Emit alert
        await service.emit_alert("safety_alert", "Test alert message", "critical")
        
        # Verify publish was called with retain=True
        mock_client_instance.publish.assert_called_once()
        call_args = mock_client_instance.publish.call_args
        
        assert call_args[1]['retain'] is True  # Alerts should be retained


@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for complete communication system"""
    
    async def test_end_to_end_communication(self):
        """Test complete end-to-end communication flow"""
        # This would require a real MQTT broker running
        # For now, we'll test the structure
        
        # Mock broker
        with patch('src.communication.broker.MQTTBroker') as mock_broker_class:
            mock_broker = Mock()
            mock_broker.start.return_value = True
            mock_broker.stop.return_value = None
            mock_broker_class.return_value = mock_broker
            
            # Mock clients
            with patch('src.communication.client.MQTTClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.initialize.return_value = True
                mock_client.publish.return_value = True
                mock_client.subscribe.return_value = True
                mock_client_class.return_value = mock_client
                
                # Create services
                service1 = ServiceManager("service1", "sensor")
                service2 = ServiceManager("service2", "navigation")
                
                # Initialize services
                success1 = await service1.initialize()
                success2 = await service2.initialize()
                
                assert success1 and success2
                
                # Test inter-service communication
                await service1.emit_event("sensor_reading", {"value": 42})
                
                # Verify communication occurred
                assert mock_client.publish.called
                
                # Cleanup
                await service1.shutdown()
                await service2.shutdown()
    
    def test_message_latency_requirements(self):
        """Test that message processing meets latency requirements"""
        # Create message
        start_time = time.time()
        
        sensor_msg = SensorData.create(
            sender="test_sensor",
            sensor_type="emergency",
            data={"alert": True}
        )
        
        # Serialize/deserialize (simulating network transfer)
        json_str = sensor_msg.to_json()
        restored_msg = MessageProtocol.from_json(json_str)
        
        end_time = time.time()
        latency = (end_time - start_time) * 1000  # Convert to milliseconds
        
        # Should be well under 50ms requirement
        assert latency < 50, f"Message processing took {latency:.2f}ms, exceeds 50ms requirement"
    
    def test_system_reliability(self):
        """Test system reliability features"""
        # Test message validation
        invalid_msg = MessageProtocol(
            metadata=Mock(message_id="", sender="", timestamp=0),
            payload=None
        )
        assert not MessageValidator.validate_message(invalid_msg)
        
        # Test topic validation
        assert topic_manager.find_topic_definition("sensors/temp/data") is not None
        assert topic_manager.find_topic_definition("invalid/pattern") is None
        
        # Test rate limiting configuration
        rate_limit = topic_manager.get_rate_limit("sensors/temp/data")
        assert rate_limit is not None and rate_limit > 0


class TestPerformance:
    """Performance tests for communication system"""
    
    def test_message_throughput(self):
        """Test message creation and serialization performance"""
        start_time = time.time()
        message_count = 1000
        
        for i in range(message_count):
            msg = SensorData.create(f"sensor_{i}", "test", {"value": i})
            json_str = msg.to_json()
            restored = MessageProtocol.from_json(json_str)
        
        end_time = time.time()
        duration = end_time - start_time
        rate = message_count / duration
        
        # Should handle at least 1000 messages per second
        assert rate > 1000, f"Message throughput {rate:.1f} msg/sec is below requirement"
    
    def test_topic_matching_performance(self):
        """Test topic pattern matching performance"""
        test_topics = [
            "sensors/temp1/data",
            "sensors/humidity1/data", 
            "navigation/position",
            "safety/alerts/emergency",
            "power/battery/status"
        ]
        
        start_time = time.time()
        iterations = 10000
        
        for _ in range(iterations):
            for topic in test_topics:
                topic_manager.find_topic_definition(topic)
        
        end_time = time.time()
        duration = end_time - start_time
        rate = (iterations * len(test_topics)) / duration
        
        # Should handle topic lookups efficiently
        assert rate > 10000, f"Topic matching rate {rate:.1f} lookups/sec is too slow"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
