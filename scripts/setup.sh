#!/usr/bin/env bash
set -euo pipefail

# LawnBerry Pi v2 Setup Script (idempotent)
# - Creates required directories
# - Preserves user data (config/, data/, logs/)
# - Validates headless operation (NFR-015)
# - Prints environment summary

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
LOG_DIR="$ROOT_DIR/logs"
DATA_DIR="$ROOT_DIR/data"
CFG_DIR="$ROOT_DIR/config"

echo "[setup] LawnBerry Pi v2 setup starting..."
echo "[setup] Root: $ROOT_DIR"

# Flags
UPDATE=0
for arg in "$@"; do
  case "$arg" in
    --update)
      UPDATE=1
      ;;
  esac
done

# Create directories (idempotent)
mkdir -p "$LOG_DIR" "$DATA_DIR" "$CFG_DIR"

# Preserve data note (no deletion)
echo "[setup] Ensured directories exist: logs/, data/, config/ (preserved)"

# Copy example configs if not present
if [[ ! -f "$CFG_DIR/hardware.yaml" ]]; then
  echo "[setup] Installing example config: config/hardware.yaml"
  cat > "$CFG_DIR/hardware.yaml" <<'YAML'
# Example hardware configuration for LawnBerry Pi v2
# Documented options:
# - gps.type: ZED-F9P | Neo-8M
# - imu.type: BNO085
# - sensors.tof: [left, right] using VL53L0X
# - env_sensor: BME280
# - power_monitor: INA3221 (ch1=battery, ch3=solar)
gps:
  type: ZED-F9P
  # NTRIP corrections are typically enabled on the ZED-F9P via u-center (on-device)
# This flag reflects that RTK corrections are in use, even if not managed by the Pi.
gps_ntrip_enabled: true
imu:
  type: BNO085
sensors:
  tof:
    - left
    - right
  env_sensor: BME280
power_monitor:
  type: INA3221
  channels:
    battery: 1
    solar: 3
motor_controller:
  type: RoboHAT_RP2040
blade_controller:
  # Blade uses IBT-4 H-Bridge (GPIO 24 -> IN1, GPIO 25 -> IN2)
  type: IBT_4
camera:
  enabled: false
YAML
fi

if [[ ! -f "$CFG_DIR/limits.yaml" ]]; then
  echo "[setup] Installing example config: config/limits.yaml"
  cat > "$CFG_DIR/limits.yaml" <<'YAML'
# Safety limits and thresholds (Constitutional)
estop_latency_ms: 100          # MUST be <= 100ms
tilt_threshold_degrees: 30
tilt_cutoff_latency_ms: 200    # MUST be <= 200ms
battery_low_voltage: 11.5
battery_critical_voltage: 10.0
motor_current_max_amps: 10.0
watchdog_timeout_ms: 1000
geofence_buffer_meters: 0.5
high_temperature_celsius: 80
tof_obstacle_distance_meters: 0.2
YAML
fi

# Headless validation (NFR-015)
if [[ -z "${DISPLAY:-}" ]]; then
  echo "[setup] Headless mode detected (DISPLAY is empty): PASS"
else
  echo "[setup] Warning: DISPLAY is set ($DISPLAY) - ensure headless operation for production"
fi

# Platform summary
echo "[setup] Platform: $(uname -a)"
echo "[setup] Python: $(python3 --version 2>/dev/null || echo 'not found')"

# Ensure uv is installed
if ! command -v uv >/dev/null 2>&1; then
  echo "[setup] Installing uv package manager..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Sync Python environment from lockfile (reproducible)
if [[ -f "$ROOT_DIR/uv.lock" ]]; then
  echo "[setup] Installing Python dependencies via uv (frozen lockfile)..."
  # Use project root as working directory
  (cd "$ROOT_DIR" && uv sync --frozen)
else
  echo "[setup] WARNING: uv.lock not found; creating environment from pyproject (non-frozen)."
  (cd "$ROOT_DIR" && uv sync)
fi

# Optional update step to refresh lock and re-sync explicitly when requested
if [[ $UPDATE -eq 1 ]]; then
  echo "[setup] --update specified: attempting to update dependencies and refresh lockfile."
  (cd "$ROOT_DIR" && uv lock && uv sync)
fi

