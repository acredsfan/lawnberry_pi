#!/usr/bin/env bash
set -euo pipefail

# Swap self-signed TLS to Let's Encrypt using either HTTP-01 (webroot) or DNS-01 (Cloudflare)
# Requirements:
# - DOMAIN and EMAIL must be provided (env or args)
# - HTTP-01: Port 80 must be reachable from the internet to this host (NAT/port-forwarding OK)
# - DNS-01: Set CLOUDFLARE_API_TOKEN for your zone and domain must be in Cloudflare (orange/gray cloud both fine)
#
# Usage:
#   sudo DOMAIN=example.com EMAIL=you@example.com ./scripts/setup_lets_encrypt.sh
#   sudo DOMAIN=example.com EMAIL=you@example.com CLOUDFLARE_API_TOKEN=cf_xxx ./scripts/setup_lets_encrypt.sh
#
# This script will:
# - Install certbot (and cloudflare DNS plugin when needed)
# - Obtain a certificate for $DOMAIN
# - Update nginx to use /etc/letsencrypt/live/$DOMAIN/{fullchain.pem,privkey.pem}
#   (handles /etc/nginx/nginx.conf and lawnberry site files if present)
# - Create a certbot deploy hook to reload nginx after renew
# - Reload nginx and leave certbot's systemd timers enabled for auto-renew

DOMAIN=${DOMAIN:-${1:-}}
EMAIL=${EMAIL:-${2:-}}
# Comma or space separated list of additional domain names (SANs)
ALT_DOMAINS_RAW=${ALT_DOMAINS:-}
# Optional explicit API subdomain; if not provided, auto-detect from ALT_DOMAINS (first that starts with 'api.')
API_DOMAIN=${API_DOMAIN:-}
FRONTEND_PORT=${FRONTEND_PORT:-3000}
BACKEND_PORT=${BACKEND_PORT:-8081}
WEBROOT=${WEBROOT:-/var/www}

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  echo "Error: DOMAIN and EMAIL are required."
  echo "Example: sudo DOMAIN=example.com EMAIL=you@example.com $0"
  exit 1
fi

# Wildcard domains require DNS-01
if [[ "$DOMAIN" == *"*"* ]] || [[ "${ALT_DOMAINS_RAW:-}" == *"*"* ]]; then
  if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
    echo "Error: Wildcard domains require DNS-01. Provide CLOUDFLARE_API_TOKEN for Cloudflare DNS."
    exit 1
  fi
fi

# Ensure nginx and webroot are present
sudo mkdir -p "$WEBROOT/.well-known/acme-challenge"
if ! command -v nginx >/dev/null 2>&1; then
  echo "Installing nginx..."
  sudo apt-get update -y
  sudo apt-get install -y nginx
fi

# Ensure http server_name matches DOMAIN for clarity (not strictly required for webroot)
if [[ -f /etc/nginx/nginx.conf ]] && grep -q "server_name _;" /etc/nginx/nginx.conf; then
  echo "Updating server_name to $DOMAIN in nginx.conf"
  sudo sed -i "0,/server_name _;/s//server_name $DOMAIN;/" /etc/nginx/nginx.conf || true
  if sudo nginx -t; then sudo systemctl reload nginx; fi
fi

# Also update server_name in lawnberry site files if present
for f in /etc/nginx/sites-available/lawnberry-http /etc/nginx/sites-available/lawnberry-https; do
  if [[ -f "$f" ]] && grep -q "server_name _;" "$f"; then
    echo "Updating server_name to $DOMAIN in $f"
    sudo sed -i "0,/server_name _;/s//server_name $DOMAIN;/" "$f" || true
  fi
done

# Install certbot and plugin as needed
sudo apt-get update -y
sudo apt-get install -y certbot

