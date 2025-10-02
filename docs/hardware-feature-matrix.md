# LawnBerryPi Hardware Feature Matrix

**Version:** 1.0  
**Purpose:** Comprehensive hardware configuration guide and capability matrix  
**Last Updated:** December 2024

## Overview

This document provides a complete matrix of hardware components, their capabilities, configuration options, and compatibility information. Use this guide to understand what features are available with different hardware configurations and plan system deployments.

---

## Core Processing Platform

### Raspberry Pi 4 Model B Configuration

| Component | Specification | Status | Notes |
|-----------|---------------|--------|-------|
| **CPU** | ARM Cortex-A72 Quad-core 1.5GHz | ✅ Implemented | Sufficient for all processing needs |
| **RAM** | 8GB LPDDR4 | ✅ Implemented | Supports advanced computer vision |
| **Storage** | MicroSD 64GB+ Class 10 | ✅ Implemented | High-speed card recommended |
| **GPIO** | 40-pin header | ✅ Fully Utilized | Pin mapping 100% compliant |
| **Camera Interface** | CSI connector | ✅ Implemented | 1920x1080@30fps capability |
| **USB Ports** | 4x USB 3.0 | ✅ Utilized | GPS, TPU, external devices |
| **Network** | Gigabit Ethernet + WiFi | ✅ Implemented | Dual connectivity options |

**Performance Capabilities:**
- Concurrent processing of 11 microservices
- Real-time computer vision at 30fps
- WebSocket streaming to multiple clients
- Complex mowing pattern calculations
- Sensor fusion processing at 100Hz

---

## Navigation and Positioning Systems

### GPS/GNSS Configuration

| Component | Model | Interface | Status | Accuracy | Features |
|-----------|-------|-----------|--------|----------|----------|
| **Primary GPS** | SparkFun GPS-RTK-SMA | USB (/dev/ttyACM0) | ✅ Implemented | <10cm RTK | Real-time corrections |
| **RTK Corrections** | Ohio DOT Network | Internet | ✅ Active | <2cm | Professional grade |
| **Backup GPS** | Pi Hat GPS (optional) | GPIO UART | ⚠️ Optional | 3-5m | Fallback capability |

**GPS Feature Matrix:**
- ✅ Real-time positioning
- ✅ RTK correction integration  
- ✅ Multi-constellation support (GPS, GLONASS, Galileo)
- ✅ Autonomous fix acquisition
- ✅ Position accuracy monitoring
- ⚠️ Backup GPS configuration (optional)

### Inertial Measurement Unit (IMU)

| Component | Model | Interface | Status | Capabilities |
|-----------|-------|-----------|--------|--------------|
| **IMU** | BNO085 9-DOF | UART (/dev/ttyAMA4) | ✅ Implemented | Full orientation |
| **Accelerometer** | Built-in 3-axis | Hardware | ✅ Active | ±16g range |
| **Gyroscope** | Built-in 3-axis | Hardware | ✅ Active | ±2000°/s |
| **Magnetometer** | Built-in 3-axis | Hardware | ✅ Active | Compass heading |

**IMU Capabilities:**
- ✅ Tilt and slope detection
- ✅ Collision impact detection
- ✅ Heading determination
- ✅ Motion detection
- ✅ Stability monitoring
- ✅ Drop detection

---

## Sensor Systems

### Obstacle Detection Sensors

| Sensor Type | Model | Interface | Range | Status | Use Case |
|-------------|-------|-----------|-------|--------|----------|
| **ToF Left** | VL53L0X | I2C (0x29) | 30-2000mm | ✅ Implemented | Left side obstacles |
| **ToF Right** | VL53L0X | I2C (0x30) | 30-2000mm | ✅ Implemented | Right side obstacles |
| **Camera Vision** | Pi Camera v2 | CSI | Visual range | ✅ Implemented | Object recognition |
| **Ultrasonic** | HC-SR04 (optional) | GPIO | 20-4000mm | ⚠️ Optional | Additional coverage |

