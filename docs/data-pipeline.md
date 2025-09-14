# LawnBerryPi Data Pipeline (Hardware → UI)

This document sketches the end-to-end data flow for live telemetry and camera video from the Raspberry Pi hardware up to the Web UI.

## Overview

- Hardware sensors read by `SensorService` publish structured data to MQTT
- `MQTTBridge` (inside the FastAPI backend) subscribes to topics, caches recent payloads, and forwards to WebSocket clients
- The Web UI subscribes over a single WebSocket connection with topic filters and updates dashboards in real time

## MQTT Topics (Canonical and Aliases)

All topics are prefixed at the broker with `lawnberry/` (omitted below for brevity).

- `sensors/gps/data` — RTK GPS position: `{ latitude, longitude, altitude, accuracy, satellites, timestamp }`
- `sensors/imu/data` — BNO085 IMU: `{ orientation:{roll,pitch,yaw}, acceleration:{x,y,z}, gyroscope:{x,y,z}, temperature, timestamp }`
- `sensors/tof/data` — VL53L0X ToF aggregated: `{ left_distance, right_distance, timestamp }` (units: mm if > 5, else meters)
- `sensors/tof/left` — Left ToF (per-sensor): `{ distance_mm, timestamp }`
- `sensors/tof/right` — Right ToF (per-sensor): `{ distance_mm, timestamp }`
- `sensors/environmental/data` — BME280 Env: `{ temperature, humidity, pressure, rain_detected?, timestamp }`
- `sensors/power/data` — INA3221 Power: `{ battery_voltage, battery_current, battery_level, solar_voltage, solar_current, charging, timestamp }`
- `power/battery` — Legacy alias of `sensors/power/data` for backward compatibility
- `sensors/all` — Combined payload of all categories
- System/health:
  - `system/status` — service lifecycle (retained)
  - `system/health` — health summary
  - `system/tof_status` — ToF manager status snapshots
- RC/Control:
  - `rc/status`, `hardware/rc/status` — RoboHAT status (retained)
  - `hardware/rc/#` — Control commands (mode, PWM, etc.)

## Backend Behavior (FastAPI + MQTTBridge)

- `src/web_api/mqtt_bridge.py`
  - Subscribes to mapped topics (including `sensors/+/data`, `sensors/tof/+`, and legacy `power/battery`)
  - Normalizes payloads, updates in-memory cache, then broadcasts to all connected WebSocket clients
- `src/web_api/routers/websocket.py`
  - Supports topic subscriptions with MQTT wildcards over WebSocket
  - Forwards `sensor_data` frames to the UI and responds to `subscribe`/`unsubscribe`
- `src/web_api/main.py` (`/api/v1/status`)
  - Aggregates cached topics, prefers `sensors/power/data` with fallback to `power/battery`
  - ToF fallback: if `sensors/tof/data` missing/zero, derives from `sensors/tof/left` and `sensors/tof/right`

## UI Consumption

- WebSocket connection to `/ws/realtime`
- Subscribes to:
  - `sensors/+/data`, `sensors/power/data`, and others (`navigation/*`, `safety/*`, etc.)
- `web-ui/src/services/sensorDataService.ts`
  - Listens for `sensors/gps/data`, `sensors/imu/data`, `sensors/tof/data`, `sensors/environmental/data`, and `sensors/power/data`
  - Maintains current state and notifies components

## Camera Stream

- API initializes a shared `HardwareInterface` on startup (bounded by timeouts) and starts camera capture when available
- Endpoints:
  - `GET /api/v1/camera/stream` — MJPEG stream (with buffering disabled headers)
  - `GET /api/v1/camera/frame` — Single frame as base64 metadata payload
  - `GET /api/v1/camera/status` — Capability and last-frame info
- UI can embed `<img src="/api/v1/camera/stream" />` for live video

## Run Order (with timeouts)

- Verify venv, then run components:
  - `timeout 2s venv/bin/python -c "print('venv OK')"`
  - API: `timeout 5s venv/bin/python -m src.web_api.main` (for dev via uvicorn); prefer systemd services in production
  - Sensors: `timeout 60s venv/bin/python -m src.hardware.sensor_service` (may require hardware present)

## Notes

- Keep `power/battery` as a compatibility alias until all consumers migrate fully to `sensors/power/data`
- Per-ToF topics are subscribed and cached to support API/UI fallback when aggregated ToF is missing
- All blocking operations in services obey strict timeouts to avoid hangs on Pi OS Bookworm
