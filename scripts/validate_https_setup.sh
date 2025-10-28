#!/usr/bin/env bash
set -euo pipefail

# Validate HTTPS/ACME setup on Raspberry Pi (idempotent, safe)
# - Ensures nginx is installed and running
# - Ensures ACME challenge location is served on port 80
# - Verifies TLS termination on :443 (handshake + HTTP response)
# - Does NOT attempt to obtain a real certificate
#
# Usage:
#   ./scripts/validate_https_setup.sh
#   sudo ./scripts/validate_https_setup.sh --install-nginx   # allow installing nginx if missing

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

ALLOW_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --install-nginx)
      ALLOW_INSTALL=1
      ;;
  esac
done

need_cmd(){ command -v "$1" >/dev/null 2>&1 || { echo "[validate][ERR] Missing command: $1"; exit 1; }; }

need_cmd bash
need_cmd curl

if ! command -v nginx >/dev/null 2>&1; then
  if [[ $ALLOW_INSTALL -eq 1 ]]; then
    echo "[validate] nginx not found; installing..."
    sudo apt-get update -y && sudo apt-get install -y nginx
  else
    echo "[validate][ERR] nginx not found. Re-run with --install-nginx or run scripts/setup.sh first." >&2
    exit 1
  fi
fi

echo "[validate] Ensuring baseline HTTPS config via setup_https.sh (idempotent)"
sudo FRONTEND_PORT="${FRONTEND_PORT:-3000}" BACKEND_PORT="${BACKEND_PORT:-8081}" bash "$REPO_ROOT/scripts/setup_https.sh"

echo "[validate] Checking nginx configuration syntax"
sudo nginx -t >/dev/null

echo "[validate] Ensuring nginx is active"
sudo systemctl enable --now nginx >/dev/null 2>&1 || true

# Validate ACME challenge path on HTTP (port 80)
ACME_DIR=/var/www/.well-known/acme-challenge
TEST_FILE="lb-acme-test-$(date +%s)-$$"
sudo mkdir -p "$ACME_DIR"
echo "$TEST_FILE" | sudo tee "$ACME_DIR/$TEST_FILE" >/dev/null

HTTP_RESP=$(curl -sS --max-time 5 "http://127.0.0.1/.well-known/acme-challenge/$TEST_FILE" || true)
if [[ "$HTTP_RESP" != "$TEST_FILE" ]]; then
  echo "[validate][ERR] ACME challenge path not served correctly: expected '$TEST_FILE', got '${HTTP_RESP:-<empty>}'" >&2
  sudo rm -f "$ACME_DIR/$TEST_FILE"
  exit 2
fi
sudo rm -f "$ACME_DIR/$TEST_FILE"
echo "[validate] ACME challenge path served on HTTP: OK"

# Validate TLS termination on 443 (handshake + HTTP response)
if curl -sk --max-time 5 https://127.0.0.1/ -o /dev/null; then
  echo "[validate] TLS handshake and HTTP response on :443: OK"
else
  echo "[validate][ERR] TLS handshake/HTTP response failed on :443" >&2
  exit 3
fi

echo "[validate] HTTPS/ACME validation: PASS"
