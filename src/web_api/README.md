# Lawnberry Web API Backend

FastAPI-based REST API backend with WebSocket support for real-time communication with the autonomous lawn mower system.

## Features

- **FastAPI Framework**: Modern Python web framework with automatic OpenAPI documentation
- **Real-time Communication**: WebSocket support for live data streaming
- **MQTT Integration**: Bridge between MQTT messaging system and web clients
- **Authentication**: JWT-based authentication with role-based access control
- **Rate Limiting**: Configurable rate limiting to prevent API abuse
- **Comprehensive Logging**: Structured logging with request tracing
- **Performance Optimization**: Response caching, connection pooling, and compression
- **Security**: HTTPS/WSS support, input validation, and security headers

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web UI        │    │   Mobile App     │    │   External      │
│   (React)       │    │   (Future)       │    │   Integration   │
└─────────┬───────┘    └─────────┬────────┘    └─────────┬───────┘
          │                      │                       │
          └──────────────────────┼───────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │    FastAPI Backend      │
                    │  - REST API Endpoints   │
                    │  - WebSocket Server     │
                    │  - Authentication       │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │    MQTT Bridge          │
                    │  - Topic Subscriptions  │
                    │  - Message Forwarding   │
                    │  - Data Caching         │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Local MQTT Broker     │
                    │  - Mosquitto            │
                    │  - Topic Management     │
                    │  - QoS Handling         │
                    └─────────────────────────┘
```

## API Endpoints

### System Management
- `GET /api/v1/system/status` - Overall system status
- `GET /api/v1/system/services` - Service health status
- `GET /api/v1/system/metrics` - Performance metrics
- `POST /api/v1/system/emergency-stop` - Emergency stop trigger

### Sensor Data
- `GET /api/v1/sensors/` - All sensor status
- `GET /api/v1/sensors/{type}` - Current sensor data
- `GET /api/v1/sensors/{type}/history` - Historical data
- `POST /api/v1/sensors/{type}/calibrate` - Trigger calibration

### Navigation Control
- `GET /api/v1/navigation/status` - Current navigation status
- `POST /api/v1/navigation/start` - Start mowing operation
- `POST /api/v1/navigation/stop` - Stop operation
- `GET /api/v1/navigation/path` - Current path plan

### Mowing Patterns
- `GET /api/v1/patterns/` - Available patterns
- `GET /api/v1/patterns/{pattern}` - Pattern configuration
- `POST /api/v1/patterns/{pattern}` - Update pattern
- `GET /api/v1/patterns/schedule/` - Mowing schedules

### Configuration
- `GET /api/v1/config/system` - System configuration
- `PUT /api/v1/config/system` - Update system config
- `GET /api/v1/config/safety` - Safety configuration
- `PUT /api/v1/config/safety` - Update safety config

### Maps & Boundaries
- `GET /api/v1/maps/` - Complete map data
- `GET /api/v1/maps/boundaries` - Yard boundaries
- `POST /api/v1/maps/boundaries` - Create boundary
- `GET /api/v1/maps/no-go-zones` - No-go zones

### Weather Data
- `GET /api/v1/weather/current` - Current conditions
- `GET /api/v1/weather/forecast` - Weather forecast
- `GET /api/v1/weather/alerts` - Weather alerts
- `GET /api/v1/weather/suitable-for-mowing` - Mowing suitability

### Power Management
- `GET /api/v1/power/status` - Complete power status
- `GET /api/v1/power/battery` - Battery status
- `GET /api/v1/power/solar` - Solar charging status
- `POST /api/v1/power/charging-mode` - Set charging mode

### WebSocket
- `WS /ws/realtime` - Real-time data streaming

## Installation

### Prerequisites
- Python 3.9+
- Redis server
- MQTT broker (Mosquitto)
- Virtual environment

### Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MQTT_BROKER_HOST=localhost
export MQTT_BROKER_PORT=1883
export REDIS_HOST=localhost
export REDIS_PORT=6379
export JWT_SECRET_KEY=your-secret-key-here

# Run the server
python src/web_api/run_server.py
```

### Production Deployment

1. **Install as systemd service:**
```bash
sudo cp src/web_api/lawnberry-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lawnberry-api
sudo systemctl start lawnberry-api
```

