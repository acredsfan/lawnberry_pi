# LawnBerryPi Copilot Instructions

## Platform Requirements

**Target Platform**: Raspberry Pi OS Lite (aarch64) Bookworm - ALL code must be compatible with this environment.

**Critical Agent Guidelines**:
- **NEVER run commands without timeouts** - Agents cannot use Ctrl+C to exit hanging processes
- **Always use `timeout` command**: `timeout 30s python script.py` or implement internal timeouts
- **Clean workspace obsessively** - Delete ALL temporary test files, debug scripts, and verification files
- **Never commit sensitive data** - Check for API keys, passwords, or personal information before any commits
- **NEVER use workarounds or shortcuts** - Always make sure fixes are complete and ensure intended design/functionality.
- **Always keep user and developer documentation up-to-date** - Update README, API docs, and inline comments with every change.
- **Double and Triple check all changes** - Review code thoroughly before committing.
- **Ensure all changes made are also integrated into the installation script** - Update installation scripts and deployment configurations accordingly.
- **Use docs/SENSOR-LIBRARY-EXAMPLE-LINKS.md to understand the sensor library structure** - Follow the example links to ensure proper integration of new and existing sensors.
- **Use the `#server-memory` toolset for persistent context management** - Always read the current graph first, prune aggressively, and never store sensitive data.
- **Use the '#sequential-thinking' toolset for managing state across multiple steps** - This helps in maintaining context and ensuring coherent interactions.

## Agent venv enforcement (MANDATORY)

Agents and automation MUST verify and use the repository virtual environments before running any Python commands or tooling. This prevents ABI mismatches and missing native drivers on Raspberry Pi (Bookworm) and ensures consistent, repeatable runs.

Required checks and behaviour for agents:
- Always read `/home/pi/lawnberry/.github/copilot-instructions.md` and the `VirtualEnvs` server-memory entity before running Python commands to determine which venv to use.
- Verify the chosen venv exists before running commands. Example checks:
    - `test -f venv/bin/activate || echo "venv missing"`
    - `test -x venv/bin/python || echo "venv python missing or not executable"`
- Run commands inside the venv using one of these patterns (prefer these over system `python3`):
    - Non-interactive: `venv/bin/python -m module_or_script` (preferred)
    - Interactive / long debugging: `source venv/bin/activate && python -m module_or_script`
- For Coral/TPU tasks that require Python 3.9 runtimes use `venv_coral_pyenv/bin/python` (do NOT mix runtimes in a single process).
- If a venv check fails, do NOT proceed with system `python3` unless the user explicitly approves a fallback. Log the venv failure and recommended remediation.
- Always combine venv execution with project timeout and isolation rules (e.g., `timeout 60s venv/bin/python -m ...` or `systemd-run --user --scope --property=TimeoutStopSec=30s venv/bin/python -m ...`).

Example quick verification snippet agents should run before Python work:
```bash
# prefer non-interactive execution
test -f venv/bin/activate || (echo "ERROR: venv missing"; exit 2)
venv/bin/python -V || (echo "ERROR: venv python not runnable"; exit 2)
venv/bin/python -c "import pkgutil; print('FOUND' if pkgutil.find_loader('adafruit_vl53l0x') else 'MISSING')"
```

These rules are mandatory for agent runs and automated scripts. If the venv layout differs on a target device, prefer `venv` for main services and `venv_coral_pyenv` for Coral workloads; document any deviations in the `VirtualEnvs` server-memory entity.

### server-memory Usage (Persistent Context Management)
**Always** Use the `#server-memory` toolset to maintain persistent context across sessions. This allows agents to store and retrieve observations, entities, and relationships without losing critical information.

Core rules:
1. Always read current graph first: `mcp_server-memory_read_graph`.
2. Add concise observations grouped by stable entity names (e.g., `WebUI`, `HardwareInterface`, `DeploymentPipeline`).
3. Prune aggressively—delete outdated observations or entire entities when superseded.
4. Never store secrets, credentials, tokens, personal data, or transient debug output.
5. Before large architectural or refactor steps, re-sync by reading the graph again.

Quick reference:
- Read graph: `mcp_server-memory_read_graph`
- Create entities: `mcp_server-memory_create_entities`
- Add observations: `mcp_server-memory_add_observations`
- Relate entities: `mcp_server-memory_create_relations`
- Delete observations: `mcp_server-memory_delete_observations`
- Delete entities: `mcp_server-memory_delete_entities`

If memory pollution suspected (irrelevant or cross-project data), clear affected entities immediately to prevent decision drift.

## Architecture Overview

