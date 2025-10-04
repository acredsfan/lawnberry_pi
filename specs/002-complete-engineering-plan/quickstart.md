# Quickstart Validation Guide

**Feature**: Complete Engineering Plan Phases 0-7 Implementation  
**Purpose**: Step-by-step validation that all 7 phases are operational  
**Target**: Fresh Raspberry Pi 5 with Raspberry Pi OS Bookworm (64-bit)  
**Duration**: ~30 minutes (20min setup + 10min validation)

## Prerequisites

- Raspberry Pi 5 or Pi 4B with Raspberry Pi OS Bookworm (64-bit)
- Internet connection (for initial setup and dependencies)
- Physical E-stop button wired to GPIO (see hardware.yaml for pin assignment)
- Optional: GPS module, IMU, ToF sensors for full hardware validation (can run in SIM_MODE=1 without)

## Phase 0: Foundation & Tooling Validation

### Step 1: Automated Setup (<20 minutes)

```bash
# Clone repository
cd ~
git clone https://github.com/acredsfan/lawnberry_pi.git
cd lawnberry_pi

# Run automated setup script (idempotent)
./scripts/setup.sh

# Expected output:
# ✓ Python 3.11 installed
# ✓ uv package manager installed
# ✓ Backend dependencies installed
# ✓ systemd services enabled
# ✓ Configuration files initialized
# ✓ Setup complete in <20 minutes
```

**Validation**:
```bash
# Verify services running
systemctl status lawnberry-backend.service
systemctl status lawnberry-sensors.service
systemctl status lawnberry-health.service

# All should show "active (running)"

# Verify configuration loaded
curl http://localhost:8000/api/v1/config/hardware
# Should return hardware.yaml content as JSON

# Verify structured logs
tail -f /home/pi/lawnberry/logs/backend.log
# Should show JSON-formatted log entries with timestamps
```

**FR Coverage**: FR-001 (setup script), FR-003 (hardware config), FR-004 (safety limits), FR-005 (structured logs)

---

## Phase 1: Core Abstractions & IPC Validation

### Step 2: Message Bus & Driver Registry

```bash
# Check message bus operational
curl http://localhost:8000/api/v1/debug/bus/stats
# Expected response:
# {
#   "total_subscriptions": 0,
#   "messages_published_1m": 0,
#   "latency_p99_ms": 0.0,
#   "persistence_enabled": true
# }

# Start simulation mode (no hardware required)
export SIM_MODE=1
sudo systemctl restart lawnberry-backend

# Verify mock drivers loaded
curl http://localhost:8000/api/v1/drivers
# Expected response:
# {
#   "drivers": {
#     "gps": {"type": "MockGPSDriver", "status": "running", "health": "ok"},
#     "imu": {"type": "MockIMUDriver", "status": "running", "health": "ok"},
#     "tof_left": {"type": "MockToFDriver", "status": "running", "health": "ok"},
#     "tof_right": {"type": "MockToFDriver", "status": "running", "health": "ok"},
#     "power": {"type": "MockPowerDriver", "status": "running", "health": "ok"}
#   }
# }
```

**Validation - Message Bus Latency**:
```bash
# Publish test message and measure latency
time curl -X POST http://localhost:8000/api/v1/debug/bus/publish \
  -H "Content-Type: application/json" \
  -d '{"topic": "test/latency", "payload": {"timestamp": 1234567890}}'

# Should complete in <10ms
```

**FR Coverage**: FR-008 (pub/sub bus <10ms latency), FR-009 (driver registry), FR-010 (canonical robot state), FR-011 (simulation mode)

---

## Phase 2: Safety & Motor Control Validation

### Step 3: Emergency Stop & Watchdog

```bash
# Test E-stop API endpoint
curl -X POST http://localhost:8000/api/v1/safety/estop
# Expected response:
# {"status": "stopped", "timestamp": "2025-10-03T12:34:56.789Z", "latency_ms": 15}

# Verify E-stop logged
tail -n 20 /home/pi/lawnberry/logs/safety.log | grep estop
# Should show JSON log entry with timestamp

# Test watchdog timeout simulation
curl -X POST http://localhost:8000/api/v1/debug/safety/trigger-watchdog-timeout
# Should trigger emergency stop and log watchdog timeout

# Verify motors in OFF state on startup
curl http://localhost:8000/api/v1/motors/status
# Expected response:
# {"drive_left": "off", "drive_right": "off", "blade": "off", "authorized": false}
```