**Sensor Fusion Matrix:**
- ✅ Multi-sensor obstacle detection
- ✅ Cross-validation between sensors
- ✅ Confidence scoring
- ✅ Real-time processing
- ✅ Environmental adaptation

### Environmental Monitoring

| Parameter | Sensor | Interface | Range | Status | Purpose |
|-----------|--------|-----------|-------|--------|---------|
| **Temperature** | BME280 | I2C (0x76) | -40°C to +85°C | ✅ Implemented | Operating limits |
| **Humidity** | BME280 | I2C (0x76) | 0-100% RH | ✅ Implemented | Moisture detection |
| **Pressure** | BME280 | I2C (0x76) | 300-1100 hPa | ✅ Implemented | Weather prediction |
| **Light Level** | Optional sensor | I2C/ADC | Variable | ⚠️ Optional | Dawn/dusk detection |

---

## Vision and AI Systems

### Camera Configuration

| Component | Specification | Status | Capabilities |
|-----------|---------------|--------|--------------|
| **Camera Module** | Pi Camera v2 8MP | ✅ Implemented | 1920x1080@30fps |
| **Lens** | Fixed focus | ✅ Standard | 62.2° field of view |
| **Night Vision** | Optional IR camera | ⚠️ Optional | Low-light operation |
| **Pan/Tilt** | Optional servo mount | ⚠️ Optional | 360° coverage |

**Vision Processing Capabilities:**
- ✅ Real-time object detection
- ✅ Obstacle identification
- ✅ Edge detection for boundaries
- ✅ Color-based grass detection
- ⚠️ Advanced AI with TPU (optional)

### AI Acceleration (Optional)

| Component | Model | Interface | Status | Performance Gain |
|-----------|-------|-----------|--------|------------------|
| **Google Coral TPU** | USB Accelerator | USB 3.0 | ❌ Not Implemented | 10-100x AI speedup |
| **Neural Compute Stick** | Intel Movidius | USB 3.0 | ⚠️ Compatible | 5-20x AI speedup |
| **Jetson Nano** | NVIDIA | GPIO/USB | ⚠️ Alternative | Complete AI platform |

**AI Enhancement Matrix:**
- ❌ TPU-accelerated object detection
- ❌ Advanced computer vision models  
- ❌ Real-time semantic segmentation
- ❌ Custom lawn-specific AI models
- ✅ CPU-based OpenCV processing (current)

---

## Power Management System

### Battery Configuration

| Component | Specification | Status | Capabilities |
|-----------|---------------|--------|--------------|
| **Primary Battery** | 30Ah LiFePO4 12V | ✅ Implemented | 8-12 hours operation |
| **Chemistry** | Lithium Iron Phosphate | ✅ Confirmed | Safe, long-life |
| **BMS** | Built-in protection | ✅ Active | Overcurrent, thermal |
| **Backup Battery** | Optional 12V SLA | ⚠️ Optional | Emergency power |

**Battery Management Features:**
- ✅ Real-time voltage/current monitoring
- ✅ State of charge calculation
- ✅ Health monitoring
- ✅ Temperature protection
- ✅ Low voltage cutoff
- ⚠️ Automatic shutdown (requires RP2040 enhancement)

### Solar Charging System

| Component | Specification | Status | Performance |
|-----------|---------------|--------|-------------|
| **Solar Panel** | 30W Monocrystalline | ✅ Implemented | Peak 30W output |
| **Charge Controller** | 20A MPPT | ✅ Implemented | 95%+ efficiency |
| **Mounting** | Adjustable tilt | ✅ Physical | Seasonal optimization |
| **Tracking** | Optional sun tracking | ❌ Not Implemented | 20-30% gain potential |

**Solar Capabilities:**
- ✅ Maximum Power Point Tracking
- ✅ Battery protection during charging
- ✅ Efficiency monitoring
- ✅ Weather-based optimization
- ❌ Automatic sun tracking (future enhancement)

### Power Monitoring

