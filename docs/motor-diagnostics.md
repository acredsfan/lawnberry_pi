# Motor Control Diagnostics Guide

## Overview

Two new diagnostic systems help troubleshoot motor turning issues:

1. **Progressive Stiffness Detection** — Slowly increase turn effort until the motor is stuck
2. **Heading Validation** — Quickly determine if GPS or IMU heading is correct

## 1. Progressive Stiffness Detection

### Purpose
Detects when a motor is physically stuck or has restricted movement. Gradually increases turn effort (10% → 15% → 20% ... 100%) and monitors heading change. When heading stops changing (< 0.3° per 2 seconds), the system knows the motor is stuck and stops applying force.

### Usage

#### Via API
```bash
# Start a left turn stiffness test
curl -X POST http://localhost:8000/api/v2/control/diagnose/stiffness \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-123",
    "direction": "left",
    "initial_effort": 0.1,    # Start at 10% effort (optional, default 0.1)
    "step": 0.05,             # Increase by 5% each iteration (optional, default 0.05)
    "max_effort": 1.0         # Stop at 100% (optional, default 1.0)
  }'
```

#### Via Script
```bash
# Test progressive stiffness on left turn
./scripts/test_motor_diagnostics.sh stiffness left

# Test progressive stiffness on right turn
./scripts/test_motor_diagnostics.sh stiffness right

# Run both in sequence
./scripts/test_motor_diagnostics.sh test
```

### Response

```json
{
  "ok": true,
  "test_active": true,
  "current_effort": 0.15,
  "heading": 45.2,
  "heading_delta": 1.5,
  "status": "testing"
}
```

**Fields:**
- `test_active` — Test is still running and applying turning force
- `current_effort` — Current turn effort as percentage (0.1 = 10%)
- `heading` — Current mower heading in degrees (GPS or IMU depending on config)
- `heading_delta` — Degrees rotated since last check (0° = motor stuck)
- `status` — One of:
  - `started` — Initial request, test just began
  - `testing` — Motor responding, increasing effort
  - `stuck` — Motor unable to turn further (heading_delta < 0.3°)
  - `completed` — Reached max effort without stalling

### Interpretation

**Normal behavior:**
```
Iteration 1: effort=0.10, heading_delta=1.2° → Motor responding
Iteration 2: effort=0.15, heading_delta=1.4° → Motor responding
Iteration 3: effort=0.20, heading_delta=1.3° → Motor responding
...
Iteration 8: effort=0.45, heading_delta=0.2° → Motor stuck
Status: "stuck", test_active=false
```

**What to check if motor is stuck:**
1. **Physical obstruction** — Is grass/debris binding the wheel?
2. **Wheel alignment** — Is one wheel turned sideways in the grass?
3. **Motor current** — Check power monitor for motor stall current (> 30A)
4. **Wheel contact** — Lift each wheel; does it spin freely by hand?
5. **Encoder feedback** — Check navigation logs for hall effect sensor errors

## 2. Heading Validation

### Purpose
Determines which heading source is reliable:
- **GPS Course-Over-Ground (COG)** — Accurate when mower is moving in open areas
- **IMU Yaw (Bussard BNO085)** — Can be inverted if calibration procedure was wrong

Drives forward for ~5 meters while collecting GPS and IMU heading samples. Compares averages to detect agreement, inversion, or conflicts.

### Usage

#### Via API
```bash
# Validate heading by driving forward
curl -X POST http://localhost:8000/api/v2/control/diagnose/heading-validation \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-123",
    "distance_m": 5.0,    # Distance to drive (optional, default 5.0)
    "samples": 10         # Number of GPS/IMU samples to collect (optional, default 10)
  }'
```

#### Via Script
```bash
# Run heading validation
./scripts/test_motor_diagnostics.sh heading
```

### Response

```json
{
  "ok": true,
  "heading_source": "gps",
  "gps_cog": 45.23,
  "imu_yaw": 45.18,
  "difference": 0.05,
  "confidence": 0.9997,
  "recommendation": "GPS Course-Over-Ground is reliable; IMU calibration is correct",
  "gps_samples": 10,
  "imu_samples": 10
}
```

**Fields:**
- `heading_source` — Which source is being used or is correct:
  - `gps` — GPS and IMU agree (difference < 5°)
  - `imu` — 180° difference detected (IMU appears inverted)
  - `conflict` — Other significant mismatch
- `gps_cog` — Average GPS Course-Over-Ground heading
- `imu_yaw` — Average IMU yaw heading
- `difference` — Absolute difference between averages
- `confidence` — Certainty (0.0 to 1.0) that this diagnosis is correct
- `recommendation` — What to do about the heading

### Interpretation

**Healthy GPS + IMU agreement:**
```json
{
  "heading_source": "gps",
  "gps_cog": 45.23,
  "imu_yaw": 45.18,
  "difference": 0.05,
  "confidence": 0.9997,
  "recommendation": "GPS Course-Over-Ground is reliable; IMU calibration is correct"
}
```
✅ **Action:** Navigation can use GPS COG with confidence; IMU calibration is correct.

