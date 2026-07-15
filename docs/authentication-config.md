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
9. [Developer Guidance](#developer-guidance)
10. [Troubleshooting](#troubleshooting)

## Overview

LawnBerry Pi v2 features a configurable authentication system with four security levels:

1. **Password**: Explicit deployment credential or configured username/password
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
**Requirements**: The deployment credential, or a configured username/password

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

Local authentication suitable for initial setup and secure local networks. A fresh
installation has no public default username/password pair. The login screen first
accepts `LAWN_BERRY_OPERATOR_CREDENTIAL`; an authenticated operator may then
configure a custom username/password.

### Initial Setup

```bash
# Set a unique operator credential in the protected service environment.
# Do not commit the value to the repository.
LAWN_BERRY_OPERATOR_CREDENTIAL=<long-unique-operator-credential>
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

### Programmatic Password Configuration

Users can configure custom login credentials via an authenticated API endpoint. This allows creating custom username/password combinations without requiring physical access or system-level permissions.

#### API Endpoint

```
POST /api/v2/auth/configure/password
Authorization: Bearer <valid-session-token>
Content-Type: application/json

{
  "username": "admin",
  "password": "new_secure_password_12345"
}
```

#### Requirements

- **Authentication**: Caller must have a valid authenticated session (Bearer token)
- **Username**: Desired login username (typically `admin` or your preferred username)
- **Password**: New password (minimum six characters; use a much longer unique value)

#### Response

**Success (200 OK)**:
```json
{
  "success": true,
  "message": "Password configured successfully",
  "security_level": "password"
}
```

**Error (400 Bad Request)**:
```json
{
  "detail": "Passwords do not match"
}
```

**Error (401 Unauthorized)**:
```json
{
  "detail": "Not authenticated"
}
```

#### Example Usage

```bash
# Step 1: Authenticate with the explicitly configured operator credential
SESSION=$(curl -s -X POST http://localhost:8081/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "credential": "<operator-credential>"
  }' | jq -r '.access_token')

# Step 2: Configure a new custom password
curl -X POST http://localhost:8081/api/v2/auth/configure/password \
  -H "Authorization: Bearer $SESSION" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "MyNewSecure@123"
  }'

# Step 3: Use the new credentials for subsequent logins
curl -X POST http://localhost:8081/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "MyNewSecure@123"
  }'
```

#### Important Notes

1. **Session Persistence**: The new password is stored in `data/settings.json` and persists across service restarts
2. **Global Availability**: Once configured, the password works from any client accessing the LawnBerry API
3. **Backward Compatibility**: Existing Cloudflare Access and OAuth authentication methods continue to work
4. **No Default Credentials**: `admin/admin` is rejected unless an operator deliberately configures that weak value
5. **Security**: Passwords are hashed using bcrypt before storage; plain text passwords are never logged

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
  # Inject client_secret from the protected service environment.
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

### Automatic Session Bootstrap

After Cloudflare Access authenticates the browser, the frontend exchanges the
edge-provided assertion at a dedicated endpoint. Local credentials are never
submitted and the local login rate limiter is not involved:

```
Request Flow:
1. User accesses https://lawnberry.yourdomain.com
2. Cloudflare Access intercepts and authenticates the user
3. The route guard calls POST /api/v2/auth/cloudflare
4. Cloudflare attaches CF-Access-Jwt-Assertion at the edge
5. LawnBerry verifies RS256 signature, issuer, audience, expiry, and key ID
6. Signed email/sub becomes the LawnBerry session principal
7. The requested page opens without the local login screen

