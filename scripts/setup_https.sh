#!/usr/bin/env bash
set -euo pipefail

# LawnBerry Pi HTTPS setup using nginx
# - Installs nginx if missing
# - Creates self-signed cert (for immediate HTTPS) under /etc/lawnberry/certs/selfsigned
# - Configures nginx to:
#   * Listen on 80 for ACME challenges and redirect to 443
#   * Listen on 443 and proxy / (frontend) to :3000, /api to backend :8081, and upgrade WS
# - Prepares /.well-known/acme-challenge for certbot/ACME
# - Leaves hooks for Cloudflare Tunnel (optional) but does not require it

FRONTEND_PORT=${FRONTEND_PORT:-3000}
BACKEND_PORT=${BACKEND_PORT:-8081}
DOMAIN=${DOMAIN:-}
EMAIL=${EMAIL:-}
ALT_DOMAINS_RAW=${ALT_DOMAINS:-}
SELF_DIR=/etc/lawnberry/certs/selfsigned

sudo mkdir -p "$SELF_DIR" /var/www/.well-known/acme-challenge

build_openssl_san_config() {
    local cn=${DOMAIN:-lawnberry.local}
    local hostname_short
    local tmp
    local index=1
    local ip_index=1
    local -a dns_names ipv4_addrs
    local -A seen_dns=() seen_ip=()

    hostname_short=$(hostname -s 2>/dev/null || echo lawnberry)
    tmp=$(mktemp)
    dns_names=("$cn" "localhost" "$hostname_short" "${hostname_short}.local" "lawnberry.local")

    if [[ -n "$ALT_DOMAINS_RAW" ]]; then
        ALT_DOMAINS_RAW=${ALT_DOMAINS_RAW//,/ }
        for entry in $ALT_DOMAINS_RAW; do
            [[ -n "$entry" ]] && dns_names+=("$entry")
        done
    fi

    ipv4_addrs=("127.0.0.1")
    while read -r ip; do
        [[ -n "$ip" ]] && ipv4_addrs+=("$ip")
    done < <(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' || true)

    {
        echo "[req]"
        echo "distinguished_name = req_distinguished_name"
        echo "x509_extensions = v3_req"
        echo "prompt = no"
        echo
        echo "[req_distinguished_name]"
        echo "CN = $cn"
        echo
        echo "[v3_req]"
        echo "basicConstraints = critical,CA:FALSE"
        echo "keyUsage = critical,digitalSignature,keyEncipherment"
        echo "extendedKeyUsage = serverAuth"
        echo "subjectAltName = @alt_names"
        echo
        echo "[alt_names]"
        for name in "${dns_names[@]}"; do
            [[ -n "$name" && -z "${seen_dns[$name]:-}" ]] || continue
            seen_dns[$name]=1
            echo "DNS.$index = $name"
            index=$((index + 1))
        done
        for ip in "${ipv4_addrs[@]}"; do
            [[ -n "$ip" && -z "${seen_ip[$ip]:-}" ]] || continue
            seen_ip[$ip]=1
            echo "IP.$ip_index = $ip"
            ip_index=$((ip_index + 1))
        done
    } >"$tmp"

    echo "$tmp"
}

cert_has_subject_alt_name() {
    [[ -f "$SELF_DIR/fullchain.pem" ]] || return 1
    openssl x509 -in "$SELF_DIR/fullchain.pem" -noout -ext subjectAltName 2>/dev/null | grep -q "Subject Alternative Name"
}

generate_self_signed() {
    local san_cfg

    echo "Generating self-signed certificate..."
    san_cfg=$(build_openssl_san_config)
    trap 'rm -f "$san_cfg"' RETURN
    sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$SELF_DIR/privkey.pem" \
        -out "$SELF_DIR/fullchain.pem" \
        -config "$san_cfg" \
        -extensions v3_req
    rm -f "$san_cfg"
    trap - RETURN
}

ensure_self_signed_certificate() {
    if [[ ! -f "$SELF_DIR/fullchain.pem" || ! -f "$SELF_DIR/privkey.pem" ]]; then
        generate_self_signed
        return
    fi

    if ! cert_has_subject_alt_name; then
        echo "Existing self-signed certificate lacks SAN entries; regenerating it for browser compatibility..."
        generate_self_signed
    fi
}

# Install nginx if not present
if ! command -v nginx >/dev/null 2>&1; then
  echo "Installing nginx..."
  sudo apt-get update -y
  sudo apt-get install -y nginx
fi

# Generate self-signed cert if needed
ensure_self_signed_certificate

NGINX_HTTP_CONF=/etc/nginx/sites-available/lawnberry-http
NGINX_HTTPS_CONF=/etc/nginx/sites-available/lawnberry-https

# HTTP: ACME and redirect
sudo tee ${NGINX_HTTP_CONF} >/dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name _;

    # ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www;
        try_files $uri =404;
    }

    # Everything else -> HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}
EOF

# HTTPS: proxy
sudo tee ${NGINX_HTTPS_CONF} >/dev/null <<EOF
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name _;

    ssl_certificate     /etc/lawnberry/certs/selfsigned/fullchain.pem;
    ssl_certificate_key /etc/lawnberry/certs/selfsigned/privkey.pem;

    # Frontend (Vue static server) at /
    location / {
        proxy_pass http://127.0.0.1:${FRONTEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # API direct to backend
    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # WebSocket upgrades to frontend (which proxies to backend)
    location /ws {
        proxy_pass http://127.0.0.1:${FRONTEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
    }

    # Also allow direct WS to backend API paths
    location /api/v2/ws/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
    }
}
EOF

# Enable sites
echo "Enabling nginx sites..."
sudo ln -sf ${NGINX_HTTP_CONF} /etc/nginx/sites-enabled/lawnberry-http
sudo ln -sf ${NGINX_HTTPS_CONF} /etc/nginx/sites-enabled/lawnberry-https

# Test and reload nginx
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx

echo "HTTPS setup complete. You can access the UI at: https://<your-pi-ip>/"
echo "Note: Browser will warn about self-signed certificate until you install a valid one."

echo "Next: To swap to a real Let's Encrypt certificate, run our helper script:"
echo "  sudo DOMAIN=your.domain EMAIL=you@domain.com ./scripts/setup_lets_encrypt.sh"
echo "  # For DNS-01 with Cloudflare: add CLOUDFLARE_API_TOKEN=cf_xxx"
