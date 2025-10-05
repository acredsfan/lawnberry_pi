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

echo "[setup] Complete. You can now run the backend."