# Ensure cloudflared tunnel binary is installed
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "[setup] Installing Cloudflare Tunnel (cloudflared)..."
  TMP_DEB="$(mktemp)"
  if curl -fsSL --output "$TMP_DEB" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb; then
    if ! sudo dpkg -i "$TMP_DEB" >/dev/null 2>&1; then
      echo "[setup] cloudflared install reported missing dependencies; attempting fix..."
      sudo apt-get install -y -f >/dev/null 2>&1
      sudo dpkg -i "$TMP_DEB" >/dev/null 2>&1
    fi
  else
    echo "[setup] WARNING: Failed to download cloudflared binary. Please install manually." >&2
  fi
  rm -f "$TMP_DEB"
else
  echo "[setup] cloudflared already installed"
fi

# Ensure ngrok agent is available as fallback provider
if ! command -v ngrok >/dev/null 2>&1; then
  echo "[setup] Installing ngrok agent..."
  if [[ ! -f /etc/apt/sources.list.d/ngrok.list ]]; then
    curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
    echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list >/dev/null
  fi
  sudo apt-get update >/dev/null 2>&1
  sudo apt-get install -y ngrok >/dev/null 2>&1 || echo "[setup] WARNING: Failed to install ngrok; install manually if needed." >&2
else
  echo "[setup] ngrok already installed"
fi

echo "[setup] Complete. You can now run the backend."

# --- Automated HTTPS & Certificate Setup (idempotent) ---
# Goal: Zero-touch HTTPS. If nginx is missing, install and configure self-signed.
# If LB_DOMAIN and LETSENCRYPT_EMAIL are present in .env, automatically switch to Let's Encrypt

# Load .env if present to discover TLS configuration
if [[ -f "$ROOT_DIR/.env" ]]; then
  # shellcheck source=.env
  source "$ROOT_DIR/.env"
fi

install_units_once() {
  local unit_src="$ROOT_DIR/systemd"
  local unit_dst="/etc/systemd/system"
  sudo install -m 0644 -o root -g root "$unit_src/lawnberry-cert-renewal.service" "$unit_dst/" || true
  sudo install -m 0644 -o root -g root "$unit_src/lawnberry-cert-renewal.timer" "$unit_dst/" || true
  sudo systemctl daemon-reload || true
}

ensure_nginx_https() {
  if ! command -v nginx >/dev/null 2>&1; then
    echo "[setup][https] Installing nginx..."
    sudo apt-get update -y && sudo apt-get install -y nginx
  fi
  echo "[setup][https] Ensuring self-signed HTTPS baseline (nginx + redirect + ACME webroot)"
  sudo FRONTEND_PORT="${FRONTEND_PORT:-3000}" BACKEND_PORT="${BACKEND_PORT:-8081}" bash "$ROOT_DIR/scripts/setup_https.sh"
}

maybe_setup_lets_encrypt() {
  local domain="${LB_DOMAIN:-${DOMAIN:-}}"
  local email="${LETSENCRYPT_EMAIL:-${EMAIL:-}}"
  if [[ -n "$domain" && -n "$email" ]]; then
    echo "[setup][https] Detected LB_DOMAIN/EMAIL; attempting Let's Encrypt provisioning for $domain"
    sudo DOMAIN="$domain" EMAIL="$email" ALT_DOMAINS="${ALT_DOMAINS:-}" CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}" bash "$ROOT_DIR/scripts/setup_lets_encrypt.sh" || echo "[setup][https] WARNING: Let's Encrypt setup failed; continuing with self-signed"
  else
    echo "[setup][https] No LB_DOMAIN/LETSENCRYPT_EMAIL set; keeping self-signed until configured in .env"
  fi
}

enable_cert_renew_timer() {
  install_units_once
  echo "[setup][https] Enabling certificate renewal/validation timer"
  sudo systemctl enable --now lawnberry-cert-renewal.timer || true
  # Prefer our new timer over legacy ACME timer if present
  if systemctl list-unit-files | grep -q '^lawnberry-acme-renew.timer'; then
    echo "[setup][https] Disabling legacy lawnberry-acme-renew.timer"
    sudo systemctl disable --now lawnberry-acme-renew.timer || true
  fi
  if systemctl list-unit-files | grep -q '^lawnberry-acme-renew.service'; then
    echo "[setup][https] Disabling legacy lawnberry-acme-renew.service"
    sudo systemctl disable --now lawnberry-acme-renew.service || true
  fi
}

# Execute HTTPS automation
ensure_nginx_https
maybe_setup_lets_encrypt
enable_cert_renew_timer

echo "[setup][https] HTTPS is configured. If a real domain is set in .env, a valid Let's Encrypt cert will be provisioned automatically."
