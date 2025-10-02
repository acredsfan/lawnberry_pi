# LawnBerryPi Hardware Overview

This guide provides a comprehensive overview of the LawnBerryPi hardware components and their functions. Understanding your hardware helps with maintenance, troubleshooting, and system optimization.

## System Architecture Diagram

```
                    LawnBerryPi Hardware Architecture
                           
    ┌─────────────────────────────────────────────────────────────┐
    │                     POWER SYSTEM                            │
    │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
    │  │ Solar Panel │──│ Charge       │──│ 30Ah LiFePO4     │    │
    │  │ 30W         │  │ Controller   │  │ Battery          │    │
    │  └─────────────┘  │ 15A          │  └──────────────────┘    │
    │                   └──────────────┘          │               │
    └─────────────────────────────────────────────┼───────────────┘
                                                  │
    ┌─────────────────────────────────────────────┼──────────────┐
    │                 MAIN COMPUTE                │              │
    │  ┌─────────────────────────────────────┐    │              │
    │  │        Raspberry Pi 5 (16GB)        │    │ 12V Bus      │
    │  │  ┌─────────────────────────────┐    │    │              │
    │  │  │      RoboHAT (RP2040)       │    │    │              │
    │  │  │                             │    │    │              │
    │  │  └─────────────────────────────┘    │    │              │
    │  └─────────────────────────────────────┘    │              │
    │                    │                        │              │
    │              5V DC-DC Converter ←───────────┘              │
    └────────────────────┼───────────────────────────────────────┘
                        │
    ┌───────────────────┼─────────────────────────────────────┐
    │              SENSOR SYSTEMS                 │           │
    │                                             │           │
    │  I2C Bus (3.3V):                            │           │
    │  ├─ VL53L0X ToF (Left)  - 0x29              │           │
    │  ├─ VL53L0X ToF (Right) - 0x30              │           │
    │  ├─ BME280 Environment  - 0x76              │           │
    │  ├─ INA3221 Power Mon   - 0x40              │           │
    │  └─ SSD1306 Display     - 0x3C              │           │
    │                                             │           │
    │  Serial/UART:                               │           │
    │  ├─ GPS RTK Module   - /dev/ttyACM1         │           │
    │  ├─ BNO085 IMU       - /dev/ttyAMA4         │           │ <----(Pi 5 UART4, GPIO12/13)
    │  └─ RoboHAT Comms    - /dev/serial0         │           │
    │                                             │           │
    │  Camera:                                    │           │
    │  └─ Pi Camera        - /dev/video0          │           │
    └─────────────────────────────────────────────┼───────────┘
                                                  │
    ┌─────────────────────────────────────────────┼───────────┐
    │                MOTOR SYSTEMS                │           │
    │                                             │           │
    │  Drive Motors (12V):                        │           │
    │  ├─ Left Drive Motor  ←─ Cytron MDDRC10 ←───┤           │
    │  └─ Right Drive Motor ←─ Motor Driver   ←───┤           │
    │                                             │           │
    │  Blade Motor (12V):                         │           │
    │  └─ 997 DC Motor ←─ IBT-4 Driver ←──────────┤           │
    │                                             │           │
    │  Control Signals:                           │           │
    │  ├─ GPIO 24 (Blade IN1)                     │           │
    │  ├─ GPIO 25 (Blade IN2)                     │           │
    │  ├─ PWM/DIR to Motor Driver                 │           │
    │  └─ Hall Effect Feedback                    │           │
    └─────────────────────────────────────────────────────────┘
```

## Core Components

### Raspberry Pi 5 (16GB RAM)
**Function**: Main computing platform running all software systems
**Specifications**:
- Broadcom BCM2712 quad-core Arm Cortex A76 processor @ 2.4GHz
- 16GB LPDDR4X-4267 RAM for advanced processing
- WiFi 802.11ac and Gigabit Ethernet
- Multiple I2C, SPI, UART, and GPIO interfaces
- 2 × 4-lane MIPI camera/display transceivers

**Key Responsibilities**:
- Web interface hosting and API services
- GPS processing and navigation algorithms
- Computer vision and obstacle detection
- Weather monitoring and schedule management  
- Safety system coordination and emergency response