| Channel | Monitor Point | Sensor | Status | Purpose |
|---------|---------------|--------|--------|---------|
| **Channel 1** | Solar Input | INA3221 | ✅ Active | Generation monitoring |
| **Channel 2** | Reserved | INA3221 | ⚠️ Available | Future expansion |
| **Channel 3** | Battery Bank | INA3221 | ✅ Active | Consumption monitoring |

---

## Motor and Drive Systems

### Drive Motors

| Component | Specification | Status | Control Method |
|-----------|---------------|--------|----------------|
| **Left Motor** | 12V Worm Gear DC | ✅ Implemented | PWM via MDDRC10 |
| **Right Motor** | 12V Worm Gear DC | ✅ Implemented | PWM via MDDRC10 |
| **Motor Driver** | Cytron MDDRC10 | ✅ Implemented | Dual H-bridge |
| **Encoders** | Hall Effect | ✅ Implemented | Speed feedback |

**Drive Capabilities:**
- ✅ Variable speed control (0-100%)
- ✅ Precise directional control
- ✅ Speed feedback monitoring
- ✅ Stall detection
- ✅ Emergency stop capability

### Cutting System

| Component | Specification | Status | Safety Features |
|-----------|---------------|--------|-----------------|
| **Blade Motor** | 997 DC Motor | ✅ Implemented | High-speed cutting |
| **Blade Driver** | IBT-4 H-Bridge | ✅ Implemented | Bidirectional control |
| **Safety Switch** | Tilt cutoff | ✅ Implemented | Auto-disable on tilt |
| **Blade Guard** | Physical protection | ✅ Required | User safety |

---

## Communication Systems

### Primary Communication

| Interface | Protocol | Status | Usage |
|-----------|----------|--------|-------|
| **WiFi** | 802.11n/ac | ✅ Implemented | Primary connectivity |
| **Ethernet** | Gigabit | ✅ Available | Backup/setup |
| **Bluetooth** | 5.0 | ⚠️ Available | Optional RC/maintenance |

### Internal Communication

| Interface | Protocol | Devices | Status |
|-----------|----------|---------|--------|
| **I2C Bus** | 400kHz | Sensors, Display | ✅ Implemented |
| **UART** | Various baud | GPS, IMU | ✅ Implemented |
| **USB** | USB 3.0 | GPS, TPU | ✅ Implemented |
| **GPIO** | Digital I/O | Motors, switches | ✅ Implemented |

---

## Display and User Interface

### On-Board Display

| Component | Specification | Status | Capabilities |
|-----------|---------------|--------|--------------|
| **OLED Display** | SSD1306 128x64 | ✅ Implemented | Status information |
| **Interface** | I2C (0x3c) | ✅ Active | Real-time updates |
| **Backlight** | None (OLED) | ✅ Self-lit | Day/night readable |

**Display Information:**
- ✅ System status
- ✅ Battery level
- ✅ GPS status
- ✅ Current operation mode
- ✅ Error messages
- ✅ Network connectivity

### Remote Interface

| Interface | Type | Status | Capabilities |
|-----------|------|--------|--------------|
| **Web UI** | Responsive web app | ✅ Implemented | Full system control |
| **Mobile App** | Progressive web app | ✅ Available | Touch-optimized |
| **API Access** | REST + WebSocket | ✅ Implemented | Developer integration |

---

## Optional and Future Hardware

### Remote Control (Optional)

| Component | Interface | Status | Capabilities |
|-----------|-----------|--------|--------------|
| **RC Receiver** | PPM/PWM | ❌ Not Implemented | Manual override |
| **Emergency Remote** | 2.4GHz | ⚠️ Optional | Safety backup |
| **Range** | 100-500m | ⚠️ Dependent | Line of sight |

### Advanced Sensors (Optional)

| Sensor Type | Purpose | Interface | Status |
|-------------|---------|-----------|--------|
| **LiDAR** | 360° obstacle detection | USB/Serial | ⚠️ Compatible |
| **Radar** | Weather-resistant detection | GPIO/SPI | ⚠️ Compatible |
| **Ground sensors** | Soil moisture, pH | I2C/ADC | ⚠️ Expandable |
| **Weather station** | Local micro-climate | I2C/1-Wire | ⚠️ Compatible |