2. **Configure reverse proxy (nginx):**
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /ws/ {
        # FastAPI serves the WebSocket endpoint at /ws/realtime on the same backend port
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 75s;
        proxy_send_timeout 75s;
    }
}
```

## Configuration

### Environment Variables
- `HOST` - Server host (default: 0.0.0.0)
- `PORT` - Server port (default: 8000)
- `DEBUG` - Debug mode (default: False)
- `LOG_LEVEL` - Logging level (default: INFO)
- `MQTT_BROKER_HOST` - MQTT broker host
- `MQTT_BROKER_PORT` - MQTT broker port
- `REDIS_HOST` - Redis server host
- `REDIS_PORT` - Redis server port
- `JWT_SECRET_KEY` - JWT signing key
- `AUTH_ENABLED` - Enable authentication (default: True)

### Configuration Files
- `.env` - Environment variables
- `config/` - YAML configuration files

## Authentication

The API uses JWT-based authentication with the following roles:
- **admin** - Full system access
- **operator** - Read/write access (no management)
- **viewer** - Read-only access
- **user** - Basic read access

### Login Process
```bash
# Login to get token
curl -X POST "/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'

# Use token in requests
curl -H "Authorization: Bearer <token>" "/api/v1/system/status"
```

## WebSocket Usage

### Connection
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/realtime');

ws.onopen = function(event) {
    console.log('Connected to WebSocket');
    
    // Subscribe to sensor data
    ws.send(JSON.stringify({
        type: 'subscribe',
        topic: 'sensors/gps/data'
    }));
};

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};
```

### Message Types
- `subscribe` - Subscribe to topic
- `unsubscribe` - Unsubscribe from topic  
- `command` - Send command
- `ping`/`pong` - Keep-alive

## Development

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
python -m pytest src/web_api/test_api.py -v

# Run basic validation
python src/web_api/test_api.py
```

### API Documentation
When running in debug mode, interactive API documentation is available at:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
- OpenAPI Schema: http://localhost:8000/api/openapi.json

### Development Server
```bash
# Run with auto-reload
python src/web_api/run_server.py

# Or use uvicorn directly
uvicorn web_api.main:app --reload --host 0.0.0.0 --port 8000
```

## Performance

### Response Times (Target)
- Cached data: < 50ms
- Real-time data: < 100ms
- Command execution: < 200ms
- WebSocket latency: < 50ms

### Optimization Features
- Redis caching for frequently accessed data
- Connection pooling for database and MQTT
- Response compression (gzip)
- Rate limiting to prevent abuse
- Efficient WebSocket message broadcasting

## Monitoring

### Health Checks
- `GET /health` - Basic liveness (no auth)
- `GET /api/v1/meta` - API service metadata (no auth; not mower state)
- `GET /api/v1/status` - Detailed mower/runtime status (auth)

Add the optional post-start systemd probe (already present in `lawnberry-api.service`):

```
ExecStartPost=/bin/bash -c '/home/pi/lawnberry/scripts/health_check_web_api.sh http://127.0.0.1:8000 || { echo "lawnberry-api health probe failed" >&2; exit 1; }'
```

This ensures the unit only reports started after the API is responsive.

### Automatic UI Rebuild (ExecStartPre)
`lawnberry-api.service` now runs `scripts/auto_rebuild_web_ui.sh` before launching. The script:
* Detects source changes (`src`, `public`, `package.json`, `vite.config.*`).
* Skips quickly if unchanged (<<1s).
* Installs dependencies if `node_modules` missing.
* Builds with timeout (`MAX_BUILD_SECONDS`, default 600s) to avoid hangs.
* Writes a `.build_timestamp` for future comparisons.

Disable temporarily by commenting the `ExecStartPre` line or exporting `MAX_BUILD_SECONDS=0` and early-exiting (customize script if desired).

### Logging
Structured JSON logging with:
- Request/response logging
- Performance metrics
- Error tracking
- Security events

### Metrics
Available at `/api/v1/system/metrics`:
- CPU and memory usage
- Request rates and response times
- WebSocket connection count
- MQTT message statistics

## Security

### Features
- JWT authentication with expiration
- Role-based access control
- Rate limiting per endpoint
- Input validation and sanitization
- Security headers (HSTS, CSP, etc.)
- CORS configuration

### Production Security
- Use HTTPS/WSS in production
- Set strong JWT secret key
- Configure firewall rules
- Regular security updates
- Monitor access logs

## Troubleshooting

### Common Issues

1. **MQTT Connection Failed**
   - Check Mosquitto broker is running
   - Verify host/port configuration
   - Check network connectivity

2. **WebSocket Connection Drops**
   - Check proxy configuration
   - Verify WebSocket upgrade headers
   - Monitor connection timeouts

3. **High Memory Usage**
   - Check Redis memory usage
   - Monitor WebSocket connections
   - Review caching configuration

4. **Slow Response Times**
   - Check MQTT broker latency
   - Monitor Redis performance
   - Review database queries

### Logs Location
- Application logs: `/var/log/lawnberry/web_api.log`
- System logs: `journalctl -u lawnberry-api`
- Access logs: Included in application logs

## License

This project is part of the Lawnberry autonomous lawn mower system.
