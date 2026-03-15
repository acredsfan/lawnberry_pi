# LawnBerry Pi Hardware Feature Matrix

**Version:** 2.0  
**Purpose:** Supported hardware baseline, compatible fallbacks, and clearly labeled optional paths  
**Last Updated:** March 2026

This matrix is intentionally grounded in `spec/hardware.yaml` and `docs/hardware-integration.md`.
If this file conflicts with those sources, the spec and integration guide win.

## Baseline platform

### Supported Raspberry Pi models

| Platform | Status | Notes |
|---|---|---|
| **Raspberry Pi 5 (4–16GB)** | ✅ Primary baseline | Preferred deployment target for LawnBerry Pi v2. |
| **Raspberry Pi 4B (4–8GB)** | ✅ Supported fallback | Supported with pin/UART differences called out in `docs/hardware-integration.md`. |

### Platform characteristics

| Area | Baseline | Notes |
|---|---|---|
| OS | Raspberry Pi OS Bookworm (64-bit) | Current supported OS family. |
| Python | 3.11.x | Matches backend runtime target. |
| Storage | 32GB+ microSD recommended | Higher-capacity/high-endurance media strongly preferred for logs and updates. |
| Network | WiFi primary, Ethernet bench-only, Bluetooth optional | Matches `spec/hardware.yaml`. |

## Navigation and positioning

| Component | Interface | Status | Notes |
|---|---|---|---|
| **SparkFun GPS-RTK-SMA (u-blox ZED-F9P)** | USB | ✅ Preferred baseline | RTK-capable GPS path for high-accuracy positioning. |
| **NTRIP corrections** | Network | ✅ Supported | Configuration documented in `docs/gps-ntrip-setup.md`; provider is user-configured, not fixed to a single caster. |
| **u-blox NEO-8M** | UART | ✅ Supported fallback | Lower-accuracy fallback path when RTK hardware is unavailable. |
| **u-blox NEO-9M** | Varies | ⚠️ Doc-only recommendation | Mentioned as a possible future/alternate purchase choice, but not part of the canonical baseline. |

### GPS expectations

| Mode | Typical accuracy | Status |
|---|---|---|
| Standard GPS fallback | 3–5 m | ✅ Supported |
| RTK with corrections | 2–10 cm | ✅ Supported |

## Orientation and environmental sensing

| Component | Interface | Status | Notes |
|---|---|---|---|
| **BNO085 IMU** | UART4 | ✅ Baseline | Primary IMU/heading source. |
| **BNO055** | Varies | ⚠️ Backup-only mention | Keep as a possible backup only if you verify code support first. |
| **MPU-9250** | Varies | ⚠️ Backup-only mention | Same rule as BNO055: verify code support before use. |
| **LSM9DS1** | Varies | ❌ Not in baseline | Removed from active recommendations. |
| **BME280** | I2C `0x76` | ✅ Baseline | Environmental monitoring. |

## Obstacle sensing and local display

| Component | Interface | Status | Notes |
|---|---|---|---|
| **VL53L0X Left** | I2C `0x29` | ✅ Baseline | Left obstacle sensing. |
| **VL53L0X Right** | I2C `0x30` | ✅ Baseline | Right obstacle sensing. |
| **ToF shutdown pins (GPIO 22/23)** | GPIO | ✅ Optional within baseline | Supported optional wiring for power/address sequencing. |
| **ToF interrupt pins (GPIO 6/12)** | GPIO | ✅ Optional within baseline | Supported optional wiring. |
| **SSD1306 OLED 128x64** | I2C `0x3C` | ✅ Baseline | On-device status display. |
| **Ultrasonic sensors** | — | ❌ Not in baseline | Removed; not part of supported hardware. |

## Vision and AI acceleration

| Component | Interface | Status | Notes |
|---|---|---|---|
| **Pi Camera v2** | CSI | ✅ Baseline | Canonical camera device. Camera-stream service owns the device and exposes frames via IPC. |
| **Pi Camera v3 as primary** | CSI | ❌ Not in baseline | Not documented as the supported baseline camera. |
| **Secondary USB cameras** | USB | ❌ Not in baseline | Remove from active setup guidance unless spec changes. |
| **Google Coral USB Accelerator** | USB | ⚠️ Hardware present / software support limited | Listed in the hardware baseline; treat as available hardware with implementation status that must be validated feature-by-feature. |
| **Hailo-8 AI Hat** | HAT | ⚠️ Optional with caveat | Optional in spec, with explicit conflict note around concurrent RoboHAT use. |
| **CPU inference (TFLite / OpenCV-DNN)** | CPU | ✅ Available | Current safe fallback path for vision/AI experimentation. |
| **Jetson / Movidius / other accelerators** | — | ❌ Not supported | Not part of the supported LawnBerry v2 baseline. |

## Power system