### RoboHAT with RP2040 Microcontroller
**Function**: Real-time motor control and low-level hardware interface
**Specifications**:
- RP2040 dual-core ARM Cortex-M0+ (133MHz)
- Direct GPIO access for time-critical operations
- PWM generation for motor control
- Hall effect sensor monitoring
- I2C communication with Raspberry Pi
- Serial bridge to main compute via /dev/ttyACM0 or /dev/serial0

**Key Responsibilities**:
- Drive motor PWM control and direction
- Wheel encoder reading and odometry
- Emergency stop signal processing
- Real-time safety monitoring
- Status display on integrated OLED
- Control command execution with lockout enforcement

**Control Integration**:
The RoboHAT provides a serial API for motor control commands. The backend services communicate via the `robohat_service.py` which translates high-level control commands (FORWARD, BACKWARD, ROTATE, STOP) into serial protocol messages. Status updates and command echoes are streamed back via WebSocket to the frontend control interface.

**Safety Features**:
- Hardware emergency stop circuit
- Blade safety interlocks (tilt detection)
- Lockout state management during faults
- Command validation and rate limiting

## Navigation and Positioning

### SparkFun GPS-RTK-SMA Kit
**Function**: High-precision positioning for accurate navigation
**Specifications**:
- u-blox ZED-F9P GNSS receiver
- Multi-constellation support (GPS, GLONASS, Galileo, BeiDou)
- RTK corrections for centimeter-level accuracy
- USB interface to Raspberry Pi (typically `/dev/ttyACM1`)
- External antenna for optimal satellite reception

**Accuracy Levels**:
- **Standard GPS**: 3-5 meter accuracy
- **With RTK corrections**: 2-10 centimeter accuracy
- **Time to first fix**: 30 seconds (cold start)
- **Update rate**: 10Hz position updates

### BNO085 9-Axis IMU
**Function**: Orientation sensing and compass heading
**Specifications**:
- 3-axis accelerometer, gyroscope, and magnetometer
- Built-in sensor fusion algorithms
- UART interface for high-speed data (3,000,000 baud typical)
- Calibration storage in internal flash

**Capabilities**:
- Absolute orientation (pitch, roll, yaw)
- Linear acceleration measurement
- Rotation vector and quaternion output
- Compass heading with magnetic declination correction

Note: On Raspberry Pi 5 the IMU is typically wired to UART4 on GPIO12 (TXD4) and GPIO13 (RXD4), exposed as `/dev/ttyAMA4`. The IMU plugin uses the Adafruit BNO08x UART driver and publishes quaternion, acceleration, and gyro to MQTT at `lawnberry/sensors/imu/data`.

Quick GPS smoke test (bounded, venv-enforced):

```
venv/bin/python -m scripts.gps_smoke_test --duration 20 --interval 0.5
```

## Environmental Sensing

### BME280 Environmental Sensor
**Function**: Weather monitoring for intelligent scheduling
**Specifications**:
- Temperature measurement: ±1.0°C accuracy
- Humidity measurement: ±3% relative humidity
- Barometric pressure: ±1 hPa accuracy
- I2C interface with 0x76 address

**Applications**:
- Weather-based mowing decisions
- Dew point calculation for morning operations
- Pressure trend monitoring for weather prediction
- Temperature-based safety limits

### VL53L0X Time-of-Flight Distance Sensors (2x)
**Function**: Obstacle detection and avoidance
**Specifications**:
- Laser-based distance measurement
- Range: 30mm to 2000mm
- Accuracy: ±3% at distances up to 1200mm
- Independent I2C addresses (0x29, 0x30)
- GPIO shutdown and interrupt pins

**Mounting Configuration**:
- **Left sensor**: Front-left of mower for left-side obstacles
- **Right sensor**: Front-right of mower for right-side obstacles
- **Detection pattern**: 25° cone angle per sensor
- **Response time**: <30ms measurement cycle

## Power and Monitoring Systems

### 30Ah LiFePO4 Battery
**Function**: Primary power storage for autonomous operation
**Specifications**:
- Lithium Iron Phosphate chemistry
- Nominal voltage: 12.8V (4S configuration)
- Capacity: 30Ah (384Wh energy storage)
- Cycle life: 3000+ cycles at 80% DOD
- Built-in Battery Management System (BMS)

