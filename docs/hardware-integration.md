# LawnBerry Pi v2 - Hardware Integration Guide

This guide documents wiring, pin assignments, and integration steps for Raspberry Pi 5 and Raspberry Pi 4B. Always disconnect power before wiring. Refer to `spec/hardware.yaml` for canonical configuration.

## Platform Notes
- Supported: Raspberry Pi OS Bookworm (64-bit) only
- Python 3.11.x required
- GPIO differences: Some UART pins differ between Pi 4B and Pi 5; use alternatives noted below.

## Pin Assignments (from spec/hardware.yaml)

### Blade Driver (IBT-4 H-Bridge)
- GPIO 24 → IN1 (Blade IN1)
- GPIO 25 → IN2 (Blade IN2)
- Power: 12V from battery through appropriate fuse
- Ground: Common ground with Raspberry Pi

Safety:
- Ensure E-stop physically cuts blade power path.
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
  - ToF Right IRQ: GPIO 12

### Environmental Sensor (BME280)
- I2C Bus 1: Address 0x76

### Power Monitor (INA3221)
- I2C Bus 1: Address 0x40
- Channel mapping per spec:
  - CH1: Battery
  - CH2: Unused
  - CH3: Solar Input

### IMU (BNO085)
- Preferred: UART4 at 3,000,000 baud
- Pi 5: /dev/ttyAMA4 → GPIO 12 (TXD4), GPIO 13 (RXD4)
- Pi 4B: Alternative pins may be required; map to rpi4_alt_pin as specified (e.g., TXD4 on GPIO 24, RXD4 on GPIO 21). Verify with `dtoverlay=uart4` and `gpioinfo`.

### GPS
- Preferred: USB (ZED-F9P RTK) → /dev/ttyACM*
- Alternative: UART0 for NEO-8M → /dev/serial0 at 115200 baud

### RoboHAT RP2040 → Cytron MDDRC10 (Drive)
- Serial link: /dev/serial0 or /dev/ttyACM0
- PWM and direction handled on RoboHAT; Pi communicates via serial API
- Encoders wired to RoboHAT for real-time counting

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

## Emergency Stop Wiring
- Hardware E-stop must cut power to blade driver and optionally signal RoboHAT input.
- Software API complements hardware E-stop for remote control.

## Testing Checklist
- Sensors health: GET /api/v2/sensors/health
- Telemetry: GET /api/v2/dashboard/telemetry (SIM_MODE=1 allowed)
- Blade control: POST /api/v2/control/blade (expect safety lockout by default)
- Drive control: POST /api/v2/control/drive (simulation or with RoboHAT)

## Troubleshooting
- No I2C devices: Check 3.3V and pull-ups; confirm I2C enabled
- UART not present: Ensure dtoverlay is set; verify no console on serial
- GPS not detected: Try different USB cable/port; check `dmesg`
- Blade doesn’t stop: Verify E-stop wiring and IBT-4 enable path; check software interlocks

## References
- spec/hardware.yaml (pin map and device list)
- docs/hardware-overview.md (system diagram)
- docs/OPERATIONS.md (operational procedures)
