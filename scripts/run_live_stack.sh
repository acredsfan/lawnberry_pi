#!/usr/bin/env bash
set -euo pipefail

cd /home/pi/lawnberry

# Verify venv
if ! test -x venv/bin/python; then echo "ERROR: venv python missing or not executable"; exit 2; fi

# Stop potentially conflicting user services (ignore errors)
systemctl --user stop lawnberry-sensor 2>/dev/null || true
systemctl --user stop lawnberry-api 2>/dev/null || true

# Also stop system-level services if present (non-interactive; skip if not permitted)
if systemctl is-active --quiet lawnberry-sensor 2>/dev/null; then
  if sudo -n systemctl stop lawnberry-sensor 2>/dev/null; then :; else echo "[warn] cannot stop system lawnberry-sensor (no sudo)"; fi
fi
if systemctl is-active --quiet lawnberry-api 2>/dev/null; then
  if sudo -n systemctl stop lawnberry-api 2>/dev/null; then :; else echo "[warn] cannot stop system lawnberry-api (no sudo)"; fi
fi

# Kill any lingering production-installed processes that may hold GPIO lines
# e.g., /opt/lawnberry/venv/bin/python -m src.hardware.sensor_service
pkill -f '/opt/lawnberry/venv/bin/python -m src\.hardware\.sensor_service' 2>/dev/null || true
pkill -f '/opt/lawnberry/src/web_api/run_server\.py' 2>/dev/null || true
# Try non-interactive sudo in case those are root-owned processes
sudo -n pkill -f '/opt/lawnberry/venv/bin/python -m src\.hardware\.sensor_service' 2>/dev/null || true
sudo -n pkill -f '/opt/lawnberry/src/web_api/run_server\.py' 2>/dev/null || true

# Wait briefly and verify pins 22/23 are free; if not, print diagnostics and proceed anyway
sleep 0.5
if command -v /usr/bin/gpioinfo >/dev/null 2>&1; then
  if /usr/bin/gpioinfo | awk '/^\tline/{ln=$2+0; if(ln==22||ln==23) { if($0 ~ /\[used\]/) {exit 1}}}'; then
    : # free
  else
    echo "[warn] GPIO 22/23 appear to be in use before start; attempting to continue"
    /home/pi/lawnberry/scripts/debug_gpio_owners.sh 22 23 || true
  fi
fi

# Start sensor service (publishes to MQTT) with a timeout unless one is already running
USE_EXISTING_SENSOR=0
if systemctl is-active --quiet lawnberry-sensor 2>/dev/null; then
  echo "[info] Using existing system lawnberry-sensor service"
  USE_EXISTING_SENSOR=1
fi
if pgrep -fa 'python .*src\.hardware\.sensor_service' >/dev/null 2>&1; then
  echo "[info] Found an existing sensor_service process; will not start another"
  USE_EXISTING_SENSOR=1
fi

if [ "$USE_EXISTING_SENSOR" -eq 0 ]; then
  (timeout 120s venv/bin/python -m src.hardware.sensor_service > /tmp/lb_sensor_live.log 2>&1 & echo $! > /tmp/lb_sensor_live.pid) || true
  sleep 2
else
  # Touch empty log placeholder
  : > /tmp/lb_sensor_live.log || true
fi

# Start API with a timeout and readiness polling
export PYTHONPATH=src
(timeout 90s venv/bin/python -m uvicorn web_api.main:app --host 127.0.0.1 --port 8001 --log-level warning > /tmp/lb_uvicorn_live.log 2>&1 & echo $! > /tmp/lb_uvicorn_live.pid) || true

READY=0
for i in $(seq 1 24); do
  if curl -sSf --max-time 1 http://127.0.0.1:8001/health >/tmp/lb_health_live.json 2>/dev/null; then READY=1; break; fi
  sleep 0.5
done
if [ "$READY" -ne 1 ]; then
  echo "[health] no response from API"; tail -n 80 /tmp/lb_uvicorn_live.log || true; exit 1
fi

# Poll status until non-zero values observed or timeout
STATUS_JSON=""
for i in $(seq 1 30); do
  STATUS_JSON=$(curl -sSf --max-time 2 http://127.0.0.1:8001/api/v1/status || true)
  if [ -n "$STATUS_JSON" ]; then
    # Use python to check for non-zero readings (gps lat/lng, env temp, tof distances, battery voltage/current)
    python3 - "$STATUS_JSON" <<'PY'
import json, sys
j=json.loads(sys.argv[1])
nonzero=False
try:
  gps=j.get('position',{})
  if abs(float(gps.get('lat',0)))>0 or abs(float(gps.get('lng',0)))>0:
    nonzero=True
  env=j.get('sensors',{}).get('environmental',{})
  if float(env.get('temperature',0))!=0 or float(env.get('humidity',0))!=0 or float(env.get('pressure',0))!=0:
    nonzero=True
  tof=j.get('sensors',{}).get('tof',{})
  if float(tof.get('left',0))>0 or float(tof.get('right',0))>0:
    nonzero=True
  bat=j.get('battery',{})
  if float(bat.get('voltage',0))!=0 or float(bat.get('current',0))!=0:
    nonzero=True
except Exception:
  pass
print('OK' if nonzero else 'ZERO')
PY
    if [ "$(tail -n1 <<<"$(python3 - "$STATUS_JSON" <<'PY'
import json, sys
j=json.loads(sys.argv[1])
nonzero=False
try:
  gps=j.get('position',{})
  if abs(float(gps.get('lat',0)))>0 or abs(float(gps.get('lng',0)))>0:
    nonzero=True
  env=j.get('sensors',{}).get('environmental',{})
  if float(env.get('temperature',0))!=0 or float(env.get('humidity',0))!=0 or float(env.get('pressure',0))!=0:
    nonzero=True
  tof=j.get('sensors',{}).get('tof',{})
  if float(tof.get('left',0))>0 or float(tof.get('right',0))>0:
    nonzero=True
  bat=j.get('battery',{})
  if float(bat.get('voltage',0))!=0 or float(bat.get('current',0))!=0:
    nonzero=True
except Exception:
  pass
print('OK' if nonzero else 'ZERO')
PY
)" )" == "OK" ]; then
      break
    fi
  fi
  sleep 0.8
done

# Print a concise slice of status
if [ -n "$STATUS_JSON" ]; then
  echo "[live-status]"; echo "$STATUS_JSON" | head -c 600; echo
else
  echo "[live-status] no response"
fi

# Cleanup servers (only kill our own sensor process if we started it)
kill $(cat /tmp/lb_uvicorn_live.pid 2>/dev/null) 2>/dev/null || true
wait $(cat /tmp/lb_uvicorn_live.pid 2>/dev/null) 2>/dev/null || true
if [ "$USE_EXISTING_SENSOR" -eq 0 ]; then
  kill $(cat /tmp/lb_sensor_live.pid 2>/dev/null) 2>/dev/null || true
  wait $(cat /tmp/lb_sensor_live.pid 2>/dev/null) 2>/dev/null || true
fi

# Show recent logs for diagnostics
printf "\n--- sensor_service tail ---\n"; tail -n 80 /tmp/lb_sensor_live.log 2>/dev/null || true
printf "\n--- api tail ---\n"; tail -n 80 /tmp/lb_uvicorn_live.log 2>/dev/null || true
