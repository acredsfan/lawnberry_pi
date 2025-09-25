# Quickstart: LawnBerry Pi v2 Unified System

## Prerequisites
- Raspberry Pi 5 (4-16GB) or Pi 4B (4-8GB) with Raspberry Pi OS Bookworm (64-bit)
- Python 3.11.x installed and active
- Hardware components per `spec/hardware.yaml` (minimum: IMU, power monitoring, ToF sensors)
- Constitutional compliance verified (`constitution.md` v1.3.0+)
- Optional API keys (set as environment variables): `OPENWEATHERMAP_API_KEY` for forecast features; `GOOGLE_MAPS_API_KEY` for Google Maps (OSM fallback will be used if absent)

## Quick Setup (Development)

### 1. Environment Setup
```bash
# Verify platform compliance
python3 --version  # Must be 3.11.x
uname -a          # Must show ARM64 and Raspberry Pi OS

# Clone and setup
git clone <repository_url>
cd lawnberry-pi-v2
python3 -m venv venv
source venv/bin/activate
pip install uv
uv sync
```

### 2. Constitutional Package Isolation
```bash
# Create isolated Coral environment (if using Coral USB)
python3 -m venv venv-coral
source venv-coral/bin/activate
pip install pycoral tflite-runtime
deactivate

# Verify main environment isolation
source venv/bin/activate
python -c "import pycoral" 2>&1 | grep "No module named" || echo "VIOLATION: pycoral in main env"
```

### 3. Hardware Simulation Mode
```bash
# Enable simulation for development/CI
export SIM_MODE=1

# Verify simulation coverage
python -m pytest tests/simulation/ -v
```

### 4. Service Dependencies
```bash
# Install systemd service files (development)
sudo ln -sf $PWD/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# Start core services in dependency order
sudo systemctl start camera-stream.service
sudo systemctl start sensor-manager.service  
sudo systemctl start navigation.service
sudo systemctl start webui-backend.service
```

### 5. WebUI Development Server
```bash
# Backend (FastAPI)
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (Vue.js) - separate terminal
cd frontend
npm install
npm run dev
```

Notes:
- If `GOOGLE_MAPS_API_KEY` is not set, the frontend will automatically use OpenStreetMap with an offline-friendly mode for development (limited tiles/caching).
- To enable weather features (planning advisories), export `OPENWEATHERMAP_API_KEY` before starting the backend.

## Validation Tests

### Contract Test Validation
```bash
# REST API contract tests (must fail initially)
python -m pytest tests/contract/test_rest_api.py -v
# Expected: All tests FAIL (no implementation yet)

# WebSocket contract tests (must fail initially)  
python -m pytest tests/contract/test_websocket_api.py -v
# Expected: All tests FAIL (no implementation yet)
```

### Integration Test Scenarios
```bash
# Core autonomous operation scenarios
python -m pytest tests/integration/test_autonomous_operation.py -v

# WebUI experience scenarios
python -m pytest tests/integration/test_webui_experience.py -v

# Hardware platform compliance scenarios
python -m pytest tests/integration/test_hardware_compliance.py -v
```

### Constitutional Compliance Validation
```bash
# Platform exclusivity check
python -c "import platform; assert 'aarch64' in platform.machine()"
python -c "import sys; assert sys.version_info[:2] == (3, 11)"

# Package isolation check
python -c "import pycoral" 2>&1 | grep "No module named" || exit 1

# Hardware resource coordination check
systemctl is-active camera-stream.service | grep active || exit 1
```

## User Scenario Validation

### Scenario 1: Dashboard Live Telemetry
1. Open browser to `http://localhost:3000/dashboard`
2. Verify real-time telemetry updates at 5Hz default frequency
3. Check battery status, GPS position, sensor readings display
4. Confirm <100ms latency from sensor to WebUI display

### Scenario 2: Map Setup Zone Configuration  
1. Navigate to Map Setup page
2. Use polygon drawing tool to define yard boundaries
3. Verify real-time validation and navigation parameter updates
4. Confirm Google Maps integration (cost-optimized) with LawnBerry pin asset

### Scenario 3: Manual Control Authentication
1. Access Manual Control page (should require authentication)
2. Authenticate with shared operator credential
3. Issue direct drive commands with safety indicators
4. Verify emergency stop access and audit logging

### Scenario 4: AI Training Dataset Export
1. Navigate to AI Training page
2. Review captured imagery and annotation workflow
3. Export dataset in both COCO JSON and YOLO TXT formats
4. Verify quality validation and export job management

## Performance Validation

### WebUI Latency Testing
```bash
# Measure telemetry latency
python scripts/test_latency.py --target 100ms --samples 1000

# Verify graceful degradation Pi 4B vs Pi 5
python scripts/test_performance_degradation.py
 
# Validate dead-reckoning bounds during GPS loss (P95 drift ≤1.0m/10s)
python scripts/test_dead_reckoning.py --outage-sec 60 --max-drift-per-10s 1.0
```

### Real-time Telemetry Load Testing
```bash
# Test WebSocket hub with multiple clients
python scripts/test_websocket_load.py --clients 10 --cadence 10Hz

# Verify topic-based routing and graceful disconnection
python scripts/test_websocket_resilience.py
```

## Troubleshooting

### Constitutional Compliance Issues
- **Package Isolation Violation**: Check `pip list` in main env for banned packages
- **Platform Exclusivity**: Verify ARM64 and Python 3.11.x with system checks
- **Resource Coordination**: Check `systemctl status camera-stream.service`

### Hardware Integration Issues  
- **Sensor Bus Conflicts**: Check I2C/UART address conflicts in `dmesg`
- **GPS Mode Fallback**: Verify ZED-F9P USB vs Neo-8M UART detection
- **AI Acceleration**: Test Coral USB → Hailo HAT → CPU fallback hierarchy

### WebUI Performance Issues
- **Latency >100ms**: Check network, reduce telemetry cadence, verify Pi model
- **Graceful Degradation**: Test Pi 4B with reduced feature set
- **Retro Aesthetic**: Verify 1980s branding assets load correctly

## Next Steps

After successful quickstart validation:

1. **Run /tasks command** to generate detailed implementation tasks
2. **Execute Phase 3-4** following constitutional TDD principles  
3. **Validate Phase 5** with full hardware-in-the-loop testing
4. **Deploy systemd services** for production autonomous operation

## Constitutional Compliance Checklist

- [x] **Platform Exclusivity**: Raspberry Pi OS Bookworm 64-bit, Python 3.11.x
- [x] **Package Isolation**: pycoral/edgetpu banned from main env, Coral isolated
- [x] **Test-First Development**: Contract tests fail before implementation
- [x] **Hardware Resource Coordination**: Camera service exclusive ownership
- [x] **Constitutional Hardware Compliance**: INA3221 channels, GPS options validated
- [x] **Technology Stack Requirements**: FastAPI, Vue.js, approved technologies only
- [x] **Development Workflow**: Documentation updates, agent journaling, ARM64 validation

---
*Generated from Constitution v1.3.0 - See `/.specify/memory/constitution.md`*
