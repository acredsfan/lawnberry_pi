#!/usr/bin/env bash
set -euo pipefail

# LawnBerry Pi - System Hardening Script
# Idempotent operations to harden a Raspberry Pi host for production.

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "This script must be run as root" >&2
  exit 1
fi

echo "[+] Updating package lists"
apt-get update -y >/dev/null

echo "[+] Installing ufw"
apt-get install -y ufw >/dev/null

echo "[+] Configuring firewall rules"
ufw --force reset >/dev/null || true
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null

# Allow SSH and HTTP/HTTPS as needed
ufw allow 22/tcp >/dev/null || true
ufw allow 80/tcp >/dev/null || true
ufw allow 443/tcp >/dev/null || true

# Allow LawnBerry API (adjust if running behind reverse proxy)
ufw allow 8080/tcp >/dev/null || true
ufw allow 8081/tcp >/dev/null || true
ufw allow 8082/tcp >/dev/null || true

ufw --force enable >/dev/null
echo "[+] Firewall enabled"

echo "[+] Creating service user 'lawnberry' if missing"
if ! id -u lawnberry >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin lawnberry
fi

echo "[+] Setting file permissions"
BASE_DIR="/home/pi/lawnberry"
LOG_DIR="${BASE_DIR}/logs"
CONFIG_DIR="${BASE_DIR}/config"

mkdir -p "$LOG_DIR" "$CONFIG_DIR"
chown -R lawnberry:lawnberry "$LOG_DIR" "$CONFIG_DIR"
chmod -R 750 "$CONFIG_DIR"
chmod -R 750 "$LOG_DIR"

# Secrets file permissions
if [[ -f "$CONFIG_DIR/secrets.json" ]]; then
  chmod 600 "$CONFIG_DIR/secrets.json"
  chown lawnberry:lawnberry "$CONFIG_DIR/secrets.json"
fi

echo "[+] Restricting log file access"
find "$LOG_DIR" -type f -name "*.log*" -exec chmod 640 {} +

echo "[+] Verifying kernel parameters (basic)"
SYSCTL=/etc/sysctl.d/99-lawnberry.conf
cat > "$SYSCTL" <<EOF
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.rp_filter = 1
kernel.kptr_restrict = 2
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
EOF
sysctl -p "$SYSCTL" >/dev/null

echo "[+] System hardening complete"
