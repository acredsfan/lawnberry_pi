# LawnBerry Pi v2 Unified Quickstart Guide

## Prerequisites Checklist

### Hardware Requirements
- [x] Raspberry Pi 4B/5 (aarch64) with minimum 4GB RAM
- [x] Raspberry Pi OS Bookworm Lite (64-bit) installed
- [x] Python 3.11+ available (`python3 --version`)
- [x] I2C, SPI, UART interfaces enabled (`sudo raspi-config`)
- [x] Internet connection for initial setup

### Constitutional Requirements Verification
Run these commands before proceeding:

```bash
# Platform verification (REQUIRED)
[[ "$(uname -m)" == "aarch64" ]] || { echo "❌ ARM64 required"; exit 1; }
[[ "$(python3 --version)" =~ "3.11" ]] || { echo "❌ Python 3.11+ required"; exit 1; }
grep -q "bookworm" /etc/os-release || { echo "❌ Bookworm required"; exit 1; }
echo "✅ Platform constitutional compliance verified"

# I2C interface check
ls /dev/i2c-* >/dev/null 2>&1 || { echo "❌ I2C not enabled"; exit 1; }
echo "✅ I2C interface available"
```

## Quick Installation (5 Minutes)

### Step 1: Clone Repository
```bash
cd /home/pi
git clone https://github.com/spanishgum/lawnberry.git
cd lawnberry
```

### Step 2: Constitutional Environment Setup
```bash
# Create main virtual environment (Python 3.11)
python3 -m venv venv
source venv/bin/activate

# Install core dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create isolated Coral environment (Python 3.9) - ISOLATED
python3.9 -m venv venv_coral_pyenv || echo "Python 3.9 not available - Coral features disabled"
```

### Step 3: Constitutional Compliance Validation
```bash
# Verify package isolation (CRITICAL)
venv/bin/python -c "
import importlib.util
banned = ['pycoral', 'edgetpu', 'tensorflow']
violations = [p for p in banned if importlib.util.find_spec(p)]
if violations:
    print('❌ CONSTITUTIONAL VIOLATION:', violations)
    exit(1)
else:
    print('✅ Package isolation verified')
"

# Test Coral isolation (if available)
if [ -d "venv_coral_pyenv" ]; then
    venv_coral_pyenv/bin/python -c "import sys; print('✅ Coral environment isolated:', sys.executable)"
fi
```

### Step 4: Configuration Setup
```bash
# Generate constitutional hardware configuration
cp config/hardware.yaml.backup config/hardware.yaml

# Verify constitutional channel assignments
grep -A 10 "ina3221" config/hardware.yaml | grep -q "channel_1.*battery" || echo "❌ Channel 1 must be battery"
grep -A 10 "ina3221" config/hardware.yaml | grep -q "channel_3.*solar" || echo "❌ Channel 3 must be solar"
echo "✅ Constitutional hardware configuration verified"
```

## Quick Start Development (10 Minutes)

### Step 5: Run Core System Tests
```bash
# Test core data structures (constitutional compliance)
timeout 30s venv/bin/python -m pytest tests/test_core_structures.py -v

# Test hardware interface (simulation mode)
timeout 60s venv/bin/python -m pytest tests/test_hardware_interface.py -m "not hardware" -v

# Test WebSocket hub (already implemented)
timeout 30s venv/bin/python -m pytest tests/test_websocket_hub.py -v
```

### Step 6: Start Development Services
```bash
# Terminal 1: Start FastAPI development server
source venv/bin/activate
timeout 300s uvicorn src.lawnberry.api.app:app --host 0.0.0.0 --port 8000 --reload &
DEV_SERVER_PID=$!

# Terminal 2: Start WebSocket telemetry (simulation mode)
source venv/bin/activate
SIMULATION_MODE=true timeout 300s venv/bin/python -m src.lawnberry.core.telemetry_service &
TELEMETRY_PID=$!

# Verify services started
sleep 5
curl -f http://localhost:8000/health || echo "❌ API server not responding"
curl -f http://localhost:8000/api/v1/dashboard/status || echo "❌ Dashboard API not responding"
echo "✅ Development services running"
```

### Step 7: Quick WebUI Test
```bash
# Test WebSocket connection
curl -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Key: test" \
     -H "Sec-WebSocket-Version: 13" http://localhost:8000/ws

# Access development WebUI (if available)
echo "🌐 Access WebUI at: http://$(hostname -I | awk '{print $1}'):8000"
echo "📊 API docs at: http://$(hostname -I | awk '{print $1}'):8000/docs"
```