**IMU inverted (180° offset):**
```json
{
  "heading_source": "imu",
  "gps_cog": 45.23,
  "imu_yaw": 225.18,
  "difference": 180.0,
  "confidence": 0.95,
  "recommendation": "IMU yaw appears to be inverted (180° offset); check BNO085 calibration or fix yaw formula"
}
```
⚠️ **Action:** 
1. Check BNO085 calibration procedure (see section below)
2. Or verify yaw formula in `navigation_service.py` line 162 is correct
3. Run recalibration if needed

**Heading conflict (other mismatch):**
```json
{
  "heading_source": "conflict",
  "gps_cog": 45.23,
  "imu_yaw": 80.5,
  "difference": 35.27,
  "confidence": 0.61,
  "recommendation": "Heading conflict detected (35.3°). Verify GPS fix quality and IMU calibration"
}
```
❌ **Action:**
1. Check GPS RTK fix status (should be RTK_FIXED, not RTK_FLOAT or GPS)
2. Run IMU recalibration
3. Check for magnetic interference near GPS/IMU antennas

## 3. IMU Calibration Procedure

If the heading validation detects a 180° inversion, recalibrate the BNO085:

### Quick Recalibration
```bash
# 1. Enable calibration mode
curl -X POST http://localhost:8000/api/v2/sensors/calibrate/imu \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'

# 2. Hold mower and rotate it through all orientations for ~30 seconds:
#    - Point forward, rotate 360°
#    - Point left, rotate 360°
#    - Point up, rotate 360°

# 3. Check calibration status
curl http://localhost:8000/api/v2/sensors/calibration-status
```

### Detailed Calibration
The BNO085 has four calibration systems:
1. **System Calibration** — Overall gyro/accel alignment
2. **Gyro Calibration** — Gyroscope drift correction
3. **Accel Calibration** — Accelerometer scale and offset
4. **Mag Calibration** — Magnetometer hard iron / soft iron

If quick recalibration doesn't fix the 180° issue, it may be in the firmware's yaw calculation. Check:

```python
# In backend/src/services/navigation_service.py, line ~162:
self._imu_yaw_offset = float(getattr(hardware, "imu_yaw_offset_degrees", 0.0))

# If reading -180° when should be +180°, add 180° to offset:
# config/hardware.yaml:
#   imu:
#     yaw_offset_degrees: 180.0
```

## 4. Common Issues and Fixes

### Issue: Progressive stiffness test shows "stuck" immediately
**Likely cause:** Motor not spinning at all, or wheel is off the ground.

**Fixes:**
1. Verify wheel contact — Lift each wheel, confirm it's on the ground
2. Check motor power — Use multimeter on motor leads while test running
3. Check hall effect encoders — Verify encoder status in logs
4. Test individual motor — Use `/api/v2/control/drive` with throttle-only (no turn)

### Issue: Heading validation shows 180° inversion
**This is expected if:**
- IMU was installed upside-down
- Yaw calibration procedure was done backward (rotated opposite direction)

**Fixes:**
1. Physically rotate IMU mount 180° in enclosure, OR
2. Add `imu_yaw_offset_degrees: 180` to `config/hardware.yaml`
3. Rerun heading validation to confirm

### Issue: Heading validation shows 30-90° conflict
**Likely causes:**
- GPS lost RTK fix (check `gps_mode` should be RTK_FIXED)
- Magnetic interference near IMU
- IMU not fully calibrated

**Fixes:**
1. Move away from metal objects (fences, buildings)
2. Ensure GPS has clear sky view
3. Rerun IMU calibration
4. Check logs for "IMU yaw outlier" warnings

## 5. Using Results to Fix Navigation

Once you've identified the heading source and stiffness, configure navigation:

### If GPS is reliable and IMU correct:
```python
# In navigation_service.py, use GPS COG
heading = self.navigation_state.gps_cog  # Course-Over-Ground from u-blox ZED-F9P
```

### If motor is stuck on one direction:
```python
# In navigation_service.py, tank_turn_watchdog around line 508
# Add condition to detect stuck motor and switch to alternative maneuver
if motor_stall_detected(duration=5.0):
    # Try blade lift or different wheel speeds
    break_tank_turn()
```

### If heading constantly conflicts:
```python
# Fallback to dead reckoning + obstacle avoidance
# See DeadReckoningSystem class around line 83
```

## 6. Test Script Details

The `scripts/test_motor_diagnostics.sh` script automates the tests:

```bash
# Show all available tests
./scripts/test_motor_diagnostics.sh

# Run single test
./scripts/test_motor_diagnostics.sh stiffness left
./scripts/test_motor_diagnostics.sh stiffness right
./scripts/test_motor_diagnostics.sh heading

# Run complete diagnostic (left stiffness, right stiffness, heading)
./scripts/test_motor_diagnostics.sh test
```

Results are printed as JSON, making them easy to parse or pipe to other tools:
```bash
# Get just the heading_source from stiffness test
./scripts/test_motor_diagnostics.sh heading | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['heading_source'])"
```
