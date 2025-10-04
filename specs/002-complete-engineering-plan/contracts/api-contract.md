# API Contract: Engineering Plan Implementation

**Version**: 1.0.0  
**Base URL**: `http://{pi-hostname}:8000/api/v1`  
**Authentication**: JWT Bearer token (single operator, password-based login)  
**Date**: 2025-10-02

## Overview
This OpenAPI 3.0 specification defines REST + WebSocket APIs for the complete Engineering Plan implementation. All endpoints require authentication except `/auth/login`. WebSocket telemetry streams at 5Hz minimum (NFR-003).

---

## Authentication

### POST /auth/login
**Purpose**: Authenticate operator and obtain JWT session token

**Request**:
```json
{
  "username": "admin",
  "password": "changeme"
}
```

**Response** (200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 28800
}
```

**Errors**:
- `401 Unauthorized`: Invalid credentials
- `429 Too Many Requests`: Rate limit exceeded (5 attempts/minute)

**Contract Test**: `tests/contract/test_auth_login.py`

---

## System Configuration

### GET /config/hardware
**Purpose**: Retrieve active hardware configuration (FR-003)

**Response** (200 OK):
```json
{
  "gps_type": "zed-f9p-usb",
  "gps_ntrip_enabled": true,
  "imu_type": "bno085-uart",
  "tof_sensors": ["left", "right"],
  "env_sensor": true,
  "power_monitor": true,
  "motor_controller": "robohat-rp2040",
  "blade_controller": "ibt-4",
  "camera_enabled": false
}
```

**Contract Test**: `tests/contract/test_config_hardware.py`

---

### GET /config/limits
**Purpose**: Retrieve safety limits (FR-004)

**Response** (200 OK):
```json
{
  "estop_latency_ms": 100,
  "tilt_threshold_degrees": 30.0,
  "tilt_cutoff_latency_ms": 200,
  "battery_low_voltage": 10.0,
  "battery_critical_voltage": 9.5,
  "motor_current_max_amps": 5.0,
  "watchdog_timeout_ms": 1000,
  "geofence_buffer_meters": 0.5,
  "high_temperature_celsius": 80.0,
  "tof_obstacle_distance_meters": 0.2
}
```

**Contract Test**: `tests/contract/test_config_limits.py`

---

## Robot State

### GET /status
**Purpose**: Get current robot state (FR-013)

**Response** (200 OK):
```json
{
  "position": {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "accuracy_m": 0.8,
    "inside_geofence": true
  },
  "motion": {
    "heading_degrees": 90.0,
    "velocity_mps": 0.5,
    "angular_velocity_dps": 5.0
  },
  "orientation": {
    "tilt_roll_degrees": 2.5,
    "tilt_pitch_degrees": -1.3
  },
  "power": {
    "battery_voltage": 12.6,
    "battery_current_amps": -2.5,
    "battery_percent": 85,
    "solar_voltage": 18.3,
    "solar_current_amps": 1.2
  },
  "environment": {
    "temperature_celsius": 25.5,
    "humidity_percent": 60.2,
    "pressure_hpa": 1013.25
  },
  "safety": {
    "active_interlocks": [],
    "estop_engaged": false,
    "watchdog_healthy": true
  },
  "navigation": {
    "mode": "MANUAL",
    "current_waypoint_id": null,
    "distance_to_waypoint_m": null
  },
  "motors": {
    "motor_left_pwm": 0,
    "motor_right_pwm": 0,
    "blade_active": false,
    "blade_rpm": null
  },
  "timestamp_us": 1696262400000000
}
```

**Contract Test**: `tests/contract/test_status.py`

---

## Motor Control

### POST /control/teleop
**Purpose**: Manual teleoperation motor control (FR-018)

**Request**:
```json
{
  "throttle": 0.5,
  "turn": 0.2
}
```
- `throttle`: float [-1.0, 1.0] - Forward/backward speed
- `turn`: float [-1.0, 1.0] - Left/right turning rate

**Response** (200 OK):
```json
{
  "motor_left_pwm": 153,
  "motor_right_pwm": 102,
  "validated": true
}
```

**Errors**:
- `400 Bad Request`: Invalid throttle/turn values
- `403 Forbidden`: Active safety interlocks prevent motion
- `409 Conflict`: Not in MANUAL mode

**Contract Test**: `tests/contract/test_control_teleop.py`

---

### POST /control/estop/reset
**Purpose**: Reset emergency stop after interlock cleared (FR-020)

**Request**:
```json
{
  "confirmation": true,
  "force": false
}
```

**Response** (200 OK):
```json
{
  "estop_engaged": false,
  "interlocks_cleared": ["emergency_stop"],
  "mode": "IDLE"
}
```

**Errors**:
- `403 Forbidden`: E-stop trigger condition not resolved
- `400 Bad Request`: Missing confirmation

**Contract Test**: `tests/contract/test_estop_reset.py`

---

## Navigation

### GET /navigation/mode
**Purpose**: Get current navigation mode (FR-032)

**Response** (200 OK):
```json
{
  "mode": "MANUAL",
  "allowed_transitions": ["AUTONOMOUS", "CALIBRATION", "IDLE"]
}
```

**Contract Test**: `tests/contract/test_navigation_mode_get.py`

---

### POST /navigation/mode
**Purpose**: Change navigation mode

**Request**:
```json
{
  "mode": "AUTONOMOUS"
}
```

**Response** (200 OK):
```json
{
  "mode": "AUTONOMOUS",
  "transitioned_at_us": 1696262400000000
}
```

**Errors**:
- `403 Forbidden`: Safety interlocks prevent mode change
- `400 Bad Request`: Invalid mode or illegal transition

**Contract Test**: `tests/contract/test_navigation_mode_post.py`

---

### GET /navigation/geofence
**Purpose**: Get active geofence boundary

**Response** (200 OK):
```json
{
  "geofence_id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "Front Lawn",
  "vertices": [
    {"latitude": 37.7749, "longitude": -122.4194},
    {"latitude": 37.7750, "longitude": -122.4193},
    {"latitude": 37.7748, "longitude": -122.4192},
    {"latitude": 37.7749, "longitude": -122.4194}
  ],
  "buffer_distance_m": 0.5,
  "active": true
}
```

**Contract Test**: `tests/contract/test_navigation_geofence.py`

---

### POST /navigation/geofence
**Purpose**: Update geofence boundary (requires MANUAL mode)

**Request**:
```json
{
  "name": "Front Lawn",
  "vertices": [
    {"latitude": 37.7749, "longitude": -122.4194},
    {"latitude": 37.7750, "longitude": -122.4193},
    {"latitude": 37.7748, "longitude": -122.4192},
    {"latitude": 37.7749, "longitude": -122.4194}
  ]
}
```

**Response** (201 Created):
```json
{
  "geofence_id": "123e4567-e89b-12d3-a456-426614174000",
  "validated": true,
  "area_sqm": 150.5
}
```

**Errors**:
- `400 Bad Request`: Invalid polygon (self-intersection, not closed, <3 vertices)
- `409 Conflict`: Cannot modify during autonomous operation

**Contract Test**: `tests/contract/test_navigation_geofence_post.py`

---

### GET /navigation/waypoints
**Purpose**: List waypoints in current coverage pattern

**Response** (200 OK):
```json
{
  "pattern_id": "pattern-uuid",
  "total_waypoints": 120,
  "completed_waypoints": 45,
  "waypoints": [
    {
      "waypoint_id": "wp-uuid-1",
      "latitude": 37.7749,
      "longitude": -122.4194,
      "sequence_number": 45,
      "waypoint_type": "coverage",
      "completed": true
    },
    {
      "waypoint_id": "wp-uuid-2",
      "latitude": 37.7750,
      "longitude": -122.4195,
      "sequence_number": 46,
      "waypoint_type": "coverage",
      "completed": false
    }
  ]
}
```

**Contract Test**: `tests/contract/test_navigation_waypoints.py`

---

## Scheduling

### GET /jobs
**Purpose**: List all scheduled jobs

**Query Parameters**:
- `state` (optional): Filter by job state (`IDLE`, `SCHEDULED`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`)

