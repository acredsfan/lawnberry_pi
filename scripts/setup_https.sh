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

sudo mkdir -p /etc/lawnberry/certs/selfsigned /var/www/.well-known/acme-challenge

# Install nginx if not present
if ! command -v nginx >/dev/null 2>&1; then
  echo "Installing nginx..."
  sudo apt-get update -y
  sudo apt-get install -y nginx
fi

# Generate self-signed cert if not present
if [ ! -f /etc/lawnberry/certs/selfsigned/fullchain.pem ] || [ ! -f /etc/lawnberry/certs/selfsigned/privkey.pem ]; then
  echo "Generating self-signed certificate..."
  sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/lawnberry/certs/selfsigned/privkey.pem \
    -out /etc/lawnberry/certs/selfsigned/fullchain.pem \
    -subj "/CN=${DOMAIN:-lawnberry.local}"
fi

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
