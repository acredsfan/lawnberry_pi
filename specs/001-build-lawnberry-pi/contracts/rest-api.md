# REST API Contract

## System Management

### GET /api/v1/system/status
**Purpose**: Get overall system health and status
**Response**:
```json
{
  "system_status": "operational",
  "uptime_seconds": 3600,
  "services": {
    "mower_core": {"status": "healthy", "pid": 1234},
    "camera_stream": {"status": "healthy", "pid": 1235},
    "webui": {"status": "healthy", "pid": 1236}
  },
  "hardware": {
    "pi_model": "Raspberry Pi 5",
    "cpu_temp": 45.2,
    "available_accelerators": ["coral_tpu", "cpu_tflite"]
  },
  "version": "2.0.0"
}
```

### GET /api/v1/system/logs
**Purpose**: Retrieve system logs with filtering
**Query Parameters**:
- `level`: Log level filter (debug, info, warning, error)
- `service`: Service name filter
- `since`: ISO timestamp for log range start
- `limit`: Maximum number of entries (default: 100)
**Response**:
```json
{
  "logs": [
    {
      "timestamp": "2025-09-24T10:30:00Z",
      "level": "info",
      "service": "mower_core",
      "message": "Navigation system initialized",
      "context": {"module": "navigation", "sensor_count": 5}
    }
  ],
  "total_count": 250,
  "has_more": true
}
```

## Configuration Management

### GET /api/v1/config
**Purpose**: Retrieve current system configuration
**Response**:
```json
{
  "navigation_settings": {
    "max_speed": 1.0,
    "obstacle_avoidance_distance": 1.5,
    "turn_radius": 0.8,
    "path_planning_algorithm": "a_star"
  },
  "safety_thresholds": {
    "max_tilt_angle": 30.0,
    "min_battery_voltage": 11.0,
    "obstacle_detection_sensitivity": 0.8
  },
  "ai_settings": {
    "preferred_runner": "coral_tpu",
    "inference_timeout_ms": 200,
    "confidence_threshold": 0.7
  },
  "camera_settings": {
    "resolution": {"width": 1280, "height": 720},
    "fps": 15,
    "quality": "medium"
  }
}
```

### PUT /api/v1/config
**Purpose**: Update system configuration
**Request Body**:
```json
{
  "navigation_settings": {
    "max_speed": 1.2,
    "obstacle_avoidance_distance": 1.0
  },
  "safety_thresholds": {
    "max_tilt_angle": 25.0
  }
}
```
**Response**:
```json
{
  "success": true,
  "updated_sections": ["navigation_settings", "safety_thresholds"],
  "restart_required": false,
  "validation_errors": []
}
```

## Sensor Data

### GET /api/v1/sensors/current
**Purpose**: Get current readings from all sensors
**Response**:
```json
{
  "timestamp": "2025-09-24T10:30:01Z",
  "sensors": {
    "imu": {
      "acceleration": {"x": 0.1, "y": 0.2, "z": 9.8},
      "gyroscope": {"x": 0.01, "y": 0.02, "z": 0.003},
      "heading": 45.5,
      "status": "active"
    },
    "power": {
      "battery_voltage": 12.6,
      "current_draw": 2.3,
      "battery_percentage": 85.2,
      "charging_status": "discharging"
    },
    "tof_sensors": [
      {
        "sensor_id": "front",
        "distance_mm": 1200,
        "quality": 0.95,
        "status": "active"
      }
    ],
    "encoders": {
      "left_wheel": {"count": 12345, "rpm": 120},
      "right_wheel": {"count": 12350, "rpm": 118}
    }
  }
}
```

### GET /api/v1/sensors/history
**Purpose**: Retrieve historical sensor data
**Query Parameters**:
- `sensor_type`: Filter by sensor type (imu, power, tof, encoder)
- `start_time`: ISO timestamp for range start
- `end_time`: ISO timestamp for range end
- `resolution`: Data resolution (1s, 10s, 1m, 10m)
**Response**:
```json
{
  "sensor_type": "power",
  "resolution": "10s",
  "data_points": [
    {
      "timestamp": "2025-09-24T10:30:00Z",
      "battery_voltage": 12.6,
      "current_draw": 2.3,
      "battery_percentage": 85.2
    }
  ],
  "count": 360
}
```

## Navigation Control

