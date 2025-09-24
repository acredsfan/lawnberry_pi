# Research: LawnBerry Pi v2

## Technology Decisions

### FastAPI + WebSocket Real-time Telemetry
**Decision**: FastAPI with WebSocket connections for bidirectional real-time communication
**Rationale**: FastAPI provides excellent async support, automatic OpenAPI docs, and built-in WebSocket support. Constitutional requirement for real-time telemetry demands low-latency bidirectional communication.
**Alternatives considered**: Flask-SocketIO (heavier), raw asyncio (more complex), MQTT (external dependency)

### AI Acceleration Integration
**Decision**: Tiered approach with graceful degradation: Coral USB TPU (isolated `venv-coral`) → Hailo AI Hat → CPU TFLite
**Rationale**: Constitutional requirement for AI acceleration hierarchy and ban on `pycoral`/`edgetpu` in the primary environment. Coral isolation prevents package conflicts, Hailo provides optional performance boost without hat stacking conflicts, CPU ensures universal compatibility.
**Alternatives considered**: Single acceleration method (limits hardware flexibility), OpenVINO (Intel-focused), TensorRT (NVIDIA only)

### GPS Module Strategy
**Decision**: Primary ZED-F9P RTK over USB with NTRIP corrections, alternative Neo-8M over UART when RTK unavailable.
**Rationale**: Constitution locks F9P as preferred path for precision and mandates mutually exclusive selection with Neo-8M fallback. USB host capabilities differentiate F9P, while UART simplicity keeps Neo-8M viable for budget builds.
**Alternatives considered**: Concurrent dual-GPS fusion (violates spec), external NMEA receivers (insufficient precision), RTK via cellular modem (adds dependency).

### Raspberry Pi Hardware Interfaces
**Decision**: Direct hardware access via python-periphery + lgpio for GPIO, pyserial for UART4 BNO085, smbus2 for I2C peripherals (INA3221, VL53L0X pair, BME280, SSD1306), Picamera2 for camera streaming.
**Rationale**: Constitutional requirement for specific hardware libraries and explicit bus/address mappings; direct access ensures deterministic timing for safety systems.
**Alternatives considered**: RPi.GPIO (deprecated), gpiozero (higher-level abstraction), opencv camera (less Pi-optimized)

### Motor Controller Options
**Decision**: Preferred RoboHAT RP2040 commanding Cytron MDDRC10 with hall encoder feedback; alternative L298N dual H-bridge when RoboHAT unavailable.
**Rationale**: Constitution mandates RoboHAT→MDDRC10 path but permits L298N fallback. Abstraction layer must adapt to hardware availability while preserving safety interlocks.
**Alternatives considered**: CAN-based motor controllers (additional hardware), direct GPIO PWM (less robust), commercial ESCs (lack encoder integration).

### Power Monitoring & INA3221 Mapping
**Decision**: INA3221 at 0x40 with immutable channel assignments (Ch1 battery voltage/current, Ch2 reserved unused, Ch3 solar panel input).
**Rationale**: Constitutional enforcement prevents mis-wiring and ensures documentation/UI reflect fixed power semantics. Software must reject remapping attempts.
**Alternatives considered**: ADS1115 (insufficient multi-channel current sensing), dynamic channel reassignment (invites operator error).

### React Retro 80s Theme & Branding
**Decision**: Custom CSS with neon colors, monospace fonts, terminal-style UI elements, and synthwave color palette derived from `LawnBerryPi_logo.png` and `LawnBerryPi_icon2.png`
**Rationale**: User requirement for retro 80s aesthetic and mandated reuse of official logo and icon across the WebUI, favicon, and splash/loading states. Direct asset-driven palette keeps branding consistent.
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
Module-oriented packages under `src/lawnberry/` for sensors (BNO085, VL53L0X pair, BME280, SSD1306), navigation, motion (RoboHAT→MDDRC10 preferred, L298N alternative), safety, power (INA3221 fixed mapping), camera, AI runners (Coral/Hailo/CPU), webui, and service core. GPS modules (`rtk_gps_f9p`, `gps_neo8m_alt`) expose mutually exclusive drivers with shared interface.

### Testing Strategy
Contract tests for WebSocket/REST APIs, integration tests for hardware abstractions with SIM_MODE toggles covering both GPS and motor controller branches, unit tests for AI runners enforcing isolation, and power monitor tests validating channel mapping guards.

### Deployment Automation
`pi_bootstrap.sh` handles uv installation, primary venv setup, creation of isolated `venv-coral`, systemd service installation, configuration file creation, and migration from v1 if detected. Scripts enforce Wi-Fi runtime assumption and warn if Ethernet-only networking detected.

### Configuration Management
Environment-based configuration with `.env` files capturing GPS selection (`GPS_MODE=f9p|neo8m`), drive controller (`DRIVE_CONTROLLER=robohat|l298n`), accelerator availability, and SIM_MODE toggles. Separate configs for development, testing, and production. Constitutional requirement for dotenv loading.

### Build Process
Frontend: Vite build generating static assets served by FastAPI. Pre-commit hooks for code quality. CI pipeline with linting, testing, and documentation drift detection.
### Branding Asset Pipeline
Use Vite asset imports to embed `LawnBerryPi_logo.png` and `LawnBerryPi_icon2.png` into the React app, generate favicons/manifest icons during build, and expose a theming module exporting color tokens sampled from the logo for consistent retro styling across components and charts.

### Map Provider Strategy
**Decision**: Integrate Google Maps JavaScript API (with `GOOGLE_MAPS_API_KEY`) for advanced polygon editing, fallback to Leaflet + OpenStreetMap when key unavailable.
**Rationale**: Google provides robust drawing tools and satellite imagery; fallback maintains functionality offline or without key.
**Implementation Notes**: Custom robot pin derived from `LawnBerryPi_Pin.png`, polygon validation for non-self-intersecting boundaries, store GeoJSON in SQLite.

### Manual Control Interfaces
**Decision**: Provide virtual joystick plus Gamepad API and keyboard fallback with safety gating (tilt, estop). Use debounced commands over WebSocket.
**Rationale**: Supports multiple controller types while preventing unsafe activation when sensors indicate hazards.

### WebSocket Architecture
**Decision**: Single `/ws` endpoint multiplexing `telemetry`, `events`, `map`, `ai`, and `logs` topics with rate limits (telemetry 5–10 Hz, logs throttled).
**Rationale**: Keeps connection count low on constrained hardware while delivering real-time updates to UI.

### Weather & External APIs
**Decision**: Blend local BME280 readings with OpenWeatherMap forecast (`OPENWEATHERMAP_API_KEY`) when available; degrade gracefully to local data.
**Rationale**: Maintains usefulness even without external key; ensures compliance with offline-first expectation.

### AI Dataset Management
**Decision**: Store collected frames metadata in SQLite (`ai_images`), allow tagging, export to COCO/YOLO, and trigger light on-device training using TFLite.
**Rationale**: Supports iterative dataset curation without overwhelming Pi hardware; offloads heavy training externally via packaged export.

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