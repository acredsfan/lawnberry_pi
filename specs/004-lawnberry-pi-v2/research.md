# Research: LawnBerry Pi v2 Unified System

## Research Tasks Executed

### 1. Backend Framework Selection: FastAPI vs Flask

**Decision**: FastAPI
**Rationale**: 
- Native async/await support critical for real-time telemetry (5Hz+ requirements)
- Built-in WebSocket support for telemetry hub (FR-016)
- Automatic OpenAPI schema generation aligns with contract-first approach
- Type hints improve constitutional compliance validation
- Performance advantages for <100ms latency requirements
- ARM64 compatibility confirmed

**Alternatives considered**: 
- Flask: Simpler but requires additional libraries (Flask-SocketIO) for WebSocket support
- Django: Too heavyweight for embedded system constraints
- Custom async framework: Violates constitutional simplicity principles

### 2. Camera Integration: Picamera2+GStreamer Exclusive Service

**Decision**: Dedicated camera-stream.service with IPC distribution
**Rationale**:
- Constitutional requirement for exclusive camera ownership
- GStreamer provides efficient ARM64-optimized video processing
- IPC via Unix domain sockets enables multiple consumer services
- Supports both WebUI streaming and AI processing pipelines
- Picamera2 provides modern Pi Camera v2 support

**Alternatives considered**:
- Direct camera access per service: Violates constitutional resource coordination
- V4L2 direct access: Less efficient than Picamera2 on Pi hardware
- OpenCV VideoCapture: Conflicts with exclusive ownership requirement

### 3. AI Acceleration Libraries (ARM64 Compatible)

**Decision**: Constitutional hierarchy implementation
**Rationale**:
- TensorFlow Lite: ARM64 native, CPU fallback, constitutional compliance
- OpenCV-DNN: ARM64 optimized, multiple backend support
- Coral USB isolation in venv-coral maintains package separation
- Hailo HAT optional support without RoboHAT conflicts
- Graceful degradation path: Coral → Hailo → CPU

**Alternatives considered**:
- ONNX Runtime: Limited ARM64 acceleration options
- PyTorch Mobile: Larger memory footprint, less Pi-optimized
- Custom inference: Violates constitutional technology stack requirements

### 4. Systemd Service Coordination Patterns

**Decision**: Service dependency chains with resource coordination
**Rationale**:
- camera-stream.service (exclusive camera owner)
- sensor-manager.service (I2C/UART coordination)
- navigation.service (depends on sensor-manager)
- webui-backend.service (depends on camera-stream, sensor-manager)
- webui-frontend.service (static file serving)
- Unix domain sockets for IPC between services
- systemd socket activation for service coordination

**Alternatives considered**:
- Monolithic service: Violates constitutional resource coordination
- Docker containers: Adds complexity, constitutional simplicity violation
- Manual process management: Unreliable, no automatic restart

### 5. Retro 1980s WebUI Framework

**Decision**: Vue.js 3 with custom retro CSS framework
**Rationale**:
- Vue.js provides reactive components for real-time telemetry
- Lightweight enough for Pi 4B graceful degradation
- Custom CSS enables authentic 1980s aesthetic (green/amber terminal colors)
- Component architecture supports 7 mandated pages
- WebSocket integration for telemetry streams
- ARM64 Node.js build process compatibility

**Alternatives considered**:
- React: Larger bundle size, more complex for simple retro UI
- Angular: Too heavyweight for embedded constraints
- Vanilla JavaScript: Insufficient for complex state management
- Server-side rendering: Increases backend complexity unnecessarily

### 6. Hardware Abstraction Layer Design

**Decision**: Constitutional hardware compliance abstraction
**Rationale**:
- INA3221 wrapper enforcing constitutional channel assignments
- GPS abstraction supporting ZED-F9P USB and Neo-8M UART modes
- Motor control abstraction for RoboHAT→Cytron vs L298N fallback
- Hardware detection with graceful degradation
- SIM_MODE=1 complete simulation for CI testing

**Alternatives considered**:
- Direct hardware access: Violates coordination principles
- HAL-over-HAL abstraction: Unnecessary complexity
- Hardware-agnostic design: Conflicts with constitutional Pi exclusivity

### 7. Data Persistence Strategy

**Decision**: SQLite + JSON configuration files
**Rationale**:
- SQLite handles operational data, telemetry history, user sessions
- JSON files for system configuration (human-readable, git-friendly)
- No external database dependencies (constitutional simplicity)
- Atomic writes for configuration integrity
- Backup/migration support via file copies

**Alternatives considered**:
- PostgreSQL: Violates embedded system constraints
- Pure file-based: Insufficient for telemetry queries and relationships
- Redis: Unnecessary complexity, additional daemon

### 8. Authentication & Security Model

**Decision**: Single shared operator credential with session tokens
**Rationale**:
- Constitutional requirement for shared operator credential
- JWT tokens for WebUI session management
- Authentication gates for manual control, exports, configuration
- Audit logging for all privileged operations
- No external auth providers (constitutional simplicity)

**Alternatives considered**:
- Multi-user system: Conflicts with constitutional single operator model
- No authentication: Violates safety requirements for manual control
- OAuth integration: Unnecessary complexity, external dependencies

## Constitutional Compliance Validation

All research decisions align with constitutional requirements:
- ✅ Platform Exclusivity: ARM64-compatible libraries only
- ✅ Package Isolation: AI acceleration properly isolated
- ✅ Hardware Resource Coordination: Exclusive ownership patterns
- ✅ Technology Stack Requirements: Approved technologies only
- ✅ Development Workflow: Test-first approach supported

## Next Phase Dependencies

Phase 1 design work can proceed with:
- FastAPI backend framework selected
- Vue.js frontend framework selected  
- Service coordination patterns defined
- Hardware abstraction approach established
- Data persistence strategy confirmed
