#!/usr/bin/env bash
set -euo pipefail

# LawnBerry Pi certificate renewal + validation + fallback
# - Tries to renew Let's Encrypt certificates via certbot
# - Validates expiry and reloads nginx on success
# - Falls back to self-signed certificate if renewal fails or cert expiring imminently
# - Emits syslog messages for monitoring/alerts

# Configurable via env or .env at repo root
#   LB_DOMAIN, DOMAIN, LETSENCRYPT_EMAIL, FRONTEND_PORT, BACKEND_PORT

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

# Load .env if present
if [[ -f "$REPO_ROOT/.env" ]]; then
  # shellcheck disable=SC1090
  source "$REPO_ROOT/.env"
fi

DOMAIN=${LB_DOMAIN:-${DOMAIN:-}}
EMAIL=${LETSENCRYPT_EMAIL:-${EMAIL:-}}
FRONTEND_PORT=${FRONTEND_PORT:-3000}
BACKEND_PORT=${BACKEND_PORT:-8081}

LOG_TAG="lawnberry-cert"
log_info(){ echo "[INFO] $*"; logger -t "$LOG_TAG" "$*" || true; }
log_warn(){ echo "[WARN] $*"; logger -p daemon.warning -t "$LOG_TAG" "$*" || true; }
log_err(){ echo "[ERR ] $*"; logger -p daemon.err -t "$LOG_TAG" "$*" || true; }

require_cmd(){ command -v "$1" >/dev/null 2>&1 || { log_err "Missing command: $1"; exit 1; }; }

require_cmd openssl
require_cmd nginx

# Determine Let's Encrypt live path
LE_PATH=""
if [[ -n "$DOMAIN" && -d "/etc/letsencrypt/live/$DOMAIN" ]]; then
  LE_PATH="/etc/letsencrypt/live/$DOMAIN"
else
  # Pick the first live directory if domain not specified
  FIRST_LIVE=$(ls -1d /etc/letsencrypt/live/* 2>/dev/null | head -n 1 || true)
  if [[ -n "$FIRST_LIVE" ]]; then
    LE_PATH="$FIRST_LIVE"
  fi
fi

SELF_DIR="/etc/lawnberry/certs/selfsigned"
mkdir -p "$SELF_DIR"

generate_self_signed(){
  local cn=${DOMAIN:-lawnberry.local}
  log_warn "Generating self-signed certificate for CN=$cn as fallback"
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SELF_DIR/privkey.pem" \
    -out "$SELF_DIR/fullchain.pem" \
    -subj "/CN=$cn"
}

switch_nginx_to_self_signed(){
  local ts; ts=$(date +%s)
  local files=(/etc/nginx/nginx.conf /etc/nginx/sites-available/* /etc/nginx/sites-enabled/*)
  for f in "${files[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -q "/etc/letsencrypt/live/" "$f"; then
      cp "$f" "$f.bak.$ts" || true
      sed -i "s#ssl_certificate\s\+/etc/letsencrypt/live/[^;]*/fullchain.pem;#ssl_certificate     $SELF_DIR/fullchain.pem;#" "$f" || true
      sed -i "s#ssl_certificate_key\s\+/etc/letsencrypt/live/[^;]*/privkey.pem;#ssl_certificate_key $SELF_DIR/privkey.pem;#" "$f" || true
    fi
  done
  nginx -t && systemctl reload nginx || true
}

check_cert_expiry(){
  local pem=$1
  local seconds=$2
  if [[ ! -f "$pem" ]]; then
    return 2
  fi
  # returns 0 if certificate will NOT expire in next $seconds
  if openssl x509 -checkend "$seconds" -noout -in "$pem" >/dev/null 2>&1; then
    return 0
  else
    return 1
  fi
}

renew(){
  if ! command -v certbot >/dev/null 2>&1; then
    log_info "Installing certbot..."
    apt-get update -y && apt-get install -y certbot
  fi
  log_info "Running certbot renew --quiet"
  if ! certbot renew --quiet; then
    log_warn "certbot renew returned non-zero"
    return 1
  fi
  if nginx -t; then
    systemctl reload nginx || true
  fi
}

main(){
  # If no LE path exists yet, just ensure self-signed exists and exit 0
  if [[ -z "$LE_PATH" ]]; then
    log_warn "No Let's Encrypt live directory found; ensuring self-signed certificate exists"
    [[ -f "$SELF_DIR/fullchain.pem" && -f "$SELF_DIR/privkey.pem" ]] || generate_self_signed
    switch_nginx_to_self_signed
    exit 0
  fi

  local pem="$LE_PATH/fullchain.pem"
  local key="$LE_PATH/privkey.pem"
  if [[ ! -f "$pem" || ! -f "$key" ]]; then
    log_warn "LE files missing; falling back to self-signed"
    generate_self_signed
    switch_nginx_to_self_signed
    exit 0
  fi

  # If expires in less than 30 days, try renew
  if ! check_cert_expiry "$pem" $((30*24*3600)); then
    log_info "Certificate expiring within 30 days; attempting renewal"
    renew || true
  fi

  # Validate again with 7-day window
  if check_cert_expiry "$pem" $((7*24*3600)); then
    log_info "Certificate is valid for at least 7 more days; keeping Let's Encrypt configuration"
    nginx -t && systemctl reload nginx || true
    exit 0
  else
    log_warn "Certificate still expiring soon (<7 days) or invalid after renewal"
    generate_self_signed
    switch_nginx_to_self_signed
    exit 0
  fi
}

main "$@"
