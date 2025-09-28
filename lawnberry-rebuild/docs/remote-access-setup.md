# Remote Access Setup Guide

This guide covers setting up secure remote access to your LawnBerry Pi system using various methods including Cloudflare Tunnels, ngrok, and custom configurations.

## Table of Contents

1. [Overview](#overview)
2. [Cloudflare Tunnel Setup (Recommended)](#cloudflare-tunnel-setup-recommended)
3. [ngrok Setup](#ngrok-setup)
4. [Custom Domain Configuration](#custom-domain-configuration)
5. [ACME TLS Certificate Management](#acme-tls-certificate-management)
6. [Security Considerations](#security-considerations)
7. [Troubleshooting](#troubleshooting)

## Overview

LawnBerry Pi v2 supports multiple remote access methods to provide secure connectivity from anywhere:

- **Cloudflare Tunnel**: Most secure, enterprise-grade solution with built-in DDoS protection
- **ngrok**: Easy setup for development and testing
- **Custom Domain**: Full control with your own domain and certificates
- **Port Forwarding**: Traditional method (not recommended for security)

### Security Levels

Each method provides different security levels:
- **Cloudflare Tunnel**: Highest security, no exposed ports
- **Custom Domain + ACME**: High security with proper TLS
- **ngrok**: Medium security, suitable for development
- **Port Forwarding**: Lowest security, requires additional hardening

## Cloudflare Tunnel Setup (Recommended)

Cloudflare Tunnel provides the most secure remote access without exposing any ports on your router.

### Prerequisites

1. **Cloudflare Account**: Free account at [cloudflare.com](https://cloudflare.com)
2. **Domain Name**: Either purchase through Cloudflare or transfer existing domain
3. **DNS Management**: Domain DNS managed by Cloudflare

### Step 1: Install Cloudflared

```bash
# Download and install cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb

# Verify installation
cloudflared --version
```

### Step 2: Authenticate with Cloudflare

```bash
# Login to Cloudflare (opens browser)
cloudflared tunnel login

# This will download a certificate to ~/.cloudflared/cert.pem
```

### Step 3: Create Tunnel

```bash
# Create a new tunnel
cloudflared tunnel create lawnberry

# Note the tunnel ID from the output
# Example: Created tunnel lawnberry with id 12345678-1234-1234-1234-123456789abc
```

### Step 4: Configure DNS

```bash
# Create DNS record for your subdomain
cloudflared tunnel route dns lawnberry lawnberry.yourdomain.com

# Replace 'yourdomain.com' with your actual domain
```

### Step 5: Create Tunnel Configuration

```bash
# Create config directory
mkdir -p ~/.cloudflared

# Create tunnel configuration
cat > ~/.cloudflared/config.yml << EOF
tunnel: lawnberry
credentials-file: /home/pi/.cloudflared/12345678-1234-1234-1234-123456789abc.json

ingress:
  - hostname: lawnberry.yourdomain.com
    service: http://localhost:3000
    originRequest:
      httpHostHeader: lawnberry.yourdomain.com
  - hostname: api.lawnberry.yourdomain.com
    service: http://localhost:8081
    originRequest:
      httpHostHeader: api.lawnberry.yourdomain.com
  - service: http_status:404
EOF
```

### Step 6: Configure LawnBerry Pi

```bash
# Configure remote access in LawnBerry Pi
lawnberry-pi config remote-access --method cloudflare \
    --tunnel-name lawnberry \
    --domain lawnberry.yourdomain.com \
    --api-domain api.lawnberry.yourdomain.com \
    --enable-tunnel-auth

# Test configuration
lawnberry-pi config remote-access --test
```

### Step 7: Start Tunnel Service

```bash
# Install as systemd service
sudo cloudflared service install

# Start the service
sudo systemctl start cloudflared
sudo systemctl enable cloudflared

# Check status
sudo systemctl status cloudflared
```

### Step 8: Configure Cloudflare Access (Optional)

For additional security, configure Cloudflare Access to require authentication:

1. **Go to Cloudflare Dashboard** → Your Domain → Access → Applications
2. **Add Application**:
   - Type: Self-hosted
   - Name: LawnBerry Pi
   - Subdomain: lawnberry
   - Domain: yourdomain.com
3. **Configure Policies**:
   - Allow emails: your-email@domain.com
   - Require email domain: yourdomain.com (optional)
4. **Save Configuration**

### Step 9: Update LawnBerry Configuration

```bash
# Enable Cloudflare tunnel authentication
lawnberry-pi config auth --level tunnel \
    --tunnel-provider cloudflare \
    --required-headers "CF-Access-Authenticated-User-Email"

# Test remote access
curl https://lawnberry.yourdomain.com/api/v1/status
```

## ngrok Setup

ngrok provides easy remote access, ideal for development and testing.

### Step 1: Install ngrok

```bash
# Download ngrok
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok

# Verify installation
ngrok version
```

### Step 2: Setup ngrok Account

1. **Create Account**: Sign up at [ngrok.com](https://ngrok.com)
2. **Get Auth Token**: From ngrok dashboard
3. **Configure Auth Token**:
   ```bash
   ngrok config add-authtoken YOUR_AUTH_TOKEN
   ```

### Step 3: Configure ngrok

```bash
# Create ngrok configuration
cat > ~/.ngrok2/ngrok.yml << EOF
version: "2"
authtoken: YOUR_AUTH_TOKEN
tunnels:
  lawnberry-web:
    proto: http
    addr: 3000
    hostname: your-custom-domain.ngrok.io  # Only for paid plans
  lawnberry-api:
    proto: http
    addr: 8081
    hostname: api-your-custom-domain.ngrok.io  # Only for paid plans
EOF
```

### Step 4: Configure LawnBerry Pi

```bash
# Configure ngrok remote access
lawnberry-pi config remote-access --method ngrok \
    --web-port 3000 \
    --api-port 8081 \
    --enable

# Test configuration
lawnberry-pi config remote-access --test
```

### Step 5: Start ngrok Tunnels

```bash
# Start tunnels (for testing)
ngrok start lawnberry-web lawnberry-api

# For permanent setup, create systemd service
sudo tee /etc/systemd/system/ngrok.service << EOF
[Unit]
Description=ngrok tunnel
After=network.target

[Service]
ExecStart=/usr/local/bin/ngrok start --all --config /home/pi/.ngrok2/ngrok.yml
Restart=always
User=pi
Group=pi

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl enable ngrok
sudo systemctl start ngrok
```

## Custom Domain Configuration

Set up remote access with your own domain and TLS certificates.

### Prerequisites

1. **Domain Name**: Owned domain with DNS control
2. **DNS Provider**: Ability to create A/AAAA records
3. **Router Configuration**: Port forwarding capability (443, 80)

### Step 1: Configure DNS

```bash
# Create DNS A record pointing to your public IP
# Example DNS records:
# lawnberry.yourdomain.com    A    YOUR_PUBLIC_IP
# api.lawnberry.yourdomain.com A   YOUR_PUBLIC_IP
```

### Step 2: Configure Router

Set up port forwarding on your router:
- **Port 80** → Pi IP:80 (for ACME challenges)
- **Port 443** → Pi IP:443 (for HTTPS traffic)

### Step 3: Configure nginx

```bash
# Install nginx if not already installed
sudo apt install nginx

# Create nginx configuration
sudo tee /etc/nginx/sites-available/lawnberry << EOF
server {
    listen 80;
    server_name lawnberry.yourdomain.com api.lawnberry.yourdomain.com;
    
    # ACME challenge location
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    # Redirect to HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name lawnberry.yourdomain.com;
    
    ssl_certificate /etc/lawnberry/certs/lawnberry.yourdomain.com/cert.pem;
    ssl_certificate_key /etc/lawnberry/certs/lawnberry.yourdomain.com/key.pem;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}

server {
    listen 443 ssl http2;
    server_name api.lawnberry.yourdomain.com;
    
    ssl_certificate /etc/lawnberry/certs/api.lawnberry.yourdomain.com/cert.pem;
    ssl_certificate_key /etc/lawnberry/certs/api.lawnberry.yourdomain.com/key.pem;
    
    location / {
        proxy_pass http://localhost:8081;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/lawnberry /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Step 4: Configure LawnBerry Pi

```bash
# Configure custom domain remote access
lawnberry-pi config remote-access --method custom \
    --domain lawnberry.yourdomain.com \
    --api-domain api.lawnberry.yourdomain.com \
    --enable-acme \
    --acme-email your-email@domain.com

# This will automatically request TLS certificates
```

## ACME TLS Certificate Management

LawnBerry Pi includes automatic TLS certificate management using ACME (Let's Encrypt).

### Automatic Certificate Requests

```bash
# Request certificate for domain
lawnberry-pi certificates request \
    --domain lawnberry.yourdomain.com \
    --email your-email@domain.com

# Request wildcard certificate (requires DNS-01 challenge)
lawnberry-pi certificates request \
    --domain "*.yourdomain.com" \
    --challenge-type dns-01 \
    --dns-provider cloudflare \
    --dns-token YOUR_CLOUDFLARE_TOKEN
```

### Certificate Management

```bash
# List certificates
lawnberry-pi certificates list

# Check certificate status
lawnberry-pi certificates status --domain lawnberry.yourdomain.com

# Manually renew certificate
lawnberry-pi certificates renew --domain lawnberry.yourdomain.com

# Revoke certificate
lawnberry-pi certificates revoke --domain lawnberry.yourdomain.com
```

### Automatic Renewal

Certificates are automatically renewed via systemd timer:

```bash
# Check renewal service status
sudo systemctl status lawnberry-acme-renew.timer
sudo systemctl status lawnberry-acme-renew.service

# View renewal logs
sudo journalctl -u lawnberry-acme-renew.service

# Test renewal process
sudo systemctl start lawnberry-acme-renew.service
```

## Security Considerations

### Best Practices

1. **Use Cloudflare Tunnel when possible** - Provides best security
2. **Enable authentication** - Never expose unprotected endpoints
3. **Use strong passwords** - Enable TOTP or OAuth when possible
4. **Monitor access logs** - Review authentication attempts
5. **Keep system updated** - Regular security updates

### Authentication Integration

```bash
# Configure authentication for remote access
lawnberry-pi config auth --level totp \
    --setup-totp \
    --session-timeout 30

# Enable IP-based restrictions (optional)
lawnberry-pi config security --allowed-ips "192.168.1.0/24,10.0.0.0/8"

# Configure rate limiting
lawnberry-pi config security --rate-limit 100 --rate-window 3600
```

### Monitoring and Alerting

```bash
# Enable access monitoring
lawnberry-pi config monitoring --enable-access-logs \
    --alert-failed-logins 5 \
    --alert-email your-email@domain.com

# View access logs
lawnberry-pi logs access --tail 100

# Check security status
lawnberry-pi security status --check-all
```

## Troubleshooting

### Common Issues

#### Cloudflare Tunnel Issues

1. **Tunnel not connecting**:
   ```bash
   # Check cloudflared logs
   sudo journalctl -u cloudflared -f
   
   # Test connectivity
   cloudflared tunnel info lawnberry
   
   # Verify DNS
   nslookup lawnberry.yourdomain.com
   ```

2. **502 Bad Gateway**:
   ```bash
   # Check LawnBerry services
   sudo systemctl status lawnberry-frontend
   sudo systemctl status lawnberry-backend
   
   # Test local connectivity
   curl http://localhost:3000
   curl http://localhost:8081/api/v1/status
   ```

#### ngrok Issues

1. **Tunnel disconnecting**:
   ```bash
   # Check ngrok logs
   ngrok log
   
   # Verify auth token
   ngrok config check
   
   # Test with simple tunnel
   ngrok http 3000
   ```

2. **Custom domain not working**:
   - Verify you have a paid ngrok plan
   - Check domain configuration in ngrok.yml
   - Ensure domain is properly configured in ngrok dashboard

#### Custom Domain Issues

1. **Certificate not working**:
   ```bash
   # Check certificate status
   lawnberry-pi certificates status --domain lawnberry.yourdomain.com
   
   # Check nginx configuration
   sudo nginx -t
   
   # View ACME logs
   sudo journalctl -u lawnberry-acme-renew.service -f
   ```

2. **Port forwarding not working**:
   ```bash
   # Test port accessibility
   curl -I http://YOUR_PUBLIC_IP
   
   # Check router configuration
   # Verify ports 80 and 443 are forwarded
   
   # Test from external network
   nmap -p 80,443 YOUR_PUBLIC_IP
   ```

### Debug Commands

```bash
# Test remote access configuration
lawnberry-pi config remote-access --test --verbose

# Check all services
lawnberry-pi health check --remote-access

# View detailed logs
sudo journalctl -u lawnberry-backend -u lawnberry-frontend -u cloudflared -f

# Network connectivity test
lawnberry-pi network test --external --dns --certificates
```

### Getting Help

If you're still experiencing issues:

1. **Check system logs**: `sudo journalctl -f`
2. **Review configuration**: `lawnberry-pi config show --all`
3. **Run diagnostics**: `lawnberry-pi diagnose --remote-access`
4. **Test step-by-step**: Follow the setup guide exactly
5. **Check firewall**: Ensure no blocking rules

For specific error messages, consult the main troubleshooting guide or system logs for detailed information.