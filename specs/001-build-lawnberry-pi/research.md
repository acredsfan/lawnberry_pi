# Research: LawnBerry Pi v2

## Technology Decisions

### FastAPI + WebSocket Real-time Telemetry
**Decision**: FastAPI with WebSocket connections for bidirectional real-time communication
**Rationale**: FastAPI provides excellent async support, automatic OpenAPI docs, and built-in WebSocket support. Constitutional requirement for real-time telemetry demands low-latency bidirectional communication.
**Alternatives considered**: Flask-SocketIO (heavier), raw asyncio (more complex), MQTT (external dependency)

### AI Acceleration Integration
**Decision**: Tiered approach with graceful degradation: Coral TPU (isolated venv) → Hailo AI Hat → CPU TFLite
**Rationale**: Constitutional requirement for AI acceleration hierarchy. Coral isolation prevents package conflicts, Hailo provides optional performance boost, CPU ensures universal compatibility.
**Alternatives considered**: Single acceleration method (limits hardware flexibility), OpenVINO (Intel-focused), TensorRT (NVIDIA only)

### Raspberry Pi Hardware Interfaces
**Decision**: Direct hardware access via python-periphery + lgpio for GPIO, Picamera2 for camera, pyserial for UART
**Rationale**: Constitutional requirement for specific hardware libraries. Direct access provides reliable low-level control without abstraction overhead.
**Alternatives considered**: RPi.GPIO (deprecated), gpiozero (higher-level abstraction), opencv camera (less Pi-optimized)

### React Retro 80s Theme
**Decision**: Custom CSS with neon colors, monospace fonts, terminal-style UI elements, and synthwave color palette
**Rationale**: User requirement for retro 80s aesthetic. CSS provides performance and customization without heavy theme frameworks.
**Alternatives considered**: Material-UI retro theme (limited customization), styled-components (build complexity), CSS frameworks (generic)

### SQLite Schema Design
**Decision**: Normalized schema with tables for runs, telemetry, faults, settings, and operational history
**Rationale**: sqlite-utils constitutional requirement. Single-file database simplifies deployment and backup. Normalized design supports efficient queries and data integrity.
**Alternatives considered**: JSON file storage (no relational queries), PostgreSQL (overkill for single-device), time-series DB (additional complexity)

### SystemD Service Orchestration
**Decision**: Three systemd services: mower-core.service, camera-stream.service, webui.service with dependencies
**Rationale**: Constitutional requirement for systemd service management. Service separation enables independent scaling and failure isolation.
**Alternatives considered**: Single monolithic service (no isolation), Docker compose (constitutional violation), supervisor (non-standard on RPi OS)

## Integration Patterns

### WebSocket Hub Architecture
Central message router pattern with typed event schemas. Services publish/subscribe to specific event types. WebSocket clients receive filtered event streams based on subscriptions.

### AI Runner Interface
Abstract base runner with common interface. Each acceleration tier implements the same contract. Runtime detection selects best available option with automatic fallback.

### Hardware Abstraction Layer
Service classes wrapping hardware interfaces with error handling, retry logic, and graceful degradation. Mock implementations for testing without hardware.

### Error Handling Strategy
Structured logging with contextual information. Service-level error boundaries preventing cascade failures. User notification through WebSocket events for critical errors.

## Implementation Approaches

### Module Organization
Eight core modules as separate Python packages under src/lawnberry/: sensors, navigation, motion, safety, power, camera, webui, ai. Each module exports service classes and data models.

### Testing Strategy
Contract tests for API endpoints, integration tests for hardware interfaces with mocks, unit tests for business logic. Simulation mode for testing without physical hardware.

### Deployment Automation
pi_bootstrap.sh script handling: uv installation, venv setup, systemd service installation, configuration file creation, migration from v1 if detected.

### Configuration Management
Environment-based configuration with .env files. Separate configs for development, testing, and production. Constitutional requirement for dotenv loading.

### Build Process
Frontend: Vite build generating static assets served by FastAPI. Pre-commit hooks for code quality. CI pipeline with linting, testing, and documentation drift detection.

## Performance Considerations

### Real-time Requirements
WebSocket connection pooling, event batching for high-frequency telemetry, background task queues for non-critical operations.

### Memory Management
Circular buffers for sensor data, periodic database cleanup, lazy loading of AI models, stream processing for camera data.

### Power Optimization
Dynamic service scaling based on operational mode, efficient sleep states during idle periods, battery-aware processing intensity.

## Security Measures

### Network Security
Local network operation only, WebSocket origin validation, rate limiting on API endpoints, secure default configurations.

### System Security
Service user isolation, file permission restrictions, minimal attack surface through service separation.

### Data Protection
SQLite file encryption option, log rotation with secure deletion, configuration secret management.