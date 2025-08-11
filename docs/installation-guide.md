# LawnBerryPi Installation Guide

This guide will walk you through the complete installation of your LawnBerryPi autonomous lawn mower system. No robotics or programming experience is required - just follow the steps carefully.

## What You'll Need

### Hardware Requirements
- LawnBerryPi kit (all components included)
- MicroSD card (32GB or larger, Class 10 recommended)
- Computer with SD card reader
- HDMI monitor and keyboard (for initial Raspberry Pi setup)
- Ethernet cable or WiFi network access
- Phillips head screwdriver
- Wire strippers (if making custom connections)

### Required API Keys (Free)
- OpenWeather API key (for weather data)
- Google Maps API key (for mapping interface)

### Time Required
- Initial setup: 2-3 hours
- Hardware assembly: 1-2 hours (if not pre-assembled)
- Software installation: 30-60 minutes (includes Bookworm optimizations)
- Testing and calibration: 30-45 minutes
- Total: 4-6 hours for complete setup

## Step 1: Raspberry Pi OS Setup

### 1.1 Prepare the SD Card

1. **Download Raspberry Pi Imager**
   - Go to [rpi.org](https://www.raspberrypi.com/software/)
   - Download and install Raspberry Pi Imager for your computer

2. **Flash Raspberry Pi OS Bookworm (REQUIRED)**
   - Insert your SD card into your computer (32GB+ recommended)
   - Open Raspberry Pi Imager
   - Click "CHOOSE OS" → "Raspberry Pi OS (64-bit)" → **Ensure Bookworm is selected**
   - Click "CHOOSE STORAGE" and select your SD card
   - **Important**: Click the gear icon (⚙️) for advanced options:
     - ✅ Enable SSH (set password: `lawnberry`)
     - ✅ Set username: `pi` and password: `lawnberry`
     - ✅ Configure WiFi (enter your network details)
     - ✅ Set locale settings (your timezone and keyboard layout)
   - Click "WRITE" and wait for completion

### 1.2 First Boot

1. **Insert SD card** into your Raspberry Pi
2. **Connect peripherals**:
   - HDMI monitor
   - USB keyboard
   - Ethernet cable (if not using WiFi)
   - Power cable (connect last)
3. **Wait for boot** (2-3 minutes for first boot)
4. **Login** with username `pi` and password `lawnberry`

### 1.3 Enable Required Interfaces

Open terminal and run these commands:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Enable required interfaces
sudo raspi-config nonint do_i2c 0      # Enable I2C
sudo raspi-config nonint do_camera 0   # Enable Camera
sudo raspi-config nonint do_serial 0   # Enable Serial
sudo raspi-config nonint do_ssh 0      # Enable SSH

# Reboot to apply changes
sudo reboot
```

## Step 2: Hardware Assembly

### 2.1 Power System Setup

**⚠️ Safety Warning**: Work with power disconnected. Double-check all connections before applying power.

1. **Mount the LiFePO4 Battery**
   - Secure 30Ah LiFePO4 battery in the designated compartment
   - Ensure battery is easily accessible for maintenance

2. **Install Solar Charge Controller**
   - Mount 20A solar charge controller in protected location
   - **Battery connections** (RED = Positive, BLACK = Negative):
     - Battery positive (+) → Controller "BAT +" terminal
     - Battery negative (-) → Controller "BAT -" terminal
   - **Solar panel connections**:
     - Panel positive (+) → Controller "PV +" terminal
     - Panel negative (-) → Controller "PV -" terminal

3. **Install DC-DC Converter**
   - Mount 12V-to-5V DC-DC buck converter
   - **Input**: 12V from battery system
   - **Output**: 5V to Raspberry Pi power input

### 2.2 Raspberry Pi and Hat Installation

1. **Mount Raspberry Pi**
   - Secure Raspberry Pi 4 in protective enclosure
   - Ensure adequate ventilation for cooling

2. **Install RoboHAT**
   - Carefully align RoboHAT with Raspberry Pi GPIO pins
   - Press down firmly until fully seated
   - **Verify**: All 40 pins are properly connected

3. **Connect Power**
   - Connect 5V output from DC-DC converter to Raspberry Pi
   - **Do not power on yet**

### 2.3 Motor System Installation

1. **Mount Drive Motors**
   - Install 2x 12V worm gear DC motors for wheel drive
   - Ensure motors are securely mounted with proper alignment
   - **Gear ratios**: Verify proper gear engagement

2. **Install Motor Driver**
   - Mount Cytron MDDRC10 motor driver in protected location
   - **Motor connections**:
     - Left motor: M1A/M1B terminals
     - Right motor: M2A/M2B terminals
   - **Power connections**:
     - VDD: +12V from battery
     - GND: Battery ground
   - **Control connections** (from RoboHAT):
     - PWM1 → Speed control for left motor
     - DIR1 → Direction control for left motor
     - PWM2 → Speed control for right motor
     - DIR2 → Direction control for right motor

3. **Install Blade Motor**
   - Mount 997 DC motor for blade control
   - Install IBT-4 motor driver
   - **Connections**:
     - Motor: Connect to IBT-4 output terminals
     - Power: +12V and GND from battery
     - Control: GPIO 24 (IN1) and GPIO 25 (IN2) from Raspberry Pi

### 2.4 Sensor Installation

1. **Install ToF Sensors**
   - Mount 2x VL53L0X sensors on front of mower
   - **Left sensor**:
     - VCC → 3.3V
     - GND → Ground
     - SDA → I2C SDA (GPIO 2)
     - SCL → I2C SCL (GPIO 3)
     - SHDN → GPIO 22
   - **Right sensor**:
     - VCC → 3.3V
     - GND → Ground
     - SDA → I2C SDA (GPIO 2)
     - SCL → I2C SCL (GPIO 3)
     - SHDN → GPIO 23

2. **Install IMU Sensor**
   - Mount BNO085 IMU sensor
   - **Connections**:
     - VCC → 3.3V (Pin 17)
     - GND → Ground
     - RX → TXD 4 (Pin 24)
     - TX → RXD 4 (Pin 21)
     - PS1 → 3.3V (for UART mode)

3. **Install Environmental Sensor**
   - Mount BME280 sensor in weather-protected location
   - **I2C connections**:
     - VCC → 3.3V
     - GND → Ground
     - SDA → I2C SDA (GPIO 2)
     - SCL → I2C SCL (GPIO 3)
     - **I2C Address**: 0x76

4. **Install Power Monitor**
   - Mount INA3221 power monitor near battery
   - **I2C connections**:
     - VCC → 3.3V
     - GND → Ground
     - SDA → I2C SDA (GPIO 2)
     - SCL → I2C SCL (GPIO 3)
     - **I2C Address**: 0x40
   - **Current sensing**: Connect in series with main power lines

5. **Install GPS Module**
   - Mount SparkFun GPS-RTK-SMA kit with clear sky view
   - **USB connection** to Raspberry Pi (`/dev/ttyACM0`)
   - Configure for 38400 baud

6. **Install Camera**
   - Connect Raspberry Pi Camera to camera port
   - Mount in protective housing with clear view forward
   - **Verify**: Camera is accessible as `/dev/video0`

### 2.5 Display and Indicators

1. **OLED Display** (if separate from RoboHAT)
   - Mount SSD1306 OLED display for status
   - **I2C connections**:
     - VCC → 3.3V
     - GND → Ground
     - SDA → I2C SDA (GPIO 2)
     - SCL → I2C SCL (GPIO 3)
     - **I2C Address**: 0x3C

## Step 3: Software Installation

### 3.1 Download LawnBerryPi Software

```bash
# Create directory and download
cd /home/pi
git clone https://github.com/your-repo/lawnberry-pi.git
cd lawnberry-pi

# Make installation script executable
chmod +x install_system_integration.sh
```

### 3.2 Install System Dependencies

```bash
# Run the automated installation script
./install_system_integration.sh

# This script will:
# - Install Python dependencies
# - Install Node.js and web UI dependencies  
# - Set up system services
# - Configure hardware interfaces
# - Create necessary directories
# - Prompt for optional Coral TPU installation
```

**Coral TPU Installation Prompt**: During installation, you'll be asked if you want to install Coral Edge TPU support. This is optional and provides AI acceleration for object detection. See [Section 3.3 Coral TPU Setup](#33-coral-tpu-setup-optional) for details.

### 3.3 Coral TPU Setup (Optional)

The Coral Edge TPU provides hardware acceleration for AI inference, significantly improving object detection performance. This section covers installation for users who have or plan to get Coral TPU hardware.

#### 3.3.1 Hardware Compatibility

**Supported Hardware**:
- ✅ **Coral USB Accelerator** (most common, plug-and-play)
- ✅ **Coral Dev Board Mini** (embedded option)
- ✅ **Coral M.2 Accelerator** (for compatible carrier boards)

**Software Requirements**:
- ✅ **Pi OS Bookworm** (required - this guide assumes Bookworm)
- ✅ **Python 3.11+** (Bookworm default)
- ✅ **ARM64 architecture** (64-bit Pi OS)

#### 3.3.2 Installation Methods

**Method 1: Automated Installation (Recommended)**

If you didn't install Coral support during the main installation:

```bash
# Run Coral-specific installer
cd /home/pi/lawnberry-pi
sudo ./scripts/install_coral_runtime.sh

# Install Python packages
sudo ./scripts/install_coral_system_packages.sh
```

**Method 2: Manual Installation**

For advanced users or troubleshooting:

```bash
# 1. Add Google's repository
echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" | sudo tee /etc/apt/sources.list.d/coral-edgetpu.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
sudo apt-get update

# 2. Install Edge TPU runtime (choose one)
sudo apt-get install libedgetpu1-std    # Standard frequency (recommended)
# OR
sudo apt-get install libedgetpu1-max    # Maximum frequency (runs hotter)

# 3. Install Python library
sudo apt-get install python3-pycoral

# 4. Verify installation
python3 -c "from pycoral.utils import edgetpu; print('Coral packages installed successfully')"
```

#### 3.3.3 Hardware Detection and Verification

After installation, verify your Coral TPU is detected:

```bash
# Check for USB Accelerator
lsusb | grep -i "google\|coral"
# Expected output: Bus 001 Device 004: ID 18d1:9302 Google Inc.

# Test Coral functionality
cd /home/pi/lawnberry-pi
python3 scripts/verify_coral_installation.py

# Check hardware enumeration
python3 -c "from pycoral.utils import edgetpu; print(f'Detected {len(edgetpu.list_edge_tpus())} Edge TPU device(s)')"
```

**Expected Results**:
- ✅ **With hardware present**: "Detected 1 Edge TPU device(s)"
- ✅ **Without hardware**: "Detected 0 Edge TPU device(s)" (CPU fallback will be used)

#### 3.3.4 Performance Modes

The Edge TPU runtime supports two performance modes:

| Mode | Package | Performance | Temperature | Power |
|------|---------|-------------|-------------|-------|
| **Standard** | `libedgetpu1-std` | ~4 TOPS | Cool running | Lower |
| **Maximum** | `libedgetpu1-max` | ~4 TOPS | Runs hot | Higher |

**Recommendation**: Use **Standard mode** unless you need maximum performance and have adequate cooling.

**Switch modes**:
```bash
# Switch to standard mode
sudo apt-get install --reinstall libedgetpu1-std

# Switch to maximum mode  
sudo apt-get install --reinstall libedgetpu1-max

# Restart services after mode change
sudo systemctl restart lawnberry-*
```

### 3.4 CPU Fallback Configuration

LawnBerryPi automatically uses CPU-based inference when Coral TPU is not available. No additional configuration is required - the system will:

- ✅ **Automatically detect** Coral hardware presence
- ✅ **Use Coral acceleration** when available
- ✅ **Fall back to CPU** when Coral is not present
- ✅ **Show status** in web interface

**Performance Impact**: CPU inference is 5-10x slower than Coral TPU but still functional for most use cases.

### 3.5 Configure Environment Variables

1. **Create environment file**:
```bash
cp .env.example .env
nano .env
```

2. **Set required variables** (replace with your actual keys):
```bash
# Weather Service
OPENWEATHER_API_KEY=your_openweather_api_key_here

# Google Maps (for web UI)
REACT_APP_GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here

# System Configuration
LAWNBERRY_FLEET_API_KEY=your_fleet_key_here
DEBUG_MODE=false
LOG_LEVEL=INFO

# Optional: Coral TPU Configuration
CORAL_TPU_ENABLED=true          # Set to false to force CPU mode
CORAL_MODEL_PATH=/opt/lawnberry/models/custom/  # Custom model directory
# Canonical Runtime & Fast Deploy

LawnBerry now uses a canonical runtime directory at `/opt/lawnberry` for all enabled systemd services. Your cloned repository (e.g. `/home/pi/lawnberry_pi`) is the editable source tree. After making code changes, use the fast deploy helper to sync changes into the runtime without a full reinstall:

```bash
./scripts/install_lawnberry.sh --deploy-update
```

This performs:
1. Incremental rsync of source (excluding venv, data, logs, node_modules, build artifacts) to `/opt/lawnberry`.
2. Optional sync of `web-ui/dist` if you built the frontend separately.
3. Validation / creation of the runtime virtualenv and dependency install (only if needed).
4. Automatic correction of any legacy service units still pointing at the project root.
5. Restart of core services (system, data, hardware, safety, api).

Development Workflow:
- Edit code in source tree.
- (Optional) Build web UI: `(cd web-ui && npm run build)`.
- Deploy update: `./scripts/install_lawnberry.sh --deploy-update`.
- Check service status: `systemctl status lawnberry-system.service`.

Production Isolation Benefits:
- Reduces risk of accidental edits to running code.
- Stable path simplifies documentation & monitoring.
- Easier backups (`/opt/lawnberry`, `/var/lib/lawnberry`, `/var/log/lawnberry`).

Do NOT manually edit files under `/opt/lawnberry` except for emergency hotfixes—these will be overwritten on the next deploy.

### Troubleshooting Fast Deploy

If a core service fails after deploy:
1. Re-run `--deploy-update` (repairs legacy paths and dependencies).
2. Inspect logs: `journalctl -xeu lawnberry-system.service`.
3. Verify runtime venv: `/opt/lawnberry/venv/bin/python -c "import fastapi"`.
4. Check for syntax errors introduced by the recent change.

### Uninstall (Extended Cleanup)

Standard removal:
```bash
sudo systemctl stop lawnberry-system lawnberry-data lawnberry-hardware lawnberry-safety lawnberry-api || true
sudo systemctl disable lawnberry-system lawnberry-data lawnberry-hardware lawnberry-safety lawnberry-api || true
sudo rm -f /etc/systemd/system/lawnberry-*.service
sudo systemctl daemon-reload
sudo rm -rf /opt/lawnberry /var/log/lawnberry /var/lib/lawnberry
```

Remove any legacy service units referencing a source path (older versions):
```bash
sudo find /etc/systemd/system -maxdepth 1 -name 'lawnberry-*.service' -exec grep -l '/home/pi/lawnberry_pi' {} \; | xargs -r sudo rm
sudo systemctl daemon-reload
```

Backup before uninstall (optional):
```bash
sudo tar -czf lawnberry-backup-$(date +%Y%m%d).tar.gz /opt/lawnberry/config /var/lib/lawnberry /var/log/lawnberry
```

---
Updated: 2025-08-10 – Added canonical runtime + fast deploy instructions.

### Fast Deploy Advanced Environment Variables

You can tune the fast deploy behavior via environment variables when invoking `--deploy-update` (prefix assignment then command).

Common examples:
```bash
# Minimal deploy skipping service restarts and venv check (quick frontend-only change)
FAST_DEPLOY_DIST_MODE=minimal FAST_DEPLOY_SKIP_VENV=1 FAST_DEPLOY_SKIP_SERVICES=1 ./scripts/install_lawnberry.sh --deploy-update

# Force full dist sync and restart services with shorter timeouts
FAST_DEPLOY_DIST_MODE=full FAST_DEPLOY_SERVICE_TIMEOUT=4 ./scripts/install_lawnberry.sh --deploy-update
```

Variables:
- FAST_DEPLOY_HASH=0|1 (default 1) – Enable subset drift hash before sync.
- FAST_DEPLOY_DIST_MODE=skip|minimal|full (default minimal) – Control web-ui/dist sync strategy.
   - skip: Don’t sync frontend assets.
   - minimal: Only copy changed core files (index.html, manifests) and any new hashed bundles (no deletion).
   - full: Rsync entire dist with deletion (uses a bounded timeout; falls back to minimal on timeout).
- FAST_DEPLOY_SERVICE_TIMEOUT=SECONDS (default 10) – Per service restart timeout.
- FAST_DEPLOY_SKIP_SERVICES=1 – Skip restarting services entirely.
- FAST_DEPLOY_SKIP_VENV=1 – Skip runtime virtualenv validation/install.
- FAST_DEPLOY_INCLUDE_TESTS=1 – Include the tests directory in sync (excluded by default for speed).
- FAST_DEPLOY_MAX_SECONDS=TOTAL – Abort remaining directory syncs if total fast deploy exceeds this duration.
- FAST_DEPLOY_SKIP_POST_HASH=1 – Skip post-sync verification hash.

Recommended patterns:
| Scenario | Command |
|----------|---------|
| Backend code tweak | `./scripts/install_lawnberry.sh --deploy-update` |
| Frontend asset change only | `FAST_DEPLOY_DIST_MODE=minimal FAST_DEPLOY_SKIP_VENV=1 ./scripts/install_lawnberry.sh --deploy-update` |
| Large refactor (full refresh) | `FAST_DEPLOY_DIST_MODE=full FAST_DEPLOY_HASH=1 ./scripts/install_lawnberry.sh --deploy-update` |
| Skip service restart (manual control) | `FAST_DEPLOY_SKIP_SERVICES=1 ./scripts/install_lawnberry.sh --deploy-update` |

If a deploy is approaching an outer supervisor timeout, set `FAST_DEPLOY_MAX_SECONDS` to ensure the script exits cleanly and can be retried.


```

### 3.6 Get Required API Keys

#### OpenWeather API Key (Free)
1. Go to [OpenWeatherMap](https://openweathermap.org/api)
2. Click "Sign Up" and create free account
3. Verify your email address
4. Go to "API Keys" section
5. Copy your default API key
6. Paste into `.env` file as `OPENWEATHER_API_KEY`

#### Google Maps API Key (Optional - Free tier available)

**Note**: Google Maps API is optional. If not configured, LawnBerryPi will automatically use OpenStreetMap as a fallback with full functionality.

**Step-by-step Google Maps API setup**:

1. **Create Google Cloud Account**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Sign in with your Google account
   - Accept terms of service if prompted

2. **Create or Select Project**
   - Click "Select a project" dropdown at the top
   - Click "New Project" or select existing project
   - Enter project name (e.g., "LawnBerryPi Maps")
   - Click "Create"

3. **Enable Required APIs**
   - Go to "APIs & Services" → "Library"
   - Search for and enable these APIs:
     - **Maps JavaScript API** (required for map display)
     - **Geocoding API** (required for address search)
     - **Places API** (optional, for enhanced location search)

4. **Create API Key**
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "API Key"
   - Copy the generated API key
   - **Important**: Click "Restrict Key" for security

5. **Configure API Key Restrictions** (Recommended for security)
   - **Application restrictions**: Select "HTTP referrers"
   - Add your LawnBerryPi domains:
     - `http://localhost:3000/*` (for local development)
     - `http://[your-pi-ip]:3000/*` (replace with your Pi's IP)
     - `https://[your-domain]/*` (if using custom domain)
   - **API restrictions**: Select "Restrict key"
   - Choose: Maps JavaScript API, Geocoding API, Places API

6. **Set Up Billing** (Required even for free tier)
   - Go to "Billing" in Google Cloud Console
   - Add a billing account (credit card required)
   - **Note**: Free tier includes $200 monthly credit, sufficient for personal use
   - Set up billing alerts to avoid unexpected charges

7. **Configure in LawnBerryPi**
   - Add API key to `.env` file as `REACT_APP_GOOGLE_MAPS_API_KEY`
   - Set usage level: `REACT_APP_GOOGLE_MAPS_USAGE_LEVEL=medium`

**Cost Management Options**:
- **Low usage**: Updates every 10 seconds, basic features only
- **Medium usage**: Updates every 5 seconds, all features (recommended)
- **High usage**: Real-time updates, maximum quality (higher API usage)

**Troubleshooting Common Issues**:
- **"API key denied"**: Check API restrictions and billing account
- **"Quota exceeded"**: Check usage limits in Google Cloud Console
- **"Billing required"**: Add billing account even for free tier usage
- **Map not loading**: System automatically falls back to OpenStreetMap

## Step 4: Initial Configuration and Testing

### 4.1 Hardware Connection Test

```bash
# Test I2C devices
python3 -c "
import smbus
bus = smbus.SMBus(1)
devices = []
for addr in range(0x03, 0x78):
    try:
        bus.read_byte(addr)
        devices.append(f'0x{addr:02x}')
    except:
        pass
print('I2C devices found:', devices)
"

# Expected devices:
# 0x3c (SSD1306 Display)
# 0x40 (INA3221 Power Monitor) 
# 0x76 (BME280 Environmental)
```

### 4.2 Test Camera

```bash
# Test camera functionality
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
if ret:
    print('Camera working: Frame size', frame.shape)
else:
    print('Camera not detected')
cap.release()
"
```

### 4.3 Test GPS

```bash
# Check GPS connection
ls /dev/ttyACM* 
# Should show /dev/ttyACM0 (GPS)

# Test GPS data
python3 -c "
import serial
try:
    gps = serial.Serial('/dev/ttyACM0', 38400, timeout=5)
    data = gps.read(100)
    print('GPS data received:', len(data), 'bytes')
    gps.close()
except Exception as e:
    print('GPS error:', e)
"
```

### 4.4 Start System Services

```bash
# Enable and start LawnBerryPi services
sudo systemctl enable lawnberry-hardware
sudo systemctl enable lawnberry-web-api
sudo systemctl enable lawnberry-web-ui

sudo systemctl start lawnberry-hardware
sudo systemctl start lawnberry-web-api
sudo systemctl start lawnberry-web-ui

# Check service status
sudo systemctl status lawnberry-hardware
sudo systemctl status lawnberry-web-api
sudo systemctl status lawnberry-web-ui
```

## Step 5: Web Interface Access

### 5.1 Find Raspberry Pi IP Address

```bash
# Find IP address
hostname -I
```

### 5.2 Access Web Interface

1. **Open web browser** on any device connected to the same network
2. **Navigate to**: `http://[raspberry-pi-ip]:3000`
   - Example: `http://192.168.1.100:3000`
3. **You should see** the LawnBerryPi dashboard

### 5.3 Initial System Check

The web interface should show:
- ✅ **Green status** for all connected hardware
- 📊 **Sensor readings** updating in real-time
- 🗺️ **Map view** with current location
- 🔋 **Battery status** and power metrics

## Step 6: Initial Calibration

### 6.1 GPS Calibration

1. **Place mower outdoors** with clear sky view
2. **Wait 5-10 minutes** for GPS to acquire satellites
3. **Verify GPS lock** in web interface (should show coordinates)

### 6.2 Compass Calibration

1. **In web interface**: Go to Settings → Hardware → IMU Calibration
2. **Follow calibration routine**:
   - Rotate mower slowly through all axes
   - Complete figure-8 motions
   - Wait for "Calibration Complete" message

### 6.3 Safety System Test

1. **Emergency Stop Test**:
   - Press emergency stop button
   - Verify all motors stop immediately
   - Reset emergency stop and verify normal operation

2. **Obstacle Detection Test**:
   - Place obstacle in front of mower
   - Enable obstacle detection in web interface
   - Verify distance readings update correctly

## Troubleshooting Installation Issues

### Common Problems

**Problem**: I2C devices not detected
- **Solution**: Check wiring connections, ensure I2C is enabled
- **Command**: `sudo raspi-config` → Interface Options → I2C → Enable

**Problem**: Camera not working
- **Solution**: Check camera cable connection, enable camera interface
- **Command**: `sudo raspi-config` → Interface Options → Camera → Enable

**Problem**: GPS not receiving data
- **Solution**: Ensure outdoor location with sky view, check USB connection
- **Check**: `ls /dev/tty*` should show `/dev/ttyACM0`

**Problem**: Web interface not accessible
- **Solutions**:
  - Check service status: `sudo systemctl status lawnberry-web-ui`
  - Restart services: `sudo systemctl restart lawnberry-web-ui`
  - Check firewall: `sudo ufw allow 3000`

**Problem**: API keys not working
- **Solutions**:
  - Verify `.env` file format (no spaces around =)
  - Check API key validity at provider websites
  - Restart services after changing `.env`

### Getting Help

If you encounter issues:

1. **Check system logs**:
```bash
journalctl -u lawnberry-hardware -f
journalctl -u lawnberry-web-api -f
```

2. **Run hardware diagnostics**:
```bash
cd /home/pi/lawnberry-pi
python3 validate_hardware.py
```

3. **See our troubleshooting guide**: [troubleshooting-guide.md](troubleshooting-guide.md)

## Next Steps

Once installation is complete:

1. **[First-Time Setup](first-time-setup.md)** - Configure your specific yard
2. **[User Manual](user-manual.md)** - Learn to operate your LawnBerryPi
3. **[Safety Guide](safety-guide.md)** - Important safety information

---

**Congratulations!** Your LawnBerryPi is now installed and ready for configuration. Take some time to explore the web interface and familiarize yourself with the controls before proceeding to first-time setup.

*Installation Guide - Part of LawnBerryPi Documentation v1.0*
