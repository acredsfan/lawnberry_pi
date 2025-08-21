# LawnBerryPi API Reference

**Version:** 1.0  
**Base URL:** `http://localhost:8000/api/v1`  
**Authentication:** Token-based with role-based access control  
**Last Updated:** December 2024  
**WebSocket:** `ws://localhost:8001/ws` for real-time updates

## Overview

The LawnBerryPi system provides a comprehensive REST API with WebSocket support for real-time communication. The API follows RESTful principles and uses JSON for data exchange.

## Authentication

Most API endpoints require authentication (token-based with role-based access control). However, the following read-only endpoints are intentionally exposed for unauthenticated access to support public map viewing and basic service diagnostics:

Public (no token required):
* `GET /api/v1/meta` – API service meta/status (not mower state)
* `GET /api/v1/maps` – Combined map data (read-only)
* `GET /api/v1/maps/boundaries`
* `GET /api/v1/maps/no-go-zones`
* `GET /api/v1/maps/home-location` / `home-locations`
* `GET /api/v1/maps/validation/*` (map geometry validation helpers)

All write (POST/PUT/DELETE) map endpoints and every other domain (navigation, power, sensors, patterns, configuration, RC control, camera) still require valid authorization.

### Headers
```
Authorization: Bearer <token>
Content-Type: application/json
```

## Maps API

### Get Map Data
**GET** `/api/v1/maps`

Returns complete map data including boundaries, no-go zones, and current location.

**Response:**
```json
{
  "boundaries": [
    {
      "points": [
        {"latitude": 40.7128, "longitude": -74.0060},
        {"latitude": 40.7130, "longitude": -74.0058}
      ],
      "name": "Main Yard"
    }
  ],
  "no_go_zones": [
    {
      "center": {"latitude": 40.7129, "longitude": -74.0059},
      "radius": 5.0,
      "name": "Garden Bed"
    }
  ],
  "home_position": {"latitude": 40.7128, "longitude": -74. (60},
  "charging_spots": [],
  "coverage_map": {}
}
```

### Boundaries Management

**GET** `/api/v1/maps/boundaries`
- Returns all defined yard boundaries

**POST** `/api/v1/maps/boundaries`
- Creates a new boundary
- **Body:** Boundary object with points array

**PUT** `/api/v1/maps/boundaries/{id}`
- Updates existing boundary
- **Body:** Updated boundary object

**DELETE** `/api/v1/maps/boundaries/{id}`
- Removes boundary

### No-Go Zones Management

**GET** `/api/v1/maps/no-go-zones`
- Returns all no-go zones

**POST** `/api/v1/maps/no-go-zones`
- Creates new no-go zone
- **Body:** NoGoZone object with center and radius

**PUT** `/api/v1/maps/no-go-zones/{id}`
- Updates existing no-go zone

**DELETE** `/api/v1/maps/no-go-zones/{id}`
- Removes no-go zone

### Home Location Management

**GET** `/api/v1/maps/home-location`
- Returns current home location

**POST** `/api/v1/maps/home-location`
- Sets home location
- **Body:** Position object with latitude/longitude

## Navigation API

### Navigation Control
**GET** `/api/v1/navigation/status`
- Returns current navigation status and position

**POST** `/api/v1/navigation/start`
- Starts autonomous navigation
- **Body:** `{"pattern": "parallel", "area": "main_yard"}`

**POST** `/api/v1/navigation/stop`
- Stops current navigation

**POST** `/api/v1/navigation/emergency-stop`
- Immediate emergency stop

**POST** `/api/v1/navigation/return-home`
- Returns mower to home location

## Patterns API

### Mowing Patterns
**GET** `/api/v1/patterns`
- Returns available mowing patterns

**GET** `/api/v1/patterns/{pattern_name}`
- Returns specific pattern details

**POST** `/api/v1/patterns/generate`
- Generates mowing pattern for specified area
- **Body:** 
```json
{
  "pattern_type": "parallel",
  "area": "main_yard",
  "line_spacing": 0.5,
  "angle": 45
}
```

Available patterns:
- `parallel` - Parallel line pattern
- `checkerboard` - Checkerboard pattern
- `spiral` - Spiral pattern from outside in
- `waves` - Sinusoidal wave pattern
- `crosshatch` - Dual-angle crosshatch pattern

## Sensors API

### Sensor Data
**GET** `/api/v1/sensors`
- Returns current readings from all sensors

**GET** `/api/v1/sensors/{sensor_type}`
- Returns data from specific sensor type

