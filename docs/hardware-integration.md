# LawnBerry Pi v2 - Hardware Integration Guide

This guide documents wiring, pin assignments, and integration steps for Raspberry Pi 5 and Raspberry Pi 4B. Always disconnect power before wiring. Refer to `spec/hardware.yaml` for canonical configuration.

## Platform Notes
- Supported: Raspberry Pi OS Bookworm (64-bit) only
- Python 3.11.x required
- GPIO differences: Some UART pins differ between Pi 4B and Pi 5; use alternatives noted below.

## Pin Assignments (from spec/hardware.yaml)

### Blade Driver (IBT-4 H-Bridge)
- Pi 5 current mower profile: GPIO 24 → IN1, GPIO 25 → IN2.
- Pi 4B conflict-free profile: GPIO 26 → IN1, GPIO 27 → IN2.
- Power: 12V from battery through appropriate fuse
- Ground: Common ground with Raspberry Pi
- Backend config uses an explicit `blade:` block (`controller`, `allow_autonomous`, `pins`, timeouts).
  The legacy `blade_controller` key is still accepted, but runtime never silently remaps blade pins.
  If moving a Pi 5-wired mower to a Pi 4B, physically rewire the IBT-4 inputs and use
  `config/hardware.pi4.example.yaml` as the template.

Safety:
- Aaron's reference mower has no dedicated E-stop. Its accessible physical power button is a verified master cutoff for every component downstream of the solar charge controller, including the Raspberry Pi and all mower hardware/motors.
- A dedicated hardwired E-stop is optional, but strongly recommended when a build has no other quick, accessible physical control that removes hazardous actuator power.
- Builders must document and bench-test their chosen physical intervention method. A software/API stop complements but does not replace a physical way to intervene.
- Software interlocks: tilt, obstacle, watchdog enforced.

### Time-of-Flight Sensors (VL53L0X x2)
- I2C Bus 1: SDA (GPIO 2), SCL (GPIO 3)
- Left Sensor Address: 0x29
- Right Sensor Address: 0x30
- Optional shutdown pins:
  - ToF Left Shutdown: GPIO 22
  - ToF Right Shutdown: GPIO 23
- Optional interrupts:
  - ToF Left IRQ: GPIO 6
  - ToF Right IRQ: GPIO 12 only when it does not conflict with the active UART profile.
    On the Pi 5 BNO085 UART4 profile, GPIO 12 is UART4 TX and ToF-right IRQ mode is unsupported.

Driver behavior (backend/src/drivers/sensors/vl53l0x_driver.py):
- Uses Adafruit CircuitPython backend first (adafruit-circuitpython-vl53l0x), then Pololu-style bindings.
- Falls back to previous reading if hardware access errors occur.
- Honors environment overrides:
  - TOF_BUS (default 1)
  - TOF_LEFT_ADDR (default 0x29)
  - TOF_RIGHT_ADDR (default 0x30)
  - TOF_RANGING_MODE (short|better_accuracy|best_accuracy|long_range|high_speed; default better_accuracy)
  - TOF_TIMING_BUDGET_US (default 66000 — 66 ms, better_accuracy mode)
- Timing budget is also set via `config/hardware.yaml` `tof_config.timing_budget_us`. The configured default is
  66 000 µs (66 ms, better_accuracy mode), giving 3× faster obstacle detection than the previous 200 ms setting.
- You can also set these in `config/hardware.yaml` under `sensors.tof_config`.

Verification steps:
1. Ensure SIM_MODE=0 in the systemd unit or shell.
2. `sudo i2cdetect -y 1` should show 0x29 and 0x30.
3. Start the backend and open the dashboard; the ToF tiles should update with live distances.
4. If no readings appear, check journal logs for `vl53l0x` messages and verify the Python binding is installed.

### Environmental Sensor (BME280)
- I2C Bus 1: Address 0x76