| Component | Status | Notes |
|---|---|---|
| **30Ah LiFePO4 12V battery** | ✅ Baseline | Canonical battery chemistry and capacity. |
| **30W solar panel** | ✅ Baseline | Baseline solar input. |
| **15A MPPT controller** | ✅ Baseline | Baseline solar charge controller. |
| **INA3221 power monitor** | ✅ Baseline | Channel mapping: battery / unused / solar input. |
| **Victron SmartSolar BLE telemetry** | ✅ Optional within baseline | Optional supplement or preferred telemetry source when configured. |
| **Backup SLA battery** | ❌ Not in baseline | Not part of the supported hardware baseline. |

### Runtime expectations

| Metric | Baseline guidance | Notes |
|---|---|---|
| Typical runtime | 4–8 hours | Use conservative field guidance as default. |
| Best-case runtime | up to ~12 hours | Treat as best-case, terrain and solar dependent, not the default expectation. |

## Drive and cutting system

| Component | Status | Notes |
|---|---|---|
| **RoboHAT RP2040 → Cytron MDDRC10** | ✅ Preferred baseline | Primary drive-control path. |
| **L298N dual H-bridge** | ✅ Supported fallback | Lower-capability fallback path for drive control. |
| **Hall effect encoders** | ✅ Baseline | Four magnets per wheel per spec. |
| **997 DC blade motor** | ✅ Baseline | Current cutting motor. |
| **IBT-4 blade driver** | ✅ Baseline | GPIO 24 / 25 control path. |
| **BTS7960** | ❌ Not in baseline | Removed from recommendations. |

## Supported communication and buses

| Bus / interface | Status | Notes |
|---|---|---|
| **I2C bus 1** | ✅ Baseline | Primary bus for ToF, BME280, INA3221, OLED. |
| **UART4** | ✅ Baseline | BNO085 on Pi 5; Pi 4B alternate pins documented in integration guide. |
| **USB** | ✅ Baseline | GPS, Coral, high-gain WiFi adapter. |
| **GPIO** | ✅ Baseline | Blade control, optional ToF shutdown/interrupt, safety integration. |

## Configuration tiers

### Current supported baseline

| Area | Components | Status |
|---|---|---|
| Compute | Pi 5 primary / Pi 4B fallback | ✅ Supported |
| Navigation | ZED-F9P + NTRIP preferred, NEO-8M fallback | ✅ Supported |
| Sensors | Dual VL53L0X + BME280 + BNO085 + INA3221 + OLED | ✅ Supported |
| Vision | Pi Camera v2 | ✅ Supported |
| Drive | RoboHAT → Cytron MDDRC10 preferred, L298N fallback | ✅ Supported |
| Cutting | 997 motor + IBT-4 | ✅ Supported |

### Optional but still in scope

| Area | Component | Status | Notes |
|---|---|---|---|
| Power telemetry | Victron SmartSolar BLE | ✅ Optional | Supplement or preferred source over INA3221 when configured. |
| AI acceleration | Coral USB | ⚠️ Optional | Hardware is in baseline; validate software path before relying on it in production. |
| AI acceleration | Hailo-8 | ⚠️ Optional | Optional with explicit RoboHAT conflict caveat. |

### Out of scope for the supported baseline

| Item | Status | Guidance |
|---|---|---|
| LiDAR | ❌ Not in baseline | Future idea only; not supported today. |
| RC receiver manual override | ❌ Not in baseline | Would require safety and control-model redesign. |
| Cellular modem | ❌ Not in baseline | Remove from active setup guidance. |
| Weather-station hardware | ❌ Not in baseline | Not part of the current supported hardware list. |
| Night-vision / pan-tilt camera rigs | ❌ Not in baseline | Future-only concepts, not active support. |
| Perimeter-wire sensors | ❌ Not in baseline | Not part of current hardware architecture. |

## Pin and address summary

### GPIO usage from the canonical spec

| Physical pin | GPIO / UART | Role |
|---|---|---|
| 15 | GPIO 22 | ToF left shutdown |
| 16 | GPIO 23 | ToF right shutdown |
| 18 | GPIO 24 | Blade IN1 |
| 22 | GPIO 25 | Blade IN2 |
| 31 | GPIO 6 | ToF left interrupt |
| 32 | GPIO 12 | ToF right interrupt |
| 33 | RXD4 / Pi 4B alt GPIO 21 | BNO085 RX |
| 32 | TXD4 / Pi 4B alt GPIO 24 | BNO085 TX |

### I2C addresses

| Address | Device |
|---|---|
| `0x29` | VL53L0X left |
| `0x30` | VL53L0X right |
| `0x3C` | SSD1306 OLED |
| `0x40` | INA3221 |
| `0x76` | BME280 |

## Deployment guidance

- For exact wiring, UART overlays, and environment overrides, use `docs/hardware-integration.md`.
- For returning-maintainer context, use `docs/developer-toolkit.md`.
- For items not listed here, assume they are unsupported unless they are first added to `spec/hardware.yaml`.

## References

- `spec/hardware.yaml`
- `docs/hardware-integration.md`
- `docs/hardware-overview.md`
- `docs/hallucination-audit.md`
