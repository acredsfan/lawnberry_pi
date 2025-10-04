# Phase 0: Research & Technology Decisions

**Feature**: Complete Engineering Plan Phases 0-7 Implementation  
**Date**: 2025-10-02  
**Status**: Complete

## Overview
This document consolidates research findings and technology decisions for implementing the missing Engineering Plan phases. The feature builds upon existing Phase 5 (Web UI) and partial Phase 1-3 implementations to complete the full autonomous mowing system architecture.

---

## Research Areas

### 1. Message Bus Architecture (Phase 1)

**Decision**: Two-tier pub/sub message bus with Redis Streams backend

**Rationale**:
- Redis Streams provides ordered, persistent message delivery with consumer groups
- Supports two-tier model: persistent critical messages (safety events, E-stop, geofence violations) + best-effort telemetry (sensor readings, position updates)
- <10ms p99 latency achievable with local Redis instance on Pi
- Native Python support via `redis-py` with async support for FastAPI integration
- Built-in message acknowledgment and replay for service recovery (FR-008c requirement)
- Lightweight memory footprint suitable for Pi 5/4B hardware

**Alternatives Considered**:
- **RabbitMQ**: Heavier memory footprint (~100MB idle), overkill for single-node deployment, harder ARM64 build
- **MQTT (mosquitto)**: Best-effort only, no native persistence for critical messages, would require separate durable queue
- **ZeroMQ**: No built-in persistence, would require custom disk-backed queue implementation for safety-critical messages
- **Custom file-based queue**: Simpler but lacks atomic operations, harder to achieve <10ms latency target

**Implementation Notes**:
- Safety-critical topics (e.g., `safety.estop`, `safety.interlock`, `nav.geofence_violation`) use Redis consumer groups with acknowledgment
- Telemetry topics (e.g., `sensor.gps`, `sensor.imu`, `state.position`) use fire-and-forget pub/sub
- Message TTL: safety messages retained 24h, telemetry messages 1h
- Dead letter queue for failed message processing after 3 retries

### 2. Driver Registry & Lifecycle Management (Phase 1)

**Decision**: Plugin-based driver registry with abstract base class and asyncio lifecycle

**Rationale**:
- `HardwareDriver` ABC defines standard interface: `async def init()`, `async def start()`, `async def stop()`, `async def health_check()`
- Drivers loaded dynamically from `backend/src/drivers/` based on `config/hardware.yaml` declarations
- Simulation mode (SIM_MODE=1) swaps real drivers for mock implementations without code changes
- Python's `importlib` + `pkgutil` provide robust plugin discovery
- Asyncio lifecycle ensures clean startup/shutdown with resource cleanup
- Health check endpoints support constitutional observability requirements

**Alternatives Considered**:
- **Static imports**: No dynamic loading, breaks simulation mode, requires code changes for hardware substitution
- **Microservices per driver**: Over-engineered for single Pi, higher latency, complex coordination
- **Threading model**: Python GIL limits true parallelism, asyncio better for I/O-bound hardware operations

**Implementation Notes**:
- `DriverRegistry` singleton manages driver instances, publishes health to message bus every 5s
- Mock drivers include realistic latency simulation and failure injection for testing
- Driver dependencies declared in hardware.yaml: `requires: [gpio, i2c-1]` for resource coordination

### 3. GPIO E-stop Handler (Phase 2)

**Decision**: `lgpio` library with asyncio event loop integration for <100ms latency

**Rationale**:
- `lgpio` is modern Raspberry Pi GPIO library replacing deprecated RPi.GPIO
- Native support for Pi 5 GPIO (40-pin header compatible with Pi 4B)
- Alert callbacks with microsecond precision timestamps
- Asyncio integration via `add_reader()` for non-blocking event handling
- Constitutional <100ms E-stop latency achievable with interrupt-driven design
- No kernel module compilation required (unlike some alternatives)

**Alternatives Considered**:
- **RPi.GPIO**: Deprecated, not recommended for Pi 5, lacks asyncio integration
- **gpiod (libgpiod)**: More complex C library, Python bindings available but less documented
- **wiringPi**: Unmaintained, compatibility issues with Pi 5

**Implementation Notes**:
- E-stop button wired to GPIO 17 (BCM), pull-up resistor, active-low (pressed = LOW)
- Interrupt on falling edge triggers safety coordinator service
- Safety coordinator broadcasts `safety.estop` message and calls motor controller emergency stop API
- Debouncing: 50ms window to prevent bounce-induced retriggering
- Recovery requires operator acknowledgment per FR-020 (web UI button or CLI `--force` flag)

### 4. Watchdog Daemon (Phase 2)

**Decision**: Systemd watchdog integration + custom Python watchdog service