### Power Monitor (INA3221)
- I2C Bus 1: Address 0x40
- Channel mapping per spec:
  - CH1: Battery
  - CH2: Unused
  - CH3: Solar Input

### Victron SmartSolar BLE telemetry
- Optional replacement or supplement for INA3221 readings.
- Follow `docs/victron-ble-integration.md` to install the `victron-ble` CLI, patch the upstream scanner guard, and register the Instant Readout key.
- Configure the `victron` block in the ignored runtime `config/hardware.yaml`; set `prefer_battery`, `prefer_solar`, and `prefer_load` to prioritize SmartSolar data when both sources are available. Never put a live Instant Readout key in tracked examples or docs.
- Each response reports its actual source. When `prefer_battery: true`, missing Victron battery voltage stays unavailable instead of silently switching to INA3221; this keeps a disconnected preferred source from looking healthy. Other metrics follow their configured preference policy.

### IMU (BNO085)
- Pi 5: /dev/ttyAMA4 → GPIO 12 (TXD4), GPIO 13 (RXD4)
- Pi 4B: UART4 uses GPIO 24 (TXD4) and GPIO 21 (RXD4). This conflicts with the
  legacy Pi 5 blade GPIO 24 wiring, so the Pi 4B IBT-4 blade profile uses GPIO 26/27 instead.
  Verify with `dtoverlay=uart4` and `gpioinfo`.

#### UART mode: RVC vs SHTP (the PS1 strap)

The BNO085's **PS1 pin selects the UART protocol in hardware**. Software cannot
change it — the strap decides, and the driver must match.

| PS1 | Mode | Baud | Contents |
|-----|------|------|----------|
| **HIGH** | **RVC** (recommended) | 115,200 | 19-byte frame @ 100 Hz: yaw/pitch/roll + accel, per-frame checksum |
| LOW (board default) | SHTP | 3,000,000 | Full fusion, gyro, magnetometer, calibration registers |

**RVC is recommended for LawnBerry.** Navigation needs heading, tilt, and accel;
it deliberately ignores the magnetometer (motor-current interference) and derives
calibration status from stream uptime, so SHTP's extra data is unused. RVC also
runs 26× slower, checksums every frame, and resynchronises after corruption —
which matters on jumper wire next to brushed motors. It is parsed in-tree
(`parse_rvc_frame` / `RvcStream`), with no third-party library.

On the common Adafruit BNO08x breakouts (e.g. 4754) PS1 is a labelled solder
jumper on the underside of the board; other vendors expose it as a header pin to
tie to 3V3. Consult your board's silkscreen — pull PS1 to 3V3 for RVC.

Set the transport in `config/hardware.yaml` under `imu.mode`:

```yaml
imu:
  type: BNO085
  port: /dev/ttyAMA4
  mode: auto        # auto (default) | rvc | shtp
```

`auto` probes RVC first — that probe is passive, listening only, so it cannot
disturb a sensor genuinely in SHTP mode — then falls back to SHTP. Set the mode
explicitly to skip the ~1.5 s detection at startup.

> [!WARNING]
> **SHTP at 3 Mbaud is unreliable on this hardware.** The `adafruit_bno08x`
> library desyncs against the live stream and crashes during its constructor's
> `soft_reset()`, alternating between
> `IndexError: list assignment index out of range` (`uart.py:118`, decoded SHTP
> channel outside the valid 0–5 range) and
> `RuntimeError: Unhandled UART control SHTP protocol`. Pre-aligning to a `0x7E`
> frame boundary does not help — the library has no resync path. If you must run
> SHTP, expect the IMU to be intermittently unavailable.

**Diagnosing "no heading":**
- `GET /api/v2/sensors/imu/status` → `imu_epoch_id: null` means **no transport
  ever opened**. That UUID is assigned only after a successful open.
- `initialized: true` is set unconditionally and is **not** evidence of success.
  Check `imu_epoch_id` and `connected` instead.