LawnBerryPi is a plugin-based autonomous lawn mower system with layered architecture:

- **Hardware Layer** (`src/hardware/`): Plugin-based abstraction with I2C, Serial, GPIO, Camera managers coordinated by `HardwareInterface`
- **Core Services** (`src/`): Independent modules for navigation, safety, vision, power management, weather integration
- **Web API** (`src/web_api/`): FastAPI backend with WebSocket real-time communication and MQTT bridge
- **Configuration** (`config/`): YAML-driven hardware and system configuration with validation

## Critical Patterns

### Hardware Plugin System
All hardware components use the plugin architecture in `src/hardware/plugin_system.py`:

```python
class CustomSensorPlugin(HardwarePlugin):
    @property
    def plugin_type(self) -> str:
        return "i2c_sensor"  # or "serial_device", "gpio_device"
    
    @property 
    def required_managers(self) -> List[str]:
        return ["i2c", "gpio"]  # Dependencies on hardware managers
    
    async def read_data(self) -> SensorReading:
        # Must return standardized SensorReading from data_structures.py
```

Register plugins in `config/hardware.yaml` under `plugins` section with `name`, `enabled`, and `parameters`.

### Data Structure Standards
All sensor data uses `SensorReading` from `src/hardware/data_structures.py`:
- `timestamp`, `sensor_id`, `value`, `unit`, `quality` (0.0-1.0), `metadata`
- Specialized subclasses: `I2CDeviceReading`, `SerialDeviceReading`, `GPIOReading`

### Async Hardware Interface
Main coordination through `HardwareInterface` class:
- **Initialize**: `await hw.initialize()` - Sets up all managers and plugins
- **Read Data**: `await hw.get_all_sensor_data()` - Returns Dict[str, SensorReading]  
- **Device Control**: `await hw.send_robohat_command('pwm', 1500, 1600)` - Motor control
- **Health Monitoring**: `await hw.get_system_health()` - System-wide status

### Configuration Management
YAML configuration in `config/` directory:
- `hardware.yaml`: I2C addresses, GPIO pins, plugin definitions
- Hardware configuration loaded via `ConfigManager` with validation
- Plugin parameters passed through config to enable/disable features

## Development Workflows

### Testing Strategy - ALWAYS USE TIMEOUTS
Use pytest markers for test categorization with mandatory timeouts:
```bash
# Hardware-in-the-loop tests with timeout protection
timeout 60s python -m pytest -m "hardware" tests/

# Integration tests with mocked hardware - max 30s
timeout 30s python -m pytest -m "integration" tests/

# Safety-critical tests (100% coverage required) - max 45s
timeout 45s python -m pytest -m "safety" tests/

# Performance tests - ALWAYS timeout these as they can hang
timeout 120s python -m pytest -m "performance" tests/performance/
```

### Raspberry Pi OS Bookworm Compatibility
**CRITICAL**: All code must work on Pi OS Lite (aarch64) Bookworm:
```bash
# Use systemd-run for process isolation with timeouts
systemd-run --user --scope --property=TimeoutStopSec=30s python script.py

# For hardware initialization that might hang
timeout 60s python scripts/setup_dual_tof.py || echo "Hardware setup timed out"

# Always check Python version compatibility (3.11+)
python3 --version  # Must be 3.11+ for Bookworm
```

### ARM64/Raspberry Pi Compatibility Assessment (Summer 2025)
**BEFORE implementing any solution, consider ARM64 compatibility**:
- **Package Versions**: Use newest compatible versions, not oldest stable - balance security with compatibility
- **Binary Dependencies**: Many Node.js packages now have ARM64 binaries, but verify compatibility
- **Native Modules**: C++ extensions may need ARM64-specific builds or compilation flags
- **Version Selection Strategy**: Start with latest LTS/stable, step down incrementally if issues arise
- **Raspberry Pi 4/5 Support**: Modern ARM64 Cortex-A72/A76 supports most current software
- **Test Early**: Verify ARM64 compatibility immediately after package installation

### Installation and Setup
Primary installation via `scripts/install_lawnberry.sh`:
- **Hardware Detection**: Automatically scans I2C bus and detects connected devices
- **Configuration Generation**: Updates `config/hardware.yaml` based on detected hardware
- **Service Setup**: Creates systemd services with proper permissions
- **ToF Sensor Initialization**: Special handling for VL53L0X dual sensor setup with address conflicts

### Canonical Runtime vs Source Tree
The editable source repository (typically `/home/pi/lawnberry`) is synced to the immutable runtime directory `/opt/lawnberry` used by all systemd services. Services MUST NOT run directly from the source tree for security and consistency.