Available sensor types:
- `tof` - Time of Flight sensors
- `imu` - Inertial Measurement Unit
- `gps` - GPS location data
- `camera` - Camera system status
- `environmental` - BME280 environmental data

**Response Example:**
```json
{
  "timestamp": "2024-12-01T10:30:00Z",
  "tof": {
    "left": {"distance_mm": 1500, "status": "good"},
    "right": {"distance_mm": 2000, "status": "good"}
  },
  "imu": {
    "acceleration": {"x": 0.1, "y": 0.2, "z": 9.8},
    "rotation": {"x": 0, "y": 0, "z": 0},
    "heading": 45.5
  },
  "gps": {
    "latitude": 40.7128,
    "longitude": -74.0060,
    "accuracy": 1.2,
    "fix_quality": "rtk"
  },
  "environmental": {
    "temperature": 22.5,
    "humidity": 65.2,
    "pressure": 1013.25
  }
}
```

## Power API

### Power Monitoring
**GET** `/api/v1/power`
- Returns current power system status

**GET** `/api/v1/power/battery`
- Returns detailed battery information

**GET** `/api/v1/power/solar`
- Returns solar panel performance data

**Response Example:**
```json
{
  "battery": {
    "voltage": 12.6,
    "current": -2.5,
    "power": -31.5,
    "charge_percentage": 85,
    "time_remaining": "4h 30m"
  },
  "solar": {
    "voltage": 18.2,
    "current": 1.8,
    "power": 32.76,
    "efficiency": 87.2
  },
  "consumption": {
    "total_power": 45.5,
    "drive_motors": 25.0,
    "blade_motor": 15.0,
    "electronics": 5.5
  }
}
```

## Weather API

### Weather Data
**GET** `/api/v1/weather/current`
- Returns current weather conditions

**GET** `/api/v1/weather/forecast`
- Returns 5-day weather forecast

**Response Example:**
```json
{
  "current": {
    "temperature": 22.5,
    "humidity": 65,
    "description": "partly cloudy",
    "wind_speed": 5.2,
    "precipitation": 0.0,
    "is_mowing_safe": true
  },
  "forecast": [
    {
      "date": "2024-12-02",
      "high": 24,
      "low": 18,
      "precipitation_chance": 20,
      "description": "sunny"
    }
  ]
}
```

## System API

### System Status
**GET** `/api/v1/system/status`
- Returns overall system health and status

**GET** `/api/v1/system/services`
- Returns status of all microservices

**POST** `/api/v1/system/restart`
- Restarts specified service or entire system

**Response Example:**
```json
{
  "status": "operational",
  "uptime": "2d 14h 30m",
  "version": "1.0.0",
  "services": {
    "hardware": "running",
    "safety": "running",
    "vision": "running",
    "navigation": "running",
    "power": "running",
    "weather": "running",
    "communication": "running"
  },
  "health_score": 98
}
```

## WebSocket API

### Real-Time Data Streaming
**Connection:** `ws://localhost:8000/api/v1/websocket`

The WebSocket connection provides real-time updates for:
- Robot position and status
- Sensor readings
- Power consumption
- Safety alerts
- Navigation progress
 - RC control status (topic `rc/status`)
 - Sensor service heartbeat (topic `sensors/heartbeat`)
 - System service status (retained, topic `system/status`)

### Message Format
```json
{
  "type": "sensor_update",
  "timestamp": "2024-12-01T10:30:00Z",
  "data": {
    "position": {"lat": 40.7128, "lng": -74.0060},
    "heading": 45.5,
    "speed": 0.5,
    "battery": 85
  }
}
```

### Message Types
- `position_update` - Robot location changes
- `sensor_update` - Sensor data updates
- `power_update` - Power system changes
- `safety_alert` - Safety system notifications
- `navigation_update` - Navigation progress
- `weather_update` - Weather condition changes

### RC Status Forwarding

Subscribe to `rc/status` (and `hardware/rc/status` for compatibility) to receive RC control status as MQTT-backed WebSocket messages of type `mqtt_data`:

```
{
  "type": "mqtt_data",
  "topic": "rc/status",
  "data": { "rc_enabled": true, "rc_mode": "manual", ... }
}
```

### Heartbeat and Service Status

The hardware sensor service publishes the following to support UI readiness and monitoring:

- `sensors/heartbeat` (QoS 0, every ~2s)
  - Example:
  ```json
  {
    "service": "hardware_sensor_service",
    "timestamp": "2025-08-21T12:34:56.789Z"
  }
  ```