- Driver init warnings are emitted only at startup and are lost to journal
  rotation on a long-running unit. `systemctl restart lawnberry-backend` to
  regenerate them.
- To confirm what the sensor is actually sending, stop the backend (it holds the
  port exclusively) and sample the raw UART. Clean `0x7E`-delimited frames at
  3,000,000 baud mean PS1 is LOW (SHTP); `0xAA 0xAA`-headed 19-byte frames at
  115,200 mean PS1 is HIGH (RVC). Noise at every baud means power or wiring.

**IMU heading formula** (from `backend/src/services/navigation_service.py`):
```
adjusted_yaw = (-raw_yaw + imu_yaw_offset_degrees + session_heading_alignment) % 360.0
```
- `imu_yaw_offset_degrees`: static mechanical mounting offset from `config/hardware.yaml`
  (`imu.yaw_offset_degrees`). Must be `0.0` unless the IMU is physically rotated in its
  enclosure; do not use this as a heading-error correction knob.
- Do not use GPS movement from the calibration endpoint to set `imu.yaw_offset_degrees`; BNO085 Game Rotation Vector yaw is boot-relative, so mission startup owns dynamic GPS alignment.
- `session_heading_alignment`: dynamic per-mission offset derived from GPS Course Over Ground (COG) during the heading bootstrap drive at mission start. Resets at each new mission.

**GPS COG heading bootstrap**: At each mission start, the navigation service drives briefly forward at ~75% throttle for up to 5 seconds. It polls the shared sensor manager and derives GPS COG from receiver course or actual coordinate deltas. As soon as stable COG is available, `session_heading_alignment` is set and the bootstrap drive stops. This compensates for the BNO085's arbitrary yaw zero at power-on.

### GPS
- Preferred: USB (ZED-F9P RTK) → `/dev/lawnberry-gps` (udev symlink; configured via `gps.usb_device` in `config/hardware.yaml`)
- Alternative: UART0 for NEO-8M → /dev/serial0 at 115200 baud
- Localization owns the antenna-to-body-center correction when `gps.antenna_offset_forward_m` or
  `gps.antenna_offset_right_m` is set. These values describe the antenna location relative to the
  mower navigation point/body center: positive is forward/right, negative is behind/left. Example:
  if the antenna is 1.5 ft behind the point the mower should navigate from, set
  `gps.antenna_offset_forward_m: -0.46`.
- The corrected body-center coordinate is published only after a verified world-frame heading is
  available, such as GPS COG bootstrap alignment. Before that, telemetry reports the raw antenna
  position with `antenna_correction_state="pending_heading"` rather than inventing a body-center
  coordinate from boot-relative IMU yaw.
- Satellite/orthophoto imagery alignment is display-only and source-specific. Legacy
  `satellite_display_north_m/east_m` settings migrate to alignment profiles; Google, Esri, and
  custom orthophoto sources do not share offsets unless a profile explicitly aliases them.
- Use `POST /api/v2/sensors/gps/stationary-average` for stationary RTK reference averaging. It
  observes unique samples already acquired by the canonical sensor-manager owner, returns an averaged
  antenna coordinate for setup/reference workflows, and never writes a hidden GPS offset. Use
  `GET /api/v2/sensors/gps/status` to distinguish `live` from `cached` and inspect the real sample age;
  the status request itself never reads or competes for the serial device.

#### RTK Positioning with NTRIP Corrections

For centimeter-level accuracy, configure RTK corrections via NTRIP. **See the comprehensive guide:**
- **[GPS RTK with NTRIP Configuration Guide](gps-ntrip-setup.md)** - Complete step-by-step instructions

**Quick Setup Summary:**

Two methods are supported:

1. **Method 1: Direct GPS Configuration** (Recommended)
   - Configure NTRIP in the ZED-F9P using u-blox u-center (Windows)
   - GPS connects directly to NTRIP caster
   - More reliable, no Pi dependency
   - Set `gps_ntrip_enabled: true` in `config/hardware.yaml`