**Performance Characteristics**:
- **Runtime**: 4-8 hours depending on terrain and conditions
- **Solar-Only Charging time**: 3-4 days from 20% to 100% depending on conditions
- **Operating temperature**: -20°C to 60°C
- **Safety features**: Over/under voltage, current, and temperature protection

### Solar Charging System
**Components**:
- **30W Solar Panel**: Monocrystalline silicon with aluminum frame
- **15A Victron SmartSolar MPPT Charge Controller**: Maximum Power Point Tracking for efficiency
- **Charge regulation**: Automatic multi-stage charging profile

**Charging Performance**:
- **Peak charging**: 1.5A in full sunlight (30W panel)
- **Daily energy**: 80-120Wh in typical conditions
- **Seasonal variation**: 60% capacity in winter, 140% in summer
- **Maintenance charging**: Keeps battery topped off during storage

### INA3221 Triple-Channel Power Monitor
**Function**: Real-time power consumption and battery monitoring
**Specifications**:
- Three independent current/voltage channels
- ±40A current measurement range
- 26V maximum voltage measurement
- I2C interface with 0x40 address

**Monitoring Channels**:
- **Channel 1**: Main battery voltage and total current
- **Channel 2**: Not Used
- **Channel 3**: Solar panel voltage and current

## Motor and Drive Systems

### Drive Motor System
**Components**:
- **2x 12V Worm Gear DC Motors**: High torque, low speed for traction
- **Cytron MDDRC10 Motor Driver**: Dual-channel motor control
- **Hall Effect Sensors**: Wheel rotation feedback
- **4x magnets per wheel**: to be read by Hall Sensors

**Specifications**:
- **Motor power**: 35W per motor (70W total drive power)
- **Gear ratio**: 218:1 for high torque
- **Maximum speed**: 2.5 m/s (5.6 mph)
- **Typical operating speed**: 1.0-1.5 m/s
- **Differential steering**: Independent left/right wheel control

### Blade Motor System
**Components**:
- **997 DC Motor**: High-speed motor for blade rotation
- **IBT-4 Motor Driver**: High-current motor controller
- **GPIO Control**: Direction and enable signals from Raspberry Pi

**Specifications**:
- **Motor power**: 50W maximum
- **Blade speed**: 3000-4000 RPM typical
- **Control method**: PWM speed control
- **Safety features**: Emergency stop and blade brake

## Camera and Vision System

### Raspberry Pi Camera Module
**Function**: Object detection, monitoring, and documentation
**Specifications**:
- 8MP Sony IMX219 sensor
- 1080p video at 30fps
- Fixed focus lens with 62.2° field of view
- Camera Serial Interface (CSI) connection

**Applications**:
- Real-time obstacle detection and identification
- Live monitoring via web interface
- Image collection for AI training
- Progress documentation and time-lapse creation
- RTK GPS for real-time location monitoring and geofencing

**Computer Vision Capabilities**:
- TFlite or OpenCV integration for image processing
- Optional Google Coral or Hailo for offloading vision
- Object detection using trained models
- Edge detection for boundary recognition
- Motion detection for security monitoring

## Display and User Interface

### SSD1306 OLED Display
**Function**: Local status display and diagnostics
**Specifications**:
- 128x64 pixel monochrome display
- I2C interface with 0x3C address
- Integrated into RoboHAT for compact design
- High contrast for outdoor visibility

**Display Information**:
- Current operating mode and status
- Battery voltage and charge level
- GPS coordinates and satellite count
- Error codes and diagnostic messages
- Network connectivity status

## Physical Design and Enclosures

**Sensor Protection**:
- Individual weatherproof housings for exposed sensors
- UV-resistant materials for long-term outdoor exposure
- Easy access for cleaning and maintenance
- Secure mounting to prevent vibration damage

### Mechanical Platform
**Chassis Design**:
- 3D printed body
- Low center of gravity for stability on slopes
- Modular design for easy component access
- Integrated cable management and routing

## Connectivity and Communication

### Wireless Communications
**WiFi Connectivity**:
- 802.11ac dual-band (2.4GHz and 5GHz)
- WPA2/WPA3 security support
- Automatic reconnection and fallback
- Range: 100+ meters from access point

### Wired Interfaces
**Available Ports**:
- USB ports for the External Wifi Antenna, RTK GPS, Google Coral TPU Accelerator, and secondary connection to RoboHAT RP2040
- HDMI for direct display connection
- MicroSD card for system storage and logging

