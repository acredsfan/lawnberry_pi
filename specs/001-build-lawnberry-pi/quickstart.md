# LawnBerry Pi v2 Quickstart Guide

## Prerequisites
- Raspberry Pi 5 (8GB) or Pi 4B (2-8GB minimum) running Pi OS Bookworm (64-bit)
- MicroSD card (32GB minimum, Class 10 recommended)
- Required sensors: BNO085 IMU, INA3221 power monitor, VL53L0X ToF sensors, hall effect encoders
- Motor control: Cytron MDDRC10 via RoboHAT RP2040
- Pi Camera module v2 or v3
- Optional: USB Coral TPU or Hailo AI Hat for AI acceleration

## Installation

### 1. System Setup
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y git python3.11 python3.11-venv libcamera-dev

# Clone repository
git clone https://github.com/acredsfan/lawnberry_pi.git
cd lawnberry_pi/v2/lawnberry-v2
```

### 2. Automated Installation
```bash
# Run bootstrap script (handles all setup)
sudo ./scripts/pi_bootstrap.sh

# Script performs:
# - UV package manager installation
# - Python virtual environment creation
# - Dependency installation with hardware detection
# - SystemD service installation
# - Configuration file creation
# - Hardware interface setup
```

### 3. Configuration
```bash
# Copy example configuration
cp .env.example .env

# Edit configuration for your hardware setup
nano .env

# Key settings to configure:
# - HARDWARE_CONFIG_PATH=/spec/hardware.yaml
# - CORAL_TPU_ENABLED=true  # if Coral TPU available
# - HAILO_HAT_ENABLED=false # if Hailo AI Hat available
# - CAMERA_RESOLUTION=1280x720
# - LOG_LEVEL=INFO
```

## First Run

### 1. Start Services
```bash
# Enable and start all services
sudo systemctl enable mower-core camera-stream webui
sudo systemctl start mower-core camera-stream webui

# Check service status
sudo systemctl status mower-core
sudo systemctl status camera-stream
sudo systemctl status webui
```

### 2. Access Web Interface
1. Open browser to `http://<pi-ip-address>:8000`
2. Default interface shows retro 80s styled dashboard
3. Verify all telemetry data is displaying correctly
4. Check camera stream is active at `http://<pi-ip-address>:8001/camera`

### 3. Hardware Verification
**System Status Check:**
- Navigate to System tab in web interface
- Verify all sensors show "Active" status
- Check AI acceleration tier (Coral TPU > Hailo > CPU TFLite)
- Confirm motor controllers respond to test commands

**Sensor Calibration:**
- IMU calibration: Place mower on level surface, click "Calibrate IMU"
- Power calibration: Connect to known voltage source, click "Calibrate Power"
- ToF sensor verification: Check distance readings match physical measurements
- Encoder calibration: Manually rotate wheels, verify count increments

## Safety Testing

### 1. Emergency Stop Test
```bash
# Test emergency stop functionality
curl -X POST http://localhost:8000/api/v1/navigation/emergency_stop \
  -H "Content-Type: application/json" \
  -d '{"reason": "safety_test"}'

# Verify immediate motor shutdown
# Check web interface shows emergency state
```

### 2. Tilt Detection Test
- Manually tilt mower beyond safety threshold (30°)
- Verify automatic motor shutdown
- Confirm safety alert appears in web interface
- Test manual reset functionality

### 3. Obstacle Detection Test
- Place object in front of mower
- Verify ToF sensors detect obstacle
- Check AI vision system identifies object (if AI acceleration available)
- Confirm obstacle avoidance behavior

## Basic Operation

### 1. Manual Control
1. In web interface, switch to "Manual" mode
2. Use directional controls to test movement
3. Verify left/right wheel speed controls
4. Test cutting blade on/off functionality
5. Monitor real-time telemetry during operation

### 2. Autonomous Operation Setup
1. Define mowing area boundaries:
   ```json
   {
     "area_bounds": {
       "min_x": 0, "max_x": 20,
       "min_y": 0, "max_y": 15
     }
   }
   ```
