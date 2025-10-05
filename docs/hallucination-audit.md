# LawnBerry Pi v2 – Hallucination Audit (Hardware/Features)

This audit lists hardware and feature mentions introduced in this repository that are not present in the canonical hardware baseline and integration docs. Source of truth used for grounding:
- spec/hardware.yaml (canonical hardware baseline)
- docs/hardware-integration.md
- docs/hardware-overview.md
- docs/hardware-feature-matrix.md

Scope: Identify out-of-scope or misleading items ("hallucinations"), where they appear, why they’re out-of-scope, and propose remediation.

## Summary of Findings

- Secondary USB cameras ("USB Cameras (compatible as secondary)")
- Ultrasonic sensors (HC-SR04)
- LiDAR modules (e.g., RPLidar A1/A2)
- Physical weather station hardware
- Cellular modem (4G/LTE USB)
- RC receiver (PPM/PWM manual override)
- Jetson Nano / Intel Movidius Neural Compute Stick accelerators
- Night-vision IR camera and pan/tilt servo mount
- Perimeter wire sensors
- u-blox NEO-9M GPS module (recommendation)
- Non-BNO085 IMUs (BNO055, MPU-9250, LSM9DS1)
- Pi Camera Module v3 as primary
- BTS7960 motor driver recommendation

Notes:
- Coral USB and Hailo accelerators are listed in spec/hardware.yaml; these are not hallucinations (though Hailo is optional and conflicts with RoboHAT per spec notes).
- OLED SSD1306 display and L298N blade/drive fallback are in the baseline; not hallucinations.

## Detailed Items

### 1) Secondary USB Cameras
- Where found:
  - docs/installation-setup-guide.md → Hardware Requirements → Camera System: "USB Cameras (compatible as secondary)"
- Why out-of-scope:
  - spec/hardware.yaml specifies a single Pi Camera (vision.camera: Pi Camera v2); no mention of multiple/secondary cameras.
  - docs/hardware-integration.md does not mention secondary cameras.
- Remediation:
  - Remove the bullet from installation guide, or move to a "Future Considerations" section clearly marked as not implemented/spec’d.
  - If multi-camera is desired later, add to spec/hardware.yaml first with platform constraints.

### 2) Ultrasonic Sensors (HC-SR04)
- Where found:
  - docs/installation-setup-guide.md → Hardware Requirements → Proximity & Safety: "Ultrasonic Sensors: 4x HC-SR04 or equivalent"
  - docs/hardware-feature-matrix.md → Sensors: Ultrasonic (optional) [present as optional]
- Why out-of-scope:
  - spec/hardware.yaml sensors list VL53L0X ToF (x2), BME280, BNO085; no ultrasonic devices.
- Remediation:
  - Remove from installation guide. In feature matrix, either remove or mark as explicitly "Not in baseline; not implemented" under a separate "Proposed/Backlog" section.

### 3) LiDAR (RPLidar A1/A2 or generic LiDAR)
- Where found:
  - docs/installation-setup-guide.md → Optional Hardware: "LiDAR Module: RPLidar A1/A2 or similar"
  - docs/hardware-feature-matrix.md → Advanced Sensors (Optional): LiDAR
  - docs/hardware-overview.md → Expansion Possibilities: LiDAR module
- Why out-of-scope:
  - Not present in spec/hardware.yaml devices list.
- Remediation:
  - Remove LiDAR mentions from installation guide. In the other docs, move LiDAR to a "Future/Ideas" section with a clear note: not supported/implemented in v2 baseline, not validated for Pi 4/5 constraints.

### 4) Physical Weather Station Hardware
- Where found:
  - docs/installation-setup-guide.md → Optional Hardware: "Weather Station: I2C weather sensors"
  - docs/hardware-feature-matrix.md → Optional/Future Hardware: Weather station integration (appears in multiple sections)
- Why out-of-scope:
  - spec/hardware.yaml only references external weather via software (OpenWeather) indirectly through services; no physical station listed.
- Remediation:
  - Remove from installation guide. In feature matrix, move to "Proposed/Backlog" and explicitly state: not implemented; current system uses OpenWeather API only.

### 5) Cellular Modem (4G/LTE USB)
- Where found:
  - docs/installation-setup-guide.md → Optional Hardware: "Cellular Modem: 4G/LTE USB modem for remote connectivity"
- Why out-of-scope:
  - spec/hardware.yaml comms include WiFi, Bluetooth (optional), Ethernet (bench-only); no cellular modem.
- Remediation:
  - Remove from installation guide. If cellular is desired later, add to spec with driver, bandwidth, and power constraints first.

### 6) RC Receiver (PPM/PWM Manual Override)
- Where found:
  - docs/hardware-feature-matrix.md → Optional and Future Hardware → Remote Control (PPM/PWM)
- Why out-of-scope:
  - Not present in spec/hardware.yaml or integration guide; introduces safety and control model changes.
- Remediation:
  - Remove from matrix or move under "Proposed/Backlog" with explicit note: not implemented and not planned without safety sign-off.