**Validation - Safety Interlock**:
```bash
# Attempt motor operation without authorization (should fail)
curl -X POST http://localhost:8000/api/v1/motors/drive \
  -H "Content-Type: application/json" \
  -d '{"throttle": 0.5, "turn": 0.0}'
# Expected response:
# {"error": "Motor operation requires operator authorization", "code": 403}

# Grant authorization
curl -X POST http://localhost:8000/api/v1/auth/authorize-motors \
  -H "Authorization: Bearer <token>" \
  -d '{"confirm": true}'

# Now drive command should succeed (simulation mode)
curl -X POST http://localhost:8000/api/v1/motors/drive \
  -H "Content-Type: application/json" \
  -d '{"throttle": 0.3, "turn": 0.1}'
# Expected response:
# {"status": "ok", "drive_left_pwm": 0.35, "drive_right_pwm": 0.25}
```

**Physical E-stop Test** (requires hardware):
```bash
# Monitor safety events
curl -N http://localhost:8000/api/v1/events/stream?topics=safety.estop

# Press physical E-stop button
# Should see event within 100ms:
# {"topic": "safety.estop", "timestamp": "...", "latency_ms": 87, "source": "gpio"}
```

**FR Coverage**: FR-014 (E-stop GPIO <100ms), FR-015 (watchdog timeout), FR-016 (OFF default), FR-017 (safety interlocks), FR-018 (manual teleop), FR-020 (E-stop recovery)

---

## Phase 3: Sensors & Extended Safety Validation

### Step 4: Sensor Integration & Fusion

```bash
# Check sensor health
curl http://localhost:8000/api/v1/sensors/health
# Expected response (simulation mode):
# {
#   "tof_left": {"status": "ok", "last_reading": "2025-10-03T12:35:00Z", "distance_m": 1.5},
#   "tof_right": {"status": "ok", "last_reading": "2025-10-03T12:35:00Z", "distance_m": 1.8},
#   "imu": {"status": "ok", "last_reading": "2025-10-03T12:35:00Z", "calibration": "good"},
#   "bme280": {"status": "ok", "last_reading": "2025-10-03T12:35:00Z", "temp_c": 22.5},
#   "power": {"status": "ok", "last_reading": "2025-10-03T12:35:00Z", "battery_v": 12.3}
# }

# Test sensor fusion state
curl http://localhost:8000/api/v1/fusion/state
# Expected response:
# {
#   "position": {"lat": 37.7749, "lon": -122.4194},
#   "velocity": {"x": 0.0, "y": 0.0},
#   "heading": 90.0,
#   "sources": ["gps", "imu", "odometry"],
#   "quality": "good"
# }

# CLI sensor diagnostics
python -m backend.cli.sensor_test --live
# Should display live sensor readings table:
# Sensor       Value                 Status    Last Update
# --------------------------------------------------------
# GPS          37.7749, -122.4194    OK        0.5s ago
# IMU          Roll: 0.1° Pitch: 0.2° Yaw: 90.0°  OK        0.1s ago
# ToF (L)      1.5m                  OK        0.2s ago
# ToF (R)      1.8m                  OK        0.2s ago
# BME280       22.5°C 45% 1013hPa    OK        1.0s ago
# Power        12.3V 2.1A            OK        1.0s ago
```

**Tilt Safety Test** (simulation):
```bash
# Trigger simulated tilt event
curl -X POST http://localhost:8000/api/v1/debug/sensors/inject-tilt \
  -H "Content-Type: application/json" \
  -d '{"roll_deg": 35.0, "pitch_deg": 5.0}'

# Verify blade stopped within 200ms
curl http://localhost:8000/api/v1/motors/status
# Expected response:
# {"blade": "off", "interlock": "tilt_detected", "tilt_timestamp": "..."}
```

**FR Coverage**: FR-021 (ToF sensors), FR-022 (IMU tilt <200ms), FR-023 (BME280), FR-024 (INA3221 power), FR-025 (sensor fusion), FR-026 (CLI diagnostics), FR-027 (safety interlocks)

---

## Phase 4: Navigation Core Validation

### Step 5: Geofence & Waypoint Navigation

