# Data Model: Engineering Plan Implementation

**Feature**: Complete Engineering Plan Phases 0-7  
**Date**: 2025-10-02  
**Status**: Design Complete

## Overview
This document defines the data entities, relationships, and state transitions for the complete Engineering Plan implementation. All entities align with constitutional requirements and functional specifications.

---

## Core Entities

### 1. HardwareConfig
**Purpose**: Declares physical hardware modules present in the system  
**Source**: Loaded from `config/hardware.yaml` at system startup (FR-003)

**Attributes**:
- `gps_type`: string - GPS module type (`"zed-f9p-usb"` | `"neo-8m-uart"` | `null`)
- `gps_ntrip_enabled`: boolean - NTRIP corrections enabled for RTK (ZED-F9P only)
- `imu_type`: string - IMU module (`"bno085-uart"` | `null`)
- `tof_sensors`: array<string> - ToF sensor positions (`["left", "right"]` | `[]`)
- `env_sensor`: boolean - BME280 environmental sensor present
- `power_monitor`: boolean - INA3221 power monitor present
- `motor_controller`: string - Motor control interface (`"robohat-rp2040"` | `"l298n"`)
- `blade_controller`: string - Blade motor control (`"ibt-4"` | `null`) – IBT-4 H-Bridge wired to Raspberry Pi GPIO 24 (IN1) and GPIO 25 (IN2) per hardware-overview.md
- `camera_enabled`: boolean - Picamera2 module present

**Relationships**:
- → `DriverInstance`: Determines which drivers to load in registry

**Validation**:
- GPS type mutually exclusive: ZED-F9P (USB) OR Neo-8M (UART)
- NTRIP requires ZED-F9P (error if enabled with Neo-8M)
- ToF sensors require I2C bus availability
- Motor controller required for motion (cannot be null)

---

### 2. SafetyLimits
**Purpose**: Defines constitutional safety thresholds and timeouts  
**Source**: Loaded from `config/limits.yaml` (FR-004)

**Attributes**:
- `estop_latency_ms`: integer - Maximum E-stop response time (default: 100, constitutional: <100ms)
- `tilt_threshold_degrees`: float - IMU tilt angle for blade cutoff (default: 30.0, constitutional: >30°)
- `tilt_cutoff_latency_ms`: integer - Tilt detection to blade stop (default: 200, constitutional: <200ms)
- `battery_low_voltage`: float - Low battery threshold (default: 10.0V)
- `battery_critical_voltage`: float - Critical battery (emergency return) (default: 9.5V)
- `motor_current_max_amps`: float - Per-motor current limit (default: 5.0A)
- `watchdog_timeout_ms`: integer - Heartbeat timeout (default: 1000ms)
- `geofence_buffer_meters`: float - Warning zone before violation (default: 0.5m)
- `high_temperature_celsius`: float - Thermal shutdown (default: 80°C)
- `tof_obstacle_distance_meters`: float - Emergency stop distance (default: 0.2m)

**Relationships**:
- → `SafetyInterlock`: Thresholds determine when interlocks trigger

**Validation**:
- `estop_latency_ms` ≤ 100 (constitutional requirement)
- `tilt_cutoff_latency_ms` ≤ 200 (constitutional requirement)
- `battery_critical_voltage` < `battery_low_voltage`
- All timeout values > 0

---

### 3. MessageBusEvent
**Purpose**: Pub/sub event for inter-service communication  
**Message Bus**: Redis Streams (two-tier persistence model)

**Attributes**:
- `topic`: string - Hierarchical topic (e.g., `"safety.estop"`, `"sensor.gps"`, `"state.robot"`)
- `timestamp_us`: integer - Unix timestamp microseconds (NTP-synchronized)
- `payload`: JSON object - Event-specific data
- `source_service`: string - Publishing service identifier
- `message_id`: string - Redis-assigned message ID (for acknowledgment)
- `persistence_tier`: enum - `"critical"` | `"best_effort"`

**Relationships**:
- → `DriverInstance`: Drivers publish sensor readings
- → `RobotState`: State updates consume events from multiple sources

**State Transitions**: N/A (events are immutable)

