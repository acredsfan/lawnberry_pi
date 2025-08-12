# LawnBerryPi Hardware Overview

This guide provides a comprehensive overview of the LawnBerryPi hardware components and their functions. Understanding your hardware helps with maintenance, troubleshooting, and system optimization.

## System Architecture Diagram

```
                    LawnBerryPi Hardware Architecture

    ┌─────────────────────────────────────────────────────────────┐
    │                     POWER SYSTEM                            │
    │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐    │
    │  │ Solar Panel │──│ Charge       │──│ 30Ah LiFePO4   │    │
    │  │ 30W         │  │ Controller   │  │ Battery         │    │
    │  └─────────────┘  │ 20A          │  └─────────────────┘    │
    │                   └──────────────┘           │              │
    └─────────────────────────────────────────────┼──────────────┘
                                                  │
    ┌─────────────────────────────────────────────┼──────────────┐
    │                 MAIN COMPUTE                │              │
    │  ┌─────────────────────────────────────┐    │              │
    │  │   Raspberry Pi 4/5 (8GB)        │    │ 12V Bus      │
    │  │  ┌─────────────────────────────┐    │    │              │
    │  │  │      RoboHAT (RP2040)       │    │    │              │
    │  │  │                             │    │    │              │
    │  │  └─────────────────────────────┘    │    │              │
    │  └─────────────────────────────────────┘    │              │
    │                    │                        │              │
    │              5V DC-DC Converter ←───────────┘              │
    └────────────────────┼─────────────────────────────────────┘
                        │
    ┌───────────────────┼─────────────────────────────────────┐
    │              SENSOR SYSTEMS                 │           │
    │                                            │           │
    │  I2C Bus (3.3V):                          │           │
    │  ├─ VL53L0X ToF (Left)  - 0x29            │           │
    │  ├─ VL53L0X ToF (Right) - 0x30            │           │
    │  ├─ BME280 Environment  - 0x76            │           │
    │  ├─ INA3221 Power Mon   - 0x40            │           │
    │  └─ SSD1306 Display     - 0x3C            │           │
    │                                            │           │
    │  Serial/UART:                              │           │
    │  ├─ GPS RTK Module   - /dev/ttyACM0       │           │
    │  ├─ BNO085 IMU       - /dev/ttyAMA4       │           │
    │  └─ RoboHAT Comms    - /dev/ttyACM1       │           │
    │                                            │           │
    │  Camera:                                   │           │
    │  └─ Pi Camera        - /dev/video0        │           │
    └────────────────────────────────────────────┼───────────┘
                                                │
    ┌───────────────────────────────────────────┼───────────┐
    │                MOTOR SYSTEMS               │           │
    │                                           │           │
    │  Drive Motors (12V):                      │           │
    │  ├─ Left Drive Motor  ←─ Cytron MDDRC10 ←─┤           │
    │  └─ Right Drive Motor ←─ Motor Driver   ←─┤           │
    │                                           │           │
    │  Blade Motor (12V):                       │           │
    │  └─ 997 DC Motor ←─ IBT-4 Driver ←────────┤           │
    │                                           │           │
    │  Control Signals:                         │           │
    │  ├─ GPIO 24 (Blade IN1)                  │           │
    │  ├─ GPIO 25 (Blade IN2)                  │           │
    │  ├─ PWM/DIR to Motor Driver               │           │
    │  └─ Hall Effect Feedback                  │           │
    └───────────────────────────────────────────────────────┘
```

## Core Components

### Raspberry Pi 4/5 (8GB RAM)
**Function**: Main computing platform running all software systems
**Specifications**:
- ARM Cortex-A72 quad-core processor (1.5GHz)
- 8GB LPDDR4 RAM for advanced processing
- WiFi 802.11ac and Gigabit Ethernet
- Multiple I2C, SPI, UART, and GPIO interfaces
- Camera Serial Interface (CSI) for Pi Camera

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

**Key Responsibilities**:
- Drive motor PWM control and direction
- Wheel encoder reading and odometry
- Emergency stop signal processing
- Real-time safety monitoring
- Status display on integrated OLED

## Navigation and Positioning

### SparkFun GPS-RTK-SMA Kit
**Function**: High-precision positioning for accurate navigation
**Specifications**:
- u-blox ZED-F9P GNSS receiver
- Multi-constellation support (GPS, GLONASS, Galileo, BeiDou)
- RTK corrections for centimeter-level accuracy
- USB interface to Raspberry Pi
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
- UART interface for high-speed data
- Calibration storage in internal flash