This eliminates double authentication (Cloudflare + app login).
```

### How Session Bootstrap Works

`POST /api/v2/auth/cloudflare` is intentionally separate from
`POST /api/v2/auth/login`:

- the configured team domain pins the HTTPS issuer and JWKS endpoint;
- the configured Access application AUD pins the intended application;
- only RS256 assertions with a known rotating Cloudflare key are accepted;
- identity comes from signed `email` or `sub` claims, never the unsigned
  `CF-Access-Authenticated-User-Email` forwarding header;
- a missing, expired, forged, wrong-issuer, or wrong-audience assertion fails
  closed and never falls back to password authentication;
- the frontend tries bootstrap once per navigation session. Refresh requests
  are single-flight and never recursively retry auth endpoints.

### Why This Matters

**Without this bypass**:
- Users authenticate with Cloudflare Access
- Are forced to see the app's login screen
- Must authenticate again with local credentials
- Results in poor UX and confusion

**With this bootstrap**:
- Users authenticate once with Cloudflare Access
- Seamlessly access the app
- No local login screen when already authenticated upstream
- Improved security posture (trust upstream auth)

### Preserving Local Authentication

Direct/local access without a valid Cloudflare assertion still uses the normal
login screen and `POST /api/v2/auth/login`. Raw Cloudflare-looking headers on
that endpoint are ignored, preserving local authentication without creating an
unsigned bypass.

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

Set both values in the backend environment file. The team domain is the bare
`<team>.cloudflareaccess.com` hostname; the AUD is copied from the Access
self-hosted application's overview:

```bash
CLOUDFLARE_ACCESS_TEAM_DOMAIN=<team>.cloudflareaccess.com
CLOUDFLARE_ACCESS_AUD=<64-character-application-aud>
```

### Header Validation

Cloudflare provides the `CF-Access-Jwt-Assertion`. LawnBerry fetches the team's
public JWKS from `/cdn-cgi/access/certs` with a bounded cache and refreshes it
when a key ID rotates. Other forwarding headers are not authentication proof.

### Testing Tunnel Authentication

Use an authenticated browser and inspect the Network panel. The protected-page
navigation should show one successful `POST /api/v2/auth/cloudflare` followed
by `GET /api/v2/auth/profile`; it must not send `POST /api/v2/auth/login`.

An unauthenticated local probe proves the endpoint fails closed:

```bash
curl -i -X POST http://127.0.0.1:8081/api/v2/auth/cloudflare
# HTTP/1.1 401 Unauthorized
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

Logout, credential changes, and concurrent-session eviction revoke the signed
session ID through a conservative high-water that covers every same-SID JWT
which could have been issued before termination. This remains true when an older
token is the first sibling restored after restart. The compact revocation
registry is stored with owner-only permissions under
`LAWN_DATA_DIR/auth_session_revocations.json`, so restarting the backend cannot
resurrect a revoked token. Expired entries are removed automatically. Each
update is written to an owner-only temporary file, fsynced, atomically replaced,
and followed by a directory fsync. If the registry cannot be read or durably
replaced, token-backed authentication fails closed; `POST /api/v2/auth/logout`
returns `503` instead of claiming the session ended.

Manual-control grants created from a LawnBerry bearer token or verified
Cloudflare assertion are dependent on the canonical authentication session.
Logout, credential rotation, expiry, or concurrent-session eviction immediately
invalidates those dependent grants. A separately verified password or TOTP
manual grant remains independent and expires on its configured manual-session
timeout.

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

The global limiter keeps separate token buckets for each client and matched
endpoint policy. In particular, the stricter Cloudflare bootstrap allowance
cannot consume or resize that client's ordinary API allowance.

Uvicorn ignores generic proxy headers. The local frontend removes any inbound
`Forwarded`, `X-Forwarded-For`, `X-Real-IP`, and `X-LawnBerry-Client-IP` values,
then creates one internal client-IP header. It accepts `CF-Connecting-IP` or
`X-Real-IP` only when the immediate frontend peer is loopback (local cloudflared
or nginx); direct LAN peers are identified by their socket address. The backend trusts the
internal header only from its loopback frontend peer. This preserves per-client
quotas without letting a browser choose another operator's lockout identity.

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

## Developer Guidance

### Architecture Overview

The LawnBerry authentication system is built with clear separation of concerns across multiple layers:

1. **AuthService** (`backend/src/services/auth_service.py`): Core authentication logic, session management, credential validation
2. **Auth Endpoints** (`backend/src/api/routers/auth.py`): FastAPI endpoints that expose authentication APIs
3. **Session Storage**: Uses `active_sessions` dictionary keyed by `session_id` (not username)
4. **Security Settings**: Stored in three synchronized locations:
   - `primary_auth_service.config` (the source of truth)
   - `global_state._security_settings` (module-level reference)
   - `rest_api._security_settings` (legacy import for backward compatibility)

### Critical Implementation Details

#### Session Storage Pattern

**DO**: Store sessions by `session_id`:
```python
self.active_sessions[session_id] = session_object
```

**DON'T**: Store sessions by username:
```python
# WRONG - causes verify_token to fail
self.active_sessions[username] = [session_list]
```

