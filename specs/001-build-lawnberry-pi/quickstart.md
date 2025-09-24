# LawnBerry Pi v2 Quickstart Guide

## Prerequisites
- Raspberry Pi 5 (8 GB) primary platform or Pi 4B (2–8 GB) compatible fallback running Raspberry Pi OS Bookworm 64-bit
- MicroSD card (≥32 GB, Class 10)
- Sensors & peripherals (per `/spec/hardware.yaml`): BNO085 (UART4), VL53L0X left 0x29 & right 0x30, BME280 0x76, SSD1306 0x3C, INA3221 0x40 with fixed channels (Ch1 battery, Ch2 unused, Ch3 solar), hall encoders on RoboHAT
- GPS (choose one, never both): ZED-F9P RTK over USB with NTRIP (preferred) or Neo-8M over UART (alternative)
- Motor drive (choose one path): RoboHAT RP2040 → Cytron MDDRC10 (preferred) or L298N dual H-bridge (fallback)
- Blade control: IBT-4 H-Bridge on GPIO24/25 with tilt & e-stop interlocks
- Camera: Raspberry Pi Camera Module (v2/v3) with Picamera2 support
- AI acceleration: Coral USB TPU (isolated `venv-coral`) → optional Hailo HAT → CPU TFLite fallback
- Wi-Fi network for runtime connectivity (Ethernet bench-only diagnostics)

## Installation

### 1. System Setup
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3.11 python3.11-venv libcamera-dev

# Clone repository and switch to feature branch
git clone https://github.com/acredsfan/lawnberry_pi.git
cd lawnberry_pi/v2/lawnberry-v2
```

### 2. Automated Installation
```bash
sudo ./scripts/pi_bootstrap.sh
```
The bootstrap script:
- Installs uv and creates the primary Python environment plus isolated `venv-coral`
- Installs project dependencies and validates forbidden packages (`pycoral`, `edgetpu`) stay out of the main env
- Detects optional hardware (Coral USB, Hailo HAT, RoboHAT) and records availability
- Installs systemd units (`mower-core`, `camera-stream`, `webui`)
- Generates configuration samples and verifies bus/address wiring

### 3. Configuration
```bash
cp .env.example .env
nano .env
```
Key variables:
- `HARDWARE_CONFIG_PATH=/spec/hardware.yaml`
- `GPS_MODE=f9p_usb` **or** `GPS_MODE=neo8m_uart` (mutually exclusive)
- `DRIVE_CONTROLLER=robohat_mddrc10` **or** `DRIVE_CONTROLLER=l298n_alt`
- `ACCELERATOR_ORDER=coral,hailo,cpu` (reorder if hardware missing)
- `SIM_MODE=0` (set to `1` for full simulated drivers)
- `WIFI_SSID` (runtime network), `ETHERNET_BENCH_ONLY=true`
- `CAMERA_RESOLUTION=1280x720`
- `LOG_LEVEL=INFO`

## First Run

### 1. Start Services
```bash
sudo systemctl enable mower-core camera-stream webui
sudo systemctl start mower-core camera-stream webui
sudo systemctl status mower-core
sudo systemctl status camera-stream
sudo systemctl status webui
```

### 2. Access Web Interface
1. Browse to `http://<pi-ip>:8000`
2. Retro 80s dashboard should load; confirm WebSocket connection indicator is green and header displays the official logo/icon set
3. Open `http://<pi-ip>:8001/camera` for Picamera2→GStreamer stream and ensure the embed panel at `/dashboard` reflects same feed
4. Navigate through the branded WebUI surfaces:
  - `/dashboard` — live telemetry, power, GPS, safety banner
  - `/map-setup` — yard boundary + zone editor using `LawnBerryPi_Pin.png`
  - `/manual` — joystick/gamepad controls with motor + blade restraint indicators
  - `/mow-plan` — scheduler + job timeline with progress sparklines
  - `/ai-train` — AI image gallery, labeling, export
  - `/settings` & `/docs` — configuration panels and embedded documentation

### 3. Hardware Verification Checklist
- Sensors report **Active** with correct bus/address labels (UART4, I2C 0x29/0x30/0x3C/0x76, etc.)
- GPS panel shows selected mode (F9P + NTRIP or Neo-8M) with current fix type
- Power dashboard maps INA3221 channels correctly: Ch1 Battery, Ch2 Unused, Ch3 Solar
- AI panel lists active accelerator tier (Coral → Hailo → CPU) and shows Coral isolated in `venv-coral` when present
- Motion tab reflects chosen drive controller and hall encoder feedback
- Blade control respects tilt/e-stop interlocks before enabling IBT-4
- Branding audit: Header displays `LawnBerryPi_logo.png`, favicon uses `LawnBerryPi_icon2.png`, and UI colors match neon palette derived from logo

## Safety Testing

### Emergency Stop Drill
```bash
curl -X POST http://localhost:8000/api/v1/navigation/emergency_stop \
  -H "Content-Type: application/json" \
  -d '{"reason": "safety_test"}'
```
Expected: Motor outputs drop to zero in <10 ms, UI displays emergency banner, requires manual reset.

### Tilt Detection
1. Gently tilt mower beyond safety threshold (>30°).
2. Confirm automatic blade cutoff, motor lockout, and WebUI alert.
3. Verify logs contain `safety_event` with tilt trigger data.