**Rationale**:
- Systemd provides hardware watchdog timer interface (`/dev/watchdog`) and service monitoring
- Custom Python `watchdog-daemon` service enforces heartbeat for safety-critical services
- Motor control service must send heartbeat every <1000ms or watchdog triggers emergency stop
- Constitutional requirement: automatic motor stop on timeout (FR-015)
- Systemd's `WatchdogSec=` configuration enables automatic service restart on failure
- Integrates with existing systemd service architecture

**Alternatives Considered**:
- **Hardware watchdog only**: No application-level control, requires kernel watchdog driver setup
- **Manual threading timer**: Error-prone, less robust than systemd integration
- **Third-party watchdog library**: Adds dependency, systemd native is simpler

**Implementation Notes**:
- Motor control service sends `sd_notify(WATCHDOG=1)` every 500ms
- Watchdog daemon monitors heartbeat messages on `watchdog.heartbeat` topic
- Timeout triggers `safety.watchdog_timeout` message and emergency stop API call
- Systemd unit: `WatchdogSec=2`, `Restart=on-watchdog`, `RestartSec=5s`

### 5. Drive vs Blade Control Split (Phase 2)

**Decision**: Split control paths — Drive via RoboHAT RP2040 UART (pyserial-asyncio), Blade via IBT-4 H-Bridge on Pi GPIO 24/25

**Rationale**:
- Drive motors require low-latency, synchronized PWM; RoboHAT RP2040 exposes UART on Pi GPIO 14/15 (TX/RX) to Cytron MDDRC10 and is suited for closed-loop control and watchdog echo.
- Blade motor is a separate high-current path driven by IBT-4 H-Bridge; direct Pi GPIO control (IN1=GPIO 24, IN2=GPIO 25) simplifies wiring and avoids overloading the RoboHAT path.
- Binary protocol over UART is more efficient than JSON for drive commands (lower latency). Blade toggling over GPIO is immediate and integrates tightly with E-stop/tilt interlocks.
- Pyserial-asyncio provides non-blocking serial I/O for drive; lgpio/python-periphery provide fast GPIO toggling for blade.

**Alternatives Considered**:
- JSON over UART for drive: human-readable but slower parsing, higher bandwidth, more latency.
- I2C for drive: shared bus contention with sensors, clock stretching issues, less reliable for real-time motor control.
- SPI: Faster but requires additional GPIO pins; RoboHAT path does not expose SPI for drive; unnecessary for blade GPIO control.

**Implementation Notes**:
- Drive (RoboHAT): 115200 baud, 8N1; command timeout 50ms (retry once, then report failure). Safety interlocks validate before UART transmission (FR-017). Emergency stop command bypasses queues for <100ms latency.
- Blade (IBT-4): Use GPIO 24 (IN1) and GPIO 25 (IN2); default OFF. Implement safe enable/disable with direction control and braking behavior as needed. Ensure tilt cutoff <200ms by wiring interlocks to disable blade immediately and by honoring software interlocks.

### 6. Sensor Fusion Architecture (Phase 3)

**Decision**: Extended Kalman Filter (EKF) with sensor-specific Kalman instances

**Rationale**:
- EKF handles nonlinear state transitions (heading, velocity) for robot navigation
- Separate filters: IMU (orientation), GPS (position), Odometry (velocity), Power (battery state)
- Sensor fusion combines estimates: GPS (1Hz) provides position corrections, IMU (10Hz) fills gaps, odometry validates motion
- `filterpy` library provides Python EKF implementation with scipy integration
- Time synchronization via NTP ensures consistent timestamps across sensors

**Alternatives Considered**:
- **Particle Filter**: More computationally expensive, overkill for deterministic sensors
- **Complementary Filter**: Simpler but less robust to sensor noise and drift
- **Raw sensor averaging**: No temporal smoothing, susceptible to outliers and latency jitter

**Implementation Notes**:
- State vector: `[x, y, heading, velocity, tilt_x, tilt_y, battery_voltage]`
- Measurement updates: GPS at 1Hz, IMU at 10Hz, ToF at 5Hz, Power at 1Hz
- Outlier rejection: Mahalanobis distance threshold for GPS jumps, IMU gyro integration reset on large errors
- Fused state published to `state.robot` topic every 100ms (10Hz) for navigation consumption

### 7. Geofence Enforcement Engine (Phase 4)

**Decision**: Polygon-based geofence with ray casting point-in-polygon algorithm

**Rationale**:
- Geofence defined as WGS84 lat/lon polygon in `config/geofence.json`
- Ray casting algorithm (Shapely library) provides fast point-in-polygon test
- Constitutional zero-tolerance policy: position check every GPS update (1Hz minimum)
- Buffer zone (0.5m) triggers warning before violation triggers emergency stop
- Shapely provides robust geometric operations (intersection, buffer, distance)