**Topic Categories**:
- **Safety (critical)**: `safety.estop`, `safety.interlock`, `safety.watchdog_timeout`
- **Navigation (critical)**: `nav.geofence_violation`, `nav.waypoint_reached`
- **Sensors (best_effort)**: `sensor.gps`, `sensor.imu`, `sensor.tof`, `sensor.power`, `sensor.env`
- **State (best_effort)**: `state.robot`, `state.battery`, `state.position`
- **Commands (critical)**: `cmd.motor`, `cmd.blade`, `cmd.mode`

**Validation**:
- Topic must follow hierarchical pattern: `<category>.<subcategory>`
- Critical topics: messages persisted 24h, consumer group acknowledgment required
- Best-effort topics: fire-and-forget pub/sub, 1h TTL

---

### 4. DriverInstance
**Purpose**: Registered hardware driver with lifecycle management  
**Registry**: Loaded dynamically from `backend/src/drivers/` based on HardwareConfig

**Attributes**:
- `driver_id`: string - Unique identifier (e.g., `"gps-zed-f9p"`, `"imu-bno085"`)
- `driver_class`: string - Python class name (`"ZedF9pDriver"`, `"BNO085Driver"`)
- `hardware_resource`: array<string> - Required resources (`["usb-device-/dev/ttyACM0"]`, `["i2c-1-addr-0x28"]`)
- `simulation_mode`: boolean - SIM_MODE=1 loads mock driver instead
- `lifecycle_state`: enum - `"uninitialized"` | `"initializing"` | `"ready"` | `"running"` | `"stopped"` | `"failed"`
- `health_status`: enum - `"healthy"` | `"degraded"` | `"unhealthy"`
- `last_health_check_ts`: integer - Unix timestamp microseconds
- `error_message`: string | null - Last error (if failed/unhealthy)

**Relationships**:
- ← `HardwareConfig`: Config determines which drivers load
- → `MessageBusEvent`: Publishes sensor readings and health updates

**State Transitions**:
```
uninitialized → initializing → ready → running → stopped
                     ↓              ↓       ↓
                   failed         failed  failed
```

**Lifecycle Methods** (abstract interface):
- `async def init()`: Initialize hardware connection
- `async def start()`: Begin sensor polling loop
- `async def stop()`: Graceful shutdown, release resources
- `async def health_check()`: Return health status + metrics

**Validation**:
- Hardware resources must not conflict with other drivers (single-owner principle)
- Mock drivers in SIM_MODE=1 must implement same interface
- Health check must complete in <500ms

---

### 5. RobotState
**Purpose**: Canonical system state aggregating all subsystem inputs  
**Source**: Updated by sensor fusion engine, exposed via API (FR-013)

**Attributes**:
**Position & Motion**:
- `position_lat`: float | null - WGS84 latitude (degrees)
- `position_lon`: float | null - WGS84 longitude (degrees)
- `position_accuracy_m`: float | null - GPS accuracy (meters)
- `heading_degrees`: float - Compass heading (0-360°, 0=North)
- `velocity_mps`: float - Ground speed (meters/second)
- `angular_velocity_dps`: float - Turning rate (degrees/second)

**Orientation**:
- `tilt_roll_degrees`: float - IMU roll angle
- `tilt_pitch_degrees`: float - IMU pitch angle

**Power**:
- `battery_voltage`: float - LiFePO4 battery (volts)
- `battery_current_amps`: float - Discharge rate (negative=charging)
- `battery_percent`: integer - State of charge (0-100%)
- `solar_voltage`: float - Solar panel voltage
- `solar_current_amps`: float - Solar charge rate

**Environment**:
- `temperature_celsius`: float | null - BME280 temperature
- `humidity_percent`: float | null - BME280 relative humidity
- `pressure_hpa`: float | null - BME280 atmospheric pressure

**Safety**:
- `active_interlocks`: array<string> - Active safety conditions (e.g., `["emergency_stop", "low_battery"]`)
- `estop_engaged`: boolean - E-stop button pressed
- `watchdog_healthy`: boolean - Motor control heartbeat OK

