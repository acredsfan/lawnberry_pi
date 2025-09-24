# WebSocket Events Contract

## Connection Events

### `client.connect`
**Direction**: Client → Server
**Purpose**: Establish WebSocket connection and request initial state
```json
{
  "event": "client.connect",
  "data": {
    "client_type": "web_ui",
    "requested_subscriptions": ["telemetry", "safety", "navigation"],
    "client_info": {
      "user_agent": "string",
      "screen_resolution": "1920x1080"
    }
  }
}
```

### `server.connected`
**Direction**: Server → Client
**Purpose**: Confirm connection and provide session information
```json
{
  "event": "server.connected",
  "data": {
    "session_id": "uuid",
    "server_time": "2025-09-24T10:30:00Z",
    "system_status": "operational",
    "available_subscriptions": ["telemetry", "safety", "navigation", "camera", "ai"]
  }
}
```

## Telemetry Events

### `telemetry.sensor_data`
**Direction**: Server → Client
**Purpose**: Real-time sensor measurements
```json
{
  "event": "telemetry.sensor_data",
  "timestamp": "2025-09-24T10:30:01.500Z",
  "data": {
    "imu": {
      "acceleration": [0.1, 0.2, 9.8],
      "gyroscope": [0.01, 0.02, 0.003],
      "heading": 45.5
    },
    "power": {
      "battery_voltage": 12.6,
      "current_draw": 2.3,
      "battery_percentage": 85.2
    },
    "tof_sensors": [
      {"sensor_id": "front", "distance_mm": 1200, "quality": 0.95},
      {"sensor_id": "left", "distance_mm": 800, "quality": 0.87}
    ],
    "encoders": {
      "left_wheel": {"count": 12345, "rpm": 120},
      "right_wheel": {"count": 12350, "rpm": 118}
    }
  }
}
```

### `telemetry.system_status`
**Direction**: Server → Client
**Purpose**: System health and operational metrics
```json
{
  "event": "telemetry.system_status",
  "timestamp": "2025-09-24T10:30:02.000Z",
  "data": {
    "uptime_seconds": 3600,
    "cpu_usage": 25.5,
    "memory_usage": 45.2,
    "disk_usage": 12.8,
    "network_status": "connected",
    "service_health": {
      "mower_core": "healthy",
      "camera_stream": "healthy",
      "webui": "healthy"
    }
  }
}
```

## Control Events

### `control.navigation_command`
**Direction**: Client → Server
**Purpose**: Manual navigation control
```json
{
  "event": "control.navigation_command",
  "data": {
    "command_type": "manual_drive",
    "left_wheel_speed": 0.5,
    "right_wheel_speed": 0.5,
    "cutting_blade": true,
    "duration_ms": 1000
  }
}
```

### `control.start_autonomous`
**Direction**: Client → Server
**Purpose**: Begin autonomous mowing operation
```json
{
  "event": "control.start_autonomous",
  "data": {
    "mowing_pattern": "spiral",
    "area_bounds": {
      "min_x": 0, "max_x": 50,
      "min_y": 0, "max_y": 30
    },
    "cutting_height": 25,
    "safety_mode": "standard"
  }
}
```

### `control.emergency_stop`
**Direction**: Client → Server
**Purpose**: Immediate system shutdown
```json
{
  "event": "control.emergency_stop",
  "data": {
    "reason": "user_initiated",
    "timestamp": "2025-09-24T10:30:03.000Z"
  }
}
```

## Safety Events

### `safety.alert`
**Direction**: Server → Client
**Purpose**: Safety condition notifications
```json
{
  "event": "safety.alert",
  "timestamp": "2025-09-24T10:30:04.000Z",
  "data": {
    "alert_type": "obstacle_detected",
    "severity": "warning",
    "description": "Forward obstacle detected at 0.8m",
    "sensor_data": {
      "tof_front": 800,
      "confidence": 0.95
    },
    "actions_taken": ["reduce_speed", "alert_user"],
    "requires_acknowledgment": false
  }
}
```

### `safety.emergency`
**Direction**: Server → Client
**Purpose**: Critical safety events requiring immediate attention
```json
{
  "event": "safety.emergency",
  "timestamp": "2025-09-24T10:30:05.000Z",
  "data": {
    "emergency_type": "tilt_detected",
    "severity": "critical",
    "description": "Excessive tilt detected - motors stopped",
    "trigger_data": {
      "imu_tilt_angle": 45.2,
      "safety_threshold": 30.0
    },
    "actions_taken": ["stop_all_motors", "enable_safety_lockout"],
    "requires_manual_reset": true
  }
}
```

## Navigation Events

### `navigation.state_update`
**Direction**: Server → Client
**Purpose**: Current navigation state and planned path
```json
{
  "event": "navigation.state_update",
  "timestamp": "2025-09-24T10:30:06.000Z",
  "data": {
    "current_position": {"x": 12.5, "y": 8.3, "heading": 45.0},
    "navigation_mode": "autonomous",
    "planned_path": [
      {"x": 13.0, "y": 8.5},
      {"x": 13.5, "y": 8.7},
      {"x": 14.0, "y": 9.0}
    ],
    "path_confidence": 0.92,
    "obstacles": [
      {"x": 15.2, "y": 9.5, "radius": 0.5, "type": "static"}
    ],
    "progress": {
      "area_completed": 15.2,
      "estimated_time_remaining": 1800
    }
  }
}
```

## AI Processing Events

### `ai.detection_results`
**Direction**: Server → Client
**Purpose**: AI-based object detection results
```json
{
  "event": "ai.detection_results",
  "timestamp": "2025-09-24T10:30:07.000Z",
  "data": {
    "frame_id": "frame_12345",
    "runner_type": "coral_tpu",
    "inference_time_ms": 45.2,
    "detections": [
      {
        "class": "obstacle",
        "confidence": 0.87,
        "bounding_box": {"x": 100, "y": 150, "width": 80, "height": 60},
        "world_position": {"x": 12.0, "y": 5.5, "distance": 2.3}
      }
    ],
    "processing_stats": {
      "queue_size": 2,
      "fps": 15.5,
      "hardware_status": "optimal"
    }
  }
}
```

## Camera Events

### `camera.stream_info`
**Direction**: Server → Client
**Purpose**: Camera stream status and configuration
```json
{
  "event": "camera.stream_info",
  "timestamp": "2025-09-24T10:30:08.000Z",
  "data": {
    "stream_url": "ws://localhost:8001/camera/stream",
    "resolution": {"width": 1280, "height": 720},
    "fps": 15,
    "encoding": "h264",
    "quality": "medium",
    "ai_overlay": true
  }
}
```

## Configuration Events

### `config.update_request`
**Direction**: Client → Server
**Purpose**: Request configuration changes
```json
{
  "event": "config.update_request",
  "data": {
    "config_section": "navigation_settings",
    "updates": {
      "max_speed": 1.2,
      "obstacle_avoidance_distance": 1.0,
      "turn_radius": 0.5
    }
  }
}
```

### `config.update_response`
**Direction**: Server → Client
**Purpose**: Confirm configuration changes
```json
{
  "event": "config.update_response",
  "data": {
    "success": true,
    "config_section": "navigation_settings",
    "updated_values": {
      "max_speed": 1.2,
      "obstacle_avoidance_distance": 1.0,
      "turn_radius": 0.5
    },
    "restart_required": false
  }
}
```