---

## Hardware Configuration Matrix

### Standard Configuration (Current Implementation)

| System | Components | Status | Capability Level |
|--------|------------|--------|------------------|
| **Processing** | Pi 4B 8GB | ✅ Complete | Professional |
| **Navigation** | RTK GPS + IMU | ✅ Complete | Sub-centimeter |
| **Sensors** | ToF + Camera + Environmental | ✅ Complete | Comprehensive |
| **Power** | 30Ah LiFePO4 + 30W Solar | ✅ Complete | Full-day operation |
| **Communication** | WiFi + I2C + UART | ✅ Complete | Fully connected |
| **Safety** | Multi-sensor fusion | ✅ Complete | Professional grade |

### Enhanced Configuration (With Optional Components)

| System | Additional Components | Status | Capability Gain |
|--------|----------------------|--------|-----------------|
| **AI Processing** | Google Coral TPU | ❌ Available | 10x vision performance |
| **Remote Control** | RC receiver system | ❌ Available | Manual override |
| **Advanced Sensors** | LiDAR, additional ToF | ⚠️ Compatible | 360° detection |
| **Power Expansion** | Backup battery | ⚠️ Compatible | Extended operation |
| **Weather Station** | Local sensors | ⚠️ Compatible | Micro-climate data |

### Minimal Configuration (Cost-Optimized)

| System | Reduced Components | Impact | Cost Savings |
|--------|-------------------|--------|--------------|
| **Processing** | Pi 4B 8GB | Moderate | 20% reduction |
| **GPS** | Standard GPS (no RTK) | Reduced accuracy | 40% GPS cost |
| **Sensors** | Single ToF sensor | Reduced safety | 30% sensor cost |
| **Power** | Smaller battery/panel | Shorter operation | 25% power cost |

---

## Pin Usage and Expansion Capabilities

### GPIO Pin Allocation

| Physical Pin | GPIO | Function | Device | Status |
|--------------|------|----------|--------|--------|
| 15 | 22 | Output | Left ToF Shutdown | ✅ Used |
| 16 | 23 | Output | Right ToF Shutdown | ✅ Used |
| 18 | 24 | Output | Blade Controller IN1 | ✅ Used |
| 22 | 25 | Output | Blade Controller IN2 | ✅ Used |
| 31 | 6 | Input | Left ToF Interrupt | ✅ Used |
| 32 | 12 | Input | Right ToF Interrupt | ✅ Used |
| 19 | 10 | - | **Available** | ⚠️ Free |
| 23 | 11 | - | **Available** | ⚠️ Free |
| 26 | 7 | - | **Available** | ⚠️ Free |
| 29 | 5 | - | **Available** | ⚠️ Free |

### I2C Device Addresses

| Address | Device | Status | Notes |
|---------|--------|--------|-------|
| 0x29 | Left ToF Sensor | ✅ Used | Default address |
| 0x30 | Right ToF Sensor | ✅ Used | Reprogrammed address |
| 0x3c | OLED Display | ✅ Used | Standard SSD1306 |
| 0x40 | Power Monitor | ✅ Used | INA3221 |
| 0x76 | Environmental Sensor | ✅ Used | BME280 |
| 0x48 | **Available** | ⚠️ Free | ADC expansion |
| 0x50-0x57 | **Available** | ⚠️ Free | EEPROM range |

### Expansion Capabilities

**Available Interfaces:**
- 5x GPIO pins available for expansion
- 3x I2C addresses available  
- 2x USB 3.0 ports available
- SPI interface available
- Additional UART via GPIO

**Potential Expansions:**
- Additional ToF sensors (front/rear)
- Soil moisture sensors
- Weather station integration
- Advanced lighting systems
- Security cameras
- Emergency beacons

---

## Installation and Configuration Guide

### Hardware Setup Sequence

