# Data Model: LawnBerry Pi v2 Unified System

## Hardware & Sensor Entities

### SensorData
**Purpose**: Real-time measurements from all hardware sensors
**Attributes**:
- `timestamp`: ISO 8601 timestamp with microsecond precision
- `imu_data`: BNO085 orientation, acceleration, gyroscope readings (UART4, 3Mbaud)
- `power_data`: INA3221 channels (1:Battery, 2:Unused, 3:Solar) voltage/current/power
- `distance_left`: VL53L0X ToF sensor readings (I2C 0x29) in millimeters
- `distance_right`: VL53L0X ToF sensor readings (I2C 0x30) in millimeters  
- `environmental`: BME280 temperature, humidity, pressure (I2C 0x76)
- `display_status`: SSD1306 OLED operational status (I2C 0x3C)
- `encoder_left`: Hall effect wheel encoder count and direction
- `encoder_right`: Hall effect wheel encoder count and direction
- `bus_status`: I2C/UART bus health and error conditions
- `validation_flags`: Sensor data quality and error detection

**Relationships**: 
- One-to-many with NavigationState (sensor fusion input)
- One-to-many with PowerManagement (power monitoring)

### NavigationState
**Purpose**: Current position, planned paths, and movement control
**Attributes**:
- `position`: GPS coordinates (lat/lon/altitude) with accuracy metadata
- `gps_mode`: 'ZED-F9P-USB-NTRIP' or 'Neo-8M-UART' or 'DEAD_RECKONING'
- `planned_path`: Array of GPS waypoints with timestamps
- `obstacle_map`: Real-time obstacle detection results
- `movement_commands`: Speed/direction for left/right drive motors
- `safety_constraints`: Emergency stop status, tilt detection, blade safety
- `dead_reckoning_state`: IMU+encoder fusion when GPS unavailable

**Relationships**:
- Many-to-one with SensorData (consumes IMU, GPS, encoder data)
- One-to-many with MotorControl (issues movement commands)

### MotorControl  
**Purpose**: Drive and cutting motor operation with safety interlocks
**Attributes**:
- `drive_controller`: 'RoboHAT-RP2040-Cytron-MDDRC10' or 'L298N-Fallback'
- `left_motor_speed`: PWM value (-100 to +100, negative = reverse)
- `right_motor_speed`: PWM value (-100 to +100, negative = reverse)
- `blade_motor_status`: IBT-4 H-Bridge control (GPIO24/25) on/off/speed
- `encoder_feedback`: Actual wheel speeds from hall effect sensors
- `safety_interlocks`: Tilt cutoff, emergency stop, blade safety status
- `serial_protocol`: Commands sent to RoboHAT RP2040 via `code.py` firmware

**Relationships**:
- Many-to-one with NavigationState (receives movement commands)
- One-to-many with PowerManagement (power consumption tracking)

### PowerManagement
**Purpose**: Battery, solar, and power optimization with constitutional compliance
**Attributes**:
- `battery_voltage`: INA3221 Channel 1 voltage (constitutional assignment)
- `battery_current`: INA3221 Channel 1 current (charge/discharge)
- `battery_percentage`: Calculated SoC with low-power thresholds
- `solar_voltage`: INA3221 Channel 3 voltage (constitutional assignment)
- `solar_current`: INA3221 Channel 3 current (generation)
- `power_mode`: 'NORMAL', 'POWER_SAVE', 'LOW_BATTERY', 'SOLAR_CHARGING'
- `location_preferences`: 'HOME', 'AM_SUN', 'PM_SUN' positions for power management
- `sun_seeking_active`: Boolean flag for solar-aware navigation

**Relationships**:
- One-to-many with SensorData (power monitoring data)
- One-to-many with NavigationState (influences return-to-charge behavior)

## AI & Vision Entities

### CameraStream
**Purpose**: Video frames and metadata with exclusive service ownership
**Attributes**:
- `frame_data`: Raw video frames from Picamera2
- `gstreamer_pipeline`: Pipeline configuration for encoding/streaming
- `stream_consumers`: List of services consuming frames via IPC
- `frame_metadata`: Timestamp, resolution, encoding parameters
- `ipc_socket_path`: Unix domain socket for frame distribution
- `exclusive_lock`: Service ownership enforcement

**Relationships**:
- One-to-many with AIProcessing (provides frames for inference)
- One-to-many with WebUI telemetry (provides streaming video)

### AIProcessing
**Purpose**: Object detection and inference with constitutional acceleration hierarchy
**Attributes**:
- `acceleration_mode`: 'CORAL_USB_VENV', 'HAILO_HAT', 'CPU_TFLITE_OPENCV'
- `model_inference_results`: Object detection confidence scores and bounding boxes
- `processing_latency`: Inference time tracking for performance monitoring
- `venv_isolation_status`: Package isolation compliance for Coral USB
- `graceful_degradation_path`: Fallback status through acceleration hierarchy

**Relationships**:
- Many-to-one with CameraStream (consumes video frames)
- One-to-many with NavigationState (provides obstacle detection input)
- One-to-many with TrainingData (generates training examples)

