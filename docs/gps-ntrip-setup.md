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

### Finding NTRIP Services Near You

**New to NTRIP?** Start by checking these resources in order:

1. **State/Regional DOT Networks (USA)** - Many states offer **FREE** NTRIP access:
   - Search: "[Your State] DOT RTK network" or "[Your State] CORS network"
   - Examples:
     - **California**: Caltrans CRTN (California Real Time Network)
     - **Florida**: FDOT CORS Network
     - **Texas**: TxDOT RTN
     - **Ohio**: ODOT CORS
     - **Michigan**: MiRTN (Michigan Reference Network)
   - Coverage: Usually excellent in urban/suburban areas
   - Cost: **FREE** for most state networks
   - Registration: May require account creation

2. **RTK2Go Community Network** - Worldwide free base stations:
   - Website: http://rtk2go.com/
   - Coverage: Community-contributed, quality varies
   - Best for: Rural areas, testing, backup service
   - Cost: **FREE**
   - No registration required

3. **NGS CORS Network (USA)** - NOAA's national network:
   - Website: https://geodesy.noaa.gov/CORS/
   - Coverage: Nationwide but stations may be far apart
   - Cost: **FREE**
   - Best for: Areas without state network

4. **Commercial Services** - Consistent quality, paid subscription:
   - Best for: Professional use, areas with poor free coverage
   - See [NTRIP Caster Services](#ntrip-caster-services) section below

**Coverage Check Tool:**
```bash
# Check what's available near your location
# Visit: http://monitor.use-snip.com/
# Shows all NTRIP casters worldwide with coverage maps
```

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
   - You'll see a list with columns: Mountpoint, Identifier, Format, Details

4. **Choose the Right Mountpoint** (Important!):
   
   **Selection Criteria:**
   
   a. **Distance** - Closest is best
      - Ideal: < 10 km (6 miles)
      - Acceptable: < 20 km (12 miles)
      - Difficult: > 30 km (18 miles)
      - Beyond 50 km: Poor reliability
   
   b. **Message Format** - Look for these in the "Format" column:
      - **RTCM 3.x** ✅ **BEST CHOICE** - Modern standard, works with ZED-F9P
      - **CMR/CMR+** ⚠️ Trimble proprietary - avoid unless using Trimble base
      - **RTCM 2.x** ❌ Legacy format - avoid if possible
   
   c. **Correction Type:**
      - **VRS (Virtual Reference Station)** ✅ **RECOMMENDED**
        - Generates corrections for your exact location
        - Best accuracy over wide areas
        - Requires sending GGA position to server
        - Look for: "VRS", "VIRTUAL", "NEAREST" in mountpoint name
      
      - **Single Base Station** ✅ Good if close
        - Fixed physical reference station
        - Simple and reliable
        - Accuracy decreases with distance
        - Look for: Station names, coordinates in description
      
      - **MAC (Master Auxiliary Concept)** ✅ Advanced VRS
        - Multiple stations create network solution
        - Excellent accuracy
        - Requires stable connection
   
   d. **RTCM Message Types** - Check mountpoint details:
      - **Essential Messages** (ZED-F9P requires these):
        - **1005** - Station coordinates
        - **1077** - GPS MSM7 (high-resolution GPS)
        - **1087** - GLONASS MSM7
        - **1097** - Galileo MSM7 (if available)
        - **1127** - BeiDou MSM7 (if available)
      
      - **Good Combination:**
        - `1005, 1077, 1087, 1097` = GPS + GLONASS + Galileo ✅
        - `1005, 1074, 1084, 1094` = Older format (still works)
      
      - **Avoid:**
        - Mountpoints with only 1004, 1012 (legacy, less accurate)
   
   e. **Satellite Constellations** - More is better:
      - **GPS** - Always included ✅
      - **GLONASS** - Russian, adds satellites ✅ Recommended
      - **Galileo** - European, high accuracy ✅ Recommended if available
      - **BeiDou** - Chinese, good in Asia/Oceania ✅ Use if available
      - **QZSS** - Japanese regional, use if in Asia-Pacific
      
      **Best Practice:** Enable all available constellations (GPS+GLO+GAL+BDS)
      - More satellites = faster RTK lock
      - Better performance in obstructed areas
      - ZED-F9P supports all major constellations
   
   **Example Good Mountpoint:**
   ```
   Mountpoint: SJSU_VRS
   Format: RTCM 3.2
   Messages: 1005, 1077, 1087, 1097, 1127, 1230
   Constellations: GPS, GLONASS, Galileo, BeiDou
   Type: VRS
   Network: California CORS
   ✅ Excellent choice - Modern format, all constellations, VRS
   ```
   
   **Example Poor Mountpoint:**
   ```
   Mountpoint: OLD_BASE
   Format: RTCM 2.3
   Messages: 1004, 1012
   Constellations: GPS only
   Type: Single base
   Distance: 45 km
   ❌ Avoid - Old format, GPS only, far away
   ```

5. **Configure Client Options**:
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

### Step 3b: Configure Satellite Constellations (Optional but Recommended)

Enable all satellite constellations for best performance:

1. **Open Configuration View** (F9)
2. **Navigate to GNSS Configuration**:
   ```
   CFG → CFG-SIGNAL
   ```

3. **Enable All Constellations**:
   ```
   ☑ GPS L1C/A (Always enabled)
   ☑ GPS L2C
   ☑ GLONASS L1OF
   ☑ GLONASS L2OF
   ☑ Galileo E1
   ☑ Galileo E5b
   ☑ BeiDou B1I
   ☑ BeiDou B2I
   ☐ QZSS (Enable only if in Asia-Pacific region)
   ☐ SBAS (Disable - not needed with RTK)
   ```

4. **Save Configuration** (as in Step 3)

**Why Enable Multiple Constellations?**
- GPS alone: ~8-12 visible satellites
- GPS + GLONASS + Galileo + BeiDou: **20-30 visible satellites**
- Faster RTK lock (2-3 minutes → 30-60 seconds)
- Better performance near trees/buildings
- More reliable fix in challenging conditions

**Note:** Your NTRIP mountpoint must support these constellations (check messages 1077, 1087, 1097, 1127)

### Step 4: Connect GPS to Raspberry Pi

1. **Disconnect from Windows PC**
2. **Connect to Raspberry Pi** via USB
3. **Configure LawnBerry Pi**:

Edit `./config/hardware.yaml`:
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

Create or edit `./.env` with your NTRIP credentials:

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

Edit `./config/hardware.yaml`:

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
chmod 600 ./.env

# Verify ownership
ls -l ./.env
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
cat ./.env | grep NTRIP

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

#### United States - State DOT Networks (FREE)

Most states offer free RTK networks. Here's how to find yours:

**How to Access:**
1. Search: "[Your State] DOT CORS" or "[Your State] RTK network"
2. Register for a free account (usually required)
3. Get NTRIP credentials from your account dashboard

**State Network Directory:**

| State | Network Name | Website Search Term | Typical Coverage |
|-------|--------------|---------------------|------------------|
| California | Caltrans CRTN | "Caltrans Real Time Network" | Excellent |
| Florida | FDOT CORS | "FDOT CORS Network" | Excellent |
| Texas | TxDOT RTN | "TxDOT RTK Network" | Good |
| Ohio | ODOT CORS | "ODOT CORS Network" | Excellent |
| Michigan | MiRTN | "Michigan Reference Network" | Good |
| Washington | WSDOT RTK | "WSDOT RTK Network" | Good |
| New York | NYSNet | "NYS DOT CORS" | Good |
| Illinois | IDOT CORS | "Illinois DOT CORS" | Good |
| Pennsylvania | PennDOT RTK | "PennDOT RTK Network" | Fair |
| North Carolina | NCDOT CORS | "NC DOT CORS" | Good |

**Not Listed?** Search: "[Your State] Department of Transportation CORS Network"

**Typical Credentials Format:**
```
Host: [state].cors.network (varies by state)
Port: 2101
Username: your_registered_email
Password: provided_after_registration
Mountpoints: Listed in your account
```

#### International Networks

**Europe:**
- **Germany:** SAPOS (Commercial, €5-15/month)
- **UK:** Ordnance Survey Net RTK (Commercial)
- **France:** Orphéon/Teria (Commercial)
- **Spain:** ERGNSS (Some regions free)
- **Belgium:** FloodGNSS (Free for Flanders)

**Asia-Pacific:**
- **Australia:** CORS Network (Free, by state)
- **Japan:** GEONET (Free)
- **New Zealand:** PositioNZ (Free)
- **South Korea:** NTRIP.KR (Free)

**Check your country's national survey or mapping agency for local NTRIP services.**

### Running Your Own Base Station

For maximum reliability and coverage, you can set up your own base station. This is especially useful for:
- Large properties (> 5 acres)
- Remote areas with no nearby NTRIP services
- Professional/commercial operations
- When you want guaranteed 24/7 availability

#### Cost Analysis

**Initial Investment: $400-800**

| Component | Budget Option | Premium Option |
|-----------|---------------|----------------|
| RTK GPS Receiver | SparkFun ZED-F9P ($275) | u-blox C099-F9P ($400) |
| GPS Antenna | Surveying antenna ($80) | Geodetic antenna ($200) |
| Antenna Mount | DIY/tripod ($20) | Survey monument ($100) |
| Base Computer | Raspberry Pi 4 ($75) | Raspberry Pi 5 ($100) |
| Network | Existing WiFi ($0) | LTE modem ($50) |
| **Total** | **~$450** | **~$850** |

**Ongoing Costs:**
- Power: ~$5/year (5W continuous)
- Internet: Use existing connection ($0)
- Maintenance: Minimal

**vs. Commercial NTRIP:**
- Emlid Caster: $10-20/month = $120-240/year
- Trimble RTX: $600-2000/year
- **Break-even:** 2-4 years with your own base station

#### Hardware Setup Guide

**1. Equipment Selection:**

**GPS Receiver (Base Station):**
- **SparkFun GPS-RTK-SMA Breakout - ZED-F9P** ($275) ✅ Recommended
  - Same as your rover (easier setup)
  - Multi-band (L1/L2), multi-constellation
  - USB interface for Pi
- **Alternative:** Any RTK-capable receiver (must output RTCM3)

**GPS Antenna (Critical!):**
- **Surveying-grade antenna required** ($80-200)
  - Multi-band (L1/L2) capable
  - Good multipath rejection
  - Weatherproof
- **Recommended:**
  - SparkFun GNSS Multi-Band L1/L2 Surveying Antenna ($100)
  - Tallysman TW3710 (~$150)
  - ⚠️ Don't use cheap patch antennas - poor base performance

**Antenna Mount:**
- **Requirements:**
  - Stable, doesn't move/vibrate
  - Clear 360° sky view (no obstructions > 15° elevation)
  - Secure against weather/theft
- **Options:**
  - DIY: PVC pipe cemented in ground + antenna adapter
  - Survey tripod: Portable but less stable
  - Roof mount: Good if clear view
  - Survey monument: Professional ($100-200)

**Base Computer:**
- **Raspberry Pi 4 or 5** (2GB+ RAM sufficient) ✅
- Alternative: Any Linux PC, NUC, or existing server
- Requirements: USB port, network connection, 24/7 power

**2. Antenna Position Determination (Critical!):**

Your base station needs to know its **exact** position (within ~1cm):

**Option A: Professional Survey (Most Accurate)**
- Hire local surveyor to establish point
- Cost: $200-500 (one-time)
- Accuracy: ~1cm
- Gets you:
  - Latitude (decimal degrees, 8+ decimals)
  - Longitude (decimal degrees, 8+ decimals)
  - Ellipsoidal height (meters)
  - Coordinate system (usually WGS84)

**Option B: OPUS Service (Free, USA only)**
- National Geodetic Survey's Online Positioning User Service
- Website: https://geodesy.noaa.gov/OPUS/
- Process:
  1. Collect 4-24 hours of GPS data from your antenna
  2. Upload raw data to OPUS
  3. Receive precise coordinates via email (accuracy: ~2cm)
- Requirements: GPS receiver that logs raw data (ZED-F9P can do this)
- Cost: **FREE**

**Option C: Long-term Averaging (Least Accurate)**
- Let GPS receiver average position over 48+ hours
- Accuracy: ~10-30cm (acceptable for hobby use)
- Not recommended for professional applications

**3. Software Installation - RTKBase (Recommended)**

RTKBase is an open-source, easy-to-use base station software:

**Installation Steps:**
```bash
# On your base station Raspberry Pi

# 1. Install RTKBase
wget https://raw.githubusercontent.com/Stefal/rtkbase/master/tools/install.sh -O install.sh
sudo bash install.sh --all

# 2. During installation, you'll be prompted for:
#    - GPS receiver port (e.g., /dev/ttyACM0)
#    - Antenna position (lat/lon/height from OPUS or survey)
#    - NTRIP caster settings (to share your corrections)

# 3. Access web interface
http://<base-pi-ip>:80

# 4. Configure:
#    - Set antenna position (Settings → Base Position)
#    - Enable NTRIP server (Settings → Services)
#    - Create mountpoint name (e.g., MY_BASE_01)
```

**Post-Installation Configuration:**
1. **Set Static Position:**
   - Web interface → Settings → Base Position
   - Enter coordinates from OPUS or surveyor
   - Mode: "Static" (not "Average")

2. **Configure RTCM Messages:**
   - Enable: 1005, 1077, 1087, 1097, 1127, 1230
   - Output rate: 1Hz (every 1 second)

3. **Setup NTRIP Caster** (so your rover can connect):
   - Local mode: Rover connects directly to base Pi
   - Public mode: Share on RTK2Go for community
   - Private server: Run your own caster

**4. Alternative Software Options:**

**RTKLIB (Free, Advanced Users):**
- More complex setup
- Maximum flexibility
- Command-line based
- Guide: https://rtklibexplorer.wordpress.com/

**SNIP Lite (Commercial, $59 one-time):**
- Windows-based
- Easy GUI configuration
- Built-in NTRIP caster
- Good for PC-based stations
- Website: https://www.use-snip.com/

#### Connecting Your Rover to Your Base

**Option 1: Direct Connection (Local Network)**
```yaml
# In ./.env on your rover
NTRIP_HOST=192.168.1.100  # Your base station's IP
NTRIP_PORT=2101
NTRIP_MOUNTPOINT=MY_BASE_01
# No username/password needed on local network
```

**Option 2: Share via RTK2Go (Internet Access)**
- Configure RTKBase to forward to rtk2go.com
- Your rover connects via rtk2go.com
- Useful if rover uses cellular internet

**Option 3: VPN Connection**
- Setup Tailscale or Wireguard VPN
- Connect rover to base from anywhere
- More complex but very flexible

#### Base Station Best Practices

**✅ DO:**
- Place antenna with 360° clear sky view
- Use high-quality surveying antenna
- Get precise position (OPUS or professional survey)
- Secure antenna against movement/theft
- Provide UPS backup power for 24/7 operation
- Monitor base health with web interface
- Keep base software updated

**❌ DON'T:**
- Place antenna near metal structures (multipath)
- Use consumer-grade patch antennas
- Guess antenna position (use OPUS or survey)
- Mount on structure that moves/vibrates
- Expose computer to weather
- Forget to configure static position (not averaging mode)

#### Maintenance

**Weekly:**
- Check base station web interface
- Verify NTRIP stream is active
- Check satellite count (should see 20+)

**Monthly:**
- Check for software updates
- Verify antenna mount is stable
- Review correction data quality

**Annually:**
- Clean antenna (dust/debris affects signal)
- Check all cable connections
- Verify position hasn't drifted (re-run OPUS)

#### Troubleshooting Your Base

**Poor Correction Quality:**
- Check antenna has clear view (use satellite view tools)
- Verify antenna position is accurate
- Ensure antenna cable is < 10m (signal loss in long cables)
- Check for nearby RF interference

**Rover Can't Connect:**
- Verify base NTRIP server is running
- Check firewall allows port 2101
- Test with local connection first
- Verify mountpoint name matches

**Position Drift:**
- Base must use **static** position, not averaging
- Re-verify antenna position with OPUS
- Check antenna mount hasn't moved

#### Is Your Own Base Station Worth It?

**✅ Good Reasons to Build Your Own:**
- No NTRIP service within 20km
- Property > 10 acres (base covers entire area)
- Professional use (need guaranteed uptime)
- Like DIY projects and learning
- Want to contribute to RTK2Go community
- Long-term cost savings (> 2 years)

**❌ Stick with Public NTRIP If:**
- Good free DOT network available nearby (< 10km)
- Small property (< 1 acre)
- Casual/hobby use only
- Don't want maintenance responsibility
- Can't establish precise antenna position
- No suitable antenna location with clear view

**Conclusion:**
Building your own base station is a rewarding project that provides maximum control and long-term cost savings, but requires initial investment, technical setup, and ongoing maintenance. For most users, free state DOT networks offer the best value and easiest setup.

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
