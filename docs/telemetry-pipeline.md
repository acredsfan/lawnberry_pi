# Telemetry Pipeline: Hardware → MQTT → API/WebSocket → UI

This document sketches the complete data path from hardware initialization and sensor reads, through MQTT publication and API/WebSocket bridging, to the Web UI visualizations. It also includes quick verification commands at each hop with timeouts (Bookworm-safe).

## Overview

- Hardware services read sensors (ToF, INA3221, BNO085, BME280, GPS) and publish JSON to MQTT using canonical topics: `sensors/<type>/data` with per-device topics for ToF: `sensors/tof/<id>`.
- MQTT broker (mosquitto) routes messages locally.
- API MQTT bridge subscribes to sensor topics, caches latest values, and broadcasts over WebSocket to connected UI clients.
- Web UI subscribes to topics via WebSocket and renders data.

## Canonical Topics and Payloads

- Power: `sensors/power/data` (legacy alias `power/battery` still published)
- ToF: `sensors/tof/+` (e.g., `sensors/tof/left`, `sensors/tof/right`)
- IMU: `sensors/imu/data`
- Env: `sensors/env/data` (BME280)
- GPS: `sensors/gps/data`

Payload shape (typical):
```json
{
  "timestamp": 1757881000.123,
  "sensor_id": "ina3221",
  "value": { "voltage": 12.4, "current": 0.8, "temp": 36.1 },
  "unit": null,
  "quality": 0.98,
  "metadata": { "bus": 1 }
}
```

## Verification Checklist (end-to-end)

Always use the repo venv and hard timeouts.

1) Runtime is in sync (`/opt/lawnberry`)
```bash
timeout 20s diff -ru --brief /home/pi/lawnberry/src/web_api/mqtt_bridge.py /opt/lawnberry/src/web_api/mqtt_bridge.py || true
timeout 20s diff -ru --brief /home/pi/lawnberry/web-ui/src/services/sensorDataService.ts /opt/lawnberry/web-ui/src/services/sensorDataService.ts || true
```

2) Broker and bridge connectivity
```bash
timeout 10s systemctl is-active mosquitto || true
timeout 5s curl -fsS http://127.0.0.1:8000/api/v1/meta | jq '.mqtt_connected' || true
```

3) Hardware service publishing
```bash
timeout 15s sudo journalctl -u lawnberry-hardware -n 80 --no-pager | tail -n 80
# Quick local subscribe (requires mosquitto-clients)
timeout 10s mosquitto_sub -t 'lawnberry/sensors/+/data' -C 1 -W 5 || true
timeout 10s mosquitto_sub -t 'lawnberry/sensors/tof/+' -C 1 -W 5 || true
```

4) API bridge caching and WebSocket broadcast
```bash
# REST cache checks (examples; adjust as implemented)
timeout 5s curl -fsS http://127.0.0.1:8000/api/v1/sensors/power | jq || true
timeout 5s curl -fsS http://127.0.0.1:8000/health | jq || true

# WebSocket (one-shot) using websocat if available
# timeout 10s websocat -1 ws://127.0.0.1:8000/ws/realtime | head -n 20 || true
```

5) Web UI subscription
```bash
timeout 5s curl -fsS http://127.0.0.1:8000/ | head -n 20 # UI index served
# Open browser to the API-served UI and observe live widgets
```

## Typical Failure Modes and Targeted Checks

- UI shows no updates, API meta `mqtt_connected=false`:
  - API ↔ MQTT bridge down or broker not reachable.
  - Check `mosquitto` active and API logs for MQTT connection errors.

- Broker OK, API connected, but no sensor data:
  - Hardware service not publishing or topic mismatch.
  - Confirm `lawnberry-hardware` logs and `mosquitto_sub` receive on `sensors/+/data`.

- ToF missing only:
  - Ensure per-ToF topics `sensors/tof/+` are being published and subscribed by bridge.

- Power tile empty but others OK:
  - UI expects `sensors/power/data`; verify legacy alias exists but canonical is preferred.

## Operational Notes

- Canonical vs legacy topics: The system publishes canonical topics with legacy aliases for backward compatibility; UI and API prefer canonical.
- Auto-redeploy watcher observes `/home/pi/lawnberry` and redeploys to `/opt/lawnberry` with structured logs: DETECT → INIT → DEPLOY SUCCESS/FAILED.
- All scripts enforce timeouts; long or hanging commands should be avoided.

## Quick Redeploy

```bash
timeout 240s bash scripts/lawnberry-deploy.sh
timeout 10s bash scripts/health_check_web_api.sh http://127.0.0.1:8000
```
# Telemetry Pipeline: Hardware → MQTT → API/WebSocket → UI

This document sketches the end-to-end data flow and lists quick verification steps at each hop so we can pinpoint where data stops flowing.

