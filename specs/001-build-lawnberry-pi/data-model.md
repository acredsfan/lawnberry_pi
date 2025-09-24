# Data Model: LawnBerry Pi v2

## Core Entities

### SensorData
**Purpose**: Real-time measurements from hardware sensors on their mandated buses/addresses
**Fields**:
- `timestamp`: ISO datetime of measurement
- `sensor_type`: Enum (IMU_BNO085, POWER_INA3221, TOF_LEFT, TOF_RIGHT, ENV_BME280, OLED_STATUS, ENCODER_LEFT, ENCODER_RIGHT)
- `sensor_id`: String identifier for multi-sensor types (e.g., `ina3221_ch1_battery`, `tof_l`, `tof_r`)
- `bus`: Enum (UART4, I2C1, SPI, GPIO)
- `address`: Optional string (hex) for I2C devices (0x40, 0x29, 0x30, 0x76, 0x3C)
- `raw_values`: Dict of sensor-specific measurements
- `processed_values`: Dict of calibrated/filtered values
- `quality_score`: Float (0.0-1.0) indicating data reliability
- `status`: Enum (ACTIVE, DEGRADED, FAILED)
**Relationships**: Referenced by NavigationState, SafetyEvents, PowerManagement
**Validation**: Timestamp within last 10 seconds, quality_score range, address/bus match sensor_type, INA3221 channels fixed (Ch2 must remain UNUSED)

### GpsStatus
**Purpose**: Track GPS mode (F9P RTK vs Neo-8M) and fix quality
**Fields**:
- `gps_mode`: Enum (F9P_USB, NEO8M_UART)
- `fix_type`: Enum (NONE, FIX_2D, FIX_3D, RTK_FLOAT, RTK_FIXED)
- `ntrip_connected`: Boolean indicating active NTRIP session (F9P only)
- `satellite_count`: Integer satellites in view
- `position_accuracy`: Float meters estimated accuracy
- `rtk_base_id`: Optional string for NTRIP base station ID
- `last_update`: Timestamp of latest fix
- `simulated`: Boolean indicating SIM_MODE measurement
**Relationships**: Consumed by NavigationState and TelemetryData
**Validation**: `ntrip_connected` only allowed when `gps_mode=F9P_USB`; `rtk_base_id` required for RTK_FIXED

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
**Purpose**: Speed and direction commands for propulsion and cutting across preferred and fallback controllers
**Fields**:
- `controller_type`: Enum (ROBOHAT_MDDRC10, L298N_ALT)
- `left_wheel_speed`: Float (-1.0 to 1.0) normalized speed
- `right_wheel_speed`: Float (-1.0 to 1.0) normalized speed
- `left_encoder_counts`: Integer hall encoder ticks (preferred path)
- `right_encoder_counts`: Integer hall encoder ticks (preferred path)
- `cutting_blade_speed`: Float (0.0 to 1.0) cutting motor intensity
- `blade_interlocks`: Dict with `tilt_ok`, `estop_ok`, `guard_closed`
- `motor_status`: Dict per motor with health indicators
- `emergency_stop`: Boolean immediate stop override
- `last_command_time`: Timestamp of last command
- `safety_lockout`: Boolean prevents motor operation
**Relationships**: Controlled by NavigationState, monitored by SafetyEvents
**Validation**: Speed ranges, safety lockout prevents operation, hall encoder counts required when `controller_type=ROBOHAT_MDDRC10`

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
**Purpose**: Battery levels, consumption, solar input, and charging status from INA3221 fixed channels
**Fields**:
- `battery_voltage`: Float current battery voltage (INA3221 Ch1)
- `battery_current`: Float amperes draw (Ch1 shunt)
- `battery_percentage`: Float (0.0-100.0) estimated charge
- `solar_voltage`: Float volts from solar input (Ch3)
- `solar_current`: Float amperes from solar input (Ch3)
- `channel_assignments`: Dict enforcing `{"ch1": "battery", "ch2": "unused", "ch3": "solar"}`
- `charging_status`: Enum (DISCHARGING, CHARGING, CHARGED, FAULT)
- `power_consumption`: Float watts total system power
- `estimated_runtime`: Integer minutes remaining at current consumption
- `low_power_mode`: Boolean reduced functionality mode
- `charge_cycles`: Integer total charge cycles
**Relationships**: Monitored by SafetyEvents for low power conditions, surfaced in TelemetryData and WebUI power map
**Validation**: Voltage ranges, percentage consistency, INA3221 channel map immutability (`channel_assignments` read-only)

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

### UiBranding
**Purpose**: Centralize WebUI visual identity requirements
**Fields**:
- `branding_version`: String semantic version of the asset pack
- `logo_path`: String path to primary logo asset (default `/LawnBerryPi_logo.png`)
- `icon_path`: String path to app icon/favicons (default `/LawnBerryPi_icon2.png`)
- `color_palette`: Dict with primary/secondary/accent hex values derived from logo
- `font_stack`: List of preferred fonts (monospace + synthwave headings)
- `usage_notes`: Dict describing placement (header, splash, favicon, PWA manifest)
- `animation_style`: Enum (NEON_GLITCH, SCANLINES, STATIC) for retro effects
**Relationships**: Referenced by SystemConfiguration and WebUI build pipeline
**Validation**: Logo/icon paths must resolve, palette must include accessible contrast ratios