1. **Core Assembly:**
   - Mount Raspberry Pi and RoboHAT
   - Install sensors per pin mapping
   - Connect power distribution

2. **Sensor Installation:**
   - Mount ToF sensors at front corners
   - Install IMU with proper orientation
   - Mount camera with clear field of view
   - Install environmental sensor

3. **Power System:**
   - Install battery in weatherproof enclosure
   - Mount solar panel with optimal exposure
   - Connect charge controller and monitoring

4. **Verification:**
   - Test all sensor connections
   - Verify power system operation
   - Confirm GPIO pin assignments
   - Validate communication interfaces

### Configuration Requirements

**Software Configuration:**
- Hardware configuration in `config/hardware.yaml`
- Pin mapping verification required
- Sensor calibration recommended
- Power thresholds adjustment

**Hardware Configuration:**
- GPS antenna positioning for sky view
- Camera angle and focus adjustment
- Solar panel optimal positioning
- Sensor mounting and protection

---

## Troubleshooting Matrix

### Common Hardware Issues

| Symptom | Possible Cause | Hardware Check | Solution |
|---------|----------------|----------------|----------|
| **No GPS fix** | Antenna obstruction | Sky view clearance | Relocate antenna |
| **ToF sensor errors** | Dirty sensor face | Visual inspection | Clean sensor lens |
| **Power issues** | Connection problems | Voltage measurements | Check all connections |
| **Camera not working** | Cable/connection | CSI cable check | Reseat camera cable |
| **I2C device missing** | Address conflict | I2C scan | Check address assignment |

### Diagnostic Tools

**Hardware Tests:**
- GPIO test scripts
- I2C device scanning
- Sensor individual testing
- Power system monitoring
- Communication verification

**Built-in Diagnostics:**
- System health dashboard
- Sensor status monitoring
- Power consumption tracking
- Error logging and analysis

---

## Maintenance Schedule

### Hardware Maintenance Matrix

| Component | Frequency | Maintenance Task | Tools Required |
|-----------|-----------|------------------|----------------|
| **Camera** | Weekly | Clean lens | Soft cloth |
| **ToF Sensors** | Weekly | Clean sensor face | Cotton swabs |
| **Solar Panel** | Monthly | Clean surface | Water, soft brush |
| **Connections** | Monthly | Inspect and tighten | Screwdrivers |
| **Battery** | Quarterly | Performance test | Multimeter |
| **Mechanical** | Seasonally | Lubricate, inspect | Lubricants |

### Replacement Schedule

| Component | Expected Life | Replacement Indicator |
|-----------|---------------|----------------------|
| **MicroSD Card** | 2-3 years | Performance degradation |
| **Battery** | 5-8 years | Capacity < 80% |
| **Camera** | 3-5 years | Image quality decline |
| **Sensors** | 5-10 years | Accuracy drift |
| **Motors** | 3-5 years | Performance issues |

---

## Specifications Summary

### System Capabilities Matrix

| Capability | Current Implementation | Optional Enhancement | Future Potential |
|------------|----------------------|---------------------|------------------|
| **Positioning Accuracy** | <10cm RTK | <2cm with base station | mm-level precision |
| **Obstacle Detection** | 0.03-2m ToF + vision | 360° LiDAR | AI-enhanced detection |
| **Operation Time** | 8-12 hours | 16+ hours with backup | 24/7 with tracking |
| **AI Processing** | CPU OpenCV | TPU acceleration | Edge AI integration |
| **Connectivity** | WiFi primary | Cellular backup | Satellite uplink |
| **Weather Resistance** | IP54 rating | IP67 upgrade | Extreme weather |

**Performance Benchmarks:**
- Sensor processing: 100Hz update rate
- Vision processing: 30fps real-time
- Navigation accuracy: Sub-centimeter positioning
- Power efficiency: 45-60W typical consumption
- Communication latency: <50ms local network
- Safety response time: <100ms emergency stop

---

## Software Integration Features (V2 API)

### Backend Services