## Hardware Integration Quickstart (15 Minutes)

### Step 8: I2C Device Detection
```bash
# Scan for constitutional I2C devices
echo "Scanning for constitutional hardware..."
timeout 15s i2cdetect -y 1

# Expected constitutional devices:
# 0x29: VL53L0X ToF sensor (left, address modified)
# 0x30: VL53L0X ToF sensor (right)  
# 0x40: INA3221 power monitor
# 0x28: BNO085 IMU
# 0x77: BME280 environmental sensor
```

### Step 9: Hardware Interface Test
```bash
# Test hardware interface with real sensors
source venv/bin/activate

# Test I2C power monitor (constitutional channels)
timeout 30s venv/bin/python -c "
from src.hardware.power_monitor import INA3221PowerMonitor
import asyncio

async def test_power():
    monitor = INA3221PowerMonitor()
    await monitor.initialize()
    data = await monitor.read_all_channels()
    print('✅ Power monitor working:', data)
    
    # Verify constitutional channels
    assert 'channel_1_battery' in data
    assert 'channel_3_solar' in data
    print('✅ Constitutional channels verified')

asyncio.run(test_power())
"

# Test GPS exclusivity
timeout 30s venv/bin/python -c "
from src.hardware.gps_manager import ConstitutionalGPSManager
import asyncio

async def test_gps():
    gps = ConstitutionalGPSManager()
    await gps.initialize()
    
    # Verify only one mode active (constitutional requirement)
    active_modes = sum([gps.rtk_usb_active, gps.uart_active])
    assert active_modes == 1, 'GPS exclusivity violation'
    print('✅ GPS exclusivity verified:', gps.active_mode)

asyncio.run(test_gps())
"
```

## AI Acceleration Quickstart (10 Minutes)

### Step 10: Test AI Acceleration Hierarchy
```bash
# Test CPU fallback (always available)
source venv/bin/activate
timeout 30s venv/bin/python -c "
from src.vision.cpu_accelerator import CPUFallbackAccelerator
import asyncio

async def test_cpu():
    accelerator = CPUFallbackAccelerator()
    await accelerator.initialize()
    print('✅ CPU fallback accelerator ready')

asyncio.run(test_cpu())
"

# Test Coral USB (if available and properly isolated)
if [ -d "venv_coral_pyenv" ]; then
    echo "Testing Coral USB isolation..."
    timeout 30s venv_coral_pyenv/bin/python -c "
try:
    import pycoral
    print('✅ Coral TPU libraries available in isolated environment')
except ImportError:
    print('⚠️  Coral TPU libraries not installed in isolated environment')
"
fi

# Verify constitutional AI hierarchy
timeout 30s venv/bin/python -c "
from src.vision.ai_manager import ConstitutionalAIManager
import asyncio

async def test_ai_hierarchy():
    ai_manager = ConstitutionalAIManager()
    await ai_manager.initialize()
    
    print('✅ AI acceleration hierarchy:')
    print(f'  Active tier: {ai_manager.active_tier}')
    print(f'  Available tiers: {ai_manager.available_tiers}')
    
    # Verify constitutional isolation
    assert ai_manager.main_env_clean, 'Constitutional violation: banned packages in main env'
    print('✅ Constitutional AI isolation verified')

asyncio.run(test_ai_hierarchy())
"
```

## Production Deployment Quickstart (20 Minutes)

### Step 11: Install as System Services
```bash
# Run constitutional installation script
sudo ./scripts/install_lawnberry.sh --constitutional-compliance

# Verify systemd services created
systemctl --user list-units | grep lawnberry

# Expected services:
# lawnberry-api.service          # FastAPI backend
# lawnberry-telemetry.service    # WebSocket telemetry
# lawnberry-navigation.service   # Autonomous navigation
# lawnberry-safety.service       # Safety monitoring
```

### Step 12: Verify Production Installation
```bash
# Check service status
systemctl --user status lawnberry-api
systemctl --user status lawnberry-telemetry

# Test production WebSocket
curl -f http://mower.local:8000/health || echo "❌ Production API not responding"

# Verify constitutional compliance in production
sudo journalctl -u lawnberry-api | grep -i "constitutional" | tail -5
```