## Expansion and Customization

### Expansion Possibilities
**Sensor Additions**:
- Additional ToF sensors for full perimeter coverage
- Ultrasonic sensors for different detection characteristics
- LIDAR module

**Actuator Additions**:
- Horn or alarm for safety alerts
- Additional motors for specialized attachments

## Maintenance Access Points

### Regular Maintenance Access
**Daily/Weekly Access**:
- Battery voltage and connection points
- Blade inspection and replacement area
- Camera lens and sensor cleaning points
- Display and control interface

**Monthly/Seasonal Access**:
- Electrical connection inspection
- Software and firmware update access

### Diagnostic and Service Access
**Professional Service Points**:
- Main power disconnect for safety
- Diagnostic port access for testing
- Component replacement access
- Calibration and alignment references

## Safety Systems Integration

### Hardware Safety Features
**Mechanical Safety**:
- Blade guards and emergency stops
- Tilt sensors for rollover protection
- Collision detection and response
- Manual override capabilities

**Electrical Safety**:
- Circuit breakers and fuses
- Ground fault protection
- Overcurrent protection
- Emergency power disconnect

### Software Safety Integration
**Sensor Monitoring**:
- Continuous health checking of all sensors
- Automatic calibration verification
- Fault detection and response
- Safe mode operation capabilities

**Communication Safety**:
- Watchdog timers for system monitoring
- Emergency communication protocols
- Fail-safe defaults for lost communication
- Remote emergency stop capabilities

## Telemetry and Monitoring

### Real-Time Telemetry System
The LawnBerryPi v2 system includes a comprehensive telemetry hub that aggregates data from all sensors and subsystems:

**Telemetry Channels**:
- **GPS/Position**: Latitude, longitude, altitude, accuracy, satellite count, RTK status
- **IMU/Orientation**: Quaternion, linear acceleration, angular velocity, euler angles
- **Environmental**: Temperature, humidity, barometric pressure, dew point
- **Power**: Battery voltage, current draw, state of charge, solar input
- **Obstacle Detection**: ToF sensor distances (left/right), confidence scores
- **Motor Status**: Drive motor speeds, blade motor RPM, current consumption
- **System Health**: CPU usage, memory usage, disk space, network connectivity

**Data Access**:
- REST API: GET /api/v2/telemetry/stream for JSON snapshots
- WebSocket: Real-time streaming at configurable intervals (default 1Hz)
- Export: Historical data export in JSON/CSV formats
- Persistence: SQLite storage with configurable retention periods

### Map Configuration System
Operators can define working boundaries, exclusion zones, and point-of-interest markers through the map interface:

**Map Providers**:
- **Leaflet (Open Street Map)**: Primary offline-capable provider
- **Google Maps**: Optional provider with API key
- **Fallback Support**: Automatic provider switching on failures

**Configuration Features**:
- GeoJSON-based boundary definitions
- Overlap detection for exclusion zones
- Validation with Shapely geometry checks
- Version-controlled configuration storage
- Real-time boundary visualization

### Settings Management
The settings service provides profile-based configuration management:

**Settings Categories**:
- **Hardware**: SIM mode, RoboHAT serial port configuration
- **Network**: WiFi credentials, access point settings
- **Telemetry**: Streaming intervals, persistence options
- **Control**: Lockout timeouts, blade safety settings
- **Maps**: Provider selection, API keys, caching options
- **Camera**: Resolution, framerate, quality settings
- **AI**: Detection thresholds, learning modes
- **System**: Log levels, update preferences, branding validation

**Profile Management**:
- Dual persistence (SQLite + JSON backup)
- Version conflict detection
- Constitutional branding checksum validation
- Audit logging for all changes

---

This hardware overview provides the foundation for understanding how your LawnBerryPi operates. For specific maintenance procedures, see the [Maintenance Guide](maintenance-guide.md). For troubleshooting hardware issues, consult the [Troubleshooting Guide](troubleshooting-guide.md).

For API documentation and operational procedures, see [OPERATIONS.md](OPERATIONS.md). For hardware capabilities and configuration options, see the [Hardware Feature Matrix](hardware-feature-matrix.md).

*Hardware Overview - Part of LawnBerryPi Documentation v2.0*
