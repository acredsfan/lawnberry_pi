# GPS RTK with NTRIP Configuration Guide

This guide provides complete instructions for configuring the u-blox ZED-F9P GPS receiver with NTRIP corrections for centimeter-level RTK positioning on LawnBerry Pi v2.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Configuration Methods](#configuration-methods)
4. [Method 1: Direct GPS Configuration (Recommended)](#method-1-direct-gps-configuration-recommended)
5. [Method 2: Pi-Forwarded NTRIP Corrections](#method-2-pi-forwarded-ntrip-corrections)
6. [Testing & Verification](#testing--verification)
7. [Troubleshooting](#troubleshooting)
8. [NTRIP Caster Services](#ntrip-caster-services)

## Overview

**RTK (Real-Time Kinematic)** positioning provides centimeter-level GPS accuracy by using correction data from a reference station. **NTRIP (Networked Transport of RTCM via Internet Protocol)** is the standard protocol for streaming these corrections over the internet.

### Supported Hardware
- **Primary**: SparkFun GPS-RTK-SMA (u-blox ZED-F9P) connected via USB
- **Alternative**: u-blox ZED-F9P connected via UART
- **Device Path**: Typically `/dev/ttyACM0` (USB) or `/dev/ttyAMA0` (UART)

### RTK Fix Types
- **No Fix**: No GPS signal
- **3D Fix**: Standard GPS accuracy (5-10 meters)
- **DGPS**: Differential GPS (1-5 meters)
- **Float RTK**: Processing corrections (0.5-2 meters)
- **Fixed RTK**: Full RTK lock (0.02-0.05 meters) ✅ **Target accuracy**

## Prerequisites

### Required Information
Before configuration, gather the following from your NTRIP service provider:

- **Caster Host**: The NTRIP server hostname or IP (e.g., `rtk2go.com`, `ntrip.emlid.com`)
- **Port**: Usually `2101` (standard NTRIP port)
- **Mountpoint**: The specific correction stream (e.g., `SJSU_VRS`, `BASE_STATION_01`)
- **Username**: Your account username (if required)
- **Password**: Your account password (if required)
- **Approximate Position**: Your mower's operating location (latitude, longitude, altitude)

### System Requirements

**Recommended Tools:**
```bash
# Install helpful utilities for testing and monitoring
sudo apt install -y jq i2c-tools usbutils
```

**Verify GPS Device:**
```bash
# Verify GPS device is detected
ls -l /dev/ttyACM* /dev/ttyAMA*

# Expected output (USB connection):
# /dev/ttyACM0

# Check device appears in system logs
dmesg | grep -i gps
# or
dmesg | grep -i ttyACM

# For UART connection, verify UART is enabled
raspi-config
# Interface Options → Serial Port
# "Would you like a login shell..." → No
# "Would you like the serial port hardware..." → Yes
```

## Configuration Methods

There are two methods for receiving NTRIP corrections:

### Method 1: Direct GPS Configuration (Recommended)
The GPS receiver connects directly to the NTRIP caster and receives corrections internally. The Raspberry Pi only reads the position data.

**Advantages:**
- ✅ More reliable - GPS handles reconnection automatically
- ✅ Lower system overhead on the Pi
- ✅ Works even if backend restarts
- ✅ Easier troubleshooting

**Configuration Tool:** u-blox u-center (Windows software)

### Method 2: Pi-Forwarded NTRIP Corrections
The Raspberry Pi connects to the NTRIP caster and forwards correction data to the GPS receiver over serial.

**Advantages:**
- ✅ No Windows PC required for configuration
- ✅ Can be configured entirely via command line
- ✅ Flexible - change caster without reconfiguring GPS

**Configuration:** Environment variables + `hardware.yaml`

## Method 1: Direct GPS Configuration (Recommended)

### Step 1: Install u-blox u-center (Windows)

1. **Download u-center** from u-blox website:
   - Visit: https://www.u-blox.com/en/product/u-center
   - Download the latest version (u-center 2 recommended)
   - Install on a Windows PC

2. **Connect GPS to Windows PC**:
   ```
   Connect ZED-F9P to PC via USB cable
   ```

3. **Open u-center**:
   - Launch u-center application
   - Select the correct COM port (Tools → Receiver → Port)
   - Click "Connect" icon or press Ctrl+E

### Step 2: Configure NTRIP in u-center

1. **Open NTRIP Client Configuration**:
   ```
   Menu: Receiver → NTRIP Client
   ```

2. **Enter NTRIP Server Settings**:
   ```
   Server: rtk2go.com (or your caster hostname)
   Port: 2101
   Username: your_username (if required, otherwise leave blank)
   Password: your_password (if required, otherwise leave blank)
   ```

3. **Get Mountpoint List**:
   - Click "Get Mountpoint" button
   - Wait for the list to populate (may take 10-30 seconds)
   - Select your nearest mountpoint based on location

4. **Configure Client Options**:
   ```
   ☑ Send GGA Position
   GGA Interval: 10 seconds (recommended)
   Version: NTRIP 2.0 (recommended)
   ```

5. **Apply Configuration**:
   - Click "OK" to save settings
   - The GPS will now connect to the NTRIP caster

### Step 3: Save Configuration to GPS Flash

**IMPORTANT**: Save the configuration to non-volatile memory so it persists after power cycle.

1. **Open Configuration View**:
   ```
   Menu: View → Configuration View (or press F9)
   ```

2. **Navigate to CFG (Configuration)**:
   - Expand "CFG" in the left tree
   - Select "CFG-NAVHPG" for high precision settings

3. **Save Configuration**:
   ```
   Menu: Receiver → Action → Save Config
   ```
   Or send the UBX command:
   ```
   UBX-CFG-CFG
   - Select: Save current configuration
   - Device: BBR (Battery Backed RAM), Flash, and EEPROM
   - Click "Send"
   ```

4. **Verify Save**:
   - Disconnect and reconnect the GPS
   - Reopen u-center and check that NTRIP still connects automatically

### Step 4: Connect GPS to Raspberry Pi

1. **Disconnect from Windows PC**
2. **Connect to Raspberry Pi** via USB
3. **Configure LawnBerry Pi**:

Edit `/home/pi/lawnberry/config/hardware.yaml`:
```yaml
gps:
  type: ZED-F9P

gps_ntrip_enabled: true  # Indicates RTK corrections are active
```

4. **Restart the backend**:
```bash
sudo systemctl restart lawnberry-backend
```

The GPS will automatically connect to the NTRIP caster when powered on, and LawnBerry Pi will read the RTK-corrected position.

## Method 2: Pi-Forwarded NTRIP Corrections

### Step 1: Create .env File

Create or edit `/home/pi/lawnberry/.env` with your NTRIP credentials:

```bash
# NTRIP Caster Configuration
NTRIP_HOST=rtk2go.com
NTRIP_PORT=2101
NTRIP_MOUNTPOINT=YOUR_MOUNTPOINT
NTRIP_USERNAME=your_username
NTRIP_PASSWORD=your_password

# GPS Serial Connection
NTRIP_SERIAL_DEVICE=/dev/ttyACM0
NTRIP_SERIAL_BAUD=115200

# Static Position for GGA Sentence (Optional)
# Provide your approximate location for VRS (Virtual Reference Station)
NTRIP_GGA_LAT=37.3352
NTRIP_GGA_LON=-121.8811
NTRIP_GGA_ALT=10.0
NTRIP_GGA_INTERVAL=10

# Alternative: Provide a complete GGA sentence
# NTRIP_STATIC_GGA=$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
```

**Important Notes:**
- Replace `YOUR_MOUNTPOINT` with your actual mountpoint name
- Replace `your_username` and `your_password` with credentials (if required)
- If your caster doesn't require authentication, you can omit USERNAME and PASSWORD
- The `.env` file should NOT be committed to git (it's in `.gitignore`)

### Step 2: Enable NTRIP in Hardware Configuration

Edit `/home/pi/lawnberry/config/hardware.yaml`:

```yaml
gps:
  type: ZED-F9P

# Enable NTRIP forwarding
gps_ntrip_enabled: true
```

### Step 3: Restart Backend Service

```bash
# Restart to load new environment variables
sudo systemctl restart lawnberry-backend

# Check that NTRIP forwarder started successfully
sudo journalctl -u lawnberry-backend -n 50 | grep -i ntrip
```

Expected log output:
```
Started NTRIP forwarder to rtk2go.com:2101 mountpoint YOUR_MOUNTPOINT → /dev/ttyACM0
```

### Step 4: Verify .env File Permissions

Ensure the `.env` file is secure (contains credentials):

```bash
# Set restrictive permissions
chmod 600 /home/pi/lawnberry/.env

# Verify ownership
ls -l /home/pi/lawnberry/.env
# Should show: -rw------- 1 pi pi
```

## Testing & Verification

### Check GPS Device Detection

```bash
# Verify device exists
ls -l /dev/ttyACM0

# Check USB connection
lsusb | grep -i u-blox

# Expected output:
# Bus 001 Device 003: ID 1546:01a9 u-blox AG u-blox GNSS receiver
```

### Monitor GPS Status via API

```bash
# Get real-time GPS status
curl http://localhost:8081/api/v2/sensors/health | jq '.gps'

# Expected output when RTK lock achieved:
{
  "status": "healthy",
  "fix_type": "RTK_FIXED",
  "satellites": 18,
  "hdop": 0.8,
  "latitude": 37.335123,
  "longitude": -121.881456,
  "altitude": 10.2,
  "accuracy_horizontal": 0.014,  # 1.4 cm
  "last_update": "2025-10-24T10:30:45.123Z"
}
```

### Check NTRIP Connection Logs (Method 2 Only)

```bash
# Monitor NTRIP forwarder in real-time
sudo journalctl -u lawnberry-backend -f | grep -i ntrip

# Check for errors
sudo journalctl -u lawnberry-backend -n 100 | grep -E "(ntrip|NTRIP|rtcm|RTCM)"
```

Successful connection logs:
```
INFO: Started NTRIP forwarder to rtk2go.com:2101 mountpoint SJSU_VRS → /dev/ttyACM0
DEBUG: NTRIP caster responded: HTTP/1.1 200 OK
DEBUG: Streaming RTCM corrections to GPS receiver
```

### Monitor Fix Type Progression

After starting NTRIP corrections, the GPS will progress through these states:

```
No Fix (0-30 seconds after power-on)
    ↓
3D Fix (Standard GPS, ~5m accuracy)
    ↓
Float RTK (Processing corrections, ~50cm accuracy)
    ↓
Fixed RTK (Full lock, ~2cm accuracy) ✅
```

**Normal acquisition time:** 1-5 minutes for Fixed RTK
**Fast re-acquisition:** 10-30 seconds after temporary signal loss

### Test RTK Accuracy

Once Fixed RTK is achieved, test positioning accuracy:

```bash
# Record GPS positions for 60 seconds
for i in {1..60}; do
  curl -s http://localhost:8081/api/v2/sensors/health | \
    jq -r '[.gps.latitude, .gps.longitude, .gps.fix_type] | @csv'
  sleep 1
done > gps_test.csv

# Analyze standard deviation (should be < 0.05 meters with Fixed RTK)
# Import gps_test.csv into spreadsheet or use Python for analysis
```

### Dashboard Verification

1. **Open LawnBerry Dashboard**:
   ```
   http://<pi-ip>:3001
   ```

2. **Check GPS Widget**:
   - Look for "RTK FIXED" or "RTK FLOAT" status indicator
   - Satellite count should be 12+ for best performance
   - HDOP (Horizontal Dilution of Precision) should be < 2.0

3. **Map View**:
   - Position should update smoothly without jumps
   - When stationary, position should remain stable (< 5cm drift)

## Troubleshooting

### GPS Device Not Detected

**Symptom:** `/dev/ttyACM0` doesn't exist

**Solutions:**
```bash
# Check if device is connected
lsusb | grep -i u-blox

# Check dmesg for USB errors
dmesg | tail -30 | grep -i tty

# Try different USB port or cable
# USB 3.0 ports (blue) sometimes have issues - try USB 2.0 (black)

# Verify user permissions
sudo usermod -a -G dialout pi
# Log out and back in, or reboot
```

### NTRIP Connection Fails (Method 2)

**Symptom:** Backend logs show "NTRIP caster rejected connection"

**Solutions:**
```bash
# 1. Verify credentials in .env file
cat /home/pi/lawnberry/.env | grep NTRIP

# 2. Test caster connection manually
telnet rtk2go.com 2101
# Should connect - press Ctrl+] then 'quit' to exit

# 3. Verify mountpoint exists
# Use online NTRIP sourcetable browser or check provider's website

# 4. Check firewall (unlikely on Pi, but verify)
sudo iptables -L -n | grep 2101

# 5. Verify .env is being loaded
sudo systemctl restart lawnberry-backend
sudo journalctl -u lawnberry-backend -n 50 | grep "NTRIP"
```

### GPS Stuck in Float RTK, Never Achieves Fixed RTK

**Symptom:** Fix type remains "RTK_FLOAT" for > 5 minutes

**Possible Causes:**
1. **Poor satellite visibility** - Obstructions (trees, buildings)
2. **Multipath interference** - Reflections from metal surfaces
3. **Wrong mountpoint** - Base station too far away (> 20km)
4. **Antenna quality** - Poor GPS antenna

**Solutions:**
```bash
# 1. Check satellite count and signal strength
curl -s http://localhost:8081/api/v2/sensors/health | jq '.gps.satellites'
# Should be 15+ for reliable RTK

# 2. Verify antenna has clear sky view
# Move to open area, away from buildings/trees

# 3. Check base station distance
# Most NTRIP services provide station locations
# Ideal: < 10km, Acceptable: < 20km, Difficult: > 30km

# 4. Try different mountpoint (closer base station)
# Edit .env and change NTRIP_MOUNTPOINT

# 5. Check antenna cable and connections
# Ensure SMA connector is tight, no kinks in cable
```

### RTK Fix Drops Intermittently

**Symptom:** Fix type alternates between Fixed RTK and Float RTK

**Solutions:**
```bash
# 1. Check correction data stream
sudo journalctl -u lawnberry-backend -f | grep -i rtcm
# Should see "Streaming RTCM corrections" continuously

# 2. Verify stable network connection (Method 2)
ping -c 100 rtk2go.com
# Should have 0% packet loss

# 3. Check for USB power issues
# Add to /boot/firmware/config.txt:
max_usb_current=1

# 4. Monitor system load
top
# If CPU consistently > 80%, reduce telemetry rate

# 5. Check GPS signal quality
# Temporarily relocate to open area to eliminate sky view issues
```

### High Latency in Position Updates

**Symptom:** GPS position updates slowly (> 1 second lag)

**Solutions:**
```bash
# 1. Check backend CPU usage
top -p $(pgrep -f lawnberry-backend)

# 2. Verify GPS update rate
# ZED-F9P should provide 5-10Hz updates
curl -s http://localhost:8081/api/v2/sensors/health | \
  jq '.gps.last_update'
# Run multiple times and check timestamps

# 3. Check serial port buffer
# Add to .env for faster baud rate (if GPS supports it):
NTRIP_SERIAL_BAUD=460800

# 4. Reduce system load
# Disable unnecessary services
sudo systemctl list-units --type=service --state=running
```

### Permission Denied When Accessing GPS

**Symptom:** Backend logs show "Permission denied: /dev/ttyACM0"

**Solutions:**
```bash
# 1. Check device permissions
ls -l /dev/ttyACM0
# Should show: crw-rw---- 1 root dialout

# 2. Add user to dialout group
sudo usermod -a -G dialout pi

# 3. Verify group membership
groups pi
# Should include 'dialout'

# 4. Reboot or re-login for group changes to take effect
sudo reboot

# 5. Alternative: Set udev rule for automatic permissions
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1546", ATTRS{idProduct}=="01a9", MODE="0666"' | \
  sudo tee /etc/udev/rules.d/99-ublox-gps.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Method 1 GPS Doesn't Connect After Pi Boot

**Symptom:** RTK works with u-center but not when connected to Pi

**Possible Causes:**
- Configuration not saved to GPS flash
- USB power insufficient
- Wrong USB port

**Solutions:**
```bash
# 1. Verify configuration was saved in u-center
# Reconnect to Windows PC and check NTRIP settings persist

# 2. Increase USB power (add to /boot/firmware/config.txt)
max_usb_current=1

# 3. Use powered USB hub if Pi power insufficient

# 4. Check GPS logs in u-center after reconnecting to verify
# NTRIP connection established automatically
```

## NTRIP Caster Services

### Free Services

#### RTK2Go
- **Website:** http://rtk2go.com/
- **Host:** `rtk2go.com`
- **Port:** `2101`
- **Authentication:** No username/password required
- **Mountpoints:** Community-contributed, worldwide coverage
- **Notes:** Free, but base station quality varies. Check mountpoint list for stations near you.

#### SNIP Lite Demo
- **Website:** https://www.use-snip.com/
- **Demo servers available for testing**
- **Notes:** Limited to testing, not for production use

### Commercial Services

#### Emlid Caster
- **Website:** https://emlid.com/ntrip-caster/
- **Host:** `ntrip.emlid.com`
- **Port:** `2101`
- **Cost:** Subscription required
- **Coverage:** Global with proprietary base stations
- **Accuracy:** Consistent 1-2cm accuracy

#### Trimble RTX
- **Website:** https://www.trimble.com/
- **Premium service with global coverage**
- **Satellite-delivered corrections (no internet required)**
- **Cost:** High (enterprise pricing)**

#### Here Positioning (formerly Sapcorda)
- **Website:** https://www.here.com/
- **Global coverage with SSR corrections**
- **Cost:** Commercial subscription

### Regional Services

Many countries have national RTK networks:
- **USA:** State DOT networks (varies by state)
- **Europe:** Various national networks (e.g., SmartNet, SAPOS)
- **Australia:** CORS Network
- **Japan:** GEONET

Check with your local surveying or mapping agencies for public or commercial NTRIP services.

### Running Your Own Base Station

For maximum reliability and coverage, you can set up your own base station:

**Hardware Required:**
- Second ZED-F9P or similar RTK-capable receiver
- Fixed antenna mount with known precise position
- Raspberry Pi or similar computer
- Internet connection

**Software:**
- **RTKLIB** (Open source)
- **SNIP Caster** (Commercial, easy setup)
- **RTKBase** (Open source, Pi-friendly)

**Benefits:**
- ✅ No ongoing subscription costs
- ✅ Maximum availability and reliability
- ✅ Custom coverage for your property
- ✅ No dependency on third-party services

**Considerations:**
- Initial hardware investment (~$300-600)
- Requires precise antenna position determination
- Network setup and maintenance
- 24/7 uptime requirement

## Known Issues

### Issue 1: GGA Sentence Timing (Method 2)
**Description:** Some NTRIP casters require regular GGA position updates or will disconnect.

**Workaround:** 
- Ensure `NTRIP_GGA_LAT`, `NTRIP_GGA_LON` are set in `.env`
- Or provide a complete `NTRIP_STATIC_GGA` sentence
- Adjust `NTRIP_GGA_INTERVAL` (default 10 seconds) if needed

### Issue 2: USB Device Path Changes
**Description:** After reboot, USB GPS may appear as `/dev/ttyACM1` instead of `/dev/ttyACM0`.

**Workaround:**
Create a udev rule for consistent device naming:
```bash
# Find device vendor/product IDs
lsusb -v | grep -A 5 "u-blox"

# Create udev rule
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1546", ATTRS{idProduct}=="01a9", SYMLINK+="gps-rtk"' | \
  sudo tee /etc/udev/rules.d/99-ublox-gps.rules

# Reload rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Now GPS will always be available at /dev/gps-rtk
# Update .env or hardware.yaml to use /dev/gps-rtk
```

### Issue 3: Cellular Modem Interference (Method 2)
**Description:** If using 4G/LTE modem on the same Pi, NTRIP may experience packet loss.

**Workaround:**
- Use Method 1 (direct GPS configuration) instead
- Or use external NTRIP device/router with wired connection

## Verification Checklist

Before mowing operations, verify RTK GPS is working correctly:

- [ ] GPS device detected: `ls /dev/ttyACM0` succeeds
- [ ] Backend service running: `systemctl status lawnberry-backend`
- [ ] GPS health check passes: `curl localhost:8081/api/v2/sensors/health | jq '.gps.status'` returns "healthy"
- [ ] RTK fix achieved: `fix_type` is "RTK_FIXED" or "RTK_FLOAT"
- [ ] Satellite count: ≥ 12 visible satellites
- [ ] Accuracy: `accuracy_horizontal` < 0.05 meters (5cm)
- [ ] Position updates: `last_update` timestamp refreshes every 0.1-1 second
- [ ] Dashboard shows RTK status: Green "RTK FIXED" indicator visible
- [ ] No NTRIP errors in logs: `journalctl -u lawnberry-backend | grep -i ntrip` shows no errors

## References

- **u-blox ZED-F9P Integration Manual**: https://www.u-blox.com/en/docs/UBX-18010802
- **RTCM 3.x Standard**: http://www.rtcm.org/
- **NTRIP Protocol Specification**: https://www.use-snip.com/kb/knowledge-base/ntrip-rev1-versus-rev2/
- **LawnBerry Hardware Integration**: `/docs/hardware-integration.md`
- **LawnBerry Operations Guide**: `/docs/OPERATIONS.md`

## Support

If you encounter issues not covered in this guide:

1. Check system logs: `sudo journalctl -u lawnberry-backend -n 200`
2. Review GPS status: `curl localhost:8081/api/v2/sensors/health | jq '.gps'`
3. Verify configuration: Review `.env` and `hardware.yaml` settings
4. Test with Method 1 if Method 2 fails (and vice versa)
5. Check NTRIP caster status with your provider
6. Consult LawnBerry documentation in `/docs/` directory

---

**Last Updated:** 2025-10-24  
**Document Version:** 1.0  
**Compatible with:** LawnBerry Pi v2, u-blox ZED-F9P