```bash
# Define test geofence (rectangular boundary)
curl -X POST http://localhost:8000/api/v1/nav/geofence \
  -H "Content-Type: application/json" \
  -d '{
    "boundary": [
      {"lat": 37.7750, "lon": -122.4195},
      {"lat": 37.7750, "lon": -122.4190},
      {"lat": 37.7745, "lon": -122.4190},
      {"lat": 37.7745, "lon": -122.4195}
    ]
  }'

# Check current position against geofence
curl http://localhost:8000/api/v1/nav/geofence/status
# Expected response:
# {"status": "green_zone", "distance_to_boundary_m": 15.3}

# Simulate geofence violation
curl -X POST http://localhost:8000/api/v1/debug/gps/inject-position \
  -H "Content-Type: application/json" \
  -d '{"lat": 37.7751, "lon": -122.4192}'

# Verify emergency stop triggered
curl http://localhost:8000/api/v1/nav/geofence/status
# Expected response:
# {"status": "violation", "action": "emergency_stop", "timestamp": "..."}

# Test waypoint navigation
curl -X POST http://localhost:8000/api/v1/nav/waypoints \
  -H "Content-Type: application/json" \
  -d '{
    "waypoints": [
      {"lat": 37.7748, "lon": -122.4193, "speed": 0.5},
      {"lat": 37.7747, "lon": -122.4192, "speed": 0.5}
    ]
  }'

# Start navigation (autonomous mode)
curl -X POST http://localhost:8000/api/v1/nav/start-autonomous
# Monitor navigation state
curl -N http://localhost:8000/api/v1/events/stream?topics=nav.waypoint
```

**FR Coverage**: FR-028 (GPS integration), FR-029 (odometry), FR-030 (geofence zero-tolerance), FR-031 (waypoint navigation), FR-032 (navigation modes), FR-033 (GPS degradation), FR-034 (navigation state API)

---

## Phase 6: Scheduling & Autonomy Validation

### Step 6: Job Scheduling & Weather Integration

```bash
# Create scheduled job
curl -X POST http://localhost:8000/api/v1/scheduler/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "daily_mow",
    "schedule": "0 9 * * *",
    "zone": "front_lawn",
    "weather_check": true
  }'

# Check weather suitability
curl http://localhost:8000/api/v1/scheduler/weather
# Expected response:
# {
#   "suitable": true,
#   "source": "cache",
#   "forecast": {"condition": "clear", "temp_c": 22, "humidity_pct": 45},
#   "cache_age_hours": 2.3
# }

# Simulate weather API unavailable
curl -X POST http://localhost:8000/api/v1/debug/weather/disable-api

# Re-check weather (should fall back to sensors)
curl http://localhost:8000/api/v1/scheduler/weather
# Expected response:
# {
#   "suitable": true,
#   "source": "sensors",
#   "sensor_data": {"temp_c": 22.5, "humidity_pct": 45, "pressure_hpa": 1013}
# }

# Test coverage pattern generation
curl -X POST http://localhost:8000/api/v1/scheduler/generate-pattern \
  -H "Content-Type: application/json" \
  -d '{
    "zone": "front_lawn",
    "geofence": [...],
    "cutting_width_m": 0.3,
    "overlap_m": 0.03
  }'
# Should return parallel-line coverage pattern

# Check job state machine
curl http://localhost:8000/api/v1/scheduler/jobs/daily_mow
# Expected response:
# {"state": "scheduled", "next_run": "2025-10-04T09:00:00Z", "last_run": null}
```

**FR Coverage**: FR-035 (calendar scheduling), FR-036 (weather postponement), FR-036a/b/c (cache+sensors fallback), FR-037 (coverage patterns), FR-038 (solar charge monitoring), FR-039 (job state machine), FR-040 (safety validation), FR-041 (return-to-home)

---

## Phase 7: Reliability & Testing Validation

### Step 7: Fault Injection & Soak Testing

```bash
# Enable fault injection
export FAULT_INJECT=sensor_timeout,gps_loss
sudo systemctl restart lawnberry-backend

# Trigger sensor timeout fault
curl http://localhost:8000/api/v1/sensors/health
# Should show degraded health with timeout errors

# Verify graceful degradation
curl http://localhost:8000/api/v1/fusion/state
# Should still return position estimate with reduced quality

# Generate log bundle
curl -X POST http://localhost:8000/api/v1/debug/generate-log-bundle
# Expected response:
# {"bundle_path": "/home/pi/lawnberry/logs/bundle_20251003_123456.tar.gz"}

# Verify bundle contents
tar -tzf /home/pi/lawnberry/logs/bundle_20251003_123456.tar.gz
# Should contain:
# - backend.log
# - safety.log
# - sensors.log
# - state_snapshot.json
# - telemetry_last_1h.jsonl

# Run quick soak test (5 minutes for validation, full 8-hour in CI)
pytest tests/soak/test_quick_soak.py -v
# Expected output:
# tests/soak/test_quick_soak.py::test_5min_continuous_operation PASSED
# Metrics: Memory growth <1%, Bus latency p99: 8.3ms, Safety events: 0

# View dashboards (optional)
# Open browser to http://localhost:8000/metrics
# Should display:
# - Battery health: 12.3V, 2.1A, 87% SOC
# - Coverage progress: 0% (no active job)
# - Safety event history: 0 events
# - Uptime: 15 minutes
```