Session lookups in `verify_token()` use `session_id` as the key. Mixing storage patterns causes authentication failures where newly created sessions are invisible to token verification.

#### Global State Synchronization

When updating authentication configuration (e.g., password hashes), update all three references:

```python
# Update password in all three places
primary_auth_service.config.password_hash = hash
global_state._security_settings.password_hash = hash
rest_module._security_settings.password_hash = hash  # Legacy reference
```

If only some references are updated:
- Login endpoint may see old password (because `_current_security_settings()` checks rest module first)
- Subsequent authentication requests fail with "invalid credentials"
- Issue appears intermittent depending on request routing

#### Cloudflare Access Integration

The authentication paths are deliberately disjoint:

1. `POST /api/v2/auth/cloudflare` verifies the Access assertion and creates a
   session without receiving local credentials.
2. `POST /api/v2/auth/login` accepts the explicit shared credential or an
   operator-configured username/password and ignores Cloudflare forwarding headers.
3. A Cloudflare-backed LawnBerry JWT never outlives the verified Access assertion.
   `POST /api/v2/auth/refresh` requires a fresh verified assertion for the same
   signed principal; missing, expired, or mismatched assertions fail with 401.

An invalid assertion cannot reach the local password path, so it cannot consume
password-attempt budget or be reinterpreted as a weaker credential.

### Common Pitfalls and How to Avoid Them

#### Pitfall 1: Breaking Session Validation After Code Changes

**Symptom**: After modifying authentication code, users report "valid credentials don't work" or "login flashes then returns to login screen"

**Root Cause**: Session storage format mismatch between creation and validation

**Prevention**:
- Never change how `session_id` is used as the dictionary key
- Always verify `verify_token()` and `create_session()` use the same storage pattern
- Run `tests/unit/test_auth_security_levels_unit.py::TestAuthServiceIntegration::test_end_to_end_authentication_flow` after any session-related changes
- This test exercises the full create → validate → logout cycle

#### Pitfall 2: Configurations Not Taking Effect

**Symptom**: After updating password via API, login still uses old credentials

**Root Cause**: Updated only one of the three password storage locations

**Prevention**:
- When modifying auth configuration, use the `configure_password` endpoint as a reference
- It explicitly updates all three locations (see `auth.py` lines 553-591)
- Search for `_security_settings` and `config.password_hash` in your code
- If you modify either one, update all three

#### Pitfall 3: Cloudflare Bootstrap Not Working

**Symptom**: Cloudflare-authenticated users still see the app login screen

**Root Cause**:
- the team domain or application AUD is absent/mismatched;
- the Access policy does not protect `/api/v2/auth/cloudflare`; or
- assertion verification cannot fetch or match the rotating JWKS.

**Prevention**:
- configure the exact team domain and application AUD in the backend service environment;
- ensure the frontend and `/api/v2/auth/cloudflare` share the protected hostname;
- check backend logs for a verification-key or audience/issuer failure;
- never test by inventing `CF-Access-Authenticated-User-Email`; it is not trusted.

#### Pitfall 4: Test Failures After Refactoring Auth Code

**Symptom**: Tests pass locally but fail in CI/CD

**Root Cause**: Test fixtures don't properly reset auth state between tests

**Prevention**:
- Use the `reset_control_safety_state` fixture (defined in `conftest.py`)
- It resets:
  - `auth_service._failed_attempts`
  - `auth_service._invalidated_session_ids`
  - `auth_service.active_sessions`
  - `global_state._security_settings`
  - `rest_module._security_settings`
- See `tests/conftest.py` lines 103-167 for the complete fixture

### Testing Before Committing Auth Changes

Run this test suite after any authentication code changes:

```bash
# Run all authentication tests
python -m pytest tests/ -k auth -v

# Run specific integration tests
python -m pytest tests/integration/test_auth_custom_password.py -xvs
python -m pytest tests/contract/test_auth_login.py -xvs

# Run end-to-end auth flow
python -m pytest tests/unit/test_auth_security_levels_unit.py::TestAuthServiceIntegration::test_end_to_end_authentication_flow -xvs

# Run with rate limiting (if changed rate limit logic)
RATE_LIMIT_MAX_ATTEMPTS=5 RATE_LIMIT_WINDOW_SECONDS=60 \
  python -m pytest tests/unit/test_auth_security_levels_unit.py -xvs
```

### Important Files to Review Before Auth Changes

