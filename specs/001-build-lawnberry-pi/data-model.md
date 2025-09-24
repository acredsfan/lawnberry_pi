# Data Model: LawnBerry Pi v2

## Core Entities

### SensorData
**Purpose**: Real-time measurements from all hardware sensors
**Fields**:
- `timestamp`: ISO datetime of measurement
- `sensor_type`: Enum (IMU, POWER, TOF, ENCODER)
- `sensor_id`: String identifier for multi-sensor types
- `raw_values`: Dict of sensor-specific measurements
- `processed_values`: Dict of calibrated/filtered values
- `quality_score`: Float (0.0-1.0) indicating data reliability
- `status`: Enum (ACTIVE, DEGRADED, FAILED)
**Relationships**: Referenced by NavigationState, SafetyEvents
**Validation**: Timestamp within last 10 seconds, quality_score range, required fields per sensor_type

### NavigationState
**Purpose**: Current position, planned path, and movement commands
**Fields**:
- `position_x`: Float meters from origin
- `position_y`: Float meters from origin
- `heading`: Float degrees (0-360)
- `velocity`: Float m/s current speed
- `planned_path`: List of coordinate waypoints
- `obstacle_map`: Grid of detected obstacles
- `current_command`: Dict with motor speeds and directions
- `navigation_mode`: Enum (MANUAL, AUTO, RETURN_HOME, EMERGENCY_STOP)
- `path_confidence`: Float (0.0-1.0) path planning confidence
**Relationships**: Uses SensorData for positioning, triggers MotorControl commands
**State Transitions**: MANUAL ↔ AUTO ↔ RETURN_HOME, any → EMERGENCY_STOP

### MotorControl
**Purpose**: Speed and direction commands for propulsion and cutting
**Fields**:
- `left_wheel_speed`: Float (-1.0 to 1.0) normalized speed
- `right_wheel_speed`: Float (-1.0 to 1.0) normalized speed
- `cutting_blade_speed`: Float (0.0 to 1.0) cutting motor intensity
- `motor_status`: Dict per motor with health indicators
- `emergency_stop`: Boolean immediate stop override
- `last_command_time`: Timestamp of last command
- `safety_lockout`: Boolean prevents motor operation
**Relationships**: Controlled by NavigationState, monitored by SafetyEvents
**Validation**: Speed ranges, safety lockout prevents operation, command timeout

### SafetyEvents
**Purpose**: Emergency conditions, obstacles, and system alerts
**Fields**:
- `event_type`: Enum (OBSTACLE, TILT, POWER_LOW, SENSOR_FAIL, USER_STOP)
- `severity`: Enum (INFO, WARNING, CRITICAL)
- `description`: Human-readable event description
- `detected_at`: Timestamp of detection
- `resolved_at`: Optional timestamp of resolution
- `trigger_data`: Dict with sensor readings that triggered event
- `response_actions`: List of automated responses taken
- `requires_manual_reset`: Boolean for critical events
**Relationships**: References SensorData that triggered event
**Validation**: Severity-appropriate response actions, critical events require manual reset

### PowerManagement
**Purpose**: Battery levels, consumption, and charging status
**Fields**:
- `battery_voltage`: Float current battery voltage
- `battery_percentage`: Float (0.0-100.0) estimated charge
- `current_draw`: Float amperes current consumption
- `power_consumption`: Float watts total system power
- `charging_status`: Enum (DISCHARGING, CHARGING, CHARGED, FAULT)
- `estimated_runtime`: Integer minutes remaining at current consumption
- `low_power_mode`: Boolean reduced functionality mode
- `charge_cycles`: Integer total charge cycles
**Relationships**: Monitored by SafetyEvents for low power conditions
**Validation**: Voltage ranges, percentage consistency, consumption limits