**FR Coverage**: FR-042 (fault injection), FR-043 (8-hour soak test), FR-044 (log bundles), FR-045 (dashboards), FR-046 (operational docs), FR-047 (acceptance criteria)

---

## Final Validation: Complete System Test

### Step 8: End-to-End Autonomous Operation (Simulation)

```bash
# Ensure simulation mode
export SIM_MODE=1

# Create complete test scenario
curl -X POST http://localhost:8000/api/v1/test/e2e-scenario \
  -H "Content-Type: application/json" \
  -d '{
    "geofence": [...],
    "waypoints": [...],
    "duration_minutes": 5,
    "enable_weather": true,
    "enable_charge_management": true
  }'

# Monitor test execution
curl -N http://localhost:8000/api/v1/events/stream?topics=test.*

# Expected event sequence:
# 1. test.scenario.start
# 2. safety.authorization.granted
# 3. nav.geofence.validated
# 4. nav.waypoint.reached (multiple)
# 5. scheduler.weather.checked
# 6. power.battery.check
# 7. test.scenario.complete

# Verify test results
curl http://localhost:8000/api/v1/test/e2e-results
# Expected response:
# {
#   "status": "passed",
#   "duration_s": 300,
#   "safety_events": 0,
#   "geofence_violations": 0,
#   "waypoints_reached": 8,
#   "average_bus_latency_ms": 7.2,
#   "max_estop_latency_ms": 89
# }
```

---

## Success Criteria

All phases validated when:

- ✅ **Phase 0**: Setup completes in <20 minutes, services running, logs structured
- ✅ **Phase 1**: Message bus <10ms p99 latency, drivers loaded per config, simulation mode works
- ✅ **Phase 2**: E-stop <100ms, watchdog enforced, motors OFF by default, interlocks operational
- ✅ **Phase 3**: All sensors readable, fusion provides position, CLI diagnostics work, tilt triggers <200ms
- ✅ **Phase 4**: Geofence enforced (zero violations), waypoint navigation reaches targets, GPS degradation → MANUAL
- ✅ **Phase 6**: Jobs schedulable, weather checks work (API + sensor fallback), coverage patterns generated
- ✅ **Phase 7**: Fault injection works, log bundles complete, quick soak test passes

---

## Troubleshooting

**Setup fails with ARM64 dependency error**:
```bash
# Verify piwheels in pip config
cat ~/.pip/pip.conf
# Should contain:
# [global]
# extra-index-url=https://www.piwheels.org/simple

# Retry setup
./scripts/setup.sh --update
```

**Services not starting**:
```bash
# Check service logs
sudo journalctl -u lawnberry-backend.service -n 50

# Verify Python environment
source backend/.venv/bin/activate
python --version  # Should be 3.11.x
```

**Message bus latency high**:
```bash
# Check Redis memory usage
redis-cli INFO memory

# Clear old messages
redis-cli XTRIM safety.estop MAXLEN ~ 1000
```

**GPS not acquiring fix** (hardware mode):
```bash
# Check GPS device
ls -l /dev/ttyUSB0  # or /dev/serial0 for UART

# Enable NTRIP if available
curl -X POST http://localhost:8000/api/v1/gps/ntrip/enable \
  -d '{"server": "rtk.server.com", "mountpoint": "...", "username": "...", "password": "..."}'
```

---

## Next Steps

After successful quickstart validation:

1. **Hardware Integration**: Run `./scripts/setup.sh` on Pi with physical sensors, verify all hardware tests pass
2. **Field Calibration**: Use CLI tools to calibrate IMU, set geofence boundaries, test E-stop button
3. **Production Configuration**: Update `config/limits.yaml` with site-specific thresholds, configure weather API keys
4. **Monitoring Setup**: Enable Prometheus scraping on `/metrics`, set up alerts for safety events
5. **Documentation Review**: Read `docs/OPERATIONS.md` for operational procedures, recovery steps, maintenance schedules

**Full System Ready**: When all quickstart validations pass + physical hardware calibrated + geofence defined + operator trained on E-stop recovery