**Response** (200 OK):
```json
{
  "jobs": [
    {
      "job_id": "job-uuid-1",
      "name": "Monday Morning Mow",
      "cron_schedule": "0 8 * * 1-5",
      "pattern_id": "pattern-uuid",
      "state": "SCHEDULED",
      "scheduled_start_time_us": 1696262400000000,
      "weather_check_enabled": true,
      "min_battery_percent": 30
    }
  ],
  "total": 1
}
```

**Contract Test**: `tests/contract/test_jobs_list.py`

---

### POST /jobs
**Purpose**: Create new scheduled job (FR-035)

**Request**:
```json
{
  "name": "Monday Morning Mow",
  "cron_schedule": "0 8 * * 1-5",
  "pattern_id": "pattern-uuid",
  "weather_check_enabled": true,
  "min_battery_percent": 30
}
```

**Response** (201 Created):
```json
{
  "job_id": "job-uuid-1",
  "state": "IDLE",
  "next_run_time_us": 1696262400000000
}
```

**Errors**:
- `400 Bad Request`: Invalid cron schedule
- `404 Not Found`: Pattern ID does not exist

**Contract Test**: `tests/contract/test_jobs_create.py`

---

### POST /jobs/{job_id}/start
**Purpose**: Manually start a scheduled job

**Response** (200 OK):
```json
{
  "job_id": "job-uuid-1",
  "state": "RUNNING",
  "actual_start_time_us": 1696262400000000
}
```

**Errors**:
- `403 Forbidden`: Safety interlocks prevent start (FR-040)
- `409 Conflict`: Job already running or wrong state

**Contract Test**: `tests/contract/test_jobs_start.py`

---

### POST /jobs/{job_id}/pause
**Purpose**: Pause running job