**Navigation**:
- `navigation_mode`: enum - `"MANUAL"` | `"AUTONOMOUS"` | `"EMERGENCY_STOP"` | `"CALIBRATION"` | `"IDLE"`
- `current_waypoint_id`: string | null - Active waypoint UUID
- `distance_to_waypoint_m`: float | null - Remaining distance
- `inside_geofence`: boolean - Position within boundary

**Motor Control**:
- `motor_left_pwm`: integer - Left motor PWM (-255 to 255)
- `motor_right_pwm`: integer - Right motor PWM (-255 to 255)
- `blade_active`: boolean - Blade motor running
- `blade_rpm`: integer | null - Blade speed (if measured)

**Timing**:
- `timestamp_us`: integer - State snapshot timestamp (microseconds)

**Relationships**:
- ← `MessageBusEvent`: Consumes sensor readings, motor commands, safety events
- → API: Exposed via `/api/v1/status` (REST) and WebSocket telemetry (5Hz)

**Validation**:
- Position lat/lon valid ranges: lat [-90, 90], lon [-180, 180]
- Tilt angles constitutional threshold check: >30° triggers interlock
- Battery voltage: <10.0V triggers low_battery interlock, <9.5V triggers critical
- Navigation mode transitions validated by NavigationModeManager

---

### 6. SafetyInterlock
**Purpose**: Active safety condition preventing motor operation  
**Lifecycle**: Created when condition triggers, cleared when resolved + operator acknowledges

**Attributes**:
- `interlock_id`: string - UUID for tracking
- `interlock_type`: enum - `"emergency_stop"` | `"tilt_detected"` | `"low_battery"` | `"geofence_violation"` | `"watchdog_timeout"` | `"high_temperature"` | `"obstacle_detected"`
- `triggered_at_us`: integer - Activation timestamp (microseconds)
- `cleared_at_us`: integer | null - Resolution timestamp
- `acknowledged_at_us`: integer | null - Operator confirmation timestamp
- `state`: enum - `"active"` | `"cleared_pending_ack"` | `"acknowledged"`
- `trigger_value`: float | null - Sensor reading that caused trigger (e.g., tilt angle, battery voltage)
- `description`: string - Human-readable explanation

**Relationships**:
- → `RobotState`: Active interlocks populate `active_interlocks` array
- → Log Bundle: All interlocks logged for incident analysis

**State Transitions**:
```
active → cleared_pending_ack → acknowledged
```

**Recovery Rules**:
- `emergency_stop`: Requires operator confirmation (web UI button or CLI `--force`)
- `tilt_detected`: Blade must remain off until acknowledged + robot leveled
- `low_battery`: Cleared when voltage >10.5V (0.5V hysteresis)
- `geofence_violation`: Requires operator to move robot inside boundary manually
- `watchdog_timeout`: Requires service restart + operator confirmation

**Validation**:
- Cannot clear interlock until trigger condition resolved
- Cannot resume autonomous operation with any active interlocks (FR-040)

---

### 7. NavigationWaypoint
**Purpose**: Target position for autonomous navigation  
**Source**: Generated from coverage pattern or user-defined route

**Attributes**:
- `waypoint_id`: string - UUID
- `latitude`: float - WGS84 latitude (degrees)
- `longitude`: float - WGS84 longitude (degrees)
- `target_speed_mps`: float - Desired ground speed (default: 0.5 m/s)
- `arrival_threshold_m`: float - Distance to consider "reached" (default: 1.0m)
- `sequence_number`: integer - Order in coverage pattern (0-indexed)
- `waypoint_type`: enum - `"coverage"` | `"turning_point"` | `"charging_station"` | `"home"`
- `completed`: boolean - Waypoint reached
- `completed_at_us`: integer | null - Completion timestamp

**Relationships**:
- ← `CoveragePattern`: Generated from pattern algorithm
- → `RobotState`: Current waypoint ID referenced in state

**Validation**:
- Waypoint must be inside geofence (validated on generation)
- Target speed ≤ 1.0 m/s (safety limit)
- Sequence numbers must be contiguous in pattern

---

### 8. Geofence
**Purpose**: Boundary polygon defining safe operating area  
**Source**: Loaded from `config/geofence.json` at startup