- `system/status` (retained, QoS 1)
  - Published on start and stop with retained flag so late subscribers can immediately determine service state.
  - Example (running):
  ```json
  {
    "service": "hardware_sensor_service",
    "status": "running",
    "started_at": "2025-08-21T12:34:00.000Z",
    "timestamp": "2025-08-21T12:34:00.000Z"
  }
  ```
  - Example (stopped):
  ```json
  {
    "service": "hardware_sensor_service",
    "status": "stopped",
    "timestamp": "2025-08-21T12:45:00.000Z"
  }
  ```

## RC Control API

Endpoints under `/api/v1/rc` manage manual control and configuration:

- `GET /api/v1/rc/status` – RC system status
- `POST /api/v1/rc/mode` – Set RC mode (`emergency|manual|assisted|training`)
- `POST /api/v1/rc/enable` – Enable RC control
- `POST /api/v1/rc/disable` – Disable RC control (autonomous)
- `POST /api/v1/rc/blade` – Control blade motor (`{ enabled: true|false }`)
- `POST /api/v1/rc/channel/configure` – Configure channel mapping
- `GET /api/v1/rc/channels` – Current channel configuration
- `POST /api/v1/rc/emergency_stop` – Trigger emergency stop
- `POST /api/v1/rc/pwm` – Direct PWM drive `{ steer, throttle }` (clamped to 1000–2000 μs)

## Error Handling

### HTTP Status Codes
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `422` - Validation Error
- `500` - Internal Server Error
- `503` - Service Unavailable

### Error Response Format
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid boundary coordinates",
    "details": {
      "field": "points",
      "reason": "Minimum 3 points required for boundary"
    }
  }
}
```

## Rate Limiting

- **Maps API:** 100 requests/minute
- **Sensors API:** 500 requests/minute
- **Navigation API:** 50 requests/minute
- **WebSocket:** 1000 messages/minute

## Data Models

### Position
```typescript
interface Position {
  latitude: number;
  longitude: number;
}
```

### Boundary
```typescript
interface Boundary {
  id?: string;
  name: string;
  points: Position[];
  created_at?: string;
  updated_at?: string;
}
```

### NoGoZone
```typescript
interface NoGoZone {
  id?: string;
  name: string;
  center: Position;
  radius: number;
  created_at?: string;
  updated_at?: string;
}
```

### HomeLocation
```typescript
interface HomeLocation {
  position: Position;
  type: 'charging' | 'storage' | 'maintenance';
  name?: string;
}
```

## SDK and Client Libraries

### Python Client Example
```python
import requests
from websocket import WebSocket

class LawnBerryClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.headers = {'Authorization': f'Bearer {token}'}
    
    def get_map_data(self):
        response = requests.get(f'{self.base_url}/maps', headers=self.headers)
        return response.json()
    
    def start_mowing(self, pattern='parallel'):
        data = {'pattern': pattern}
        response = requests.post(f'{self.base_url}/navigation/start', 
                               json=data, headers=self.headers)
        return response.json()
```

### JavaScript Client Example
```javascript
class LawnBerryAPI {
  constructor(baseUrl, token) {
    this.baseUrl = baseUrl;
    this.headers = {'Authorization': `Bearer ${token}`};
  }
  
  async getMapData() {
    const response = await fetch(`${this.baseUrl}/maps`, {
      headers: this.headers
    });
    return response.json();
  }
  
  connectWebSocket() {
    const ws = new WebSocket(`ws://localhost:8000/api/v1/websocket`);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleRealtimeUpdate(data);
    };
  }
}
```

---

## Meta / Service Endpoint

### API Meta
**GET** `/api/v1/meta`

Returns meta information about the API service itself (distinct from mower runtime status). Useful for UI bootstrapping and service monitoring.

**Response Example:**
```json
{
  "api_version": "1.0.0",
  "service": "lawnberry-api",
  "status": "operational",
  "timestamp": 1733652000.123,
  "mqtt_connected": true,
  "uptime": 124.57
}
```

## SPA Routing Notes

The web UI (React + Vite) is mounted under `/ui`. Deep links like `/ui/maps` or `/ui/navigation` resolve via an internal single-page application fallback. Non-asset 404s under `/ui/*` return `index.html` automatically. Top-level convenience redirects `/maps` → `/ui/maps` are provided.

If deploying behind a reverse proxy, ensure it does NOT rewrite or pre-empt `/ui/*` paths so the backend fallback remains effective.


**Support:** For API support and questions, refer to the main documentation or contact the development team.