## 1) Hardware Initialization & Sensor Publishers (src/hardware)
- Components: I2C/Serial/GPIO managers, sensor plugins (ToF VL53L0X, INA3221, BNO085, BME280, RTK GPS), `sensor_service.py`.
- Behavior: On startup, initialize managers, then loop-read sensors and publish to MQTT.
- Canonical topics (publish):
  - Power (INA3221): `sensors/power/data` (legacy alias `power/battery`)
  - ToF: `sensors/tof/left`, `sensors/tof/right` and `sensors/tof/data` aggregate
  - IMU: `sensors/imu/data`
  - Env (BME280): `sensors/environment/data`
  - GPS (RTK): `sensors/gps/data`
- Quick checks:
  - Service: `sudo systemctl is-active lawnberry-hardware`
  - Logs: `sudo journalctl -u lawnberry-hardware -n 120 --no-pager`
  - Publish smoke: `timeout 6s mosquitto_sub -t 'lawnberry/sensors/#' -v | head -n 20`

## 2) MQTT Broker
- Component: Mosquitto broker (local).
- Behavior: Accepts sensor publishes; API and any consumers subscribe to topics using wildcards.
- Quick checks:
  - Service: `sudo systemctl is-active mosquitto`
  - Subscriptions: `timeout 6s mosquitto_sub -t 'lawnberry/sensors/#' -v`

## 3) API MQTT Bridge & Cache (src/web_api/mqtt_bridge.py)
- Component: FastAPI app embeds an MQTT bridge that subscribes to canonical topics and caches last values for WebSocket broadcast and `/health`.
- Behavior: Subscribes to `sensors/+/data` and also specific `sensors/tof/+` for per-ToF.
- Quick checks:
  - API meta: `curl -fsS http://127.0.0.1:8000/api/v1/meta | jq` -> check `mqtt_connected: true`
  - Bridge cache test: `curl -fsS http://127.0.0.1:8000/health | jq` -> verify keys present (power, tof, imu, env, gps)

Note: The API allows up to ~12 seconds for the MQTT bridge to connect during startup. If the broker is slow or temporarily unavailable, the API continues booting and completes the MQTT connection in the background. After restarting the API service, wait up to 12 seconds before expecting `mqtt_connected: true`.

## 4) WebSocket → UI (web-ui)
- Component: WebSocket server in API; UI client subscribes to topics and updates widgets.
- Behavior: On connect, UI subscribes to `sensors/+/data` (including `sensors/power/data`) and receives broadcasts.
- Quick checks:
  - WebSocket clients: `sudo journalctl -u lawnberry-api -n 200 --no-pager | grep -i websocket`
    - WS stats: `timeout 5s curl -fsS http://127.0.0.1:8000/ws/connections | jq`
  - UI dist freshness: Auto-deploy handles minimal/full dist sync; to force: `FAST_DEPLOY_DIST_MODE=full bash scripts/lawnberry-deploy.sh`
  - Browser devtools: see incoming WS messages; ensure subscription to `sensors/power/data`.

## 5) Camera Stream (FYI)
- API endpoints provide the camera stream; not part of MQTT, but included in UI.

## Fast Triage Flow
1. Is `/opt` up to date? `bash scripts/lawnberry-deploy.sh` (should report SUCCESS)
2. Is broker up? `sudo systemctl is-active mosquitto`
3. Are sensor topics publishing? `timeout 6s mosquitto_sub -t 'lawnberry/sensors/#' -v`
4. Is API bridge connected? `curl -fsS :8000/api/v1/meta | jq .mqtt_connected`
5. Do WebSocket broadcasts show in API logs? `journalctl -u lawnberry-api | grep WebSocket`
6. If 1-5 pass but UI is stale: force full dist sync: `FAST_DEPLOY_DIST_MODE=full bash scripts/lawnberry-deploy.sh`

### Common Pitfall: Paho installed in wrong environment

If API logs show `ModuleNotFoundError: No module named 'paho'` or `paho-mqtt not installed` while the package exists in `/home/pi/.local`, it means the systemd service venv at `/opt/lawnberry/venv` is missing the dependency.

Fix quickly:

```bash
timeout 20s /opt/lawnberry/venv/bin/python -c "import sys; print(sys.executable)" && \
timeout 40s /opt/lawnberry/venv/bin/python - <<'PY' || echo MISSING
import importlib.util, sys
print('FOUND' if importlib.util.find_spec('paho.mqtt') else 'MISSING')
PY

# Install if missing
timeout 90s /opt/lawnberry/venv/bin/python -m pip install 'paho-mqtt>=2.1.0,<3.0.0'
sudo systemctl restart lawnberry-api
timeout 6s curl -fsS http://127.0.0.1:8000/api/v1/meta | jq '.mqtt_connected'
```

## Notes
- Canonical topics with legacy fallbacks preserved during migration. UI subscribes to canonical `sensors/power/data`.
- All steps enforce timeouts and run under Raspberry Pi OS Bookworm constraints.