### AIProcessing
**Purpose**: Model inference results and hardware acceleration status
**Fields**:
- `runner_type`: Enum (CORAL_TPU_ISOLATED, HAILO_HAT, CPU_TFLITE)
- `isolation_scope`: Enum (PRIMARY_ENV, VENV_CORAL) verifying Coral isolation
- `model_name`: String identifier for loaded model
- `inference_time`: Float ms processing duration
- `confidence_scores`: Dict of detection confidences
- `detected_objects`: List of classified objects with positions
- `processing_queue_size`: Integer pending inference requests
- `hardware_status`: Enum (AVAILABLE, BUSY, ERROR, OFFLINE)
- `fallback_used`: Boolean indicating fallback to lower tier
**Relationships**: Processes CameraStream frames, informs NavigationState
**Validation**: Confidence ranges, queue size limits, Coral runner requires `isolation_scope=VENV_CORAL`

### SystemConfiguration
**Purpose**: Operational parameters and user-defined settings
**Fields**:
- `config_version`: String version identifier
- `operational_mode`: Enum (DEVELOPMENT, PRODUCTION, MAINTENANCE)
- `gps_mode`: Enum (F9P_USB, NEO8M_UART)
- `drive_controller`: Enum (ROBOHAT_MDDRC10, L298N_ALT)
- `sensor_calibration`: Dict of calibration parameters per sensor
- `navigation_settings`: Dict of path planning and obstacle avoidance settings
- `safety_thresholds`: Dict of safety limit values
- `ai_runner_preference`: Ordered list of acceleration tiers
- `ui_preferences`: Dict of user interface customizations (retro theming variants)
- `branding_ref`: Reference to `UiBranding` entity version in use
- `network_config`: Dict capturing Wi-Fi SSID hints and bench-only Ethernet flag
- `sim_mode_enabled`: Boolean reflecting SIM_MODE environment
- `last_modified`: Timestamp of configuration change
**Relationships**: Used by all services for operational parameters
**Validation**: Version compatibility, parameter ranges, `gps_mode` and `drive_controller` mutually exclusive per constitution (no dual selection)

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

### TelemetrySnapshot
**Purpose**: Bundled payload delivered to WebUI/clients via REST + WebSocket
**Fields**:
- `snapshot_id`: UUID for cross-channel correlation
- `collected_at`: Timestamp when snapshot was emitted
- `summary_metrics`: Dict of key runtime stats (uptime, battery %, job progress)
- `alert_level`: Enum (NORMAL, ATTENTION, CRITICAL) derived from SafetyEvents
- `power_status`: Embedded reference to current `PowerManagement`
- `map_overlay`: GeoJSON snippet from `MapConfiguration` + NavigationState
- `active_jobs`: List of `JobStatus` references with minimal fields
- `weather`: Embedded `WeatherSnapshot` summary
- `video_streams`: List of active `CameraStream` endpoints with quality tier
- `notifications`: List of user-facing messages (SafetyEvents + maintenance)
**Relationships**: Draws from TelemetryData, MapConfiguration, JobStatus, WeatherSnapshot, CameraStream
**Validation**: `collected_at` within 3 seconds of publish; references must be consistent snapshot of same tick

### MapConfiguration
**Purpose**: Persist map layers, mowing zones, and obstacle overlays for WebUI
**Fields**:
- `map_id`: UUID identifier
- `source`: Enum (SATELLITE, MANUAL_UPLOAD, SIMULATED)
- `tiles_url`: Optional URL template for map tiles (when SATELLITE)
- `yard_outline`: Polygon coordinates of operational boundary
- `mowing_zones`: List of named polygons with cut heights + schedules
- `no_go_zones`: List of polygons for exclusion
- `render_settings`: Dict (grid resolution, theme colors, retro scanline toggles)
- `last_updated`: Timestamp of last edit (WebUI map editor)
- `source_metadata`: Dict (provider attribution, upload checksum)
**Relationships**: Referenced by NavigationState for guidance, TelemetrySnapshot for overlays, UserSession for editor state
**Validation**: Polygons must be valid/non-overlapping; `tiles_url` required when `source=SATELLITE`

### JobStatus
**Purpose**: Track mowing/survey/simulation jobs surfaced in UI and APIs
**Fields**:
- `job_id`: UUID identifier
- `job_type`: Enum (MOW_FULL, MOW_ZONE, SURVEY, SIMULATION_RUN)
- `status`: Enum (PENDING, RUNNING, PAUSED, COMPLETED, FAILED, CANCELED)
- `scheduled_start`: Optional timestamp when automation planned start
- `actual_start`: Timestamp when motors engaged
- `completed_at`: Optional timestamp when finished
- `progress_percent`: Float (0.0-100.0) based on coverage or checkpoints
- `coverage_map`: Optional reference to MapConfiguration layer representing progress
- `error_codes`: List of failure reasons (links to SafetyEvents)
- `initiated_by`: Enum (SCHEDULE, MANUAL, API, SIM_MODE)
- `notes`: Optional string for operator comments
**Relationships**: Consumed by TelemetrySnapshot, linked to SafetyEvents + NavigationState, exposed via REST `/api/jobs`
**Validation**: `completed_at` only set when status terminal; `progress_percent` monotonic increasing per job