Fast deploy/update workflow:
```bash
# Minimal code + config sync (subset hashing enabled by default)
./scripts/install_lawnberry.sh --deploy-update

# With environment overrides:
FAST_DEPLOY_HASH=0 FAST_DEPLOY_DIST_MODE=minimal ./scripts/lawnberry-deploy.sh
```

Environment / mode flags (export before running deploy if needed):
- `FAST_DEPLOY_HASH=0` disables subset drift hashing (speeds large syncs)
- `FAST_DEPLOY_DIST_MODE=skip|minimal|full` controls web-ui dist syncing (default: minimal)
    - `skip`: do not sync any dist assets
    - `minimal`: sync only changed top-level files (index.html, manifest, sw.js, registerSW.js, workbox*, small static assets) and new hashed asset files
    - `full`: rsync entire `web-ui/dist/` with timeout protection
- `RSYNC_TIMEOUT_PER=<seconds>` adjust per-directory rsync timeout (default 40)

Guidelines:
- Always edit code in source tree, then fast deploy.
- Never hand-edit `/opt/lawnberry` (changes will be overwritten on next deploy).
- If drift detected, investigate uncommitted source modifications before forcing deploy.

Backup before major changes:
```bash
sudo tar -czf lawnberry-prechange-$(date +%Y%m%d).tar.gz /opt/lawnberry/config /var/lib/lawnberry
```

### Mandatory Workspace Cleanup Protocol
**BEFORE ANY COMMIT OR COMPLETION**:
```bash
# Delete ALL temporary test files
rm -f test_*.py setup_*.py verify_*.py debug_*.py
rm -f *.log *.tmp output_*.txt results_*.json

# Remove any files with sensitive data
grep -r "api_key\|password\|secret\|token" . --exclude-dir=.git --exclude="*.md" && echo "SENSITIVE DATA FOUND - CLEAN BEFORE COMMIT"

# Clean Python cache and temp files
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true

# Verify workspace is clean
git status --porcelain | grep -E "^\?\?" && echo "UNTRACKED FILES - REVIEW BEFORE COMMIT"
```

### Code Quality Standards
- **Formatting**: Black with 100-character line length
- **Type Hints**: Required for public APIs, relaxed for hardware libraries
- **Error Handling**: Custom exceptions in `hardware/exceptions.py` with proper async propagation
- **Logging**: Structured logging with per-component loggers
- **Timeout Enforcement**: All blocking operations MUST have timeouts
- **Version Selection**: Use newest compatible versions for security, test ARM64 compatibility immediately

### Hardware Testing with Timeout Protection
Key test files with timeout requirements:
- `tests/test_hardware_interface.py` - Main hardware interface tests (max 60s)
- `tests/performance/` - Performance benchmarks with asyncio (max 120s)
- `tests/automation/` - Comprehensive test automation suite (max 300s)

**Hardware Script Pattern** - Always implement internal timeouts:
```python
import asyncio
from asyncio import timeout

async def safe_hardware_operation():
    try:
        async with timeout(30.0):  # 30 second timeout
            result = await hardware_operation()
            return result
    except asyncio.TimeoutError:
        logger.error("Hardware operation timed out")
        return None
```

## Integration Points

### RoboHAT Communication
Motor control via serial protocol to RoboHAT controller:
```python
await hw.send_robohat_command('rc_disable')  # Take control
await hw.send_robohat_command('pwm', steer_us, throttle_us)  # 1000-2000μs
await hw.send_robohat_command('rc_enable')   # Return control
```

### Web API Integration
FastAPI backend with WebSocket real-time updates:
- **Routers**: Organized by domain (`sensors`, `navigation`, `power`, etc.)
- **MQTT Bridge**: Real-time pub/sub for sensor data and commands
- **Authentication**: JWT-based with role-based access control

### External Dependencies
- **Hardware Libraries**: Adafruit CircuitPython for I2C sensors, RPi.GPIO for pin control
- **Vision**: TensorFlow Lite with Coral TPU acceleration, OpenCV for image processing  
- **Navigation**: GPS RTK with custom boundary detection algorithms
- **Weather**: OpenWeather API integration for intelligent scheduling

## Common Tasks

### Adding New Sensor
1. Create plugin class extending `HardwarePlugin` in `src/hardware/plugins/`
2. Add configuration entry to `config/hardware.yaml`
3. Update `HardwareInterface` to load new plugin type
4. Add tests in `tests/test_hardware_interface.py`

