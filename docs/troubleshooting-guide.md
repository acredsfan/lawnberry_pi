# LawnBerryPi Troubleshooting Guide

This guide helps you diagnose and fix common issues with your LawnBerryPi system. Most problems can be resolved by following these step-by-step procedures.

## Quick Diagnostic Checklist

Before diving into specific problems, run through this quick checklist:

- [ ] **Power**: Is the system powered on and LED indicators lit?
- [ ] **Network**: Can you access the web interface at `http://[pi-ip]:8080`?
- [ ] **GPS**: Does the dashboard show GPS lock with coordinates?
- [ ] **Battery**: Is battery charge above 20%?
- [ ] **Weather**: Are current conditions suitable for mowing?
- [ ] **Emergency Stop**: Is the emergency stop button released?
- [ ] **Services**: Are all systemd services running? (`sudo systemctl status lawnberry-*`)
- [ ] **Logs**: Check recent error messages in `/var/log/lawnberry/`

## Problem Categories

1. [Power and Charging Issues](#power-and-charging-issues)
2. [Network and Connectivity Problems](#network-and-connectivity-problems)
3. [GPS and Navigation Issues](#gps-and-navigation-issues)
4. [Sensor and Hardware Problems](#sensor-and-hardware-problems)
5. [Mowing Performance Issues](#mowing-performance-issues)
6. [Weather Service Problems](#weather-service-problems)
7. [Coral TPU Issues](#coral-tpu-issues)
8. [Software and Interface Issues](#software-and-interface-issues)

---

## Power and Charging Issues

### Problem: System Won't Power On

**Symptoms**: No LED lights, web interface inaccessible, no response to buttons

**Diagnostic Steps**:

1. **Check Main Power**
   ```
   Is main power switch ON? → [YES] Continue to step 2
                           → [NO] Turn on main power, test system
   ```

2. **Check Battery Voltage**
   - Use multimeter to check battery voltage
   - **Expected**: 12.8V - 14.4V for LiFePO4
   ```
   Battery voltage > 12V? → [YES] Continue to step 3
                         → [NO] Charge battery or check charging system
   ```

3. **Check DC-DC Converter**
   - Measure output voltage of 5V converter
   ```
   5V output present? → [YES] Continue to step 4
                     → [NO] Replace DC-DC converter
   ```

4. **Check Raspberry Pi Power**
   - Look for power LED on Raspberry Pi
   ```
   Power LED lit? → [YES] System should boot - check network connection
                 → [NO] Check power cable connections, try different power supply
   ```

### Problem: Battery Not Charging

**Symptoms**: Battery voltage decreasing, solar panel not providing power

**Diagnostic Steps**:

1. **Check Solar Panel Output**
   - Measure voltage across solar panel terminals in sunlight
   - **Expected**: 18-22V in direct sunlight
   ```
   Panel voltage > 15V? → [YES] Continue to step 2
                       → [NO] Clean panel, check for shading/damage
   ```

2. **Check Charge Controller**
   - Look for LED indicators on charge controller
   - Check display (if equipped) for status
   ```
   Controller shows charging? → [YES] Continue to step 3
                             → [NO] Check panel connections, replace controller
   ```

3. **Check Battery Connections**
   - Verify tight connections at battery terminals
   - Look for corrosion or loose wires
   ```
   Connections secure? → [YES] Continue to step 4
                      → [NO] Clean and tighten connections
   ```

4. **Test Battery Health**
   - Check voltage under load
   - Monitor charging behavior
   ```
   Battery accepts charge? → [YES] Monitor performance over time
                          → [NO] Replace battery (may be end of life)
   ```

### Problem: Rapid Battery Drain

**Symptoms**: Battery depletes faster than expected, short runtime

**Solutions**:
- **Check for high current draw**: Use power monitor to identify excessive power usage
- **Inspect motor efficiency**: Ensure wheels turn freely, check for obstructions
- **Verify sleep mode**: System should enter low-power mode when not mowing
- **Update software**: Newer versions may have power optimizations

---

## Network and Connectivity Problems

### Problem: Cannot Access Web Interface

**Symptoms**: Browser shows "site can't be reached" or times out

**Diagnostic Flowchart**:

```
Can you ping the Raspberry Pi IP?
├─ [YES] → Is port 3000 accessible?
│          ├─ [YES] → Check browser cache/cookies
│          └─ [NO] → Check web service status
└─ [NO] → Is Pi connected to network?
           ├─ [YES] → Check firewall settings
           └─ [NO] → Fix network connection
```

**Step-by-Step Solutions**:

1. **Find Raspberry Pi IP Address**
   ```bash
   # On the Raspberry Pi directly:
   hostname -I
   
   # Or check your router's admin panel for connected devices
   ```

2. **Test Network Connection**
   ```bash
   # From another computer on same network:
   ping [raspberry-pi-ip]
   
   # Should show response times if connected
   ```

3. **Check Web Services**
   ```bash
   # On the Raspberry Pi:
   sudo systemctl status lawnberry-web-ui
   sudo systemctl status lawnberry-web-api
   
   # Restart if needed:
   sudo systemctl restart lawnberry-web-ui
   ```

4. **Check Firewall**
   ```bash
   # Allow web interface port:
   sudo ufw allow 3000
   sudo ufw allow 8000
   ```

### Problem: Frequent Network Disconnections

**Symptoms**: Web interface periodically becomes unavailable, WiFi drops

**Solutions**:
- **Check WiFi signal strength**: Move closer to router or add WiFi extender
- **Update network configuration**: Edit `/etc/wpa_supplicant/wpa_supplicant.conf`
- **Set static IP**: Prevents IP changes that break bookmarks
- **Check power saving**: Disable WiFi power management with `iwconfig wlan0 power off`

---

## GPS and Navigation Issues

### Problem: No GPS Lock

**Symptoms**: Dashboard shows "GPS: SEARCHING" or "GPS: NO FIX"

**Diagnostic Steps**:

1. **Check GPS Hardware Connection**
   ```bash
   # Verify GPS device is detected:
   ls /dev/ttyACM*
   # Should show /dev/ttyACM0 (or similar)
   ```

2. **Test GPS Data Reception**
   ```bash
   # Check for GPS data:
   sudo cat /dev/ttyACM0
   # Should show NMEA sentences like $GPGGA, $GPRMC
   ```

3. **Environmental Factors**
   ```
   Is mower outdoors with clear sky view? → [YES] Continue to step 4
                                         → [NO] Move to open area, wait 5-10 minutes
   ```

4. **Check Satellite Status**
   - In web interface, go to Settings → Hardware → GPS Status
   - Look for satellite count and signal strength
   ```
   Satellites visible > 4? → [YES] Wait for lock (up to 15 minutes)
                          → [NO] Check antenna connection, try different location
   ```

### Problem: Poor GPS Accuracy

**Symptoms**: Position jumps around, boundaries not followed precisely

**Solutions**:
- **Wait for better fix**: GPS accuracy improves over time (cold start takes longer)
- **Check for interference**: Move away from buildings, metal structures, power lines
- **Clean antenna**: Ensure GPS antenna is clean and unobstructed
- **Enable corrections**: If available, enable RTK corrections for centimeter accuracy

### Problem: Mower Doesn't Follow Boundaries

**Symptoms**: Mower goes outside defined boundaries or misses areas

**Diagnostic Steps**:

1. **Verify Boundary Definition**
   - Check boundary on map - does it look correct?
   - Ensure boundary is closed (start and end points connect)

2. **Check GPS Accuracy**
   - Current accuracy should be < 3 meters for reliable operation
   - Wait for better GPS fix before mowing

3. **Calibrate Compass**
   - Go to Settings → Hardware → IMU Calibration
   - Follow calibration procedure (figure-8 motions)

4. **Test in Manual Mode**
   - Use manual control to verify mower responds correctly
   - Check that position updates properly on map

---

## Sensor and Hardware Problems

### Problem: Obstacle Detection Not Working

**Symptoms**: Mower hits obstacles, doesn't detect objects in path

**Diagnostic Steps**:

1. **Test ToF Sensors**
   ```bash
   # Check I2C devices:
   i2cdetect -y 1
   # Should show devices at 0x29 and 0x30 (ToF sensors)
   ```

2. **Clean Sensor Lenses**
   - Use soft, dry cloth to clean ToF sensor windows
   - Remove grass clippings and debris

3. **Check Sensor Readings**
   - In web interface, go to Hardware Status
   - Verify distance readings update when objects approach

4. **Calibrate Detection Distance**
   - Adjust sensitivity in Settings → Safety → Obstacle Detection
   - Test with various objects at different distances

### Problem: Camera Issues

**Symptoms**: No camera feed, poor image quality, object detection not working

**Solutions**:

1. **Check Camera Connection**
   ```bash
   # Test camera:
   vcgencmd get_camera
   # Should show "supported=1 detected=1"
   ```

2. **Test Camera Capture**
   ```bash
   # Capture test image:
   raspistill -o test.jpg
   # Check if image is created
   ```

3. **Clean Camera Lens**
   - Use microfiber cloth to clean lens
   - Check for scratches or damage

4. **Adjust Camera Settings**
   - In Settings → Hardware → Camera
   - Adjust brightness, contrast, focus for conditions

### Problem: Environmental Sensor Errors

**Symptoms**: No temperature/humidity readings, "Sensor Error" messages

**Diagnostic Steps**:

1. **Check I2C Connection**
   ```bash
   i2cdetect -y 1
   # Should show device at 0x76 (BME280)
   ```

2. **Test Sensor Communication**
   ```bash
   # Basic sensor test:
   python3 -c "
   import smbus
   bus = smbus.SMBus(1)
   try:
       data = bus.read_byte(0x76)
       print('BME280 responding')
   except:
       print('BME280 not responding')
   "
   ```

3. **Check Sensor Mounting**
   - Ensure sensor is properly seated
   - Check for loose connections
   - Verify sensor is not damaged by moisture

---

## Mowing Performance Issues

### Problem: Poor Cut Quality

**Symptoms**: Uneven cutting, grass not cut properly, missed patches

**Diagnostic Flowchart**:

```
Is blade sharp and undamaged?
├─ [NO] → Replace or sharpen blade
└─ [YES] → Is cutting height appropriate?
           ├─ [NO] → Adjust cutting height
           └─ [YES] → Is mowing speed too fast?
                      ├─ [YES] → Reduce speed to 0.8-1.2 m/s
                      └─ [NO] → Check mowing pattern overlap
```

**Solutions by Symptom**:

- **Streaking/Uneven cut**: Increase overlap between passes to 15-20%
- **Grass tips brown after cutting**: Blade is dull - sharpen or replace
- **Missed patches**: Use checkerboard pattern or reduce turning radius
- **Scalping**: Raise cutting height, slow down on uneven terrain

### Problem: Mower Gets Stuck Frequently

**Symptoms**: Mower stops with error messages, requires manual intervention

**Common Causes and Solutions**:

1. **Wheel Slip on Slopes**
   - Avoid slopes steeper than 20 degrees
   - Mow across slopes instead of up/down
   - Add traction aids if needed

2. **Stuck on Obstacles**
   - Remove small obstacles from yard
   - Add to no-go zones if permanent
   - Adjust obstacle detection sensitivity

3. **Wet Grass Conditions**
   - Wait for grass to dry before mowing
   - Enable weather monitoring to skip wet periods
   - Consider drainage improvements in problem areas

### Problem: Inefficient Mowing Patterns

**Symptoms**: Takes too long to complete, battery runs out, poor coverage

**Optimization Steps**:

1. **Choose Appropriate Pattern**
   - **Large open areas**: Parallel pattern (most efficient)
   - **Complex shapes**: Spiral or random pattern
   - **Best cut quality**: Checkerboard (slower but thorough)

2. **Optimize Route Planning**
   - Review mowing history to identify inefficiencies
   - Adjust boundary to eliminate narrow areas
   - Consider splitting large areas into zones

3. **Adjust Speed vs. Quality**
   - Faster speeds cover more area but may reduce cut quality
   - Optimal speed is usually 1.0-1.5 m/s
   - Slower speeds for thick or wet grass

---

## Weather Service Problems

### Problem: Weather Data Not Available

**Symptoms**: Dashboard shows "Weather: Unknown" or outdated information

**Diagnostic Steps**:

1. **Check API Key**
   ```bash
   # Verify environment variable is set:
   echo $OPENWEATHER_API_KEY
   # Should show your API key (not empty)
   ```

2. **Test API Connection**
   ```bash
   # Test weather API:
   curl "http://api.openweathermap.org/data/2.5/weather?q=London&appid=YOUR_API_KEY"
   # Should return JSON weather data
   ```

3. **Check Service Status**
   ```bash
   # Check weather service:
   sudo systemctl status lawnberry-weather
   # Look for error messages in logs
   ```

4. **Verify Internet Connection**
   ```bash
   # Test internet connectivity:
   ping 8.8.8.8
   # Should show response times
   ```

### Problem: Inaccurate Weather Information

**Symptoms**: Weather data doesn't match local conditions

**Solutions**:
- **Check location settings**: Verify GPS coordinates are correct for weather lookup
- **Update location manually**: Set specific coordinates in weather settings
- **Choose different weather source**: Switch between available weather providers
- **Calibrate local sensors**: Use BME280 data to supplement weather service

---

## Coral TPU Issues

### Problem: Coral TPU Not Detected

**Symptoms**: System shows "CPU mode" in web interface, no Coral acceleration, slower inference

**Diagnostic Steps**:

1. **Check Hardware Connection**
   ```bash
   # Check for USB Accelerator
   lsusb | grep -i "google\|coral"
   ```
   ```
   Device listed? → [YES] Continue to step 2
                 → [NO] Check USB connection, try different port
   ```

2. **Check Runtime Installation**
   ```bash
   # Verify Edge TPU runtime
   dpkg -l | grep libedgetpu
   ```
   ```
   Runtime installed? → [YES] Continue to step 3
                     → [NO] Install runtime: sudo apt-get install libedgetpu1-std
   ```

3. **Check Python Packages**
   ```bash
   # Test PyCoral import
   python3 -c "from pycoral.utils import edgetpu; print('PyCoral working')"
   ```
   ```
   Import successful? → [YES] Continue to step 4
                     → [NO] Install packages: sudo apt-get install python3-pycoral
   ```

4. **Test Hardware Enumeration**
   ```bash
   # Check device enumeration
   python3 -c "from pycoral.utils import edgetpu; print(f'Found {len(edgetpu.list_edge_tpus())} TPU(s)')"
   ```
   ```
   TPU count > 0? → [YES] Hardware working - check application logs
                 → [NO] Check udev rules and permissions
   ```

### Problem: Coral Package Installation Fails

**Symptoms**: `apt-get install python3-pycoral` fails, repository errors

**Diagnostic Steps**:

1. **Check Repository Configuration**
   ```bash
   # Verify Coral repository
   ls /etc/apt/sources.list.d/coral-edgetpu.list
   cat /etc/apt/sources.list.d/coral-edgetpu.list
   ```
   ```
   Repository file exists? → [YES] Continue to step 2
                          → [NO] Add repository (see Manual Installation section)
   ```

2. **Update Package Lists**
   ```bash
   # Refresh package database
   sudo apt-get update
   ```
   ```
   Update successful? → [YES] Continue to step 3
                     → [NO] Check internet connection, fix repository configuration
   ```

3. **Check Platform Compatibility**
   ```bash
   # Verify Pi OS Bookworm
   lsb_release -a | grep bookworm
   python3 --version
   ```
   ```
   Bookworm + Python 3.11+? → [YES] Continue to step 4
                            → [NO] Upgrade to Pi OS Bookworm (required)
   ```

4. **Try Manual Installation**
   ```bash
   # Run installation scripts
   cd /home/pi/lawnberry-pi
   sudo ./scripts/install_coral_runtime.sh
   sudo ./scripts/install_coral_system_packages.sh
   ```

### Problem: PyCoral Requires Python 3.9 but pyenv Build Fails (bz2/ssl/readline missing)

**Symptoms**: During Coral optional setup, `pyenv install 3.9.18` completes with warnings/errors:

- `ModuleNotFoundError: No module named '_bz2'`
- `ModuleNotFoundError: No module named '_ssl'`
- `ModuleNotFoundError: No module named '_ctypes'`
- `ModuleNotFoundError: No module named 'readline'`
- `ModuleNotFoundError: No module named '_curses'`

This means Debian build prerequisites were missing when compiling Python.

**Fix (Debian 12 Bookworm)**:

1. Install build prerequisites:
   ```bash
   sudo apt-get update
   sudo apt-get install -y \
     make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
     wget curl llvm libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev \
     liblzma-dev libgdbm-dev libnss3-dev ca-certificates
   ```

2. Re-run the installer Coral step or build Python 3.9 manually via pyenv:
   ```bash
   # Ensure pyenv is on PATH for current shell
   export PYENV_ROOT="$HOME/.pyenv"
   export PATH="$PYENV_ROOT/bin:$PATH"
   eval "$(pyenv init -)"
   eval "$(pyenv virtualenv-init -)"

   # Rebuild Python 3.9.18
   pyenv uninstall -f 3.9.18 || true
   pyenv install 3.9.18
   ```

3. Validate core modules in the Coral venv:
   ```bash
   pyenv virtualenv-delete -f coral-python39 || true
   pyenv virtualenv 3.9.18 coral-python39
   pyenv activate coral-python39
   python - <<'PY'
import sys
failed = []
for m in ["ssl","bz2","readline","curses","ctypes"]:
    try: __import__(m)
    except Exception as e: failed.append((m, str(e)))
print("OK" if not failed else failed)
PY
   ```

If any module import fails, re-check step 1 packages and reinstall Python 3.9.

### Note: Coral APT Repository Setup (Avoid apt-key Warning)

If you see `Key is stored in legacy trusted.gpg keyring` or `apt-key is deprecated`, switch to the modern signed-by method:

```bash
sudo mkdir -p /usr/share/keyrings
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/coral-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/coral-archive-keyring.gpg] https://packages.cloud.google.com/apt coral-edgetpu-stable main" | sudo tee /etc/apt/sources.list.d/coral-edgetpu.list >/dev/null
sudo apt-get update
```

### Problem: Coral Performance Issues

**Symptoms**: Coral detected but inference is slow or unreliable

**Diagnostic Steps**:

1. **Check Performance Mode**
   ```bash
   # Check current runtime package
   dpkg -l | grep libedgetpu
   ```
   ```
   Using libedgetpu1-std? → [YES] Consider libedgetpu1-max for better performance
                         → [NO] Check if libedgetpu1-max is causing thermal issues
   ```

2. **Monitor Temperature**
   ```bash
   # Check system temperature
   vcgencmd measure_temp
   ```
   ```
   Temp < 70°C? → [YES] Temperature OK, continue to step 3
               → [NO] Switch to standard mode: sudo apt-get install --reinstall libedgetpu1-std
   ```

3. **Test Inference Speed**
   ```bash
   # Run performance test
   cd /home/pi/lawnberry-pi
   python3 scripts/test_tpu_integration.py
   ```
   ```
   Inference < 50ms? → [YES] Performance acceptable
                    → [NO] Check model optimization, thermal throttling
   ```

4. **Check USB Connection Quality**
   - Try different USB ports (USB 3.0 preferred)
   - Use shorter USB cable
   - Avoid USB hubs if possible
   ```
   Direct USB 3.0 connection? → [YES] Connection optimized
                              → [NO] Use direct USB 3.0 port
   ```

### Problem: CPU Fallback Not Working

**Symptoms**: System fails when Coral is not available, no graceful degradation

**Diagnostic Steps**:

1. **Check Fallback Packages**
   ```bash
   # Verify TensorFlow Lite availability
   python3 -c "import tflite_runtime.interpreter as tflite; print('CPU fallback available')"
   ```
   ```
   Import successful? → [YES] Continue to step 2
                     → [NO] Install: pip3 install tflite-runtime
   ```

2. **Test CPU Inference**
   ```bash
   # Force CPU mode
   cd /home/pi/lawnberry-pi
   CORAL_TPU_ENABLED=false python3 -c "from src.vision.coral_tpu_manager import CoralTPUManager; print('CPU mode working')"
   ```
   ```
   CPU mode works? → [YES] Fallback functional
                  → [NO] Check application configuration
   ```

3. **Check Configuration**
   ```bash
   # Verify environment settings
   grep CORAL_TPU_ENABLED .env
   ```
   ```
   Setting found? → [YES] Ensure CORAL_TPU_ENABLED=true for auto-detection
                 → [NO] Add CORAL_TPU_ENABLED=true to .env file
   ```

### Problem: Migration from Pip Packages Fails

**Symptoms**: Old pip-installed packages conflict with system packages

**Diagnostic Steps**:

1. **Check Current Package State**
   ```bash
   # List pip-installed Coral packages
   pip3 list | grep -E "(pycoral|tflite)"
   # List system packages
   dpkg -l | grep -E "(pycoral|edgetpu)"
   ```

2. **Run Migration Script**
   ```bash
   # Automatic migration
   cd /home/pi/lawnberry-pi
   python3 scripts/migrate_coral_packages.py --verbose
   ```

3. **Manual Cleanup if Migration Fails**
   ```bash
   # Remove pip packages
   pip3 uninstall pycoral tflite-runtime -y
   
   # Install system packages
   sudo apt-get install python3-pycoral
   
   # Verify installation
   python3 scripts/verify_coral_installation.py
   ```

### Quick Coral TPU Reference

**Check Status**:
```bash
# All-in-one status check
python3 scripts/verify_coral_installation.py

# Quick hardware check
lsusb | grep -i google && echo "Hardware detected" || echo "No hardware found"

# Quick software check  
python3 -c "from pycoral.utils import edgetpu; print(f'{len(edgetpu.list_edge_tpus())} TPU(s) available')" 2>/dev/null || echo "Software not working"
```

**Common Solutions**:
- **No hardware detected**: Check USB connection, try different port
- **Import errors**: Reinstall system packages: `sudo apt-get install --reinstall python3-pycoral`
- **Permission errors**: Add user to plugdev group: `sudo usermod -a -G plugdev $USER`
- **Performance issues**: Switch to standard mode: `sudo apt-get install --reinstall libedgetpu1-std`
- **Repository errors**: Re-add repository and update: `sudo ./scripts/install_coral_runtime.sh`

**Performance Expectations**:
- **Coral TPU**: 10-30ms inference time for typical models
- **CPU Fallback**: 100-300ms inference time (still functional)
- **System Impact**: Coral reduces CPU usage by 80-90%

---

## Software and Interface Issues

### Problem: Web Interface Slow or Unresponsive

**Symptoms**: Pages load slowly, buttons don't respond, interface freezes

**Solutions**:

1. **Check System Resources**
   ```bash
   # Check CPU and memory usage:
   top
   # Look for high CPU or memory usage
   ```

2. **Restart Services**
   ```bash
   # Restart web services:
   sudo systemctl restart lawnberry-web-ui
   sudo systemctl restart lawnberry-web-api
   ```

3. **Clear Browser Cache**
   - Clear browser cache and cookies
   - Try different browser or incognito mode
   - Refresh page with Ctrl+F5 (force refresh)

4. **Check Network Bandwidth**
   - Camera streaming uses significant bandwidth
   - Reduce camera quality if network is slow
   - Disable camera feed if not needed

### Problem: Settings Not Saving

**Symptoms**: Configuration changes don't persist after restart

**Solutions**:
- **Check file permissions**: Ensure configuration files are writable
- **Verify disk space**: Check available storage with `df -h`
- **Restart configuration service**: `sudo systemctl restart lawnberry-config`
- **Check for SD card errors**: Run `fsck` to check filesystem integrity

### Problem: Software Updates Failing

**Symptoms**: Update process errors, version doesn't change

**Solutions**:
- **Check internet connection**: Ensure stable connection to download servers
- **Free up disk space**: Updates require temporary storage space
- **Check Git status**: Ensure local changes don't conflict with updates
- **Manual update**: Use `git pull` and restart services manually

---

## Hardware Diagnostic Commands

Use these commands to diagnose hardware issues:

### I2C Device Detection
```bash
# Scan for I2C devices:
i2cdetect -y 1

# Expected devices:
# 0x3c - SSD1306 Display
# 0x40 - INA3221 Power Monitor  
# 0x76 - BME280 Environmental Sensor
```

### GPIO Testing
```bash
# Test GPIO pin (example for pin 24):
echo 24 > /sys/class/gpio/export
echo out > /sys/class/gpio/gpio24/direction
echo 1 > /sys/class/gpio/gpio24/value
echo 0 > /sys/class/gpio/gpio24/value
echo 24 > /sys/class/gpio/unexport
```

### Serial Device Testing
```bash
# List serial devices:
ls /dev/tty*

# Test GPS data:
sudo cat /dev/ttyACM0 | head -20
```

### Camera Testing
```bash
# Test camera:
raspistill -o test.jpg -t 1
vcgencmd get_camera
```

### System Health Check
```bash
# Check system temperature:
vcgencmd measure_temp

# Check voltage:
vcgencmd measure_volts

# Check memory:
free -h

# Check disk space:
df -h
```

---

## Emergency Recovery Procedures

### Safe Mode Boot

If system won't start normally:

1. **Insert SD card into computer**
2. **Edit cmdline.txt** on boot partition
3. **Add to end of line**: `init=/bin/bash`
4. **Boot Raspberry Pi** - will start in emergency shell
5. **Mount filesystem read-write**: `mount -o remount,rw /`
6. **Fix configuration issues**
7. **Remove init parameter** from cmdline.txt
8. **Reboot normally**

### Factory Reset

To restore system to original state:

1. **Backup important data**:
   ```bash
   cp -r /home/pi/lawnberry-pi/config /home/pi/config-backup
   ```

2. **Reset configuration**:
   ```bash
   cd /home/pi/lawnberry-pi
   git checkout -- .
   ./install_system_integration.sh
   ```

3. **Reconfigure environment variables**:
   ```bash
   cp .env.example .env
   nano .env  # Add your API keys
   ```

### Hardware Reset Procedure

If hardware seems unresponsive:

1. **Power off completely** (disconnect all power sources)
2. **Wait 30 seconds** for capacitors to discharge
3. **Check all connections** visually
4. **Reconnect power** starting with battery, then Pi
5. **Monitor boot sequence** for error messages
6. **Test each subsystem** individually

---

## Google Maps API Issues

### Map Not Loading or Shows Errors

**Symptoms**: Web UI shows map errors, falls back to OpenStreetMap, or displays "API key" messages.

**Solutions**:

1. **Check API Key Configuration**:
   ```bash
   # Verify API key is set in environment
   grep REACT_APP_GOOGLE_MAPS_API_KEY .env
   # Should show your API key (not the placeholder)
   ```

2. **Validate API Key Format**:
   - Google API keys start with "AIza"
   - Should be 39 characters long
   - No spaces or special characters except hyphens

3. **Test API Key**:
   ```bash
   # Run environment setup to validate key
   python3 scripts/setup_environment.py
   ```

### API Key Denied Errors

**Error**: "REQUEST_DENIED" or "API key denied"

**Solutions**:

1. **Check API Restrictions**:
   - Go to Google Cloud Console → Credentials
   - Click on your API key
   - Verify HTTP referrer restrictions include your Pi's IP
   - Add: `http://[your-pi-ip]:3000/*`

2. **Verify Enabled APIs**:
   - Go to Google Cloud Console → APIs & Services → Library
   - Ensure these APIs are enabled:
     - Maps JavaScript API
     - Geocoding API
     - Places API (optional)

3. **Check Billing Account**:
   - Even free tier requires valid billing account
   - Go to Google Cloud Console → Billing
   - Verify billing account is active

### Quota Exceeded Errors

**Error**: "OVER_QUERY_LIMIT" or quota exceeded messages

**Solutions**:

1. **Check Usage Level**:
   ```bash
   # Set lower usage level in .env
   echo "REACT_APP_GOOGLE_MAPS_USAGE_LEVEL=low" >> .env
   ```

2. **Monitor API Usage**:
   - Go to Google Cloud Console → APIs & Services → Dashboard
   - Check daily/monthly quota usage
   - Consider increasing quotas if needed

3. **Implement Cost Controls**:
   - Set up billing alerts in Google Cloud
   - Use "low" usage level for cost optimization
   - System automatically falls back to OpenStreetMap

### Billing or Payment Issues

**Error**: Billing-related error messages

**Solutions**:

1. **Verify Payment Method**:
   - Go to Google Cloud Console → Billing
   - Check payment method is valid and current
   - Update expired credit cards

2. **Check Account Status**:
   - Ensure billing account is not suspended
   - Resolve any outstanding payment issues
   - Contact Google Cloud billing support if needed

3. **Use Free Tier Effectively**:
   - $200/month credit covers typical residential use
   - Monitor usage in Google Cloud Console
   - Set up billing alerts for cost control

### Network or Connectivity Issues

**Error**: Network timeouts or connection failures

**Solutions**:

1. **Test Internet Connection**:
   ```bash
   # Test connection to Google Maps API
   curl -s "https://maps.googleapis.com/maps/api/geocode/json?address=test&key=YOUR_KEY"
   ```

2. **Check Firewall Settings**:
   - Ensure outbound HTTPS (port 443) is allowed
   - Test from Pi's network location
   - Consider proxy settings if applicable

3. **Automatic Fallback**:
   - System automatically uses OpenStreetMap on Google Maps failures
   - No user action required for fallback
   - Check web UI for fallback status messages

### OpenStreetMap Fallback Issues

**Symptoms**: Maps working but performance seems slow or features missing

**Solutions**:

1. **Verify Fallback Status**:
   - Check web UI Maps page for current provider
   - Should show "OpenStreetMap" when Google Maps unavailable

2. **Optimize Fallback Performance**:
   - Reduce usage level for better performance
   - Clear browser cache and reload
   - Check network bandwidth for tile loading

3. **Re-enable Google Maps**:
   - Resolve Google Maps API issues above
   - Refresh web UI to retry Google Maps connection
   - System will automatically switch back when available

---

## When to Seek Help

Contact support if you encounter:

- **Hardware damage** or component failures
- **Repeated software crashes** after following troubleshooting steps  
- **Safety system malfunctions** (emergency stop not working)
- **GPS accuracy issues** in clear conditions with good satellite reception
- **Electrical problems** beyond basic connection issues

## Preventive Maintenance

Prevent problems with regular maintenance:

- **Weekly**: Clean sensors and camera, check blade condition
- **Monthly**: Test emergency stop, calibrate compass, check battery health
- **Seasonally**: Deep clean all components, update software, check all connections
- **Annually**: Replace wear items (blade, filters), professional inspection

---

*Remember: When in doubt, use the emergency stop and consult this guide. Your safety and the safety of others is always the top priority.*

*Troubleshooting Guide - Part of LawnBerryPi Documentation v1.0*