1. **`backend/src/services/auth_service.py`**:
   - Lines 189-217: `AuthService.__init__()` — all required fields
   - Lines 327-345: `verify_token()` — session lookup logic
   - Lines 504-527: `create_session()` real AuthService — session storage
   - Lines 529-575: `authenticate_password()`, `authenticate_totp()` — credential validation

2. **`backend/src/api/routers/auth.py`**:
   - Lines 456-503: Login endpoint (both Cloudflare and password paths)
   - Lines 553-591: `configure_password` endpoint (three-way sync)

3. **`tests/conftest.py`**:
   - Lines 103-167: `reset_control_safety_state` fixture (fixture must reset all three security settings references)

4. **`backend/src/api/rest.py`**:
   - Check how `_security_settings` is used in the login endpoint
   - This is a legacy reference that must stay in sync with auth service config

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
    -d '{"credential":"<operator-credential>"}'
```

Notes:
- If you prefer direct backend access too, add a second public hostname mapping `lawnberry-backend.yourdomain.com` → `http://localhost:8081`.
- Cloudflare tunnels created via token (no local config.yml) manage hostnames from the dashboard; local `/etc/cloudflared/config.yml` may not exist.

4. **WebSocket 401 Unauthorized (remote access)**:

When accessing the UI through a tunnel/proxy, browsers cannot set an
`Authorization` header on WebSocket upgrades. LawnBerry sends the signed local
JWT in a `Sec-WebSocket-Protocol` value instead, which the frontend proxy
forwards without placing credentials in access-log URLs. Ensure:

- You are logged in to the UI (a valid token is stored in localStorage).
- The frontend opens clean telemetry/control URLs and adds a `lawnberry.jwt.*`
  authentication subprotocol automatically.
- If using Cloudflare Access, the `CF-Access-Jwt-Assertion` header is accepted for WS authorization when Access policy already authenticated the user.

If you still see WS failures, live telemetry will fall back to REST polling. Check the browser console network tab for 401/403 responses on `/api/v2/ws/telemetry` or `/ws/telemetry` and adjust Access policies accordingly.

5. **Login Loop with Double Authentication**:

**Problem**: After entering credentials, the app redirects back to the login screen and shows "Too many attempts" rate limiting.

**Root Cause**: A Cloudflare-authenticated browser should not enter the local
password path. Repeated login/refresh retries can consume the shared password
limiter and hide the original bootstrap failure behind a 429.

**Solution**:

1. **Verify the bootstrap endpoint**:
   ```bash
   curl -i -X POST http://127.0.0.1:8081/api/v2/auth/cloudflare
   # A local request without an edge assertion must return 401, never 429.
   ```

2. **Check the browser Network panel**: protected navigation should issue one
   `/api/v2/auth/cloudflare` request. It must not recurse through `/auth/refresh`
   or submit `/auth/login` after Cloudflare already authenticated the browser.

3. **Check service configuration without printing values**:
   ```bash
   test -n "${CLOUDFLARE_ACCESS_TEAM_DOMAIN:-}" && echo team-domain-configured
   test -n "${CLOUDFLARE_ACCESS_AUD:-}" && echo audience-configured
   ```

4. **Restart only after configuration changes**:
   `sudo systemctl restart lawnberry-backend.service`.

6. **Missing or Mismatched Credentials in Browser**:

   **Problem**: Login form appears repeatedly; frontend shows "Invalid credentials" instead of "Too many attempts".

   **Diagnosis**:
   - Browser console shows 401 Unauthorized for POST `/api/v2/auth/login`
   - Response body shows `{"detail": "Invalid credentials"}`

   **Solution**:

   1. **Verify Credentials Match**:
      - LawnBerry has no default username/password pair
      - The Operator credential field must match `LAWN_BERRY_OPERATOR_CREDENTIAL`,
        or the custom username/password must match the explicitly configured hash
      - Test with curl first to isolate frontend issues

   2. **Check Frontend Storage**:
      ```javascript
      // In browser console
      localStorage.getItem('auth_token')  // Should be null before login
      localStorage.getItem('user_data')   // Should be null before login
      ```

   3. **Clear Browser Cache**:
      - Open DevTools (F12) → Application → Local Storage → Clear all
      - Refresh page and try login again

   4. **Verify Backend is Running**:
      ```bash
      curl http://localhost:8081/api/v2/status
      # Should return 200 with system status
      ```

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

# The command prints a one-time temporary credential to the local console.
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