### Debug Hardware Issues
1. Check I2C bus: `timeout 30s python -c "import asyncio; from src.hardware import HardwareInterface; asyncio.run(HardwareInterface().i2c_manager.scan_bus())"`
2. Review device health: `timeout 45s python -c "from src.hardware import create_hardware_interface; hw = create_hardware_interface(); asyncio.run(hw.get_system_health())"`
3. Enable debug logging: Set `logging_level: DEBUG` in config
4. Use hardware-specific test scripts with timeouts: `timeout 60s python test_dual_tof.py`

### Performance Optimization
- Monitor sensor read latency with `timeout 120s python -m pytest tests/performance/test_performance_benchmarks.py`
- Use concurrent sensor reads: `asyncio.gather(*[plugin.read_data() for plugin in plugins])`
- Cache sensor data with `_sensor_data_cache` and `_cache_lock` in HardwareInterface
- Profile with `--durations=10` pytest flag to identify slow tests

### Bookworm-Specific Hardware Commands
```bash
# I2C detection with timeout (agents cannot interrupt)
timeout 15s i2cdetect -y 1 || echo "I2C scan timed out"

# GPIO testing with systemd isolation
systemd-run --user --scope --property=TimeoutStopSec=30s python test_gpio.py

# Service status checking (non-hanging)
systemctl --user is-active lawnberry-api || echo "Service not running"
```

## Project-Specific Conventions

- **File Organization**: Each major component (hardware, navigation, safety) has dedicated subdirectory
- **Configuration**: Hardware-specific settings in YAML, not hardcoded in Python
- **Error Recovery**: Exponential backoff with jitter for communication retries
- **Resource Management**: Exclusive device access prevents I2C/serial bus conflicts
- **Health Monitoring**: Continuous background health checks with automatic recovery

## Virtual environments in this repository

The repository contains multiple Python virtual environments used for different runtime roles; document them here so agents and operators know which to use:

- `venv` (Python 3.11) — Primary runtime venv used for most services in `/opt/lawnberry` and for local development. This venv normally contains general-purpose packages (MQTT client, FastAPI, hardware drivers for I2C/GPIO where available) and is the default for running `src` services such as the sensor service unless another venv is explicitly required.

- `venv_coral_pyenv` (Python 3.9) — Coral / TPU venv. This venv contains `pycoral`, `tflite_runtime` (or an equivalent Coral runtime) and other Coral-specific packages; use this environment when running Coral-accelerated vision models (object detection inference). It is NOT the default for general services because it targets Python 3.9 and contains binary wheels compiled for TPU/Coral usage.

- `venv_coral` (possible alias) — If present, treat similarly to `venv_coral_pyenv` (Python 3.9). Confirm which coral venv is present on the device before running Coral-specific tasks.

- `venv_test_mqtt` (Python 3.11) — Lightweight test venv used in CI/quick-tests for MQTT tooling, local smoke tests, and developer experiments. Contains tools like `mosquitto` clients or test helpers but may not have full hardware drivers.

Guidelines for venv usage:

- For hardware sensor services (ToF, GPS, IMU, power monitor), prefer the `venv` Python 3.11 environment unless the code requires a Coral-specific runtime. The repo's service entrypoints assume Python 3.11 compatibility unless a Coral model is used.
- For Coral/TPU model execution (vision `src/vision` tasks, TFLite+Coral accelerators), activate `venv_coral_pyenv` or run via `venv_coral_pyenv/bin/python` so the correct binary runtime is available.
- Always check for the presence of required drivers (for example `adafruit_vl53l0x`) in the chosen venv before running hardware-mode services. You can quickly inspect with:

```bash
# from repo root
venv/bin/python -c "import pkgutil; print('FOUND' if pkgutil.find_loader('adafruit_vl53l0x') else 'MISSING')"
venv_coral_pyenv/bin/python -c "import pkgutil; print('FOUND' if pkgutil.find_loader('pycoral') else 'MISSING')"
```

- If a service is to be run by systemd in production, ensure the systemd service uses the same venv that was used during local validation to avoid ABI mismatches.

Keep the venv list up to date when adding or removing environments; add notes here explaining when and why to use each.

Agent runtime enforcement (appendix):

- Before any automated or manual Python execution, agents MUST run a venv verification and then execute via the venv binary. Example (non-interactive):

```bash
# verify and run a sensor service safely
test -f venv/bin/activate || { echo "venv missing - aborting"; exit 2; }
timeout 90s venv/bin/python -m src.hardware.sensor_service
```

- For interactive debug sessions, prefer activating the venv first:

```bash
source venv/bin/activate
python -m src.web_api.main
```

Record any intentional deviations from these rules in server-memory under `VirtualEnvs` with the reason and approval.