| Service | Purpose | Status | Key Features |
|---------|---------|--------|--------------|
| **TelemetryHub** | Real-time data aggregation | ✅ Implemented | WebSocket streaming, persistence, export |
| **SensorManager** | Hardware sensor coordination | ✅ Implemented | Multi-sensor fusion, calibration |
| **RoboHATService** | Serial bridge to RP2040 | ✅ Implemented | Command translation, status monitoring |
| **MotorService** | Motor control coordination | ✅ Implemented | Safety interlocks, speed control |
| **MapsService** | Map provider management | ✅ Implemented | GeoJSON validation, fallback support |
| **SettingsService** | Configuration management | ✅ Implemented | Profile versioning, validation |

### Frontend Components

| Component | Purpose | Status | Capabilities |
|-----------|---------|--------|--------------|
| **SystemStore** | Telemetry state management | ✅ Implemented | Real-time updates, error handling |
| **ControlStore** | Control command management | ✅ Implemented | Lockout handling, command queuing |
| **MapStore** | Map configuration state | ✅ Implemented | Boundary editing, marker management |
| **DashboardView** | System overview UI | ✅ Implemented | Telemetry display, status cards |
| **ControlView** | Motor control interface | ✅ Implemented | Command buttons, safety indicators |
| **MapView** | Interactive map UI | ✅ Implemented | Boundary editor, zone management |
| **SettingsView** | Configuration UI | ✅ Implemented | Profile management, validation |
| **DocsHubView** | Documentation browser | ✅ Implemented | Offline bundle support |

### API Endpoints (V2)

| Endpoint Category | Count | Status | Features |
|------------------|-------|--------|----------|
| **Telemetry** | 3 | ✅ Complete | Stream, export, subscribe |
| **Control** | 4 | ✅ Complete | Drive, blade, stop, status |
| **Maps** | 4 | ✅ Complete | Configuration CRUD, fallback |
| **Settings** | 2 | ✅ Complete | Profile GET/PUT, validation |
| **Documentation** | 2 | ✅ Complete | Bundle generation, artifacts |
| **Planning** | 3 | ✅ Complete | Job management, scheduling |
| **AI** | 2 | ✅ Complete | Dataset management, export |

### WebSocket Topics

| Topic | Purpose | Update Rate | Status |
|-------|---------|-------------|--------|
| **telemetry** | Sensor data streaming | 1-10Hz | ✅ Active |
| **control** | Command echoes, lockouts | On event | ✅ Active |
| **maps** | Map updates | On change | ✅ Active |
| **ai** | Processing results | On completion | ✅ Active |

### Data Models

| Model Category | Models | Status | Validation |
|----------------|--------|--------|------------|
| **Telemetry** | 8 models | ✅ Complete | Pydantic v2 |
| **Control** | 4 models | ✅ Complete | Pydantic v2 |
| **Maps** | 5 models | ✅ Complete | GeoJSON + Shapely |
| **Settings** | 9 models | ✅ Complete | Branding checksums |
| **Planning** | 3 models | ✅ Complete | Pydantic v2 |

### Constitutional Compliance

| Requirement | Implementation | Status | Validation Method |
|-------------|----------------|--------|-------------------|
| **Latency Targets** | ≤250ms (Pi 5), ≤350ms (Pi 4B) | ✅ Enforced | Performance tests |
| **Audit Logging** | All state changes logged | ✅ Implemented | Audit trail verification |
| **Remediation Links** | All errors include docs links | ✅ Implemented | Error response inspection |
| **Branding Validation** | Checksum verification | ✅ Implemented | Settings validation |
| **SIM Mode Coverage** | All hardware operations | ✅ Implemented | Test suite verification |
| **Offline Documentation** | Bundle generation | ✅ Implemented | Archive creation script |

---

**Document Version:** 2.0  
**Last Updated:** October 2025  
**Next Review:** January 2026

This hardware feature matrix provides comprehensive information for planning, deploying, and maintaining LawnBerryPi systems across different hardware configurations and use cases. For V2 API details and operational procedures, see [OPERATIONS.md](OPERATIONS.md).