**Response** (200 OK):
```json
{
  "job_id": "job-uuid-1",
  "state": "PAUSED",
  "paused_at_us": 1696262400000000
}
```

**Contract Test**: `tests/contract/test_jobs_pause.py`

---

## Diagnostics

### GET /diagnostics/drivers
**Purpose**: List all driver instances and health status

**Response** (200 OK):
```json
{
  "drivers": [
    {
      "driver_id": "gps-zed-f9p",
      "driver_class": "ZedF9pDriver",
      "lifecycle_state": "running",
      "health_status": "healthy",
      "last_health_check_ts": 1696262400000000
    },
    {
      "driver_id": "imu-bno085",
      "driver_class": "BNO085Driver",
      "lifecycle_state": "running",
      "health_status": "degraded",
      "error_message": "Magnetometer calibration low"
    }
  ]
}
```

**Contract Test**: `tests/contract/test_diagnostics_drivers.py`

---

### POST /diagnostics/log-bundle
**Purpose**: Generate log bundle for incident analysis (FR-044)

**Request**:
```json
{
  "incident_type": "operator_request",
  "time_range_minutes": 60
}
```

**Response** (200 OK):
```json
{
  "bundle_id": "bundle-uuid",
  "file_path": "/var/log/lawnberry/bundles/bundle_uuid.tar.gz",
  "size_bytes": 15728640,
  "created_at_us": 1696262400000000
}
```

**Contract Test**: `tests/contract/test_diagnostics_log_bundle.py`

---

## WebSocket Telemetry

### WS /ws/telemetry
**Purpose**: Real-time state streaming at 5Hz minimum (NFR-003)

**Authentication**: JWT token in query parameter: `?token={jwt}`

**Message Format**:
```json
{
  "type": "telemetry",
  "timestamp_us": 1696262400000000,
  "data": {
    "position": {...},
    "motion": {...},
    "power": {...},
    "safety": {...}
  }
}
```

**Frequency**: 5Hz (200ms interval)

**Contract Test**: `tests/contract/test_websocket_telemetry.py`

---

## Message Bus Topics

### Safety Topics (Critical - Persistent)
- `safety.estop` - E-stop button pressed/released
- `safety.interlock` - Safety interlock created/cleared
- `safety.watchdog_timeout` - Watchdog heartbeat missed

### Navigation Topics (Critical - Persistent)
- `nav.geofence_violation` - Position outside boundary
- `nav.waypoint_reached` - Waypoint completion
- `nav.mode_changed` - Navigation mode transition

### Sensor Topics (Best-Effort)
- `sensor.gps` - GPS position updates (1Hz)
- `sensor.imu` - IMU orientation (10Hz)
- `sensor.tof` - ToF distance measurements (5Hz per sensor)
- `sensor.power` - Power monitor readings (1Hz)
- `sensor.env` - Environmental sensor (0.2Hz)

### State Topics (Best-Effort)
- `state.robot` - Fused robot state (10Hz)
- `state.battery` - Battery state of charge
- `state.position` - Position estimates

### Command Topics (Critical - Persistent)
- `cmd.motor` - Motor control commands
- `cmd.blade` - Blade on/off commands
- `cmd.mode` - Navigation mode changes

---

## Error Response Format

All endpoints use consistent error structure:

```json
{
  "error": {
    "code": "SAFETY_INTERLOCK_ACTIVE",
    "message": "Cannot start motors: emergency stop engaged",
    "details": {
      "active_interlocks": ["emergency_stop"]
    },
    "timestamp_us": 1696262400000000
  }
}
```

**HTTP Status Codes**:
- `400 Bad Request` - Invalid input parameters
- `401 Unauthorized` - Missing or invalid JWT token
- `403 Forbidden` - Safety interlocks or permissions prevent action
- `404 Not Found` - Resource does not exist
- `409 Conflict` - Operation conflicts with current state
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Unhandled exception (logged for debugging)

---

## Rate Limits

- **Authentication**: 5 login attempts per minute per IP
- **Control endpoints** (`/control/*`): 10 requests per second
- **Configuration updates** (`/config/*`, `/navigation/geofence`): 1 per 10 seconds
- **Diagnostic queries**: 20 per minute

Exceeded limits return `429 Too Many Requests` with `Retry-After` header.

---

## Contract Test Coverage

All endpoints have corresponding pytest contract tests in `tests/contract/`:

- `test_auth_login.py` - Authentication flow
- `test_config_*.py` - Configuration retrieval
- `test_status.py` - Robot state queries
- `test_control_*.py` - Motor control and E-stop
- `test_navigation_*.py` - Navigation mode, geofence, waypoints
- `test_jobs_*.py` - Job scheduling CRUD operations
- `test_diagnostics_*.py` - Driver health, log bundles
- `test_websocket_telemetry.py` - WebSocket streaming

**TDD Requirement**: All tests must FAIL initially (no implementation), then PASS after implementation (Constitution Principle III).

---

## Next Steps

✅ API Contracts Complete - Proceed to quickstart.md generation
