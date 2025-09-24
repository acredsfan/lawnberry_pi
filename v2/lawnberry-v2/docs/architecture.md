# LawnBerry Pi v2 Architecture

## Overview

LawnBerry Pi v2 is an autonomous robotic lawn mower system designed exclusively for Raspberry Pi OS Bookworm (ARM64). The architecture follows constitutional principles ensuring platform exclusivity, AI acceleration hierarchy, code quality gates, and comprehensive testing.

## System Architecture

### High-Level Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend       │    │   Hardware      │
│   (React/Vite)  │────│   (FastAPI)     │────│   (Sensors/     │
│                 │    │                 │    │    Motors)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                    ┌─────────┼─────────┐
                    │         │         │
            ┌───────▼───┐ ┌───▼───┐ ┌───▼─────┐
            │ WebSocket │ │  AI   │ │ Safety  │
            │    Hub    │ │ Accel │ │ System  │
            └───────────┘ └───────┘ └─────────┘
```

### Service Architecture

LawnBerry Pi v2 consists of three main systemd services:

1. **mower-core.service** - Core mowing logic, navigation, and safety systems
2. **camera-stream.service** - Camera processing and AI inference
3. **webui.service** - Web interface and API endpoints

## Directory Structure

### Source Code Layout

```
src/lawnberry/
├── models/              # Pydantic data models
│   ├── sensor_data.py   # SensorData, PowerManagement models
│   ├── navigation.py    # NavigationState, MotorControl models
│   ├── safety.py        # SafetyEvents model
│   └── telemetry.py     # TelemetryData, SystemConfiguration models
├── services/            # Business logic services
│   ├── sensor_service.py    # Hardware sensor interfaces
│   ├── navigation_service.py # Path planning and navigation
│   ├── safety_service.py    # Emergency stops and interlocks
│   ├── motion_service.py    # Motor control abstraction
│   └── camera_service.py    # Camera pipeline management
├── api/                 # FastAPI REST endpoints
│   ├── system.py        # System status and configuration
│   ├── sensors.py       # Sensor data endpoints
│   ├── navigation.py    # Navigation control endpoints
│   └── camera.py        # Camera streaming endpoints
├── core/                # Core system components
│   ├── websocket_hub.py # Real-time communication hub
│   ├── config.py        # Configuration management
│   └── database.py      # SQLite database interface
├── runners/             # AI acceleration implementations
│   ├── base_runner.py   # Abstract base runner interface
│   ├── cpu_tflite_runner.py    # CPU TensorFlow Lite (fallback)
│   ├── hailo_runner.py         # Hailo AI Hat (optional)
│   └── coral_runner.py         # Coral TPU (isolated venv)
├── adapters/            # Hardware abstractions and simulation
│   ├── sim_sensors.py   # Simulation sensor adapters
│   ├── gpio_adapter.py  # GPIO hardware interface
│   └── i2c_adapter.py   # I2C sensor interface
├── cli/                 # Command-line interface
│   ├── main.py          # CLI entry point
│   ├── system_commands.py # System management commands
│   └── config_commands.py # Configuration commands
└── utils/               # Utility functions and helpers
    ├── logging.py       # Structured logging setup
    ├── validation.py    # Data validation helpers
    └── hardware_detect.py # Hardware detection utilities
```

### Test Structure

```
tests/
├── conftest.py          # Test configuration and fixtures
├── contract/            # API contract tests
│   ├── test_rest_api.py     # REST endpoint contract tests
│   └── test_websocket.py    # WebSocket contract tests
├── integration/         # Service integration tests
│   ├── test_ai_runners.py   # AI acceleration integration
│   ├── test_sensor_integration.py # Hardware sensor tests
│   └── test_service_communication.py # Inter-service tests
└── unit/                # Unit tests for individual components
    ├── test_models.py       # Pydantic model tests
    ├── test_services.py     # Service logic tests
    └── test_utils.py        # Utility function tests
```

## Constitutional Compliance

### Platform Exclusivity
- **Target**: Raspberry Pi OS Bookworm (ARM64) only
- **Hardware**: Pi 5 primary, Pi 4B compatible
- **Python**: 3.11+ required
- **Validation**: Runtime checks in `__init__.py` prevent execution on other platforms

### AI Acceleration Hierarchy
```
Coral TPU (isolated venv) → Hailo AI Hat (optional) → CPU TFLite (fallback)
```

- **Coral Runner**: Runs in isolated virtual environment to prevent package conflicts
- **Hailo Runner**: Optional mid-tier acceleration with graceful fallback
- **CPU Runner**: Universal fallback using TensorFlow Lite

### Code Quality Gates
- **Package Manager**: UV with lockfile discipline
- **Linting**: Ruff for code analysis and import sorting
- **Formatting**: Black for consistent code style
- **Type Checking**: MyPy with strict mode enabled
- **Testing**: Pytest with async support and coverage reporting

### Documentation-as-Contract
- All code changes must update corresponding documentation
- CI fails if source changes don't include documentation updates
- Specifications in `/spec/` drive development decisions
- Architecture Decision Records (ADRs) document design choices

## Data Flow

### Telemetry Pipeline
```
Hardware Sensors → Sensor Service → WebSocket Hub → Frontend Display
                ↓
             Database Storage ← Telemetry Aggregation ← Service Data