**Alternatives Considered**:
- **Circle-based**: Simpler but less flexible for irregular lawn shapes
- **Grid-based**: Memory-intensive for high-resolution fencing, slower lookups
- **Custom implementation**: Error-prone, Shapely is battle-tested

**Implementation Notes**:
- Geofence loaded at startup, validated for self-intersection and closure
- Real-time check on `state.robot` updates: if `contains(position)` == False → emergency stop
- Geofence modification during operation: broadcast `nav.geofence_updated`, pause autonomous until operator confirms boundary review
- Safety margin: 0.5m buffer zone triggers `nav.approaching_boundary` warning

### 8. Calendar Scheduling & Job State Machine (Phase 6)

**Decision**: APScheduler with cron triggers + FSM library for job state management

**Rationale**:
- APScheduler provides cron-like scheduling with asyncio support
- FSM (finite state machine) via `transitions` library enforces job state transitions
- Weather API integration: OpenWeatherMap (optional, fallback to cached + sensor data per FR-036a/b/c)
- Job state: IDLE → SCHEDULED → RUNNING → PAUSED → COMPLETED → FAILED (FR-039)
- Persistent job history stored in SQLite for audit trail

**Alternatives Considered**:
- **systemd timers**: Less flexible for weather-aware postponement, harder to query job status programmatically
- **Celery**: Over-engineered for single-node, requires separate broker (Redis already used for message bus but different use case)
- **Custom cron parser**: Reinventing the wheel, APScheduler is mature and well-tested

**Implementation Notes**:
- Cron triggers stored in `config/jobs.yaml`: `schedule: "0 8 * * 1-5"` (8am Mon-Fri)
- Weather check before job start: query OpenWeatherMap API (or use cached + BME280 sensor data)
- Postponement conditions: rain probability >30%, wind speed >15mph, battery <30%
- Job retry: max 3 attempts with exponential backoff (30min, 1h, 2h) before marking FAILED

### 9. Coverage Pattern Generation (Phase 6)

**Decision**: Parallel-line sweep with obstacle avoidance using A* pathfinding

**Rationale**:
- Parallel lines ensure complete coverage with configurable overlap (FR-037)
- Cutting width: 12" blade diameter, 10% overlap recommended (1.2" margin)
- A* pathfinding for waypoint-to-waypoint navigation avoiding ToF-detected obstacles
- Pattern stored as ordered waypoint list in `NavigationWaypoint` entities
- Real-time re-planning on obstacle detection or geofence approach

**Alternatives Considered**:
- **Random walk**: Inefficient, no coverage guarantee, multiple passes
- **Spiral pattern**: Harder to implement for irregular shapes, less efficient turns
- **Grid-based coverage**: Simpler but less flexible, wastes battery on turns

**Implementation Notes**:
- Pattern generator takes geofence polygon + starting position → returns waypoint list
- Waypoint spacing: 10ft straight segments, 90° turns with 5ft radius arcs
- Progress tracking: completed waypoints logged to job history for resume after interruption
- Pattern visualization in web UI: overlay on map with color-coded completion status

### 10. Fault Injection Framework (Phase 7)

**Decision**: Python decorators + mock overrides for systematic fault injection

**Rationale**:
- Test resilience without physical hardware failures
- Decorator `@inject_fault(type='sensor_dropout', probability=0.1)` wraps driver methods
- Fault types: sensor dropout, communication timeout, GPS signal loss, battery sag, motor stall
- Constitutional requirement: system must degrade gracefully (FR-042)
- Integration with pytest fixtures for reproducible fault scenarios

**Alternatives Considered**:
- **Hardware fault emulation**: Requires custom electronics, not portable across test environments
- **Network chaos engineering tools**: Overkill for embedded system, focuses on distributed failures
- **Manual fault simulation**: Not reproducible, hard to test edge cases systematically

**Implementation Notes**:
- Fault injection enabled via environment variable `FAULT_INJECTION=1` + config file
- Fault scenarios: `gps_dropout_30s`, `imu_bias_drift`, `battery_voltage_sag`, `motor_current_spike`
- Observability: faults logged to `fault_injection.log` with timestamps and stack traces
- Graceful degradation tests: GPS loss → MANUAL mode, IMU failure → blade disabled, battery critical → return-to-solar

### 11. 8-Hour Soak Testing (Phase 7)

**Decision**: Continuous integration with hardware-in-the-loop (HIL) test bed

