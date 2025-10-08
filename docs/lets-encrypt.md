# Let's Encrypt Automation

Use the provided script to replace the self-signed certificate with a real Let's Encrypt certificate. Supports HTTP-01 (webroot) and DNS-01 (Cloudflare) flows.

## Prerequisites
- A domain name pointing to your LawnBerry Pi public IP (A/AAAA record)
- Port 80 reachable from the internet for HTTP-01, or Cloudflare-managed DNS and an API token for DNS-01
- nginx already configured by `scripts/setup_https.sh` (self-signed works initially)

## HTTP-01 (Webroot) Flow
```bash
# Replace with your domain and email
sudo DOMAIN=lawnberry.yourdomain.com EMAIL=you@yourdomain.com ./scripts/setup_lets_encrypt.sh
```

This will:
- Install certbot
- Request a cert for $DOMAIN using webroot at /var/www
- Update nginx to use /etc/letsencrypt/live/$DOMAIN/fullchain.pem and privkey.pem
- Create a deploy hook to reload nginx on renew
- Run a dry-run renew to validate timers

### Multiple Domains (SANs)
```bash
sudo DOMAIN=lawnberry.yourdomain.com \
  ALT_DOMAINS="api.lawnberry.yourdomain.com,static.lawnberry.yourdomain.com" \
  EMAIL=you@yourdomain.com ./scripts/setup_lets_encrypt.sh
```

## DNS-01 (Cloudflare) Flow
```bash
# Create a Cloudflare API token with Zone DNS:Edit for your zone
sudo DOMAIN=lawnberry.yourdomain.com EMAIL=you@yourdomain.com \
  CLOUDFLARE_API_TOKEN=cf_xxx ./scripts/setup_lets_encrypt.sh
```

## Verify
```bash
# Check nginx SSL cert
openssl s_client -connect lawnberry.yourdomain.com:443 -servername lawnberry.yourdomain.com </dev/null 2>/dev/null | openssl x509 -noout -issuer -subject -dates

# Check certbot timers
systemctl list-timers | grep certbot
```

## Notes
- The script updates both `/etc/nginx/nginx.conf` and the LawnBerry site files if they reference the self-signed paths.
- Legacy `lawnberry-acme-renew.*` systemd units are disabled in favor of certbot’s timers.
- For multi-host setups (separate api subdomain), extend nginx and request SANs as desired (e.g., `-d lawnberry.yourdomain.com -d api.lawnberry.yourdomain.com`).