```

### Control Pipeline
```
Frontend Commands → WebSocket Hub → Service Router → Hardware Controllers
                                 ↓
                           Safety Interlock Check → Emergency Stop if needed
```

### AI Pipeline
```
Camera Stream → AI Runner Selection → Object Detection → Navigation Input
     ↓               ↓                      ↓                ↓
   H.264         Coral/Hailo/CPU       Bounding Boxes   Obstacle Avoidance
```

## Hardware Interface

### Sensor Configuration
- **IMU**: BNO085 on UART4 (/dev/ttyAMA4)
- **Power**: INA3221 I2C power monitoring
- **ToF**: VL53L0X sensors on I2C bus
- **Encoders**: Hall effect sensors on GPIO pins

### Motor Control
- **Driver**: Cytron MDDRC10 via RoboHAT RP2040 bridge
- **Communication**: Serial protocol over USB
- **Safety**: Hardware emergency stop integration

### Camera System
- **Module**: Pi Camera v2/v3 via Picamera2
- **Pipeline**: Picamera2 → GStreamer → H.264/MJPEG
- **AI Integration**: Frame extraction for inference pipeline

## Performance Characteristics

### Real-time Requirements
- **Telemetry Latency**: <100ms from sensor to UI
- **Emergency Stop**: <10ms from trigger to motor shutdown
- **AI Inference**: <200ms for obstacle detection
- **Video Streaming**: 720p@15fps with AI overlay

### Resource Usage
- **Memory**: <512MB baseline, <1GB with AI acceleration
- **CPU**: <50% average load on Pi 5, <70% on Pi 4B
- **Storage**: <2GB for application, log rotation configured
- **Network**: Local WiFi only, no external dependencies

## Security Model

### Network Security
- **Scope**: Local network operation only
- **Authentication**: Basic session-based auth for web interface
- **Communication**: WebSocket with origin validation
- **API**: Rate limiting on REST endpoints

### System Security
- **Process Isolation**: Systemd user services with restricted permissions
- **File System**: Minimal read/write permissions, no sudo required
- **Coral Isolation**: Separate Python environment prevents package conflicts
- **Hardware Access**: GPIO/I2C permissions via system groups

## Deployment Model

### Installation Process
1. **Bootstrap Script**: `scripts/pi_bootstrap.sh` handles full setup
2. **Environment**: UV creates locked virtual environment
3. **Services**: Systemd unit files installed and enabled
4. **Configuration**: `.env` file generated with hardware detection
5. **Validation**: Hardware compatibility check and calibration

### Service Management
```bash
# Service control
sudo systemctl start mower-core camera-stream webui
sudo systemctl enable mower-core camera-stream webui
sudo systemctl status mower-core

# Logs and monitoring
journalctl -u mower-core -f
journalctl -u camera-stream -f
journalctl -u webui -f
```

### Configuration Management
- **Environment**: `.env` files loaded via python-dotenv
- **Database**: SQLite with automatic migration support
- **Hardware**: YAML configuration in `/spec/hardware.yaml`
- **Calibration**: Per-sensor calibration data in database

## Development Workflow

### Testing Strategy
1. **Unit Tests**: Individual component testing with mocks
2. **Integration Tests**: Service interaction testing with simulation
3. **Contract Tests**: API specification validation
4. **Hardware Tests**: Real hardware validation (manual)

### Continuous Integration
- **Linting**: Ruff and Black formatting checks
- **Type Checking**: MyPy static analysis
- **Testing**: Full test suite with coverage reporting
- **Constitutional Compliance**: Platform and package validation
- **Documentation Drift**: Ensures docs stay synchronized with code

### Release Process
1. **Feature Development**: Branch-based development with PR reviews
2. **Constitutional Validation**: All changes must pass compliance checks
3. **Testing**: Full test suite must pass including hardware simulation
4. **Documentation**: All changes must include documentation updates
5. **Deployment**: Automated installation via bootstrap script