### TrainingData
**Purpose**: Dataset management with COCO JSON and YOLO TXT export support  
**Attributes**:
- `captured_images`: Image files with metadata
- `annotation_metadata`: Bounding boxes, labels, confidence scores
- `labeling_workflow_state`: Annotation progress and quality validation
- `export_formats`: 'COCO_JSON', 'YOLO_TXT', or both
- `dataset_splits`: Train/validation/test partitioning
- `quality_validation_status`: Dataset integrity and consistency checks

**Relationships**:
- Many-to-one with AIProcessing (receives inference examples)
- One-to-many with WebUI (AI Training page management)

## WebUI & Communication Entities

### WebUIPageContracts
**Purpose**: Seven mandated pages with defined objectives and data dependencies
**Attributes**:
- `page_name`: 'Dashboard', 'MapSetup', 'ManualControl', 'MowPlanning', 'AITraining', 'Settings', 'DocsHub'
- `data_dependencies`: Required sensor data, navigation state, power status
- `rest_endpoints`: API endpoints supporting page functionality
- `websocket_topics`: Real-time telemetry subscription topics
- `authentication_requirements`: Pages requiring operator credential gates

**Relationships**:
- One-to-many with TelemetryExchange (real-time data subscriptions)
- One-to-many with UserSession (authentication and permissions)

### TelemetryExchange
**Purpose**: Real-time bidirectional communication via WebSocket hub
**Attributes**:
- `websocket_connections`: Active client connections with metadata
- `topic_subscriptions`: Client subscriptions to telemetry streams
- `telemetry_cadence`: Configurable update frequency (1-10Hz, default 5Hz)
- `message_routing`: Topic-based message distribution
- `graceful_disconnection`: Client connection lifecycle management

**Relationships**:
- Many-to-one with SensorData (streams sensor readings)
- Many-to-one with NavigationState (streams position/status updates)
- Many-to-one with PowerManagement (streams battery/power status)

### UserSession
**Purpose**: Authentication state and audit logging
**Attributes**:
- `session_token`: JWT token for authenticated WebUI sessions
- `operator_credential`: Single shared credential (constitutional requirement)
- `authentication_gates`: Manual control, dataset export, configuration access
- `audit_log_entries`: Timestamped record of privileged operations
- `session_metadata`: IP address, user agent, login/logout timestamps

**Relationships**:
- One-to-many with WebUIPageContracts (controls page access)
- One-to-many with audit logs (tracks all privileged operations)

## System Configuration & Operations Entities

### HardwareBaseline
**Purpose**: Required vs optional component detection and configuration
**Attributes**:
- `pi_model`: 'RaspberryPi5', 'RaspberryPi4B' with memory configuration
- `gps_module`: 'ZED-F9P-USB' or 'Neo-8M-UART' or 'NONE' (with fallback)
- `ai_accelerator`: 'CORAL_USB', 'HAILO_HAT', 'CPU_ONLY' (hierarchy compliance)
- `drive_system`: 'RoboHAT-Cytron-MDDRC10' or 'L298N-Fallback'
- `hat_conflicts`: Detection of RoboHAT + Hailo HAT conflicts
- `graceful_degradation`: Fallback configurations for missing hardware

**Relationships**:
- One-to-many with all hardware entities (hardware capability constraints)

### SystemConfiguration
**Purpose**: Operational parameters and user-defined settings
**Attributes**:
- `mowing_zones`: Polygon definitions for yard boundaries and exclusion areas
- `location_preferences`: GPS coordinates for HOME, AM_SUN, PM_SUN positions
- `telemetry_settings`: Update frequencies, enabled/disabled sensors
- `map_provider`: 'GOOGLE_MAPS' (cost-optimized) or 'OPENSTREETMAP' (fallback)
- `simulation_mode`: SIM_MODE=1 for CI testing without physical hardware
- `constitutional_compliance`: Version tracking and validation status

**Relationships**:
- One-to-many with all operational entities (configuration parameters)

### OperationalData
**Purpose**: Metrics, logs, and historical data with persistence
**Attributes**:
- `telemetry_history`: Time-series sensor data for analysis
- `performance_metrics`: Latency, throughput, error rates
- `maintenance_records`: System events, errors, and recovery actions
- `backup_metadata`: Configuration snapshots and migration data
- `analytics_summaries`: Mowing efficiency, power optimization results

**Relationships**:
- Aggregates data from all other entities for historical analysis
- Supports backup/restore and migration operations

## Data Flow Summary

1. **Sensor Input**: SensorData → NavigationState → MotorControl
2. **Vision Pipeline**: CameraStream → AIProcessing → NavigationState  
3. **Power Management**: SensorData → PowerManagement → NavigationState
4. **WebUI Telemetry**: All entities → TelemetryExchange → WebUIPageContracts
5. **Configuration**: SystemConfiguration influences all operational entities
6. **Persistence**: OperationalData archives all entity states and transitions

## Constitutional Compliance

- **Platform Exclusivity**: All entities assume Raspberry Pi OS Bookworm, Python 3.11.x
- **Package Isolation**: AIProcessing enforces venv-coral isolation for Coral USB
- **Hardware Resource Coordination**: CameraStream implements exclusive ownership
- **Constitutional Hardware Compliance**: PowerManagement enforces INA3221 channel assignments