### GET /api/v1/navigation/state
**Purpose**: Get current navigation state
**Response**:
```json
{
  "current_position": {"x": 12.5, "y": 8.3, "heading": 45.0},
  "navigation_mode": "autonomous",
  "planned_path": [
    {"x": 13.0, "y": 8.5},
    {"x": 13.5, "y": 8.7}
  ],
  "path_confidence": 0.92,
  "obstacles": [
    {"x": 15.2, "y": 9.5, "radius": 0.5, "type": "static"}
  ],
  "mowing_progress": {
    "area_completed_percent": 15.2,
    "estimated_time_remaining_seconds": 1800,
    "current_pattern": "spiral"
  }
}
```

### POST /api/v1/navigation/start_autonomous
**Purpose**: Begin autonomous mowing operation
**Request Body**:
```json
{
  "mowing_pattern": "spiral",
  "area_bounds": {
    "min_x": 0, "max_x": 50,
    "min_y": 0, "max_y": 30
  },
  "cutting_height": 25,
  "max_speed": 1.0,
  "safety_mode": "standard"
}
```
**Response**:
```json
{
  "success": true,
  "navigation_mode": "autonomous",
  "estimated_duration_seconds": 3600,
  "planned_path_length": 45
}
```

### POST /api/v1/navigation/emergency_stop
**Purpose**: Immediately stop all mower operations
**Request Body**:
```json
{
  "reason": "user_initiated"
}
```
**Response**:
```json
{
  "success": true,
  "stopped_at": "2025-09-24T10:30:05Z",
  "previous_mode": "autonomous",
  "motors_stopped": true,
  "safety_lockout": true
}
```

## AI Processing

### GET /api/v1/ai/status
**Purpose**: Get AI processing system status
**Response**:
```json
{
  "active_runner": "coral_tpu",
  "available_runners": [
    {
      "type": "coral_tpu",
      "status": "available",
      "model_loaded": "mobilenet_v2_obstacle_detection",
      "inference_time_avg_ms": 45.2
    },
    {
      "type": "cpu_tflite",
      "status": "standby",
      "model_loaded": "mobilenet_v2_obstacle_detection",
      "inference_time_avg_ms": 120.5
    }
  ],
  "processing_queue_size": 2,
  "fps": 15.5
}
```

### GET /api/v1/ai/detections/recent
**Purpose**: Get recent AI detection results
**Query Parameters**:
- `limit`: Number of recent detections (default: 10)
- `confidence_min`: Minimum confidence threshold
**Response**:
```json
{
  "detections": [
    {
      "timestamp": "2025-09-24T10:30:07Z",
      "frame_id": "frame_12345",
      "objects": [
        {
          "class": "obstacle",
          "confidence": 0.87,
          "bounding_box": {"x": 100, "y": 150, "width": 80, "height": 60},
          "world_position": {"x": 12.0, "y": 5.5, "distance": 2.3}
        }
      ],
      "inference_time_ms": 45.2
    }
  ]
}
```

## Operational History

### GET /api/v1/operations/runs
**Purpose**: Get mowing run history
**Query Parameters**:
- `limit`: Number of runs to return (default: 20)
- `status`: Filter by run status (completed, interrupted, failed)
**Response**:
```json
{
  "runs": [
    {
      "run_id": "run_20250924_103000",
      "start_time": "2025-09-24T10:30:00Z",
      "end_time": "2025-09-24T11:45:00Z",
      "status": "completed",
      "area_covered_m2": 450.5,
      "runtime_seconds": 4500,
      "battery_consumed_percent": 35.2,
      "pattern_used": "spiral",
      "faults_encountered": 1
    }
  ],
  "total_count": 156
}
```

### GET /api/v1/operations/faults
**Purpose**: Get system fault history
**Query Parameters**:
- `severity`: Filter by fault severity (info, warning, critical)
- `resolved`: Filter by resolution status (true, false)
**Response**:
```json
{
  "faults": [
    {
      "fault_id": "fault_12345",
      "timestamp": "2025-09-24T10:35:00Z",
      "type": "obstacle_detected",
      "severity": "warning",
      "description": "Forward obstacle detected during autonomous operation",
      "resolved": true,
      "resolution_time": "2025-09-24T10:35:05Z",
      "resolution_method": "automatic_avoidance"
    }
  ],
  "total_count": 23,
  "unresolved_count": 0
}
```