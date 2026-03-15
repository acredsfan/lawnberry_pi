# LawnBerry Pi v2 - Complete Setup & Installation Guide

This comprehensive guide covers the complete setup process for LawnBerry Pi v2, from hardware assembly to advanced configuration.

## Table of Contents

1. [Hardware Requirements](#hardware-requirements)
2. [Initial Setup](#initial-setup)
3. [Software Installation](#software-installation)
4. [Basic Configuration](#basic-configuration)
5. [Advanced Features](#advanced-features)
6. [Troubleshooting](#troubleshooting)
7. [Migration from v1](#migration-from-v1)

## Hardware Requirements

### Primary Platform
- **Raspberry Pi 5** (4GB/8GB/16GB)
- **Raspberry Pi OS Bookworm 64-bit** (only supported)
- **MicroSD Card**: 32GB minimum, Class 10 or better
- **Power Supply**: Official Pi 5 27W USB-C power adapter

### Compatible Platform
- **Raspberry Pi 4B** (4GB or 8GB RAM)
- **Raspberry Pi OS Bookworm 64-bit**
- **MicroSD Card**: 32GB minimum, Class 10 or better
- **Power Supply**: Official Pi 4 15W USB-C power adapter

### Required Sensors & Hardware (reference spec/hardware.yaml)

#### Navigation & Positioning
- **GPS Module**
   - Baseline: SparkFun GPS-RTK-SMA (u-blox ZED-F9P) via USB
   - Supported fallback: u-blox NEO-8M via UART
   - Doc-only recommendation: u-blox NEO-9M (not part of the current baseline)
- **IMU/Compass**
   - Baseline: BNO085 on UART4
   - Backup-only mentions: BNO055 or MPU-9250, but verify code support before using them

#### Camera System
- **Pi Camera Module v2** (baseline primary)
- **Camera Cable**: 15-pin to 22-pin adapter if needed

#### Proximity & Safety
- **Safety Switch**: Emergency stop button

#### Motor & Power
- **Drive Controller**
   - Preferred: Cytron MDDRC10 via RoboHAT RP2040
   - Supported fallback: L298N dual H-bridge
- **Blade Controller**
   - Baseline: IBT-4 H-Bridge on GPIO 24 / 25
- **Motors**: DC geared motors with encoders
- **Battery**: 12V 30Ah LiFePO4 baseline
- **Power Monitoring**: INA3221 baseline, optional Victron SmartSolar BLE telemetry

#### Optional Hardware
- **Solar Panel**: 30W panel with MPPT charge controller
- **Google Coral USB Accelerator**: physically present in the baseline hardware list, but validate software support before depending on it
- **Hailo-8 AI Hat**: optional only, with the RoboHAT conflict caveat documented in `spec/hardware.yaml`

## Initial Setup

### 1. Prepare Raspberry Pi OS (64-bit Bookworm)

1. **Download and Flash OS**
   ```bash
   # Download Raspberry Pi Imager
   # Flash Raspberry Pi OS Bookworm 64-bit to SD card
   # Enable SSH and set user credentials during flash
   ```

2. **Boot and Initial Config**
   ```bash
   # Boot Pi and connect via SSH
   ssh pi@<pi-ip-address>
   
   # Update system
   sudo apt update && sudo apt upgrade -y
   
   # Enable required interfaces
   sudo raspi-config
   # Enable: Camera, I2C, SPI, Serial (login shell disabled)
   ```

3. **Install Dependencies**
   ```bash
   # Install system dependencies
   sudo apt install -y python3-pip python3-venv git nginx sqlite3 \
                       build-essential cmake pkg-config libjpeg-dev \
                       libtiff5-dev libpng-dev libavcodec-dev \
                       libavformat-dev libswscale-dev libgtk2.0-dev \
                       libcanberra-gtk-module libatlas-base-dev \
                       gfortran libhdf5-dev libhdf5-serial-dev \
                       python3-dev
   
   # Install Node.js for frontend (if building UI locally)
   curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
   sudo apt install -y nodejs
   ```

### 2. Hardware Assembly (Pi 4B/5 compatible)

1. **Mount Sensors**
   - Connect the GPS module via USB (preferred) or UART fallback
   - Wire the IMU per spec (`BNO085` on UART4; use backup IMUs only after verifying support)
   - Install camera module (Pi Camera v2)

2. **Power System**
   - Connect battery to power management board
   - Wire 5V output to Pi power input
   - Connect motor controllers to battery and GPIO

3. **Motor & Drive System**
   - Mount motors to chassis
   - Connect motor controllers to drive motors
   - Wire encoders to GPIO for feedback

## Software Installation

### 1. Clone Repository
```bash
cd /home/pi
git clone https://github.com/acredsfan/lawnberry_pi.git lawnberry
cd lawnberry
```

### 2. Backend Setup (Python 3.11)
```bash
# Use uv for reproducible installs (preferred)
uv sync

# Optional: create venv manually
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Frontend Setup (optional on headless Pi)
```bash
cd ../frontend
npm install
npm run build
```

### 4. Install systemd Services
```bash
cd systemd
sudo bash install_services.sh
```

### 5. Automatic HTTPS (Zero-Touch)

HTTPS is configured automatically during setup with a self-signed certificate, and seamlessly upgrades to a valid Let's Encrypt certificate when you provide your domain and email in `.env`.

1) Self-signed baseline (automatic):
   - `scripts/setup.sh` installs nginx (if missing), creates a self-signed cert under `/etc/lawnberry/certs/selfsigned`, configures HTTP→HTTPS redirect, ACME challenge path, and WebSocket proxying.
   - The site becomes reachable at `https://<pi-ip>/` immediately (your browser will warn about the self-signed certificate until a valid one is installed).

2) Zero-touch Let’s Encrypt (recommended):
   - Edit `./.env` and set:
     - `LB_DOMAIN=your.domain`
     - `LETSENCRYPT_EMAIL=you@domain.com`
     - Optional: `ALT_DOMAINS=www.your.domain,api.your.domain`
     - Optional (for DNS-01 and wildcards): `CLOUDFLARE_API_TOKEN=cf_...`
   - Re-run `scripts/setup.sh` or reboot. The setup will provision a valid cert automatically and migrate nginx to use it.

3) Auto-renewal, validation, and fallback:
   - A daily systemd timer (`lawnberry-cert-renewal.timer`) runs `scripts/renew_certificates.sh` to renew LE certs, validate expiry, and reload nginx.
   - If renewal fails or the certificate is near expiry, the script falls back to a self-signed certificate automatically to maintain HTTPS availability.
   - Logs are written to syslog with the tag `lawnberry-cert`.

Check status and logs:
```bash
systemctl list-timers | grep lawnberry-cert-renewal
journalctl -u lawnberry-cert-renewal.service -n 100 --no-pager
```

Validate HTTPS/ACME locally (no real cert required):
```bash
# Run safe validation (installs nginx if needed when flag provided)
./scripts/validate_https_setup.sh --install-nginx

# What it checks
# - nginx syntax and service status
# - ACME challenge path served on http://127.0.0.1/.well-known/acme-challenge
# - TLS handshake + HTTP response on https://127.0.0.1/
```

## Basic Configuration

### 1. Initial System Config
```bash
# Review tracked configuration first
sed -n '1,220p' config/hardware.yaml
sed -n '1,220p' config/default.json
```

### 2. Test Installation
```bash
# Enable and start services
sudo systemctl enable --now lawnberry-backend lawnberry-health lawnberry-sensors

# Check service status
sudo systemctl status lawnberry-backend

# Test API (port 8081)
curl http://localhost:8081/health

# Access web interface (if running frontend)
# Open browser to http://<pi-ip>:3000
```

3. **Hardware Verification**

1. **GPS Calibration & RTK Configuration**
   
   For high-precision RTK GPS with NTRIP corrections, see the comprehensive guide:
   - **[GPS RTK with NTRIP Configuration Guide](gps-ntrip-setup.md)** - Complete instructions for cm-level accuracy
   
   Basic GPS testing:
   ```bash
   # Check GPS health and telemetry
   curl http://localhost:8081/api/v2/sensors/health | jq '.gps'
   curl http://localhost:8081/api/v2/dashboard/telemetry | jq '.position'
   ```

2. **IMU Calibration**
   ```bash
   # Verify IMU-related hardware appears healthy
   curl http://localhost:8081/api/v2/sensors/health | jq '.imu'
   ```

3. **Motor Calibration**
   ```bash
   # Verify self-test and RoboHAT status before any live movement testing
   curl http://localhost:8081/api/v2/system/selftest | jq
   curl http://localhost:8081/api/v2/hardware/robohat | jq
   ```

## Advanced Features

For detailed configuration of advanced features, see the dedicated guides:

- **[GPS RTK with NTRIP Configuration](gps-ntrip-setup.md)** - RTK GPS with centimeter-level accuracy
- **[Remote Access Setup](remote-access-setup.md)** - Cloudflare tunnels, ngrok, custom domains
- **[Authentication Configuration](authentication-config.md)** - Multi-factor auth, OAuth integration
- **[Maps API Setup](maps-api-setup.md)** - Google Maps, OpenStreetMap configuration

### Quick Links to Advanced Setup

1. **Remote Access** (Recommended)
   ```bash
   # Configure Cloudflare tunnel (most secure)
   lawnberry-pi config remote-access --setup-cloudflare
   
   # Alternative: ngrok setup
   lawnberry-pi config remote-access --setup-ngrok
   ```

2. **Enhanced Authentication**
   ```bash
   # Enable TOTP two-factor authentication
   lawnberry-pi config auth --level totp --setup-totp
   
   # Configure Google OAuth
   lawnberry-pi config auth --level google --setup-oauth
   ```

3. **Maps & Navigation**
   ```bash
   # Configure Google Maps API
   lawnberry-pi config maps --provider google --api-key YOUR_KEY
   
   # Set up OpenStreetMap fallback
   lawnberry-pi config maps --provider osm --enable-fallback
   ```

## Troubleshooting

### Common Issues

1. **GPS Not Working**
   ```bash
   # Check GPS device
   lsusb | grep GPS
   dmesg | grep tty
   
   # Test GPS directly
   sudo cat /dev/ttyACM0  # or another /dev/ttyACM* device exposed by the GPS
   
   # Check permissions
   sudo usermod -a -G dialout pi
   ```

2. **Camera Issues**
   ```bash
   # Test camera
   libcamera-hello --display 0
   
   # Check camera interface
   sudo raspi-config  # Enable camera
   
   # Verify camera detection
   libcamera-hello --list-cameras
   ```

3. **I2C Sensor Issues**
   ```bash
   # Check I2C devices
   sudo i2cdetect -y 1
   
   # Verify backend-reported sensor status
   curl http://localhost:8081/api/v2/sensors/health | jq
   ```

4. **Network Connectivity**
   ```bash
   # Check network status
   ping -c 4 8.8.8.8
   
   # Test API endpoints
   curl http://localhost:8081/api/v1/health/readiness
   
   # Check service logs
   sudo journalctl -u lawnberry-backend -f
   ```

### Performance Optimization (Pi 4B vs Pi 5)

1. **System Performance**
   ```bash
   # Optimize Pi performance
   echo 'gpu_mem=128' | sudo tee -a /boot/config.txt
   echo 'dtoverlay=disable-bt' | sudo tee -a /boot/config.txt
   
   # Enable performance governor
   echo 'performance' | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
   ```

2. **Database Optimization**
   ```bash
   # Optimize SQLite for Pi
   lawnberry-pi optimize database --vacuum --reindex
   ```

## Migration from v1

### Backup v1 Data
```bash
# Create backup of v1 system
sudo systemctl stop lawnberry-v1
cp -r .-v1/data .-v1-backup/
```

### Import Configuration
```bash
# Import v1 settings to v2
lawnberry-pi migrate from-v1 --config-path .-v1/config.json

# Import zone definitions
lawnberry-pi migrate zones --from-v1-db .-v1/data/zones.db

# Import job history (optional)
lawnberry-pi migrate jobs --from-v1-db .-v1/data/jobs.db
```

### Verification
```bash
# Verify migration
lawnberry-pi verify migration --check-zones --check-config

# Test basic functionality
lawnberry-pi test --all
```

## Next Steps

After completing the basic setup:

1. **Configure Remote Access** - Set up secure remote connectivity
2. **Set Up Maps Integration** - Configure mapping providers
3. **Enable Advanced Authentication** - Add multi-factor security
4. **Configure AI Training** - Set up machine learning features
5. **Create Mowing Zones** - Define cutting areas and patterns
6. **Schedule Automated Jobs** - Set up recurring mowing schedules

## Support & Resources

- **Documentation**: `./docs/`
- **Configuration**: `lawnberry-pi config --help`
- **Logs**: `sudo journalctl -u lawnberry-backend -f`
- **Web Interface**: `http://<pi-ip>:3000`
- **API Documentation**: `http://<pi-ip>:8081/docs`

For additional help, consult the troubleshooting guides or check system logs for detailed error information.