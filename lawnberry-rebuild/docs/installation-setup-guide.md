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
- **Raspberry Pi 5** (4GB or 8GB RAM recommended)
- **Raspberry Pi OS Bookworm 64-bit** (latest)
- **MicroSD Card**: 32GB minimum, Class 10 or better
- **Power Supply**: Official Pi 5 27W USB-C power adapter

### Compatible Platform
- **Raspberry Pi 4B** (4GB or 8GB RAM)
- **Raspberry Pi OS Bookworm 64-bit**
- **MicroSD Card**: 32GB minimum, Class 10 or better
- **Power Supply**: Official Pi 4 15W USB-C power adapter

### Required Sensors & Hardware

#### Navigation & Positioning
- **GPS Module**: USB GPS receiver or GPIO-connected module
  - Recommended: u-blox NEO-8M or NEO-9M based modules
  - Alternative: USB GPS dongles (BU-353S4, etc.)
- **IMU/Compass**: 9-DOF IMU module (I2C)
  - Recommended: BNO055, MPU-9250, or LSM9DS1

#### Camera System
- **Pi Camera Module v3** (primary)
- **USB Cameras** (compatible as secondary)
- **Camera Cable**: 15-pin to 22-pin adapter if needed

#### Proximity & Safety
- **Ultrasonic Sensors**: 4x HC-SR04 or equivalent
- **Safety Switch**: Emergency stop button
- **Perimeter Wire Sensors** (optional)

#### Motor & Power
- **Motor Controllers**: Dual H-bridge motor drivers
  - Recommended: L298N, BTS7960, or similar
- **Motors**: DC geared motors with encoders
- **Battery**: 12V LiFePO4 or Lead-Acid battery
- **Power Management Board**: 12V to 5V converter with monitoring

#### Optional Hardware
- **LiDAR Module**: RPLidar A1/A2 or similar
- **Weather Station**: I2C weather sensors
- **Cellular Modem**: 4G/LTE USB modem for remote connectivity
- **Solar Panel**: 12V solar charging system

## Initial Setup

### 1. Prepare Raspberry Pi OS

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
   # Enable: Camera, I2C, SPI, GPIO Serial
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
   
   # Install Node.js for frontend
   curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
   sudo apt install -y nodejs
   ```

### 2. Hardware Assembly

1. **Mount Sensors**
   - Connect GPS module via USB or GPIO UART
   - Wire IMU to I2C pins (SDA: GPIO 2, SCL: GPIO 3)
   - Connect ultrasonic sensors to GPIO pins
   - Install camera module

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
git clone https://github.com/lawnberry/lawnberry-pi.git lawnberry
cd lawnberry/lawnberry-rebuild
```

### 2. Backend Setup
```bash
# Create Python virtual environment
cd backend
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Initialize database
python -m backend.src.core.persistence init

# Run hardware self-test
SIM_MODE=0 python -m backend.src.services.hw_selftest
```

### 3. Frontend Setup
```bash
cd ../frontend
npm install
npm run build
```

### 4. Install systemd Services
```bash
cd ../systemd
sudo bash install_services.sh
```

## Basic Configuration

### 1. Initial System Config
```bash
# Start configuration wizard
sudo lawnberry-pi config --setup-wizard

# This will guide you through:
# - Network configuration
# - Basic authentication setup
# - Hardware calibration
# - Safety settings
```

### 2. Test Installation
```bash
# Start core services
sudo systemctl start lawnberry-database
sudo systemctl start lawnberry-backend
sudo systemctl start lawnberry-frontend

# Check service status
sudo systemctl status lawnberry-backend

# Test API
curl http://localhost:8081/api/v1/status

# Access web interface
# Open browser to http://<pi-ip>:3000
```

### 3. Hardware Calibration

1. **GPS Calibration**
   ```bash
   # Test GPS acquisition
   lawnberry-pi calibrate gps --test-acquisition
   
   # Set home position
   lawnberry-pi calibrate gps --set-home-position
   ```

2. **IMU Calibration**
   ```bash
   # Calibrate magnetometer (follow on-screen instructions)
   lawnberry-pi calibrate imu --magnetometer
   
   # Calibrate accelerometer and gyroscope
   lawnberry-pi calibrate imu --accel-gyro
   ```

3. **Motor Calibration**
   ```bash
   # Calibrate motor speeds and directions
   lawnberry-pi calibrate motors --speed-test
   
   # Test differential steering
   lawnberry-pi calibrate motors --steering-test
   ```

## Advanced Features

For detailed configuration of advanced features, see the dedicated guides:

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
   sudo cat /dev/ttyACM0  # or /dev/ttyUSB0
   
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
   
   # Test IMU communication
   lawnberry-pi test imu --verbose
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

### Performance Optimization

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
cp -r /home/pi/lawnberry-v1/data /home/pi/lawnberry-v1-backup/
```

### Import Configuration
```bash
# Import v1 settings to v2
lawnberry-pi migrate from-v1 --config-path /home/pi/lawnberry-v1/config.json

# Import zone definitions
lawnberry-pi migrate zones --from-v1-db /home/pi/lawnberry-v1/data/zones.db

# Import job history (optional)
lawnberry-pi migrate jobs --from-v1-db /home/pi/lawnberry-v1/data/jobs.db
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

- **Documentation**: `/home/pi/lawnberry/docs/`
- **Configuration**: `lawnberry-pi config --help`
- **Logs**: `sudo journalctl -u lawnberry-backend -f`
- **Web Interface**: `http://<pi-ip>:3000`
- **API Documentation**: `http://<pi-ip>:8081/docs`

For additional help, consult the troubleshooting guides or check system logs for detailed error information.