### CameraStream
**Purpose**: Video frames and AI processing metadata
**Fields**:
- `frame_id`: Unique identifier for each frame
- `timestamp`: Frame capture timestamp
- `resolution`: Tuple (width, height) in pixels
- `frame_rate`: Float fps current capture rate
- `encoding`: String format (H264, MJPEG)
- `ai_annotations`: List of detected objects with bounding boxes
- `processing_latency`: Float ms from capture to AI processing
- `stream_quality`: Enum (LOW, MEDIUM, HIGH) based on bandwidth
**Relationships**: Processed by AIProcessing for object detection
**Validation**: Resolution limits, frame rate constraints, encoding support

### UserSession
**Purpose**: Web interface connections and user interactions
**Fields**:
- `session_id`: Unique session identifier
- `connection_time`: Timestamp of WebSocket connection
- `last_activity`: Timestamp of last user interaction
- `user_permissions`: Dict of allowed operations
- `subscribed_events`: List of WebSocket event types
- `connection_status`: Enum (CONNECTED, IDLE, DISCONNECTED)
- `client_info`: Dict with browser/device information
**Relationships**: Receives telemetry data, sends control commands
**Validation**: Session timeout, permission verification, event subscription limits

### AIProcessing
**Purpose**: Model inference results and hardware acceleration status
**Fields**:
- `runner_type`: Enum (CORAL_TPU, HAILO_HAT, CPU_TFLITE)
- `model_name`: String identifier for loaded model
- `inference_time`: Float ms processing duration
- `confidence_scores`: Dict of detection confidences
- `detected_objects`: List of classified objects with positions
- `processing_queue_size`: Integer pending inference requests
- `hardware_status`: Enum (AVAILABLE, BUSY, ERROR, OFFLINE)
- `fallback_used`: Boolean indicating fallback to lower tier
**Relationships**: Processes CameraStream frames, informs NavigationState
**Validation**: Confidence ranges, queue size limits, hardware availability

### SystemConfiguration
**Purpose**: Operational parameters and user-defined settings
**Fields**:
- `config_version`: String version identifier
- `operational_mode`: Enum (DEVELOPMENT, PRODUCTION, MAINTENANCE)
- `sensor_calibration`: Dict of calibration parameters per sensor
- `navigation_settings`: Dict of path planning and obstacle avoidance settings
- `safety_thresholds`: Dict of safety limit values
- `ui_preferences`: Dict of user interface customizations
- `ai_model_settings`: Dict of AI processing configuration
- `last_modified`: Timestamp of configuration change
**Relationships**: Used by all services for operational parameters
**Validation**: Version compatibility, parameter ranges, required settings

### TelemetryData
**Purpose**: Aggregated system metrics and operational history
**Fields**:
- `collection_time`: Timestamp of data aggregation
- `system_uptime`: Integer seconds since system start
- `operational_stats`: Dict of performance metrics
- `error_counts`: Dict of error frequencies by type
- `resource_usage`: Dict of CPU, memory, disk usage
- `network_status`: Dict of connectivity metrics
- `historical_trends`: Dict of time-series performance data
- `maintenance_alerts`: List of suggested maintenance actions
**Relationships**: Aggregates data from all other entities
**Validation**: Data freshness, metric value ranges, historical consistency

## Entity Relationships

### Primary Flows
1. **SensorData** → **NavigationState** → **MotorControl** (autonomous navigation loop)
2. **CameraStream** → **AIProcessing** → **NavigationState** (vision-based navigation)
3. **SensorData** → **SafetyEvents** → **MotorControl** (safety monitoring)
4. **PowerManagement** → **SafetyEvents** → **NavigationState** (power management)
5. **UserSession** → **NavigationState** → **MotorControl** (manual control)

### Data Dependencies
- NavigationState depends on SensorData for positioning
- SafetyEvents monitor all sensor inputs and motor states
- AIProcessing requires CameraStream frames
- TelemetryData aggregates from all entities
- SystemConfiguration used by all operational services

### Persistence Strategy
- Real-time data (SensorData, CameraStream): Circular buffers with SQLite archival
- State data (NavigationState, MotorControl): SQLite with frequent updates
- Configuration (SystemConfiguration): SQLite with backup on change
- Historical data (TelemetryData): SQLite with periodic cleanup
- Session data (UserSession): Memory-only with connection tracking