2. Select mowing pattern (spiral, zigzag, random)
3. Set cutting height and maximum speed
4. Enable safety monitoring
5. Start autonomous operation

### 3. Monitoring and Control
- **Real-time telemetry**: Battery, position, sensor readings
- **Camera feed**: Live video with AI object detection overlay
- **Safety alerts**: Immediate notification of any safety events
- **Progress tracking**: Area coverage and estimated completion time

## Validation Tests

### Test 1: Sensor Data Accuracy
**Expected**: All sensor readings within expected ranges
- IMU: Acceleration ~9.8 m/s² on Z-axis when level
- Power: Battery voltage matches multimeter reading (±0.1V)
- ToF: Distance readings accurate to ±5cm
- Encoders: Count increments match wheel rotation

### Test 2: AI Processing Performance
**Expected**: Object detection working with acceptable latency
- Coral TPU: <50ms inference time (if available)
- Hailo Hat: <100ms inference time (if available)  
- CPU TFLite: <200ms inference time (fallback)
- Detection confidence >70% for test objects

### Test 3: Communication Latency
**Expected**: Real-time response for control commands
- WebSocket telemetry updates: <100ms latency
- Manual control response: <50ms from command to motor response
- Emergency stop: <10ms from command to motor shutdown
- Web interface responsiveness: <200ms for UI updates

### Test 4: Service Integration
**Expected**: All services communicate properly
- mower-core publishes telemetry data
- camera-stream provides video feed with AI overlay
- webui displays integrated data from both services
- Service restart doesn't lose critical state

## Troubleshooting

### Common Issues

**Service won't start:**
```bash
# Check service logs
journalctl -u mower-core -f
journalctl -u camera-stream -f
journalctl -u webui -f

# Verify Python environment
source /opt/lawnberry/venv/bin/activate
python -c "import lawnberry; print('OK')"
```

**Sensor not detected:**
```bash
# Check I2C devices
sudo i2cdetect -y 1

# Verify GPIO permissions
sudo usermod -a -G gpio lawnberry
sudo usermod -a -G i2c lawnberry
```

**AI acceleration not working:**
```bash
# Check Coral TPU
lsusb | grep "Global Unichip"

# Verify Coral environment
source /opt/coral/venv/bin/activate
python -c "import tflite_runtime.interpreter as tflite; print('Coral OK')"

# Check Hailo detection
lspci | grep Hailo
```

**Web interface not accessible:**
```bash
# Check firewall
sudo ufw status
sudo ufw allow 8000
sudo ufw allow 8001

# Verify port binding
netstat -tlnp | grep :8000
```

### Performance Optimization

**For Pi 4B:**
- Reduce camera resolution to 640x480
- Lower AI inference frequency
- Increase telemetry update intervals
- Disable unused features in configuration

**For optimal battery life:**
- Enable power-saving mode in configuration
- Reduce camera FPS during autonomous operation
- Use CPU TFLite instead of accelerators when battery <30%

## Migration from v1

If upgrading from LawnBerry Pi v1:

1. **Backup existing configuration:**
   ```bash
   sudo systemctl stop lawnberry-v1
   cp -r /opt/lawnberry-v1/config /tmp/lawnberry-v1-backup
   ```

2. **Run migration script:**
   ```bash
   ./scripts/migrate_from_v1.sh /tmp/lawnberry-v1-backup
   ```

3. **Verify migration:**
   - Check configuration transferred correctly
   - Verify historical data imported
   - Test all hardware interfaces
   - Confirm custom settings preserved

## Next Steps

After successful installation and testing:

1. **Documentation**: Review full documentation at `/docs`
2. **Customization**: Modify configuration for specific lawn requirements
3. **Monitoring**: Set up log rotation and performance monitoring
4. **Maintenance**: Schedule regular calibration and system updates
5. **Advanced Features**: Explore weather integration, scheduling, and remote monitoring