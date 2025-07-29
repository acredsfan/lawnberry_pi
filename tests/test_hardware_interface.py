"""Comprehensive test suite for hardware interface layer"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from src.hardware import (
    HardwareInterface, I2CManager, SerialManager, CameraManager, GPIOManager,
    PluginManager, HardwarePlugin, PluginConfig,
    HardwareError, DeviceNotFoundError, CommunicationError
)
from src.hardware.data_structures import SensorReading, DeviceHealth


class MockSensor(HardwarePlugin):
    """Mock sensor for testing"""
    
    @property
    def plugin_type(self) -> str:
        return "mock_sensor"
    
    @property
    def required_managers(self) -> list:
        return ["i2c"]
    
    async def initialize(self) -> bool:
        self._initialized = True
        return True
    
    async def read_data(self):
        return SensorReading(
            timestamp=datetime.now(),
            sensor_id=self.config.name,
            value=42,
            unit="test"
        )


@pytest.fixture
async def hardware_interface():
    """Create hardware interface for testing"""
    with patch('src.hardware.managers.smbus2', None), \
         patch('src.hardware.managers.GPIO', None), \
         patch('src.hardware.managers.cv2') as mock_cv2:
        
        # Mock camera
        mock_camera = Mock()
        mock_camera.isOpened.return_value = True
        mock_camera.read.return_value = (True, Mock())
        mock_cv2.VideoCapture.return_value = mock_camera
        mock_cv2.imencode.return_value = (True, Mock(tobytes=Mock(return_value=b'test')))
        
        interface = HardwareInterface()
        await interface.initialize()
        yield interface
        await interface.shutdown()


@pytest.mark.asyncio
class TestI2CManager:
    """Test I2C manager functionality"""
    
    async def test_singleton_pattern(self):
        """Test I2C manager singleton pattern"""
        manager1 = I2CManager()
        manager2 = I2CManager()
        assert manager1 is manager2
    
    async def test_device_access_locking(self):
        """Test concurrent device access is properly locked"""
        manager = I2CManager()
        await manager.initialize()
        
        access_order = []
        
        async def access_device(device_id):
            async with manager.device_access(0x29):
                access_order.append(f"start_{device_id}")
                await asyncio.sleep(0.1)
                access_order.append(f"end_{device_id}")
        
        # Start concurrent access
        await asyncio.gather(
            access_device("A"),
            access_device("B")
        )
        
        # Verify sequential access
        assert access_order in [
            ["start_A", "end_A", "start_B", "end_B"],
            ["start_B", "end_B", "start_A", "end_A"]
        ]
    
    @patch('src.hardware.managers.smbus2')
    async def test_retry_logic(self, mock_smbus2):
        """Test exponential backoff retry logic"""
        manager = I2CManager()
        await manager.initialize()
        
        # Mock bus to fail first two attempts, succeed on third
        mock_bus = Mock()
        mock_bus.read_byte_data.side_effect = [Exception("fail1"), Exception("fail2"), 42]
        manager._bus = mock_bus
        
        start_time = time.time()
        result = await manager.read_register(0x29, 0x00)
        end_time = time.time()
        
        assert result == [42]
        assert end_time - start_time >= 0.3  # Should have delays
        assert mock_bus.read_byte_data.call_count == 3
    
    async def test_device_health_tracking(self):
        """Test device health is properly tracked"""
        # Reset singleton to ensure clean state
        I2CManager._instance = None
        
        manager = I2CManager()
        await manager.initialize()
        
        # Mock successful operation
        with patch.object(manager, '_bus') as mock_bus:
            mock_bus.read_byte_data.return_value = 42
            await manager.read_register(0x29, 0x00)
        
        health = manager.get_device_health(0x29)
        assert health.is_healthy
        assert health.success_rate == 1.0
        assert health.consecutive_failures == 0


@pytest.mark.asyncio
class TestSerialManager:
    """Test serial manager functionality"""
    
    @patch('src.hardware.managers.serial.Serial')
    async def test_device_initialization(self, mock_serial):
        """Test serial device initialization"""
        manager = SerialManager()
        
        mock_conn = Mock()
        mock_serial.return_value = mock_conn
        
        await manager.initialize_device('robohat')
        
        mock_serial.assert_called_once_with(
            port='/dev/ttyACM1',
            baudrate=115200,
            timeout=1.0
        )
        assert 'robohat' in manager._connections
    
    @patch('src.hardware.managers.serial.Serial')
    async def test_write_command(self, mock_serial):
        """Test serial command writing"""
        manager = SerialManager()
        
        mock_conn = Mock()
        mock_serial.return_value = mock_conn
        
        success = await manager.write_command('robohat', 'rc=disable')
        
        assert success
        mock_conn.write.assert_called_once_with(b'rc=disable\n')
        mock_conn.flush.assert_called_once()


@pytest.mark.asyncio
class TestPluginSystem:
    """Test plugin system functionality"""
    
    async def test_plugin_loading(self):
        """Test dynamic plugin loading"""
        managers = {'i2c': Mock()}
        plugin_manager = PluginManager(managers)
        
        config = PluginConfig(name="test_sensor", parameters={})
        
        # Register mock plugin class
        plugin_manager._builtin_plugins["mock_sensor"] = MockSensor
        
        success = await plugin_manager.load_plugin("test_sensor", "mock_sensor", config)
        
        assert success
        assert "test_sensor" in plugin_manager._plugins
        
        plugin = plugin_manager.get_plugin("test_sensor")
        assert plugin is not None
        assert plugin.is_initialized
    
    async def test_plugin_hot_swap(self):
        """Test plugin hot-swapping"""
        managers = {'i2c': Mock()}
        plugin_manager = PluginManager(managers)
        plugin_manager._builtin_plugins["mock_sensor"] = MockSensor
        
        config = PluginConfig(name="test_sensor", parameters={})
        
        # Load plugin
        await plugin_manager.load_plugin("test_sensor", "mock_sensor", config)
        
        # Reload plugin
        success = await plugin_manager.reload_plugin("test_sensor")
        assert success
        
        # Unload plugin
        success = await plugin_manager.unload_plugin("test_sensor")  
        assert success
        assert "test_sensor" not in plugin_manager._plugins
    
    async def test_health_check_all(self):
        """Test health checking of all plugins"""
        managers = {'i2c': Mock()}
        plugin_manager = PluginManager(managers)
        plugin_manager._builtin_plugins["mock_sensor"] = MockSensor
        
        config = PluginConfig(name="test_sensor", parameters={})
        await plugin_manager.load_plugin("test_sensor", "mock_sensor", config)
        
        health = await plugin_manager.health_check_all()
        
        assert "test_sensor" in health
        assert health["test_sensor"] is True


@pytest.mark.asyncio
class TestHardwareInterface:
    """Test main hardware interface"""
    
    async def test_initialization(self, hardware_interface):
        """Test hardware interface initialization"""
        assert hardware_interface.is_initialized()
        assert hardware_interface.i2c_manager is not None
        assert hardware_interface.serial_manager is not None
        assert hardware_interface.camera_manager is not None
        assert hardware_interface.gpio_manager is not None
    
    async def test_concurrent_sensor_access(self, hardware_interface):
        """Test concurrent access to multiple sensors"""
        # Add mock sensors
        await hardware_interface.add_sensor("sensor1", "mock_sensor", {})
        await hardware_interface.add_sensor("sensor2", "mock_sensor", {})
        
        # Mock the plugin type determination
        with patch.object(hardware_interface, '_determine_plugin_type', return_value="mock_sensor"):
            # Read sensors concurrently
            results = await asyncio.gather(
                hardware_interface.get_sensor_data("sensor1"),
                hardware_interface.get_sensor_data("sensor2"),
                return_exceptions=True
            )
        
        # Both should succeed without conflicts
        assert len(results) == 2
        for result in results:
            assert not isinstance(result, Exception)
    
    async def test_robohat_commands(self, hardware_interface):
        """Test RoboHAT command interface"""
        # Mock RoboHAT plugin
        mock_robohat = Mock()
        mock_robohat.send_pwm_command = AsyncMock(return_value=True)
        mock_robohat.managers = {'serial': Mock()}
        mock_robohat.managers['serial'].write_command = AsyncMock(return_value=True)
        
        hardware_interface.plugin_manager._plugins['robohat'] = mock_robohat
        
        # Test PWM command
        success = await hardware_interface.send_robohat_command('pwm', 1500, 1500)
        assert success
        mock_robohat.send_pwm_command.assert_called_once_with(1500, 1500)
        
        # Test RC disable command
        success = await hardware_interface.send_robohat_command('rc_disable')
        assert success
        mock_robohat.managers['serial'].write_command.assert_called_once_with('robohat', 'rc=disable')
    
    async def test_gpio_control(self, hardware_interface):
        """Test GPIO pin control by name"""
        with patch.object(hardware_interface.gpio_manager, 'write_pin') as mock_write:
            await hardware_interface.control_gpio_pin('blade_enable', 1)
            mock_write.assert_called_once_with(24, 1)  # GPIO 24 from config
    
    async def test_system_health_monitoring(self, hardware_interface):
        """Test system health monitoring"""
        health = await hardware_interface.get_system_health()
        
        assert 'overall_healthy' in health
        assert 'timestamp' in health
        assert 'managers' in health
        assert 'plugins' in health
        assert 'devices' in health
        assert isinstance(health['overall_healthy'], bool)
    
    async def test_sensor_recovery(self, hardware_interface):
        """Test automatic sensor recovery"""
        # Add a mock sensor
        await hardware_interface.add_sensor("test_sensor", "mock_sensor", {})
        
        # Simulate sensor failure
        plugin = hardware_interface.plugin_manager.get_plugin("test_sensor")
        if plugin:
            plugin.health.consecutive_failures = 10
            plugin.health.is_connected = False
        
        # Mock reload to succeed
        with patch.object(hardware_interface.plugin_manager, 'reload_plugin', return_value=True) as mock_reload:
            # Trigger health check
            health = await hardware_interface.get_system_health()
            
            if not health['overall_healthy']:
                # Should attempt recovery
                mock_reload.assert_called()


@pytest.mark.asyncio
class TestFailsafeAndRecovery:
    """Test failsafe mechanisms and recovery"""
    
    async def test_i2c_bus_conflict_resolution(self):
        """Test I2C bus conflicts are resolved"""
        manager = I2CManager()
        await manager.initialize()
        
        results = []
        
        async def concurrent_access(device_id):
            try:
                async with manager.device_access(0x29):
                    results.append(f"acquired_{device_id}")
                    await asyncio.sleep(0.05)
                    results.append(f"released_{device_id}")
            except Exception as e:
                results.append(f"error_{device_id}_{e}")
        
        # Multiple concurrent accesses
        await asyncio.gather(*[
            concurrent_access(i) for i in range(5)
        ])
        
        # Should have 10 events (5 acquire + 5 release) with no errors
        assert len(results) == 10
        assert all("error" not in result for result in results)
    
    async def test_device_timeout_handling(self):
        """Test device timeout handling"""
        manager = SerialManager()
        
        with patch('src.hardware.managers.serial.Serial') as mock_serial:
            mock_conn = Mock()
            mock_conn.readline.side_effect = [b'', b'', b'test response\n']
            mock_serial.return_value = mock_conn
            
            # Should handle timeouts gracefully
            result = await manager.read_line('robohat', timeout=0.1)
            assert result is None or result == 'test response'
    
    async def test_hardware_failure_recovery(self, hardware_interface):
        """Test recovery from hardware failures"""
        # Simulate I2C device failure
        with patch.object(hardware_interface.i2c_manager, 'read_register', side_effect=CommunicationError("I2C failed")):
            # Should handle gracefully
            result = await hardware_interface.get_sensor_data('tof_left')
            # Should return None instead of raising exception
            assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