**Attributes**:
- `geofence_id`: string - UUID
- `name`: string - Human-readable name (e.g., "Front Lawn")
- `vertices`: array<{lat: float, lon: float}> - Polygon boundary points (WGS84)
- `buffer_distance_m`: float - Warning zone before violation (default: 0.5m from SafetyLimits)
- `created_at_us`: integer - Creation timestamp
- `modified_at_us`: integer - Last modification timestamp
- `active`: boolean - Currently enforced (only one active at a time)

**Relationships**:
- → `NavigationWaypoint`: Waypoints validated against geofence
- → `RobotState`: Position checked for containment

**Validation**:
- Polygon must be closed (first vertex == last vertex)
- Minimum 3 vertices (triangle)
- No self-intersections (validated with Shapely `is_valid`)
- Cannot modify active geofence during autonomous operation (operator must pause job)

---

### 9. CoveragePattern
**Purpose**: Mowing path plan for autonomous job execution  
**Algorithm**: Parallel-line sweep with A* pathfinding between waypoints

**Attributes**:
- `pattern_id`: string - UUID
- `geofence_id`: string - Associated boundary (foreign key to Geofence)
- `cutting_width_m`: float - Blade effective width (default: 0.305m = 12")
- `overlap_percent`: float - Line overlap for full coverage (default: 10%)
- `line_spacing_m`: float - Calculated: `cutting_width_m * (1 - overlap_percent)`
- `waypoints`: array<string> - Ordered waypoint IDs (foreign keys to NavigationWaypoint)
- `total_waypoints`: integer - Count for progress tracking
- `completed_waypoints`: integer - Current progress
- `estimated_duration_minutes`: integer - Time to complete (based on speed + distance)
- `pattern_type`: enum - `"parallel_lines"` | `"spiral"` | `"random"` (currently only parallel_lines implemented)

**Relationships**:
- → `Geofence`: Pattern generated for specific boundary
- → `NavigationWaypoint`: References waypoint list
- → `ScheduledJob`: Job executes pattern

**Generation Algorithm**:
1. Compute bounding box of geofence polygon
2. Generate parallel lines spaced by `line_spacing_m`
3. Intersect lines with geofence polygon → segments
4. Connect segments with 90° turning waypoints (5ft radius arcs)
5. Order waypoints to minimize total distance (greedy nearest-neighbor)

**Validation**:
- All waypoints inside geofence
- Line spacing ≥ 0.2m (minimum for safe operation)
- Estimated duration ≤ battery runtime at current charge

---

### 10. ScheduledJob
**Purpose**: Calendar entry for autonomous mowing execution  
**Scheduler**: APScheduler with cron triggers + FSM state machine

**Attributes**:
- `job_id`: string - UUID
- `name`: string - Human-readable job name (e.g., "Monday Morning Mow")
- `cron_schedule`: string - Cron expression (e.g., `"0 8 * * 1-5"` = 8am Mon-Fri)
- `pattern_id`: string - Coverage pattern to execute (foreign key to CoveragePattern)
- `state`: enum - `"IDLE"` | `"SCHEDULED"` | `"RUNNING"` | `"PAUSED"` | `"COMPLETED"` | `"FAILED"`
- `weather_check_enabled`: boolean - Postpone if adverse weather (FR-036)
- `min_battery_percent`: integer - Minimum charge to start (default: 30%)
- `retry_count`: integer - Current retry attempt (max 3)
- `retry_delay_minutes`: array<integer> - Backoff schedule (default: [30, 60, 120])
- `scheduled_start_time_us`: integer | null - Next scheduled execution
- `actual_start_time_us`: integer | null - When job actually started
- `completion_time_us`: integer | null - When job finished
- `error_message`: string | null - Failure reason (if FAILED)

**Relationships**:
- → `CoveragePattern`: Executes specific pattern
- → `RobotState`: Job monitors state for safety validation

**State Transitions**:
```
IDLE → SCHEDULED → RUNNING → COMPLETED
                      ↓  ↑
                    PAUSED
                      ↓
                    FAILED
```

**Transition Triggers**:
- `IDLE → SCHEDULED`: Cron trigger fires, weather check passes, battery OK
- `SCHEDULED → RUNNING`: Safety systems validated (FR-040), operator confirmation if required
- `RUNNING → PAUSED`: Operator manual pause, rain detected mid-job, low battery warning
- `PAUSED → RUNNING`: Operator resume, weather clears, battery charged
- `RUNNING → COMPLETED`: All waypoints reached, robot returns home
- `RUNNING → FAILED`: Safety interlock during job, max retries exceeded, geofence violation

**Weather Check Logic** (FR-036a/b/c):
1. Query OpenWeatherMap API (if available)
2. If API unavailable: use cached forecast (<6h old) + BME280 sensor readings
3. Postpone conditions: rain probability >30%, wind speed >15mph, temperature >35°C or <5°C
4. If cached forecast >6h old and API unavailable: sensor-only operation (BME280 temperature/humidity/pressure)

**Validation**:
- Cron schedule must be valid (APScheduler validation)
- Pattern must reference existing, valid CoveragePattern
- Cannot start if any active safety interlocks
- Retry count ≤ 3 (then mark FAILED)

---

### 11. SensorReading
**Purpose**: Timestamped measurement from hardware sensor  
**Storage**: Published to message bus (best-effort), optionally logged to disk

**Attributes**:
- `sensor_id`: string - Driver identifier (e.g., `"gps-zed-f9p"`, `"imu-bno085"`)
- `reading_type`: enum - `"gps"` | `"imu"` | `"tof"` | `"power"` | `"env"`
- `timestamp_us`: integer - Reading timestamp (microseconds, NTP-synchronized)
- `value`: JSON object - Sensor-specific data structure
- `unit`: string - Measurement unit (e.g., `"degrees"`, `"meters"`, `"volts"`)
- `quality_indicator`: float - Sensor confidence (0.0-1.0, 1.0=perfect)

**Sensor-Specific Value Structures**:

**GPS** (`reading_type="gps"`):
```json
{
  "latitude": 37.7749,
  "longitude": -122.4194,
  "altitude_m": 10.5,
  "speed_mps": 0.5,
  "heading_degrees": 90.0,
  "hdop": 1.2,
  "satellites": 12,
  "fix_type": "3D-RTK"
}
```

**IMU** (`reading_type="imu"`):
```json
{
  "accel_x": 0.1,
  "accel_y": 0.05,
  "accel_z": 9.81,
  "gyro_x": 0.01,
  "gyro_y": -0.02,
  "gyro_z": 0.0,
  "mag_x": 25.5,
  "mag_y": -10.2,
  "mag_z": 40.1,
  "roll_degrees": 2.5,
  "pitch_degrees": -1.3,
  "yaw_degrees": 90.0
}
```

**ToF** (`reading_type="tof"`):
```json
{
  "sensor_position": "left",
  "distance_m": 0.45,
  "ranging_status": "valid"
}
```

**Power** (`reading_type="power"`):
```json
{
  "battery_voltage": 12.6,
  "battery_current_amps": -2.5,
  "solar_voltage": 18.3,
  "solar_current_amps": 1.2
}
```

**Environmental** (`reading_type="env"`):
```json
{
  "temperature_celsius": 25.5,
  "humidity_percent": 60.2,
  "pressure_hpa": 1013.25
}
```

**Relationships**:
- → `MessageBusEvent`: Published to `sensor.<reading_type>` topic
- → `RobotState`: Consumed by sensor fusion to update state

**Validation**:
- Timestamp must be recent (within 10s of current time, allows for NTP drift)
- Quality indicator must be in [0.0, 1.0]
- Value structure must match reading_type schema

---

### 12. LogBundle
**Purpose**: Archived collection of logs, state snapshots, and telemetry for incident analysis  
**Storage**: Generated on-demand as tar.gz archive in `/var/log/lawnberry/bundles/`

**Attributes**:
- `bundle_id`: string - UUID
- `created_at_us`: integer - Bundle generation timestamp
- `incident_type`: enum - `"safety_interlock"` | `"geofence_violation"` | `"job_failure"` | `"operator_request"` | `"scheduled_capture"`
- `time_range_start_us`: integer - Start of captured time window
- `time_range_end_us`: integer - End of captured time window
- `file_path`: string - Absolute path to tar.gz archive
- `size_bytes`: integer - Archive file size
- `included_logs`: array<string> - Log files included (e.g., `["safety.log", "navigation.log"]`)
- `state_snapshots`: array<{timestamp_us: integer, state: RobotState}> - Robot state captures
- `sensor_readings_count`: integer - Number of sensor readings in bundle
- `interlock_events`: array<SafetyInterlock> - Safety interlocks during time window

**Relationships**:
- ← `SafetyInterlock`: Interlocks trigger automatic bundle generation
- ← `ScheduledJob`: Failed jobs generate bundles for diagnosis

**Bundle Contents** (tar.gz structure):
```
bundle_{uuid}/
├── metadata.json          # Bundle attributes
├── logs/
│   ├── safety.log         # Safety interlock events
│   ├── navigation.log     # Waypoint navigation, geofence checks
│   ├── sensors.log        # Raw sensor readings
│   └── motor_control.log  # Motor commands, blade state
├── state_snapshots.json   # RobotState captures (every 1s during incident)
├── interlocks.json        # SafetyInterlock events
└── telemetry.csv          # WebSocket telemetry data (5Hz)
```

**Generation Triggers**:
- Safety interlock activated → bundle last 60s + next 30s
- Geofence violation → bundle last 120s
- Job FAILED → bundle entire job duration
- Operator request via API or CLI
- Scheduled daily capture (last 24h, retention 7 days)

**Validation**:
- Time range must be valid (start < end)
- Archive size <500MB (prevent disk exhaustion)
- Retention policy: 7 days for automatic bundles, permanent for operator-requested

---

## Entity Relationships Diagram

```
HardwareConfig (config/hardware.yaml)
  └──> DriverInstance (registry, lifecycle)
          └──> MessageBusEvent (sensor readings)
                  └──> RobotState (fused state)
                          ├──> NavigationWaypoint (current target)
                          ├──> SafetyInterlock (active interlocks)
                          └──> ScheduledJob (monitors state)

SafetyLimits (config/limits.yaml)
  └──> SafetyInterlock (threshold triggers)

Geofence (config/geofence.json)
  ├──> NavigationWaypoint (boundary validation)
  └──> CoveragePattern (pattern generation)
          └──> ScheduledJob (executes pattern)

LogBundle (incident archive)
  ├──< SafetyInterlock (trigger)
  ├──< ScheduledJob (failure diagnosis)
  └──< RobotState (state snapshots)
```

---

## State Transition Summary

| Entity | States | Key Transitions |
|--------|--------|-----------------|
| `DriverInstance` | uninitialized → initializing → ready → running → stopped (+ failed) | Start drivers at boot, stop on shutdown, failed on error |
| `SafetyInterlock` | active → cleared_pending_ack → acknowledged | Trigger on threshold breach, clear when resolved, require operator ack |
| `ScheduledJob` | IDLE → SCHEDULED → RUNNING → COMPLETED (or PAUSED/FAILED) | Cron trigger + weather check, safety validation, retry on failure |
| `RobotState.navigation_mode` | MANUAL ↔ AUTONOMOUS ↔ EMERGENCY_STOP / CALIBRATION / IDLE | Mode transitions via API, safety interlocks force EMERGENCY_STOP |

---

## Validation Rules Summary

**Constitutional Safety**:
- E-stop latency: RobotState updated within 100ms of interlock activation
- Tilt cutoff: SafetyInterlock created within 200ms of IMU threshold breach
- Geofence: Zero tolerance, immediate EMERGENCY_STOP on RobotState.inside_geofence=false
- Watchdog: SafetyInterlock if heartbeat missing >1000ms

**Data Integrity**:
- Timestamps: All entities use Unix microsecond timestamps (NTP-synchronized)
- UUIDs: All primary keys use UUID4 for globally unique identifiers
- Foreign keys: Reference validation before entity creation
- Enums: Strict value checking, no arbitrary strings

**Resource Constraints**:
- Message bus: Safety-critical messages persisted 24h, telemetry 1h TTL
- Log bundles: Max 500MB per archive, 7-day retention for automatic bundles
- Coverage patterns: Max 1000 waypoints per pattern (memory constraint)
- Sensor readings: Discard readings >10s old (stale data)

---

## Next Steps

✅ Data Model Complete - Proceed to API Contract Generation (Phase 1 continued)
