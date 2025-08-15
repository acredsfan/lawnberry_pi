#!/usr/bin/env bash
# LawnBerryPi - Web API repair helper
# Ensures canonical runtime at /opt/lawnberry, correct unit files, Python venv deps,
# web-ui dist presence, then restarts API and probes health/UI. All steps bounded by timeouts.

set -euo pipefail

LOG_PREFIX="[repair-web-api]"
log(){ echo "$LOG_PREFIX $*"; }
warn(){ echo "$LOG_PREFIX WARN: $*" >&2; }
err(){ echo "$LOG_PREFIX ERROR: $*" >&2; }

SRC_ROOT="/home/pi/lawnberry"
RUN_ROOT="/opt/lawnberry"
API_UNIT_SRC="$SRC_ROOT/src/web_api/lawnberry-api.service"
SENSOR_UNIT_SRC="$SRC_ROOT/src/hardware/lawnberry-sensor.service"
API_UNIT_DST="/etc/systemd/system/lawnberry-api.service"
SENSOR_UNIT_DST="/etc/systemd/system/lawnberry-sensor.service"

timeout_cmd(){ local t="$1"; shift; timeout "$t" "$@"; }

log "Verifying canonical runtime at $RUN_ROOT"
if [[ ! -d "$RUN_ROOT" ]]; then
  log "Creating $RUN_ROOT and syncing source (first-time)"
  sudo mkdir -p "$RUN_ROOT"
  sudo rsync -a --delete \
    --exclude '.git/' --exclude 'node_modules/' --exclude 'web-ui/node_modules/' \
    --exclude 'venv/' --exclude 'reports/' \
    "$SRC_ROOT/" "$RUN_ROOT/"
  sudo chown -R pi:pi "$RUN_ROOT"
else
  log "Runtime exists; syncing key paths (quick)"
  sudo rsync -a --delete \
    --exclude '.git/' --exclude 'node_modules/' --exclude 'web-ui/node_modules/' \
    --exclude 'venv/' --exclude 'reports/' \
    "$SRC_ROOT/src/" "$RUN_ROOT/src/"
  sudo rsync -a "$SRC_ROOT/scripts/" "$RUN_ROOT/scripts/" || true
  sudo rsync -a "$SRC_ROOT/web-ui/" "$RUN_ROOT/web-ui/" --exclude 'node_modules/' || true
fi

log "Ensuring runtime venv"
if [[ ! -x "$RUN_ROOT/venv/bin/python3" ]]; then
  log "Creating venv in $RUN_ROOT/venv"
  sudo python3 -m venv --system-site-packages "$RUN_ROOT/venv"
  sudo chown -R pi:pi "$RUN_ROOT/venv"
fi

log "Checking FastAPI presence"
if ! "$RUN_ROOT/venv/bin/python" -c "import fastapi" >/dev/null 2>&1; then
  log "Installing backend requirements"
  "$RUN_ROOT/venv/bin/pip" install --upgrade pip >/dev/null 2>&1 || true
  timeout_cmd 300s "$RUN_ROOT/venv/bin/pip" install -r "$RUN_ROOT/requirements.txt" || warn "requirements install had issues"
fi

log "Ensuring log/data directories"
sudo mkdir -p /var/log/lawnberry /var/lib/lawnberry
sudo chown -R pi:pi /var/log/lawnberry /var/lib/lawnberry || true

log "Deploying systemd units"
if [[ -f "$API_UNIT_SRC" ]]; then sudo cp "$API_UNIT_SRC" "$API_UNIT_DST"; fi
if [[ -f "$SENSOR_UNIT_SRC" ]]; then sudo cp "$SENSOR_UNIT_SRC" "$SENSOR_UNIT_DST"; fi
sudo systemctl daemon-reload

log "Ensuring UI dist exists"
if [[ ! -f "$RUN_ROOT/web-ui/dist/index.html" ]]; then
  if command -v npm >/dev/null 2>&1; then
    log "Building web-ui (dist missing)"
    pushd "$RUN_ROOT/web-ui" >/dev/null
    timeout_cmd 600s npm install --no-audit --no-fund || warn "npm install failed"
    timeout_cmd 600s npm run build || warn "npm run build failed"
    popd >/dev/null
  else
    warn "npm not found; skipping UI build"
  fi
fi

log "Enabling and restarting lawnberry-api"
sudo systemctl enable lawnberry-api.service >/dev/null 2>&1 || true
timeout_cmd 15s sudo systemctl restart lawnberry-api.service || warn "restart failed"
sleep 2

log "Unit fragment path"
systemctl show -p FragmentPath lawnberry-api.service || true

log "Status snapshot"
systemctl --no-pager --full status lawnberry-api.service | sed -n '1,60p' || true

log "Probing /health"
if timeout_cmd 8s curl -fsS http://127.0.0.1:8000/health >/dev/null; then
  log "Health OK"
else
  err "Health probe failed; tailing logs"
  journalctl -u lawnberry-api -n 120 --no-pager || true
fi

log "Probing /ui/"
if timeout_cmd 8s curl -fsS http://127.0.0.1:8000/ui/ | head -n 5; then
  log "UI endpoint responded"
else
  warn "UI probe failed (check dist and logs above)"
fi

log "Checking listeners on :8000"
ss -ltnp | grep ':8000 ' || true

log "Done"