**Capabilities**:
- Absolute orientation (pitch, roll, yaw)
- Linear acceleration measurement
- Rotation vector and quaternion output
- Compass heading with magnetic declination correction

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
- **Charging time**: 6-8 hours from 20% to 100%
- **Operating temperature**: -20°C to 60°C
- **Safety features**: Over/under voltage, current, and temperature protection

### Solar Charging System
**Components**:
- **30W Solar Panel**: Monocrystalline silicon with aluminum frame
- **20A MPPT Charge Controller**: Maximum Power Point Tracking for efficiency
- **Charge regulation**: Automatic multi-stage charging profile

**Charging Performance**:
- **Peak charging**: 1.5A in full sunlight (30W panel)
- **Daily energy**: 120-180Wh in typical conditions
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
- **Channel 2**: Drive motor power consumption
- **Channel 3**: Blade motor and accessories power

## Motor and Drive Systems

### Drive Motor System
**Components**:
- **2x 12V Worm Gear DC Motors**: High torque, low speed for traction
- **Cytron MDDRC10 Motor Driver**: Dual-channel motor control
- **Hall Effect Sensors**: Wheel rotation feedback
- **Magnetic Encoders**: Precise distance and speed measurement

**Specifications**:
- **Motor power**: 50W per motor (100W total drive power)
- **Gear ratio**: 30:1 for high torque
- **Maximum speed**: 2.5 m/s (5.6 mph)
- **Typical operating speed**: 1.0-1.5 m/s
- **Differential steering**: Independent left/right wheel control

### Blade Motor System
**Components**:
- **997 DC Motor**: High-speed motor for blade rotation
- **IBT-4 Motor Driver**: High-current motor controller
- **GPIO Control**: Direction and enable signals from Raspberry Pi

**Specifications**:
- **Motor power**: 100W maximum
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

**Computer Vision Capabilities**:
- OpenCV integration for image processing
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

### Weatherproof Enclosures
**Main Electronics Enclosure**:
- IP65 rated protection against dust and water
- Ventilation for heat dissipation
- Clear access panels for maintenance
- Cable glands for all external connections

**Sensor Protection**:
- Individual weatherproof housings for exposed sensors
- UV-resistant materials for long-term outdoor exposure
- Easy access for cleaning and maintenance
- Secure mounting to prevent vibration damage

### Mechanical Platform
**Chassis Design**:
- Aluminum frame construction for durability
- Low center of gravity for stability on slopes
- Modular design for easy component access
- Integrated cable management and routing

**Cutting Deck**:
- Steel construction with protective guards
- Adjustable cutting height mechanism
- Grass discharge management
- Safety switches and emergency stops

## Connectivity and Communication

### Wireless Communications
**WiFi Connectivity**:
- 802.11ac dual-band (2.4GHz and 5GHz)
- WPA2/WPA3 security support
- Automatic reconnection and fallback
- Range: 100+ meters from access point

**Optional Cellular**:
- 4G LTE module for remote areas
- GPS tracking and remote monitoring
- Emergency communication capability
- Data usage optimization for cost control

### Wired Interfaces
**Available Ports**:
- Ethernet for reliable network connection
- USB ports for expansion and diagnostics
- HDMI for direct display connection
- MicroSD card for system storage and logging

## Expansion and Customization

### Available GPIO Pins
**Unused GPIO for expansion**:
- GPIO 19, 20, 21: Available for additional sensors
- GPIO 5, 6, 13, 16, 26: General purpose I/O
- Additional I2C addresses available on bus

### Expansion Possibilities
**Sensor Additions**:
- Additional ToF sensors for full perimeter coverage
- Ultrasonic sensors for different detection characteristics
- Light sensors for automatic lighting control
- Rain sensors for immediate weather response

**Actuator Additions**:
- LED lighting systems for night operation
- Horn or alarm for safety alerts
- Additional motors for specialized attachments
- Servo motors for adjustable components

## Maintenance Access Points

### Regular Maintenance Access
**Daily/Weekly Access**:
- Battery voltage and connection points
- Blade inspection and replacement area
- Camera lens and sensor cleaning points
- Display and control interface

**Monthly/Seasonal Access**:
- Motor inspection and lubrication points
- Drive belt and gear inspection
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

---

This hardware overview provides the foundation for understanding how your LawnBerryPi operates. For specific maintenance procedures, see the [Maintenance Guide](maintenance-guide.md). For troubleshooting hardware issues, consult the [Troubleshooting Guide](troubleshooting-guide.md).

*Hardware Overview - Part of LawnBerryPi Documentation v1.0*