USE_DNS_CF=0
if [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  USE_DNS_CF=1
  sudo apt-get install -y python3-certbot-dns-cloudflare
  sudo mkdir -p /etc/letsencrypt
  sudo tee /etc/letsencrypt/cloudflare.ini >/dev/null <<EOF
# Cloudflare DNS API credentials
# Permissions needed: Zone:DNS:Edit for the zone containing $DOMAIN
# Token is stored locally with restricted permissions
dns_cloudflare_api_token = ${CLOUDFLARE_API_TOKEN}
EOF
  sudo chmod 600 /etc/letsencrypt/cloudflare.ini
fi

# Build domain args
DOMAINS_ARGS=( -d "$DOMAIN" )
if [[ -n "$ALT_DOMAINS_RAW" ]]; then
  # Normalize separators to spaces
  ALT_DOMAINS_RAW=${ALT_DOMAINS_RAW//,/ }
  for d in $ALT_DOMAINS_RAW; do
    [[ -n "$d" ]] && DOMAINS_ARGS+=( -d "$d" )
  done
fi

# Derive API_DOMAIN if not provided
if [[ -z "$API_DOMAIN" && -n "$ALT_DOMAINS_RAW" ]]; then
  for d in $ALT_DOMAINS_RAW; do
    if [[ "$d" == api.* ]]; then
      API_DOMAIN="$d"
      break
    fi
  done
fi

# Obtain certificate
if [[ "$USE_DNS_CF" -eq 1 ]]; then
  echo "Requesting certificate using DNS-01 (Cloudflare) for $DOMAIN"
  sudo certbot certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
    "${DOMAINS_ARGS[@]}" \
    --non-interactive --agree-tos -m "$EMAIL"
else
  echo "Requesting certificate using HTTP-01 (webroot) for $DOMAIN"
  # Ensure nginx serves ACME challenges for all domains involved
  SERVER_NAMES="$DOMAIN"
  if [[ -n "$ALT_DOMAINS_RAW" ]]; then
    SERVER_NAMES+=" $ALT_DOMAINS_RAW"
    SERVER_NAMES=${SERVER_NAMES//,/ }
  fi
  echo "Ensuring nginx serves ACME path for: $SERVER_NAMES"
  sudo tee /etc/nginx/conf.d/lawnberry-acme.conf >/dev/null <<ACME
server {
    listen 80;
    listen [::]:80;
    server_name ${SERVER_NAMES};

    location /.well-known/acme-challenge/ {
        root ${WEBROOT};
        try_files \$uri =404;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}
ACME
  if sudo nginx -t; then sudo systemctl reload nginx; fi

  sudo certbot certonly \
    --webroot -w "$WEBROOT" \
    "${DOMAINS_ARGS[@]}" \
    --non-interactive --agree-tos -m "$EMAIL"
fi

# The live directory is named after the first domain
LE_PATH="/etc/letsencrypt/live/$DOMAIN"
if [[ ! -f "$LE_PATH/fullchain.pem" || ! -f "$LE_PATH/privkey.pem" ]]; then
  echo "Certificate files not found at $LE_PATH. Aborting."
  exit 1
fi

# Update SSL cert paths wherever self-signed was configured
ts=$(date +%s)
if [[ -f /etc/nginx/nginx.conf ]]; then
  sudo cp /etc/nginx/nginx.conf "/etc/nginx/nginx.conf.bak.$ts"
  if grep -q "/etc/lawnberry/certs/selfsigned/fullchain.pem" /etc/nginx/nginx.conf; then
    sudo sed -i "s#ssl_certificate\s\+/etc/lawnberry/certs/selfsigned/fullchain.pem;#ssl_certificate     $LE_PATH/fullchain.pem;#" /etc/nginx/nginx.conf || true
  fi
  if grep -q "/etc/lawnberry/certs/selfsigned/privkey.pem" /etc/nginx/nginx.conf; then
    sudo sed -i "s#ssl_certificate_key\s\+/etc/lawnberry/certs/selfsigned/privkey.pem;#ssl_certificate_key $LE_PATH/privkey.pem;#" /etc/nginx/nginx.conf || true
  fi
fi

for f in /etc/nginx/sites-available/lawnberry-https /etc/nginx/sites-enabled/lawnberry-https; do
  if [[ -f "$f" ]]; then
    sudo cp "$f" "$f.bak.$ts"
    if grep -q "/etc/lawnberry/certs/selfsigned/fullchain.pem" "$f"; then
      sudo sed -i "s#ssl_certificate\s\+/etc/lawnberry/certs/selfsigned/fullchain.pem;#ssl_certificate     $LE_PATH/fullchain.pem;#" "$f" || true
    fi
    if grep -q "/etc/lawnberry/certs/selfsigned/privkey.pem" "$f"; then
      sudo sed -i "s#ssl_certificate_key\s\+/etc/lawnberry/certs/selfsigned/privkey.pem;#ssl_certificate_key $LE_PATH/privkey.pem;#" "$f" || true
    fi
  fi
done

# Create a deploy hook to reload nginx after automatic renewals
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh >/dev/null <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
if command -v nginx >/dev/null 2>&1; then
  if nginx -t; then systemctl reload nginx; fi
fi
HOOK
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

# Test and reload nginx
sudo nginx -t
sudo systemctl reload nginx

# If API_DOMAIN is present, generate split server blocks for UI and API
if [[ -n "$API_DOMAIN" ]]; then
  echo "Configuring split HTTPS servers for UI and API hosts ($DOMAIN and $API_DOMAIN)"
  UI_CONF=/etc/nginx/sites-available/lawnberry-https-ui
  API_CONF=/etc/nginx/sites-available/lawnberry-https-api

  sudo tee "$UI_CONF" >/dev/null <<UIEOF
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate     $LE_PATH/fullchain.pem;
    ssl_certificate_key $LE_PATH/privkey.pem;

    # Frontend at /
    location / {
        proxy_pass http://127.0.0.1:${FRONTEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # API pass-through for UI domain (keeps relative /api calls working)
    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # WebSocket upgrades (frontend and backend paths)
    location /ws {
        proxy_pass http://127.0.0.1:${FRONTEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
    }

    location /api/v2/ws/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
    }
}
UIEOF

  sudo tee "$API_CONF" >/dev/null <<APIEOF
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $API_DOMAIN;

    ssl_certificate     $LE_PATH/fullchain.pem;
    ssl_certificate_key $LE_PATH/privkey.pem;

    # Entire API host routes to backend
    location / {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # WebSockets
    location /api/v2/ws/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
    }
}
APIEOF

  # Enable these and disable the old combined one if present
  sudo ln -sf "$UI_CONF" /etc/nginx/sites-enabled/lawnberry-https-ui
  sudo ln -sf "$API_CONF" /etc/nginx/sites-enabled/lawnberry-https-api
  if [[ -L /etc/nginx/sites-enabled/lawnberry-https ]]; then
    sudo rm -f /etc/nginx/sites-enabled/lawnberry-https
  fi
  if sudo nginx -t; then sudo systemctl reload nginx; fi
else
  echo "No API_DOMAIN provided/detected; keeping single HTTPS server (UI + /api proxy)."
fi

# Migrate custom nginx site configs under sites-available that still use the self-signed paths for these domains
ALL_DOMAINS=("$DOMAIN")
if [[ -n "$ALT_DOMAINS_RAW" ]]; then
  for d in $ALT_DOMAINS_RAW; do ALL_DOMAINS+=("$d"); done
fi

for site in /etc/nginx/sites-available/*; do
  bn=$(basename "$site")
  case "$bn" in
    lawnberry-http|lawnberry-https|lawnberry-https-ui|lawnberry-https-api) continue ;;
  esac
  [[ ! -f "$site" ]] && continue

  # Check if this site references one of our domains
  match=0
  for d in "${ALL_DOMAINS[@]}"; do
    if grep -qE "server_name[^;]*\b$d\b" "$site"; then
      match=1; break
    fi
  done
  [[ "$match" -eq 0 ]] && continue

  # Only migrate if it currently points to our self-signed paths
  if grep -q "/etc/lawnberry/certs/selfsigned/fullchain.pem" "$site" || grep -q "/etc/lawnberry/certs/selfsigned/privkey.pem" "$site"; then
    echo "Migrating site $bn to Let's Encrypt cert paths"
    sudo cp "$site" "$site.bak.$ts"
    sudo sed -i "s#ssl_certificate\s\+/etc/lawnberry/certs/selfsigned/fullchain.pem;#ssl_certificate     $LE_PATH/fullchain.pem;#" "$site" || true
    sudo sed -i "s#ssl_certificate_key\s\+/etc/lawnberry/certs/selfsigned/privkey.pem;#ssl_certificate_key $LE_PATH/privkey.pem;#" "$site" || true
    # Enable if not already
    if [[ ! -L "/etc/nginx/sites-enabled/$bn" ]]; then
      sudo ln -s "$site" "/etc/nginx/sites-enabled/$bn"
    fi
  fi
done

if sudo nginx -t; then sudo systemctl reload nginx; fi

# Optional: verify renew pipeline
echo "Running certbot renew --dry-run to verify auto-renew works..."
sudo certbot renew --dry-run || true

# Prefer certbot timers over any custom ACME renew timers bundled with LawnBerry
if systemctl list-unit-files | grep -q '^lawnberry-acme-renew.timer'; then
  echo "Disabling legacy lawnberry-acme-renew.timer in favor of certbot timers"
  sudo systemctl disable --now lawnberry-acme-renew.timer || true
fi
if systemctl list-unit-files | grep -q '^lawnberry-acme-renew.service'; then
  echo "Disabling legacy lawnberry-acme-renew.service"
  sudo systemctl disable --now lawnberry-acme-renew.service || true
fi

echo "Let's Encrypt certificate installed for $DOMAIN"
echo "Nginx now serves $DOMAIN with a valid certificate (assuming DNS points here)."
echo "Certbot auto-renew timers are enabled by default (check: systemctl list-timers | grep certbot)"