**Rationale**:
- Constitutional requirement: 8+ hour operation without memory leaks or degradation (NFR-006)
- HIL setup: Pi 5 with mock drivers + simulated sensor data playback
- Memory profiling: `memory_profiler` + `pympler` track heap growth every 10 minutes
- Performance validation: message bus latency, WebSocket jitter, safety response time logged continuously
- Automated pass/fail criteria: memory growth <5MB/hour, zero safety margin violations, zero unhandled exceptions

**Alternatives Considered**:
- **Manual testing**: Not reproducible, hard to detect gradual degradation
- **Short-duration stress tests**: Miss memory leaks that manifest over hours
- **Cloud-based simulation**: Doesn't validate ARM64 platform-specific issues

**Implementation Notes**:
- Soak test runner: `pytest-timeout` + custom fixture for 8-hour duration
- Workload: simulated autonomous mowing job with GPS waypoints, sensor readings, emergency stops every hour
- Monitoring: Prometheus metrics scraped every 30s, Grafana dashboard for live visualization
- Failure injection: random faults every 2 hours to validate recovery mechanisms
- Pass criteria: all safety checks pass, memory stable, latency targets met, zero data corruption

---

## Technology Stack Summary

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Message Bus | Redis Streams | Two-tier persistence, <10ms latency, native Python support |
| Driver Registry | Python importlib + ABC | Dynamic loading, simulation mode, asyncio lifecycle |
| GPIO | lgpio | Pi 5 support, asyncio integration, <100ms E-stop latency |
| Watchdog | Systemd + custom daemon | Hardware watchdog integration, service monitoring |
| Motor Control | pyserial + binary protocol | Low-latency UART, safety validation, emergency stop bypass |
| Sensor Fusion | filterpy EKF | Nonlinear state estimation, sensor-specific filters, outlier rejection |
| Geofencing | Shapely | Polygon operations, ray casting, buffer zones, WGS84 coordinates |
| Scheduling | APScheduler + transitions | Cron triggers, FSM state management, weather integration |
| Coverage Patterns | A* pathfinding | Parallel-line sweep, obstacle avoidance, waypoint navigation |
| Fault Injection | Python decorators | Systematic fault testing, reproducible scenarios, graceful degradation |
| Soak Testing | pytest + HIL | 8-hour continuous validation, memory profiling, performance monitoring |

---

## Open Questions Resolved

1. **Message bus persistence model**: Two-tier (safety-critical persisted, telemetry best-effort) - RESOLVED via clarification session
2. **Authentication model**: Single operator with password, JWT session tokens - RESOLVED via clarification session  
3. **Weather API fallback**: Cache last forecast + real-time sensors (BME280) - RESOLVED via clarification session
4. **Setup script idempotency**: Idempotent by default + `--update` flag for explicit updates - RESOLVED via clarification session
5. **Operator interface**: Web UI + CLI + Mobile (responsive design) - RESOLVED via clarification session

---

## Dependencies Installation

All dependencies verified ARM64-compatible via piwheels or source build:

```bash
# Backend Python dependencies (add to requirements.txt)
redis>=5.0.0                  # Message bus
filterpy>=1.4.5               # Sensor fusion EKF
shapely>=2.0.0                # Geofence polygon operations
lgpio>=0.2.2.0                # GPIO for E-stop
pyserial-asyncio>=0.6         # UART for RoboHAT
smbus2>=0.4.2                 # I2C for sensors (ToF, IMU, power, env)
apscheduler>=3.10.0           # Calendar scheduling
transitions>=0.9.0            # Job state machine
memory_profiler>=0.61.0       # Soak test memory tracking
pympler>=1.0.1                # Memory profiling
requests>=2.31.0              # Weather API integration

# System packages (ansible provisioning)
# redis-server, python3-lgpio, python3-smbus, ntp, systemd
```

---

## Constitutional Compliance

**All research decisions comply with Constitution v2.0.0**:
- ✅ Platform Exclusivity: All technologies ARM64-compatible on Pi OS Bookworm
- ✅ Package Isolation: No pycoral/edgetpu dependencies
- ✅ Test-First: Mock drivers enable TDD without hardware
- ✅ Hardware Coordination: Driver registry enforces single-owner access
- ✅ Safety-First: E-stop <100ms, watchdog enforcement, interlock validation
- ✅ Modular Architecture: Phase-aligned module boundaries
- ✅ Navigation & Geofencing: Zero-tolerance enforcement via Shapely
- ✅ Scheduling & Autonomy: Weather-aware jobs, charge management
- ✅ Observability: Structured logs, Prometheus metrics, diagnostic CLIs

**No constitutional violations or complexity deviations required.**

---

## Next Steps

✅ Phase 0 Complete - Proceed to Phase 1: Design & Contracts