### Obstacle Detection
- Place object in front of mower; ensure VL53L0X pair reports obstacle and navigation switches to avoidance.
- If Coral/Hailo available, confirm AI overlay highlights obstacle.

### API & WebSocket Smoke Tests
```bash
# REST snapshot payloads
curl http://localhost:8000/api/v1/telemetry/snapshot | jq '.summary_metrics'
curl http://localhost:8000/api/v1/map/config | jq '.mowing_zones[0]'
curl http://localhost:8000/api/v1/jobs/active | jq '.[].status'
curl http://localhost:8000/api/v1/weather/current | jq '.temperature_c'

# WebSocket telemetry stream (requires websocat or wscat)
websocat ws://localhost:8000/ws/telemetry
```
Expected: JSON payloads match schemas defined in contracts, WebSocket emits `telemetry` events at 5–10 Hz with consistent snapshot IDs.

## Basic Operation

### Manual Mode
1. Switch WebUI to **Manual**.
2. Jog wheels forward/backward; confirm hall encoder counts and motor status update.
3. Toggle blade and observe IBT-4 current draw on power dashboard.

### Autonomous Mode
1. Define mowing bounds and pattern in WebUI.
2. Ensure GPS fix quality meets thresholds (RTK Fixed for F9P, 3D Fix minimum otherwise).
3. Start run and monitor telemetry, power, and safety event feeds.

### Simulation Mode (SIM_MODE=1)
- Enables simulated GPS (F9P & Neo-8M), IMU, BME280, ToF, blade, motor (both controllers), and power.
- Ideal for CI and development without hardware; WebUI labels data as **Simulated**.

### Map & Zone Editor Walkthrough
1. In `/map-setup`, import satellite tiles or upload a stitched yard map.
2. Trace the yard outline, define named mowing zones with cut height presets, and mark no-go regions.
3. Save changes and confirm `/api/v1/map/config` reflects new GeoJSON plus timestamps; Telemetry overlays should show updated boundaries.

### Job Timeline & Scheduler
1. From `/mow-plan`, schedule a `MOW_ZONE` job; verify it appears under upcoming runs.
2. When job starts, watch `/jobs` timeline update progress %, ETA, and AI annotations via TelemetrySnapshot stream.
3. Cancel or complete job and confirm `curl http://localhost:8000/api/v1/jobs/history` lists final status.

### AI Dataset Review
1. In `/ai-train`, review latest `AiImageRecord` entries; filter by model version and runner type.
2. Approve or reject auto-labeled frames and export the current selection to `./artifacts/datasets`.
3. Verify metadata via `curl http://localhost:8000/api/v1/datasets` and ensure files reference `LawnBerryPi_icon2.png` overlay when rendered in UI.

## Validation Tests

1. **Sensor Accuracy**: IMU 9.8 m/s² ±0.2 on Z when level; ToF readings within ±5 cm; INA3221 battery voltage within ±0.1 V of multimeter.
2. **AI Performance**: Coral <50 ms, Hailo <100 ms, CPU TFLite <200 ms; fallback recorded in telemetry when tier unavailable.
3. **Telemetry Latency**: WebSocket updates <100 ms, manual command response <50 ms, emergency stop <10 ms.
4. **Service Resilience**: Restart `camera-stream` and confirm WebUI auto-reconnects and power mapping persists; check `/ws/map` pushes updated overlays once services recover.
5. **API Contract Compliance**: Run contract tests (`pytest tests/contract`) to validate REST/WS schemas against updated snapshot/job/map models.
6. **Migration Sanity**: If upgrading from v1, execute `scripts/migrate_from_v1.sh` and verify settings/telemetry history imported.

## Troubleshooting

### Sensor Not Detected
```bash
sudo i2cdetect -y 1
sudo usermod -a -G gpio,i2c,lpp lawnberry
journalctl -u mower-core -f | grep SENSOR
```

### GPS Mode Mismatch
```bash
journalctl -u mower-core -f | grep GPS
ls /dev/ttyACM*   # F9P (USB)
ls /dev/ttyAMA4   # Neo-8M (UART4)
```
Ensure `.env` `GPS_MODE` matches connected hardware and only one driver is enabled.

### INA3221 Channel Warning
```bash
python scripts/debug_power_map.py
```
If channel roles differ from canonical mapping, inspect wiring before clearing alarm.

### AI Acceleration Issues
```bash
# Coral
source /opt/coral/venv-coral/bin/activate
python -c "import tflite_runtime.interpreter as tflite; print('Coral OK')"

# Hailo
hailo fw-control list
```
Confirm `ACCELERATOR_ORDER` aligns with detected hardware.

### Branding or Theming Issues
```bash
# Verify assets copied into frontend build
ls frontend/public | grep 'LawnBerryPi'

# Rebuild frontend assets
scripts/build_frontend.sh
```
Ensure the WebUI loads the logo/icon and neon color tokens; check browser cache or service worker if stale assets persist.

### WebUI Access Problems
```bash
sudo ufw allow 8000/tcp
sudo ufw allow 8001/tcp
sudo systemctl restart webui
```

For persistent issues, gather logs with `scripts/support_bundle.sh` and attach INA3221 channel readings, GPS mode, and AI runner status.