### Step 13: Quick Operational Test
```bash
# Test manual control (safe commands only)
curl -X POST http://mower.local:8000/api/v1/manual/command \
  -H "Content-Type: application/json" \
  -d '{"command": "blade-off", "parameters": {}}'

# Test telemetry stream
timeout 10s wscat -c ws://mower.local:8000/ws

# Expected telemetry every 200ms (5Hz constitutional default)
```

## Common Issues & Quick Fixes

### Issue: Constitutional Violations
```bash
# Fix: Package isolation violation
pip uninstall pycoral edgetpu tensorflow  # Remove from main environment
source venv/bin/activate  # Ensure using correct environment

# Fix: Hardware configuration violation  
grep -v "channel_2.*battery\|channel_2.*solar" config/hardware.yaml > config/hardware.yaml.tmp
mv config/hardware.yaml.tmp config/hardware.yaml
# Channel 2 must remain unused per constitution
```

### Issue: I2C Device Not Found
```bash
# Fix: Enable I2C interface
sudo raspi-config  # Advanced Options → I2C → Enable

# Fix: I2C permissions
sudo usermod -a -G i2c pi
sudo reboot

# Fix: Address conflicts (constitutional assignments)
sudo i2cdetect -y 1  # Verify no conflicts at constitutional addresses
```

### Issue: WebSocket Connection Failed
```bash
# Fix: Service not running
systemctl --user restart lawnberry-api

# Fix: Firewall blocking
sudo ufw allow 8000/tcp

# Fix: WebSocket cadence too high
# Edit config/system.yaml: telemetry_cadence_hz: 5.0  # Constitutional limit
```

### Issue: GPS Mode Conflict
```bash
# Fix: Enforce GPS exclusivity
sudo systemctl stop gpsd  # Disable conflicting GPS daemon
# Edit config/hardware.yaml: ensure only one GPS mode enabled

# Fix: UART GPS when RTK USB available (constitutional violation)
# RTK USB must be primary when available
```

## Quick Reference Commands

### Development
```bash
# Start development environment
source venv/bin/activate
uvicorn src.lawnberry.api.app:app --reload --host 0.0.0.0

# Run constitutional compliance tests
timeout 60s venv/bin/python -m pytest tests/ -m "constitutional" -v

# Quick hardware scan
timeout 15s i2cdetect -y 1 && echo "✅ I2C scan complete"
```

### Production
```bash
# Check all services
systemctl --user list-units | grep lawnberry | grep -v "inactive\|failed"

# View real-time logs
sudo journalctl -f -u lawnberry-api

# Quick health check
curl -f http://mower.local:8000/health && echo "✅ System healthy"
```

### Debugging
```bash
# Constitutional compliance check
venv/bin/python -c "
import sys
banned = ['pycoral', 'edgetpu', 'tensorflow']
loaded = [m for m in sys.modules if any(b in m for b in banned)]
print('❌ Violations:' if loaded else '✅ Clean:', loaded)
"

# Hardware diagnostic
timeout 30s venv/bin/python -m src.hardware.diagnostic_tool

# WebSocket test
wscat -c ws://mower.local:8000/ws -x '{"type": "subscribe", "topic": "telemetry/updates"}'
```

## Next Steps

1. **Complete Implementation**: Follow `tasks.md` for systematic development
2. **Add Real Hardware**: Connect constitutional sensor complement
3. **Test Autonomous Mode**: Start by drawing your yard boundary polygon on the Map Setup page and setting Home, AM Sun, and PM Sun locations; then run boundary-only operation
4. **Deploy WebUI**: Access seven-page interface for full control
5. **Production Hardening**: Enable systemd services for autonomous operation

## Constitutional Compliance Reminder

Always verify these requirements before deployment:
- ✅ ARM64/Raspberry Pi OS Bookworm exclusive
- ✅ Python 3.11+ in main environment
- ✅ No pycoral/edgetpu/tensorflow in main environment
- ✅ INA3221 channels: 1=Battery, 2=Unused, 3=Solar
- ✅ GPS exclusivity: RTK USB primary, UART fallback only
- ✅ AI hierarchy isolation: Coral → Hailo → CPU
- ✅ WebSocket cadence: 5Hz default, 1-10Hz range
- ✅ Timeout enforcement: All operations have timeout limits

Notes:
- ToF orientation: “left” = front-left, “right” = front-right (mounted like headlights)
- RoboHAT control: Movement commands are sent via serial to RP2040 `robohat_files/code.py`; keep firmware unchanged unless adding hall-effect sensor support

🚀 **Ready to start autonomous mowing with constitutional compliance!**