### 7) Jetson Nano / Intel Movidius NCS (AI accelerators)
- Where found:
  - docs/hardware-feature-matrix.md → AI Acceleration (Optional): Jetson Nano, Intel Movidius Neural Compute Stick
- Why out-of-scope:
  - spec/hardware.yaml only lists Coral (USB) and Hailo (optional/conflicts) with specific constraints; Jetson/Movidius are not part of supported accelerators and may not meet platform isolation requirements.
- Remediation:
  - Remove these items or move to "Not supported" section. Keep only Coral/Hailo per spec with clear constraints.

### 8) Night-Vision IR Camera and Pan/Tilt Servo Mount
- Where found:
  - docs/hardware-feature-matrix.md → Camera Configuration: Night Vision (optional IR camera), Pan/Tilt (optional servo mount)
- Why out-of-scope:
  - spec/hardware.yaml defines only the standard Pi Camera v2; no night-vision or pan/tilt hardware.
- Remediation:
  - Move to "Future/Ideas" with explicit "not implemented" disclaimer, or remove to avoid confusion.

### 9) Perimeter Wire Sensors
- Where found:
  - docs/installation-setup-guide.md → Proximity & Safety: "Perimeter Wire Sensors (optional)"
- Why out-of-scope:
  - Not present in spec/hardware.yaml or integration guide.
- Remediation:
  - Remove from installation guide. If considered later, must go through design, safety, and hardware abstraction updates.

### 10) u-blox NEO-9M GPS (recommendation)
- Where found:
  - docs/installation-setup-guide.md → Hardware Requirements → Navigation & Positioning: "Recommended: u-blox NEO-8M or NEO-9M based modules"
- Why out-of-scope:
  - spec/hardware.yaml defines primary GPS as SparkFun ZED-F9P (USB) and alternative as NEO-8M via UART. NEO-9M is not listed in the baseline.
- Remediation:
  - Remove NEO-9M mention; keep only ZED-F9P (USB) and NEO-8M (UART) per spec. If NEO-9M is desired, add to spec with interface and performance details first.

### 11) Non-BNO085 IMUs (BNO055, MPU-9250, LSM9DS1)
- Where found:
  - docs/installation-setup-guide.md → Hardware Requirements → IMU/Compass: "Recommended: BNO055, MPU-9250, or LSM9DS1"
- Why out-of-scope:
  - spec/hardware.yaml specifies BNO085 on UART4 at 3,000,000 baud; no other IMUs are included in the baseline.
- Remediation:
  - Replace the recommendations with BNO085 per spec. If alternatives are needed, enumerate in spec/hardware.yaml with interface, rates, and compatibility constraints.

### 12) Pi Camera Module v3 (primary)
- Where found:
  - docs/installation-setup-guide.md → Hardware Requirements → Camera System: "Pi Camera Module v3 (primary)"
- Why out-of-scope:
  - spec/hardware.yaml and docs/hardware-overview.md specify Pi Camera v2. Camera ownership and IPC assumptions are defined for that device.
- Remediation:
  - Amend to Pi Camera v2. If v3 is supported, update spec/hardware.yaml and camera-stream service notes, and verify on Pi 4/5.

### 13) BTS7960 motor driver (recommendation)
- Where found:
  - docs/installation-setup-guide.md → Hardware Requirements → Motor & Power: "Recommended: L298N, BTS7960, or similar"
- Why out-of-scope:
  - spec/hardware.yaml defines drive as RoboHAT→Cytron MDDRC10 (preferred) with L298N fallback; cutting system uses IBT-4. BTS7960 is not listed in baseline.
- Remediation:
  - Remove BTS7960 recommendation. Keep Cytron MDDRC10 (via RoboHAT) and L298N (fallback) for drive, and IBT-4 for blade per spec.

## Non-Findings (explicitly allowed by spec)
- OLED SSD1306 display (I2C 0x3C) – In spec/hardware.yaml and integration guide.
- L298N Dual H-Bridge fallback – In spec/hardware.yaml as alternative drive controller.
- Coral USB and Hailo-8 accelerators – In spec/hardware.yaml (Hailo optional with conflict note).

## Recommended Remediation Plan
- Update docs/installation-setup-guide.md to remove items 1, 2, 3, 4, 5, 9.
- Update docs/hardware-feature-matrix.md to either:
  - Remove items 2, 3, 4, 6, 7, 8, or
  - Move them under a clearly titled section (e.g., "Future/Backlog – Not in Baseline") with an explicit disclaimer: "Not implemented or supported in LawnBerry Pi v2 baseline. Not validated for Pi 4B/5."
- In docs/hardware-overview.md, move LiDAR from "Expansion Possibilities" to the same "Future/Backlog" section or add a strong disclaimer.
- Gate any remaining mentions with SIM_MODE-only notes or mark them as "not supported" to avoid operator confusion.

## Audit Metadata
- Date: 2025-10-05
- Grounding: spec/hardware.yaml, docs/hardware-integration.md, docs/hardware-overview.md
- Reviewer note: This audit focuses on hardware scope alignment. If a feature is desired, it must be added to spec/hardware.yaml and pass Platform Compliance checks (Pi 4B/5 compatibility, power/memory constraints, GPIO mapping, safety).
