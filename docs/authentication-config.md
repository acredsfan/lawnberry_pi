# Authentication Configuration Guide

This guide covers setting up and configuring the multi-level authentication system in LawnBerry Pi v2, from basic password authentication to enterprise-grade security.

## Table of Contents

1. [Overview](#overview)
2. [Security Levels](#security-levels)
3. [Password Authentication](#password-authentication)
4. [TOTP Two-Factor Authentication](#totp-two-factor-authentication)
5. [Google OAuth Integration](#google-oauth-integration)
6. [Cloudflare Tunnel Authentication](#cloudflare-tunnel-authentication)
7. [Session Management](#session-management)
8. [Security Best Practices](#security-best-practices)
9. [Troubleshooting](#troubleshooting)

## Overview

LawnBerry Pi v2 features a configurable authentication system with four security levels:

1. **Password**: Basic username/password authentication
2. **TOTP**: Password + Time-based One-Time Password (2FA)
3. **Google OAuth**: Google account authentication with domain restrictions
4. **Tunnel Auth**: Cloudflare tunnel authentication (highest security)

Each level provides increasing security and may disable lower-level authentication methods.

### Key Features

- **Progressive Enhancement**: Start simple, upgrade security as needed
- **Session Management**: Configurable timeout and concurrent session limits
- **Audit Logging**: Complete authentication event logging
- **Rate Limiting**: Protection against brute force attacks
- **Backup Recovery**: TOTP backup codes and account recovery options

## Security Levels

### Level 1: Password Authentication

**Use Case**: Basic home networks, initial setup
**Security**: Basic protection against unauthorized access
**Requirements**: Username and password only

### Level 2: TOTP Two-Factor Authentication

**Use Case**: Enhanced home security, remote access scenarios
**Security**: Significantly improved protection with 2FA
**Requirements**: Password + TOTP code from authenticator app

### Level 3: Google OAuth

**Use Case**: Integration with existing Google Workspace/Gmail accounts
**Security**: Enterprise-grade OAuth with optional domain restrictions
**Requirements**: Valid Google account, optional domain membership

### Level 4: Cloudflare Tunnel Authentication

**Use Case**: Maximum security with zero-trust architecture
**Security**: Highest level, relies on Cloudflare Access policies
**Requirements**: Cloudflare tunnel setup with Access policies

## Password Authentication

Basic username/password authentication suitable for initial setup and secure local networks.

### Initial Setup

```bash
# Set initial admin password during first setup
lawnberry-pi config auth --level password --set-password

# Or use interactive setup
lawnberry-pi config auth --setup-wizard
```

### Configuration Options

```bash
# Configure password requirements
lawnberry-pi config auth --password-policy \
    --min-length 12 \
    --require-uppercase \
    --require-lowercase \
    --require-numbers \
    --require-symbols

# Set session timeout
lawnberry-pi config auth --session-timeout 60  # 60 minutes

# Enable password change requirement
lawnberry-pi config auth --require-password-change \
    --change-interval 90  # 90 days
```

### Password Management

```bash
# Change admin password
lawnberry-pi auth change-password

# Reset password (requires physical access)
sudo lawnberry-pi auth reset-password --user admin

# View password policy
lawnberry-pi config auth --show-policy
```

### Example Configuration

```yaml
# /etc/lawnberry/auth-config.yml
security_level: password
password_policy:
  min_length: 12
  require_uppercase: true
  require_lowercase: true
  require_numbers: true
  require_symbols: false
  max_age_days: 90
session_config:
  timeout_minutes: 60
  max_concurrent_sessions: 3
  remember_me_days: 30
```

## TOTP Two-Factor Authentication

Time-based One-Time Password (TOTP) adds significant security by requiring a second factor from your mobile device.

### Setup Process

```bash
# Enable TOTP authentication
lawnberry-pi config auth --level totp --setup-totp

# This will:
# 1. Generate a secret key
# 2. Display QR code for mobile app
# 3. Generate backup codes
# 4. Test TOTP verification
```

### Mobile App Setup

1. **Install Authenticator App**:
   - Google Authenticator (iOS/Android)
   - Authy (iOS/Android/Desktop)
   - Microsoft Authenticator (iOS/Android)
   - 1Password (iOS/Android/Desktop)

2. **Scan QR Code**: Use app to scan the displayed QR code

3. **Verify Setup**: Enter the 6-digit code to confirm

### Backup Codes

TOTP setup generates 10 backup codes for account recovery:

```bash
# Generate new backup codes
lawnberry-pi auth totp --regenerate-backup-codes

# View remaining backup codes
lawnberry-pi auth totp --show-backup-codes

# Use backup code for login (emergency)
# Enter backup code instead of TOTP during login
```

### TOTP Configuration

```bash
# Configure TOTP settings
lawnberry-pi config auth --totp-window 1 \  # Allow 1 step tolerance
    --totp-rate-limit 5 \                   # Max 5 attempts per minute
    --backup-codes-count 10                 # Generate 10 backup codes

# Disable TOTP (downgrade to password)
lawnberry-pi config auth --level password --disable-totp
```

### Recovery Process

If you lose access to your TOTP device:

1. **Use Backup Code**: Use one of your saved backup codes
2. **Physical Reset**: Access Pi directly and reset auth level
3. **Recovery Key**: Use recovery key if configured

```bash
# Physical recovery (requires sudo access on Pi)
sudo lawnberry-pi auth recovery --reset-totp --user admin

# Set up TOTP again after recovery
lawnberry-pi config auth --level totp --setup-totp
```

## Google OAuth Integration

Integrate with Google accounts for seamless authentication using existing corporate or personal Google accounts.

### Prerequisites

1. **Google Cloud Project**: Create project at [console.cloud.google.com](https://console.cloud.google.com)
2. **OAuth 2.0 Client**: Configure OAuth client credentials
3. **Domain Control**: Optional domain restrictions

### Google Cloud Setup

1. **Create Project**:
   - Go to Google Cloud Console
   - Create new project: "LawnBerry Pi Auth"

2. **Enable APIs**:
   ```bash
   # Enable Google+ API for user info
   # Navigate to APIs & Services > Library
   # Search and enable "Google+ API"
   ```

3. **Create OAuth Client**:
   - Go to APIs & Services > Credentials
   - Create OAuth 2.0 Client ID
   - Application type: Web application
   - Authorized redirect URIs:
     - `https://your-domain.com/auth/google/callback`
     - `http://localhost:3000/auth/google/callback` (for local testing)

4. **Download Credentials**: Download JSON credentials file

### LawnBerry Configuration

```bash
# Configure Google OAuth
lawnberry-pi config auth --level google \
    --google-client-id "YOUR_CLIENT_ID.googleusercontent.com" \
    --google-client-secret "YOUR_CLIENT_SECRET" \
    --google-redirect-uri "https://your-domain.com/auth/google/callback"

# Optional: Restrict to specific domains
lawnberry-pi config auth --google-allowed-domains "yourdomain.com,anotherdomain.com"

# Optional: Require specific group membership
lawnberry-pi config auth --google-required-groups "lawnberry-users@yourdomain.com"
```

### Domain Restrictions

```bash
# Allow only specific email domains
lawnberry-pi config auth --google-allowed-domains "company.com"

# Allow specific email addresses
lawnberry-pi config auth --google-allowed-emails "user1@gmail.com,user2@company.com"

# Combine domain and email restrictions
lawnberry-pi config auth --google-allowed-domains "company.com" \
    --google-allowed-emails "contractor@external.com"
```

### Testing Google OAuth

```bash
# Test OAuth configuration
lawnberry-pi auth test-google-oauth --client-id YOUR_CLIENT_ID

# Verify user authentication
lawnberry-pi auth verify-google-user --email user@domain.com
```

### Example Google OAuth Configuration

```yaml
# /etc/lawnberry/auth-config.yml
security_level: google_oauth
google_auth_config:
  client_id: "123456789.googleusercontent.com"
  client_secret: "encrypted_secret"
  allowed_domains:
    - "company.com"
    - "yourdomain.com"
  allowed_emails:
    - "admin@external.com"
  require_verified_email: true
  session_duration_hours: 8
```

## Cloudflare Tunnel Authentication

The highest security level using Cloudflare Access for zero-trust authentication.

### Prerequisites

1. **Cloudflare Account**: With domain management
2. **Cloudflare Tunnel**: Configured and running
3. **Cloudflare Access**: Access subscription (free tier available)

### Cloudflare Access Setup

1. **Enable Cloudflare Access**:
   - Go to Cloudflare Dashboard > Access
   - Set up Access for your domain
   - Configure identity providers (Google, Azure AD, etc.)

2. **Create Access Application**:
   - Name: LawnBerry Pi
   - Domain: `lawnberry.yourdomain.com`
   - Type: Self-hosted

3. **Configure Access Policies**:
   ```yaml
   # Example policy
   name: "LawnBerry Pi Access Policy"
   decision: "allow"
   rules:
     - emails:
         - "admin@yourdomain.com"
         - "user@yourdomain.com"
     - email_domains:
         - "yourdomain.com"
   ```

### LawnBerry Configuration

```bash
# Enable Cloudflare tunnel authentication
lawnberry-pi config auth --level tunnel \
    --tunnel-provider cloudflare \
    --required-headers "CF-Access-Authenticated-User-Email" \
    --verify-jwt-signature

# Configure session settings for tunnel auth
lawnberry-pi config auth --tunnel-session-timeout 120  # 2 hours
```

### Header Validation

Cloudflare provides authentication headers that LawnBerry validates:

```bash
# Configure required headers
lawnberry-pi config auth --tunnel-required-headers \
    "CF-Access-Authenticated-User-Email" \
    "CF-Ray" \
    "CF-Visitor"

# Optional: Configure user mapping
lawnberry-pi config auth --tunnel-user-header "CF-Access-Authenticated-User-Email"
```

### Testing Tunnel Authentication

```bash
# Test tunnel authentication
lawnberry-pi auth test-tunnel --simulate-headers

# Verify Access policy
curl -H "CF-Access-Authenticated-User-Email: user@domain.com" \
     https://lawnberry.yourdomain.com/api/v1/auth/verify
```

## Session Management

Configure session behavior, timeouts, and concurrent access controls.

### Session Configuration

```bash
# Configure session timeouts
lawnberry-pi config auth --session-timeout 60 \      # 60 minutes
    --absolute-timeout 480 \                         # 8 hours absolute max
    --idle-timeout 30                                # 30 minutes idle

# Configure concurrent sessions
lawnberry-pi config auth --max-concurrent-sessions 3 \
    --session-collision-policy "terminate_oldest"

# Configure remember-me functionality
lawnberry-pi config auth --remember-me-duration 30  # 30 days
```

### Session Security

```bash
# Enable secure session features
lawnberry-pi config auth --secure-sessions \
    --rotate-session-ids \
    --bind-to-ip \
    --require-https

# Configure CSRF protection
lawnberry-pi config auth --csrf-protection \
    --csrf-token-lifetime 3600  # 1 hour
```

### Session Monitoring

```bash
# View active sessions
lawnberry-pi auth sessions --list

# Terminate specific session
lawnberry-pi auth sessions --terminate SESSION_ID

# Terminate all sessions for user
lawnberry-pi auth sessions --terminate-user admin

# View session statistics
lawnberry-pi auth sessions --stats
```

## Security Best Practices

### Password Policies

```bash
# Enforce strong password policy
lawnberry-pi config auth --password-policy \
    --min-length 16 \
    --require-uppercase \
    --require-lowercase \
    --require-numbers \
    --require-symbols \
    --no-dictionary-words \
    --no-personal-info

# Set password history
lawnberry-pi config auth --password-history 12  # Remember last 12 passwords
```

### Rate Limiting

```bash
# Configure authentication rate limits
lawnberry-pi config auth --rate-limits \
    --login-attempts 5 \
    --lockout-duration 1800 \  # 30 minutes
    --progressive-delay
```

### Audit Logging

```bash
# Enable comprehensive audit logging
lawnberry-pi config auth --audit-logging \
    --log-successful-logins \
    --log-failed-attempts \
    --log-session-events \
    --log-config-changes

# View audit logs
lawnberry-pi auth audit --tail 100
lawnberry-pi auth audit --filter "failed_login" --since "1 hour ago"
```

### Security Monitoring

```bash
# Enable security monitoring
lawnberry-pi config security --monitoring \
    --alert-failed-logins 10 \
    --alert-concurrent-sessions 5 \
    --alert-suspicious-activity

# Set up email alerts
lawnberry-pi config security --email-alerts admin@yourdomain.com
```

## Troubleshooting

### Common Issues

#### Password Authentication Issues

1. **Forgot Password**:
   ```bash
   # Reset password with physical access
   sudo lawnberry-pi auth reset-password --user admin
   
   # Follow prompts to set new password
   ```

2. **Account Locked**:
   ```bash
   # Check lockout status
   lawnberry-pi auth status --user admin
   
   # Unlock account
   sudo lawnberry-pi auth unlock --user admin
   ```

#### TOTP Issues

1. **TOTP Codes Not Working**:
   ```bash
   # Check time synchronization
   sudo ntpdate -s time.nist.gov
   
   # Verify TOTP configuration
   lawnberry-pi auth totp --verify-config
   
   # Test with backup code
   # Use backup code instead of TOTP code
   ```

2. **Lost TOTP Device**:
   ```bash
   # Use backup code to login
   # Then regenerate TOTP setup
   lawnberry-pi config auth --level totp --setup-totp --force
   ```

#### Google OAuth Issues

1. **OAuth Callback Errors**:
   ```bash
   # Verify redirect URI configuration
   lawnberry-pi config auth --show-google-config
   
   # Check Google Cloud Console settings
   # Ensure redirect URI matches exactly
   ```

2. **Domain Restriction Errors**:
   ```bash
   # Check allowed domains
   lawnberry-pi config auth --show-allowed-domains
   
   # Add domain if needed
   lawnberry-pi config auth --google-allowed-domains "newdomain.com"
   ```

#### Tunnel Authentication Issues

1. **Missing Headers**:
   ```bash
   # Check Cloudflare Access configuration
   # Verify Access policy is applied
   
   # Test headers manually
   curl -v https://lawnberry.yourdomain.com/api/v1/status
   ```

2. **JWT Verification Errors**:
   ```bash
   # Check JWT signature verification
   lawnberry-pi auth test-tunnel --verify-jwt
   
   # Update Cloudflare certificates
   lawnberry-pi auth tunnel --update-certs
   ```

3. **DNS NXDOMAIN for Tunnel Hostname**:

If your browser console shows `net::ERR_NAME_NOT_RESOLVED` for your tunnel domain (e.g., `lawnberry.yourdomain.com`), the public DNS record is missing or misconfigured.

Steps to fix:

1) Verify from the Pi that DNS is missing:

```bash
getent hosts lawnberry.yourdomain.com || host lawnberry.yourdomain.com
```

2) Restore the hostname in Cloudflare Zero Trust:

- Cloudflare Dashboard → Zero Trust → Access → Tunnels → select your tunnel → Public Hostnames → Add application
- Hostname: `lawnberry.yourdomain.com`
- Service: `http://localhost:3000` (frontend server)
- Save and wait ~1–2 minutes for propagation

3) Confirm Cloudflare created the DNS record in the domain’s DNS app:

- DNS → Check for a CNAME `lawnberry` pointing to `<tunnel-uuid>.cfargotunnel.com` with Proxied = ON

4) Restart the connector (optional but helps pick up config):

```bash
sudo systemctl restart cloudflared
sudo systemctl status cloudflared --no-pager
```

5) Re-test resolution and connectivity from the Pi:

```bash
getent hosts lawnberry.yourdomain.com
curl -sS https://lawnberry.yourdomain.com/ | head -c 200
curl -sS -X POST https://lawnberry.yourdomain.com/api/v2/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"admin"}'
```

Notes:
- If you prefer direct backend access too, add a second public hostname mapping `lawnberry-backend.yourdomain.com` → `http://localhost:8081`.
- Cloudflare tunnels created via token (no local config.yml) manage hostnames from the dashboard; local `/etc/cloudflared/config.yml` may not exist.

### Debug Commands

```bash
# Test authentication configuration
lawnberry-pi auth test --all-levels

# Check authentication status
lawnberry-pi auth status --verbose

# View authentication logs
sudo journalctl -u lawnberry-backend | grep auth

# Validate configuration
lawnberry-pi config auth --validate
```

### Recovery Procedures

#### Emergency Access

```bash
# Physical recovery mode (requires Pi access)
sudo systemctl stop lawnberry-backend
sudo lawnberry-pi auth emergency-access --enable

# This creates temporary password: "emergency123"
# Login and reconfigure authentication
sudo systemctl start lawnberry-backend
```

#### Configuration Backup/Restore

```bash
# Backup authentication configuration
lawnberry-pi config backup --auth-only --file auth-backup.json

# Restore authentication configuration
lawnberry-pi config restore --auth-only --file auth-backup.json
```

### Getting Help

For authentication issues:

1. **Check logs**: `sudo journalctl -u lawnberry-backend | grep auth`
2. **Verify config**: `lawnberry-pi config auth --validate`
3. **Test connectivity**: `lawnberry-pi auth test --connectivity`
4. **Emergency access**: Use physical recovery if needed

Remember to always test authentication changes in a controlled environment before applying to production systems.