2. **Method 2: Pi-Forwarded NTRIP**
   - Pi connects to NTRIP caster and forwards corrections to GPS
   - Set `gps_ntrip_enabled: true` in `config/hardware.yaml`
   - Configure `.env` with: `NTRIP_HOST`, `NTRIP_PORT`, `NTRIP_MOUNTPOINT`, `NTRIP_USERNAME`, `NTRIP_PASSWORD`, `NTRIP_SERIAL_DEVICE`
   - Restart backend: `sudo systemctl restart lawnberry-backend`

**Verification:**
```bash
# Check GPS status
curl http://localhost:8081/api/v2/sensors/health | jq '.gps'

# Look for fix_type: "RTK_FIXED" (best) or "RTK_FLOAT" (processing)
# Target accuracy: < 0.05 meters (5cm)
```

### Drive Controller: RoboHAT RP2040 → Cytron MDDRC10 (preferred)
- Serial link (auto-discovery order when `motor_controller_port` is blank): `/dev/robohat` (udev symlink → `/dev/ttyACM0`), `/dev/serial0`, then `ttyAMA*` / `ttyACM*`; `/dev/ttyAMA4` (IMU) is always excluded
- Explicit port override: set `motor_controller_port` in ignored `config/hardware.yaml`; leave it `null` to use safe discovery.
- PWM and direction handled on RoboHAT; Pi communicates via serial API
- Encoders wired to RoboHAT for real-time counting

Alternative drive controller (fallback): L298N dual H-Bridge (basic PWM/dir via Pi GPIO, no encoder feedback).

## UART Configuration (Pi OS)
1. Enable UARTs in `raspi-config` (disable login shell on serial)
2. For Pi 5 IMU on UART4:
   - Add to `/boot/firmware/config.txt`:
     ```
     dtoverlay=uart4
     ```
3. Reboot and verify devices:
   ```bash
   ls -l /dev/ttyAMA4 /dev/serial0 || true
   ```

## I2C Verification
```bash
sudo apt install -y i2c-tools
sudo i2cdetect -y 1
# Expect addresses: 0x29 (VL53L0X Left), 0x30 (VL53L0X Right), 0x76 (BME280), 0x40 (INA3221)
```

## Physical Intervention and Optional E-stop
- Aaron's reference mower does **not** have a dedicated physical E-stop. Its accessible main power button is the verified physical intervention method: it removes power from every component downstream of the solar charge controller, including the Raspberry Pi and all mower hardware/motors.
- A dedicated hardwired E-stop is an optional build feature. It is strongly recommended when the mower otherwise lacks a quick, accessible physical control that removes hazardous drive and blade power.
- When fitted, the E-stop should interrupt the actuator-energy path without relying on the Raspberry Pi, backend, network, or Web UI. An optional RoboHAT input may report its state, but software signaling must not be the only stopping mechanism.
- When relying on a power button or other cutoff instead, document exactly what it de-energizes and bench-test stopping behavior before ground or blade-enabled operation.
- The software emergency-stop API is a complementary remote latch, not a substitute for physical intervention.

## Testing Checklist
- Sensors health: GET /api/v2/sensors/health
- Telemetry: GET /api/v2/dashboard/telemetry (SIM_MODE=1 allowed)
- Blade control: POST /api/v2/control/blade (expect safety lockout by default)
- Drive control: POST /api/v2/control/drive (simulation or with RoboHAT)

## Troubleshooting
- No I2C devices: Check 3.3V and pull-ups; confirm I2C enabled
- UART not present: Ensure dtoverlay is set; verify no console on serial
- GPS not detected: Try different USB cable/port; check `dmesg`
- Blade doesn’t stop: Verify the selected physical cutoff or optional E-stop wiring, the IBT-4 enable path, and software interlocks

## References
- spec/hardware.yaml (pin map and device list)
- docs/hardware-overview.md (system diagram)
- docs/OPERATIONS.md (operational procedures)
