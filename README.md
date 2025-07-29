# Hardware Interface Layer

A comprehensive hardware abstraction layer for the autonomous lawn mower project, providing safe, shared access to all hardware components through a modular plugin architecture.

## Features

### Core Components
- **I2C Manager**: Thread-safe singleton managing shared I2C bus access
- **Serial/UART Manager**: Handle multiple serial devices with proper locking
- **Camera Manager**: Exclusive camera access with frame buffering
- **GPIO Manager**: Centralized GPIO pin control and monitoring

### Modular Architecture
- **Plugin System**: Component-based architecture for easy sensor addition
- **Hot-Swap Support**: Dynamic loading/unloading without system restart
- **Configuration-Driven**: Hardware components defined in YAML/JSON config
- **Driver Abstraction**: Standardized interface for different sensor types

### Safety & Reliability
- **Exponential Backoff**: Retry logic with jitter for robust communication
- **Health Monitoring**: Automatic device health tracking and recovery
- **Failsafe Mechanisms**: Graceful handling of hardware failures
- **Concurrent Access**: Thread-safe operations using asyncio locks

## Hardware Support

### I2C Devices
- **VL53L0X ToF Sensors**: Distance measurement (addresses 0x29, 0x30)
- **INA3221 Power Monitor**: Voltage/current monitoring (address 0x40)
- **BME280 Environmental**: Temperature/humidity/pressure (address 0x76)
- **SSD1306 Display**: OLED display control (address 0x3c)

### Serial Devices
- **RoboHAT Controller**: Motor control via /dev/ttyACM1 (115200 baud)
- **GPS Module**: Position data via /dev/ttyACM0 (38400 baud)
- **BNO085 IMU**: Orientation data via /dev/ttyAMA4 (3M baud)

### GPIO Pins
- **ToF Control**: Shutdown pins (GPIO 22, 23), interrupt pins (GPIO 6, 12)
- **Blade Control**: Enable/direction pins (GPIO 24, 25)

### Camera
- **Raspberry Pi Camera**: /dev/video0 with configurable resolution/framerate

## Installation

```bash
# Install dependencies
pip install asyncio smbus2 pyserial opencv-python RPi.GPIO pyyaml

# Clone repository
git clone <repository-url>
cd lawnberry-pi

# Install package
pip install -e .
```

## Quick Start

```python
import asyncio
from src.hardware import create_hardware_interface

async def main():
    # Create hardware interface
    hw = create_hardware_interface("config/hardware.yaml")
    
    try:
        # Initialize all hardware
        await hw.initialize()
        
        # Read sensor data
        sensor_data = await hw.get_all_sensor_data()
        for name, reading in sensor_data.items():
            print(f"{name}: {reading.value} {reading.unit}")
        
        # Control RoboHAT
        await hw.send_robohat_command('rc_disable')
        await hw.send_robohat_command('pwm', 1500, 1500)
        
        # Control GPIO
        await hw.control_gpio_pin('blade_enable', 1)
        
        # Get camera frame
        frame = await hw.get_camera_frame()
        
    finally:
        await hw.shutdown()

asyncio.run(main())
```

## Configuration

Edit `config/hardware.yaml` to customize hardware settings:

```yaml
# I2C Configuration
i2c:
  bus_number: 1
  devices:
    tof_left: 0x29
    tof_right: 0x30
    power_monitor: 0x40

# Plugin Configuration
plugins:
  - name: "tof_left"
    enabled: true
    parameters:
      i2c_address: 0x29
      shutdown_pin: 22
      interrupt_pin: 6
```

## RoboHAT Interface

The system implements the complete RoboHAT command protocol:

```python
# Take control from RC
await hw.send_robohat_command('rc_disable')

# Send motor commands (1000-2000 μs)
await hw.send_robohat_command('pwm', 1500, 1600)  # steer, throttle

# Reset encoder
await hw.send_robohat_command('enc_zero')

# Return control to RC
await hw.send_robohat_command('rc_enable')
```

## Plugin Development

Create custom sensor plugins by extending `HardwarePlugin`:

```python
from src.hardware.plugin_system import HardwarePlugin

class CustomSensorPlugin(HardwarePlugin):
    @property
    def plugin_type(self) -> str:
        return "custom_sensor"
    
    @property
    def required_managers(self) -> list:
        return ["i2c"]
    
    async def initialize(self) -> bool:
        # Initialize your sensor
        return True
    
    async def read_data(self):
        # Read and return sensor data
        pass
```

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/test_hardware_interface.py::TestI2CManager -v

# Run with coverage
python -m pytest tests/ --cov=src/hardware --cov-report=html
```

## API Reference

### HardwareInterface

Main interface for all hardware operations:

- `initialize()` - Initialize all hardware components
- `get_sensor_data(name)` - Read data from specific sensor
- `get_all_sensor_data()` - Read data from all sensors
- `send_robohat_command(cmd, *args)` - Send command to RoboHAT
- `control_gpio_pin(name, value)` - Control GPIO pin by name
- `get_camera_frame()` - Get latest camera frame
- `get_system_health()` - Get overall system health status
- `add_sensor(name, type, params)` - Dynamically add sensor
- `remove_sensor(name)` - Dynamically remove sensor

### Data Structures

Standard sensor reading format:

```python
@dataclass
class SensorReading:
    timestamp: datetime
    sensor_id: str
    value: Any
    unit: str
    quality: float  # 0.0-1.0
    metadata: Dict[str, Any]
```

### Health Monitoring

Track device health and connection status:

```python
health = await hw.get_system_health()
print(f"System healthy: {health['overall_healthy']}")
print(f"Plugin health: {health['plugins']}")
print(f"Device health: {health['devices']}")
```

## Safety Features

### Automatic Failsafe
- Communication timeouts trigger RC mode fallback
- Hardware watchdog integration prevents system lockup
- Emergency stop capability through software controls

### Error Recovery
- Exponential backoff with jitter for communication retries
- Automatic sensor reconnection on failure
- Plugin hot-swapping for recovery without restart

### Resource Management
- Exclusive device access prevents bus conflicts
- Proper cleanup on shutdown prevents resource leaks
- Memory-efficient frame buffering for camera

## Performance

- **Sensor Reading**: <50ms typical latency
- **I2C Operations**: Concurrent access with proper locking
- **Camera Capture**: 30fps with 5-frame buffer
- **Memory Usage**: Efficient caching with automatic cleanup

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add comprehensive tests
4. Follow the existing code style
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