### WeatherSnapshot
**Purpose**: Cache weather data used by scheduler and UI banner
**Fields**:
- `provider`: Enum (OPEN_METEO, NOAA, MANUAL_ENTRY)
- `location`: Dict (lat, lon)
- `reported_at`: Timestamp from provider
- `temperature_c`: Float current temperature
- `humidity_percent`: Float relative humidity
- `precip_probability`: Float (0.0-1.0)
- `wind_speed_mps`: Float sustained wind speed
- `wind_gust_mps`: Float gust measurement
- `condition_icon`: String referencing retro-styled icon asset name
- `stale_after`: Timestamp when snapshot expires
**Relationships**: Embedded in TelemetrySnapshot and SystemConfiguration scheduler rules
**Validation**: Provider-specific ranges, `stale_after` must be `reported_at + TTL`

### AiImageRecord
**Purpose**: Manage captured frames for dataset labeling and model retraining
**Fields**:
- `record_id`: UUID identifier
- `captured_at`: Timestamp of frame capture
- `source_stream`: Reference to CameraStream frame ID
- `model_version`: String of inference model when captured
- `label_set`: List of labels applied (auto + manual)
- `bbox_annotations`: List of bounding boxes with class + confidence
- `review_status`: Enum (UNREVIEWED, AUTO_APPROVED, NEEDS_REVIEW, REJECTED)
- `storage_path`: String path in local/remote artifact store
- `ingest_job_id`: Optional link to JobStatus (for survey runs)
- `hardware_runner`: Enum (CORAL_TPU_ISOLATED, HAILO_HAT, CPU_TFLITE)
**Relationships**: Supports AIProcessing feedback loop, referenced by research tooling and `/api/datasets`
**Validation**: Storage paths must resolve; runner enum matches AIProcessing runner type

## Entity Relationships

### Primary Flows
1. **SensorData** → **NavigationState** → **MotorControl** (autonomous navigation loop)
2. **GpsStatus** → **NavigationState** → **MotorControl** (positioning with driver selection)
3. **CameraStream** → **AIProcessing** → **NavigationState** (vision-based navigation)
4. **SensorData** + **PowerManagement** → **SafetyEvents** → **MotorControl** (safety monitoring & power interlocks)
5. **UiBranding** → **SystemConfiguration** → **UserSession** (deliver consistent themed UI across clients)
6. **UserSession** → **NavigationState** → **MotorControl** (manual control)
7. **TelemetryData** → **TelemetrySnapshot** → **UserSession** (live status feeds across REST/WS)
8. **MapConfiguration** ↔ **NavigationState** (shared spatial context for planning + visualization)
9. **JobStatus** ↔ **TelemetrySnapshot** (job lifecycle surfaced to WebUI)
10. **WeatherSnapshot** → **SystemConfiguration** scheduler rules + TelemetrySnapshot banner
11. **AiImageRecord** → **AIProcessing** retraining + `/api/datasets`

### Data Dependencies
- NavigationState depends on SensorData and GpsStatus for positioning
- SafetyEvents monitor all sensor inputs and motor states
- AIProcessing requires CameraStream frames
- TelemetryData aggregates from all entities
- SystemConfiguration used by all operational services to select GPS/motor controller/AI runner modes
- UiBranding consumed by frontend build and WebSocket clients to maintain consistent logo/icon usage and retro theming
- TelemetrySnapshot composes TelemetryData, JobStatus, MapConfiguration, WeatherSnapshot, PowerManagement, and CameraStream for client delivery
- MapConfiguration provides spatial context to NavigationState, TelemetrySnapshot, JobStatus coverage overlays, and WebUI editors
- JobStatus links SafetyEvents, NavigationState, and scheduling logic; referenced in TelemetrySnapshot and `/api/jobs`
- WeatherSnapshot informs scheduler decisions, TelemetrySnapshot banners, and alerts
- AiImageRecord captures data lineage between CameraStream, AIProcessing, and research tooling

### Persistence Strategy
- Real-time data (SensorData, CameraStream): Circular buffers with SQLite archival
- State data (NavigationState, MotorControl): SQLite with frequent updates
- Configuration (SystemConfiguration): SQLite with backup on change
- Historical data (TelemetryData): SQLite with periodic cleanup
- TelemetrySnapshot: Materialized views in SQLite for WebUI cache + Redis-style in-memory fan-out (optional)
- MapConfiguration: Versioned JSON blobs stored in SQLite (with file backup) for editor undo/history
- JobStatus: SQLite table with indices on status + scheduled_start for dashboards
- WeatherSnapshot: Cached table with TTL enforcement; refresh triggers WebUI update
- AiImageRecord: Metadata persisted in SQLite, binary assets stored on disk/object store with checksum verification
- Session data (UserSession): Memory-only with connection tracking