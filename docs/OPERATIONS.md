# LawnBerry Pi v2 - Operations Guide

This document summarizes common operational procedures and API references relevant to day-to-day use on Raspberry Pi OS (64-bit, Bookworm). All examples target Raspberry Pi 5 primarily, with Pi 4B compatibility noted where relevant.

## Services
- Backend API (FastAPI/Uvicorn): port 8081
- Web UI (Vite dev): port 3000 (proxy to /api → /api/v2)
- WebSocket: ws://127.0.0.1:8081/api/v2/ws/telemetry

## Startup behavior

Use these runtime defaults consistently when starting or validating the stack:

- **Local backend development**: run Uvicorn on port `8081`
- **Local frontend development**: run Vite on port `3000`
- **Deployed/systemd runtime**: backend remains on `8081`, frontend remains on `3000`
- **Playwright preview/E2E**: Vite preview runs on port `4173` by design

This means `8081`/`3000` are the canonical backend/frontend ports for both local development and deployed operation. The preview server on `4173` is intentional and only used for preview/E2E flows.

## On-device Wi-Fi failover

On the mower, Wi-Fi is managed by NetworkManager with two radios:

- `wlan1` is the current primary client radio and normally carries `wlan1-primary`
- `wlan0` is kept managed as a standby/backup scan radio

Operational notes:

- The built-in radio must remain managed by NetworkManager; on this Pi that is enforced with
  `/etc/udev/rules.d/100-manage-wlan0.rules`
- Backup NetworkManager profiles exist on `wlan0` for `Butters Read-Link`, `Link Outdoor`, and `Link_IoT`
- `/etc/NetworkManager/dispatcher.d/90-wifi-failover` promotes the best visible backup profile on `wlan0` if
  `wlan1` drops off Wi-Fi completely
- Backup profiles intentionally keep `autoconnect=false` so they do not steal the active route during normal
  operation; the dispatcher is what activates them on failure

Useful checks:

```bash
nmcli -f DEVICE,TYPE,STATE,CONNECTION dev status
nmcli -f NAME,DEVICE,AUTOCONNECT connection show
nmcli -f SSID,SIGNAL,CHAN,FREQ dev wifi list ifname wlan0 --rescan yes
journalctl -t wifi-failover -n 50 --no-pager
```

## Simulation vs hardware mode

The backend has two meaningful startup modes:

- **`SIM_MODE=1`**: pure simulation mode; skip hardware access entirely
- **`SIM_MODE=0`**: hardware mode; attempt real hardware initialization and degrade gracefully if individual devices fail

Important nuance: leaving `SIM_MODE` unset currently behaves like hardware mode because `backend/src/main.py` checks
`os.getenv("SIM_MODE", "0")`.

Recommended commands:

```bash
# Laptop / CI / simulation-safe local dev
SIM_MODE=1 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081

# Raspberry Pi / hardware validation
SIM_MODE=0 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
```

If you want a clean local-development experience without serial/GPIO warnings, always set `SIM_MODE=1` explicitly.

## TLS/HTTPS Operations

TLS is managed automatically:
- On first setup, nginx is installed and configured with a self-signed certificate.
- If `LB_DOMAIN` and `LETSENCRYPT_EMAIL` are set in `.env`, the system provisions a valid Let’s Encrypt certificate and switches nginx to use it.
- A daily renewal timer validates and renews certificates; on issues or imminent expiry, the system falls back to self-signed to maintain availability.
- The fallback self-signed certificate now includes SAN entries for `localhost`, detected LAN IPv4 addresses, and configured domain/alt-domain values so browsers do not also fail with a hostname-mismatch error when you access the Pi by IP.

Useful commands:
```bash
# Check renewal timer status and last/next run
systemctl list-timers | grep lawnberry-cert-renewal

# Inspect recent renewal logs
journalctl -u lawnberry-cert-renewal.service -n 200 --no-pager

# Force a renewal/validation cycle
sudo systemctl start lawnberry-cert-renewal.service

# Dry-run renewal test
sudo certbot renew --dry-run

# Backend health and metrics for TLS status
curl -s http://127.0.0.1:8081/api/v2/health | jq '.subsystems.tls'
curl -s http://127.0.0.1:8081/metrics | grep lawnberry_tls_cert_
```

Environment variables (set in `.env`):
- `LB_DOMAIN` – primary domain (CN)
- `LETSENCRYPT_EMAIL` – contact email for Let’s Encrypt
- `ALT_DOMAINS` – optional hostname SANs (comma-separated), e.g., `www.example.com,api.example.com`; do not put LAN/private IPs here because Let’s Encrypt will not issue IP-address certificates
- `CLOUDFLARE_API_TOKEN` – optional, for DNS-01 (wildcards or no port 80)

Practical note: a self-signed certificate is still untrusted by default, but with SANs present the browser warning should now be about trust only, not both trust and hostname mismatch.

If you protect the public hostname with Cloudflare Access, HTTP-01 issuance will fail unless `/.well-known/acme-challenge/*` is excluded from the Access policy. Otherwise use DNS-01 with `CLOUDFLARE_API_TOKEN`.

## Health & Status
- GET http://127.0.0.1:8081/health → { status: "healthy" }
- GET http://127.0.0.1:8081/api/v2/dashboard/status → system status
- GET http://127.0.0.1:8081/api/v2/dashboard/telemetry → telemetry snapshot
- GET http://127.0.0.1:8081/api/v2/telemetry/stream → telemetry stream
- GET http://127.0.0.1:8081/api/v2/telemetry/export → export telemetry data

## Map & Planning
- GET/POST http://127.0.0.1:8081/api/v2/map/zones
- GET/PUT http://127.0.0.1:8081/api/v2/map/locations
- GET/PUT http://127.0.0.1:8081/api/v2/map/configuration → map configuration CRUD
- POST http://127.0.0.1:8081/api/v2/map/provider-fallback → trigger provider fallback
- GET http://127.0.0.1:8081/api/v2/nav/coverage-plan?config_id=default&spacing_m=0.6 → generated coverage preview polyline
- GET/POST/DELETE http://127.0.0.1:8081/api/v2/planning/jobs

## Control
- POST http://127.0.0.1:8081/api/v2/control/drive
- POST http://127.0.0.1:8081/api/v2/control/blade
- POST http://127.0.0.1:8081/api/v2/control/emergency-stop
- POST http://127.0.0.1:8081/api/v2/control/emergency_clear → clear E-stop with confirmation
- GET http://127.0.0.1:8081/api/v2/hardware/robohat → RoboHAT status
- GET http://127.0.0.1:8081/api/v2/camera/status → camera activity + FPS snapshot
- GET http://127.0.0.1:8081/api/v2/camera/frame → latest raw JPEG snapshot
- GET http://127.0.0.1:8081/api/v2/camera/stream.mjpeg → live MJPEG stream

The Web UI now exposes a virtual joystick for manual drive control. Drag in any direction to stream drive vectors (linear/forward on the Y axis, angular/turn rate on the X axis). The slider underneath scales max velocity (10–100%). Releasing the joystick or pressing **Stop Motors** immediately sends a zero-vector command and clears the motion queue; the backend rate limiter has dedicated bursts for these endpoints to prevent inadvertent HTTP 429 responses during manual driving sessions.

Operational notes:

- The RoboHAT status endpoint now treats the firmware's `rc=disable` acknowledgement as controller-ready instead of leaving the UI stuck on a stale handshake-pending warning.
- Older RoboHAT CircuitPython builds may take about three seconds to begin responding after the USB serial port opens and may emit heartbeat lines like `[RC] steer=...` instead of the newer `get_rc_status` payload. Treat that as compatible firmware, not a missing board.
- Camera snapshot and MJPEG endpoints now emit raw JPEG bytes; if the live feed regresses again, verify intermediate proxies are not recompressing or buffering `/api/v2/camera/stream.mjpeg`.

## Manual drive safety gating

Manual drive now fails closed for **non-zero** movement commands on live hardware when the backend cannot confirm a safe local-control context.

- The RoboHAT controller must be connected and controller-ready before the joystick is enabled in the WebUI.
- The backend blocks non-zero drive commands with HTTP `423` if fresh hardware telemetry is unavailable, usable GPS position
  awareness is missing, or a ToF obstacle reading is at/inside the configured clearance threshold.
- Zero-vector stop commands remain allowed so an operator can still halt motion immediately while the controller is connected.

Useful checks:

```bash
curl -s http://127.0.0.1:8081/api/v2/hardware/robohat | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/dashboard/telemetry | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/sensors/health | python -m json.tool
```

If manual motion is blocked with `OBSTACLE_DETECTED`, `LOCATION_AWARENESS_UNAVAILABLE`, or `TELEMETRY_UNAVAILABLE`,
clear nearby obstacles and restore fresh hardware telemetry before retrying.

## Mission execution safety feedback

Mission creation/start can succeed before the mower has enough verified autonomy feedback to traverse the first waypoint, so
watch the mission status contract instead of assuming `running` alone means the rover is moving.

- Autonomous obstacle gating now uses the same configured ToF clearance threshold as manual drive:
  `config/limits.yaml` → `tof_obstacle_distance_meters` (currently `0.2` m).
- If waypoint traversal cannot begin safely after the bounded verification window, the mission now fails with explicit detail
  instead of remaining indefinitely `running` / `executing` with no progress.
- RoboHAT drive commands now wait for an explicit firmware PWM acknowledgement before the backend reports them accepted; if
  the RP2040 rejects the command or never acknowledges it, the mission/manual-control path surfaces that as a controller
  failure instead of treating a successful serial write as motion success.
- `GET /api/v2/control/status` reflects the navigation mode/path state, while
  `GET /api/v2/missions/{mission_id}/status` is the authoritative mission lifecycle/detail surface.

Useful checks:

```bash
curl -s http://127.0.0.1:8081/api/v2/control/status | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/missions/<mission-id>/status | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/hardware/robohat | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/dashboard/telemetry | python -m json.tool
```

## AI
- GET http://127.0.0.1:8081/api/v2/ai/datasets
- POST http://127.0.0.1:8081/api/v2/ai/datasets/{datasetId}/export

## Settings
- GET/PUT http://127.0.0.1:8081/api/v2/settings → settings profile management
- GET http://127.0.0.1:8081/api/v2/docs/bundle → offline documentation bundle
- POST http://127.0.0.1:8081/api/v2/verification-artifacts → upload verification artifacts

## Systemd
See systemd/*.service and systemd/install_services.sh for installation. Backend service listens on port 8081.

Certificate renewal units:
- `lawnberry-cert-renewal.service` — on-demand renewal/validation + nginx reload + fallback
- `lawnberry-cert-renewal.timer` — runs the renewal daily with randomized delay

## WebSocket Topics
The V2 API provides WebSocket subscriptions for real-time data:
- `telemetry`: Real-time sensor and system telemetry data
- `control`: Control command echoes and lockout status
- `maps`: Map updates and provider status changes
- `ai`: AI processing results and status updates

Connect to ws://127.0.0.1:8081/api/v2/ws/telemetry and send:
```json
{
  "action": "subscribe",
  "topic": "telemetry"
}
```

## Latency Targets
Per constitutional requirements:
- **Pi 5**: API responses ≤250ms (p95)
- **Pi 4B**: API responses ≤350ms (p95)
- **WebSocket**: ≤100ms message delivery

Use `scripts/test_performance_degradation.py` to validate latency compliance.

## Telemetry Export
Export telemetry data for analysis:
```bash
curl -X POST http://127.0.0.1:8081/api/v2/telemetry/export \
  -H "Content-Type: application/json" \
  -d '{"start_time": "2025-01-01T00:00:00Z", "end_time": "2025-01-31T23:59:59Z", "format": "json"}'
```

## Offline Documentation
Generate offline documentation bundle:
```bash
cd .
python scripts/generate_docs_bundle.py
# Output: verification_artifacts/docs-bundle/lawnberry-docs-{timestamp}.tar.gz
```

## Emergency Stop Recovery
When an emergency stop is active, all motion is locked out. To clear it:

1) Ensure the physical E-stop button is released and area is safe
2) Clear via API with explicit confirmation flag:

```bash
curl -X POST http://127.0.0.1:8081/api/v2/control/emergency_clear \
  -H "Content-Type: application/json" \
  -d '{"confirmation": true}'
```

The system will return status EMERGENCY_CLEARED.

## Blade Safety Lockout
By default, blade engagement is locked out until safety preconditions are satisfied (no emergency stop, motors not active, authorization present). If a blade command is rejected, check active interlocks and remediate hazards before retrying.

## IMU Calibration
For best orientation accuracy, calibrate the IMU after installation:
- Warm up system for 2 minutes
- Perform figure-eight motions and gentle tilts on all axes
- In simulation (`SIM_MODE=1`), calibration is bypassed; in hardware mode (`SIM_MODE=0`), verify orientation health in `/api/v2/dashboard/telemetry`

## GPS Setup
- Preferred: ZED-F9P via USB; alternative: Neo-8M via UART
- NTRIP corrections:
  - If the rover already receives corrections directly (configured in u-center), no further changes are needed on the Pi.
  - When letting the Pi forward RTCM data, ensure `gps_ntrip_enabled: true` in `config/hardware.yaml` and update the `.env` file with the required `NTRIP_*` caster settings (host, mountpoint, credentials, serial device).
  - Restart the backend service after modifying `.env` so the connection is re-established.
- Validate GPS health via GET /api/v2/sensors/health and /api/v2/fusion/state

## Geofence Definition
Use the map configuration API to define boundaries and exclusion zones:
```bash
curl -X PUT http://127.0.0.1:8081/api/v2/map/configuration \
  -H "Content-Type: application/json" \
  -d '{"provider":"osm","zones":[{"zone_id":"boundary1","zone_type":"boundary","geometry":{"type":"Polygon","coordinates":[[[-122.4195,37.7750],[-122.4190,37.7750],[-122.4190,37.7745],[-122.4195,37.7745],[-122.4195,37.7750]]]}}]}'
```

## Telemetry Latency Troubleshooting
If dashboard telemetry latency exceeds targets:
- Reduce cadence via settings or WebSocket set_cadence
- Check CPU/memory usage; Pi 4B may require lower rates
- See also Performance Optimization below

## Performance Optimization
- Prefer Pi 5 for higher telemetry rates (target ≤250ms p95)
- On Pi 4B, reduce telemetry rate and background tasks (target ≤350ms p95)
- Use scripts/test_performance_degradation.py to measure and tune

## Documentation Troubleshooting
If documentation bundle generation fails:
- Check scripts/generate_docs_bundle.py output
- Ensure docs/ exists and markdown files are readable
- Re-run: python scripts/generate_docs_bundle.py --format tarball

## Verification Artifacts
Create verification artifacts to record validation evidence:
```bash
curl -X POST http://127.0.0.1:8081/api/v2/verification-artifacts \
  -H "Content-Type: application/json" \
  -d '{"type":"quickstart","location":"./verification_artifacts","summary":"Quickstart passed","linked_requirements":["FR-001","FR-047"],"created_by":"operator"}'
```

## Settings Management
- GET/PUT /api/v2/settings to retrieve/update the active profile
- Version conflicts return HTTP 409; update profile_version and retry
- Branding checksum validation ensures asset integrity

## Branding Assets
Branding assets are validated via checksum in settings. Provide a 64-character SHA-256 string; invalid lengths return error BRANDING_ASSET_MISMATCH.

## Constitutional Compliance
All API endpoints include remediation metadata in error responses:
```json
{
  "detail": "Validation error message",
  "remediation_link": "/docs/troubleshooting#validation-errors"
}
```

## CI/CD Gating and Quality Checks

### Automated CI Gates

The CI pipeline includes the following mandatory quality gates that must pass before merge:

#### 1. Lint and Format
- **Ruff linting**: Enforces Python code style
- **Ruff formatting**: Ensures consistent code formatting
- **Black formatting**: Additional Python formatting validation
- **Mypy type checking**: Strict type checking (currently non-blocking)
- **TODO policy**: Blocks unapproved TODOs (only TODO(v3) allowed)

#### 2. Constitutional Compliance
- **Forbidden packages**: Blocks pycoral/edgetpu (ARM64 compliance)
- **Import scanning**: Detects forbidden imports in source code
- **ARM64 reminder**: Documents platform-specific requirements

#### 3. Test Suite
- **Contract tests**: Validates all V2 API endpoints (tests/contract/)
- **Integration tests**: Validates service coordination (tests/integration/)
- **Unit tests**: Validates core services and stores (tests/unit/)
- **SIM_MODE**: All tests run in simulation mode for CI

#### 4. Telemetry Export
- **Export functionality**: Validates telemetry data export
- **Format validation**: Ensures export formats are valid (JSON/CSV)

#### 5. UI Regression
- **Frontend unit tests**: Validates Vue 3 components and stores
- **Build verification**: Ensures frontend builds without errors
- **Bundle validation**: Checks dist/ artifacts are created

#### 6. Performance Validation
- **Latency testing**: Validates API latency ≤350ms (CI target)
- **Degradation detection**: Alerts on performance regressions
- **Production targets**: ≤250ms (Pi 5), ≤350ms (Pi 4B)

#### 7. Documentation Drift
- **Markdown formatting**: Validates markdown consistency
- **Drift detection**: Prevents uncommitted documentation changes
- **Bundle freshness**: Ensures documentation bundle is up-to-date (<90 days old)

### Branch Protection Rules

Configure the following branch protection rules for the main branch:

1. **Require status checks to pass before merging**:
   - lint-and-format
   - constitutional-compliance
   - test
   - telemetry-export-test
   - ui-regression-test
   - performance-validation
   - contract-test-suite
   - integration-test-suite
   - docs-drift-check

2. **Require branches to be up to date before merging**: Enabled

3. **Require linear history**: Recommended

4. **Require signed commits**: Optional but recommended

### Remediating Failed CI Checks

#### Lint/Format Failures
```bash
# Auto-fix linting issues
ruff check --fix .

# Auto-format code
ruff format .
black .

# Check types
mypy --strict src
```

#### Test Failures
```bash
# Run specific test suite
pytest tests/contract/ -v
pytest tests/integration/ -v
pytest tests/unit/ -v

# Run with detailed output
pytest tests/contract/test_rest_api_telemetry.py -vv

# Frontend tests
cd frontend && npm test
```

#### Performance Failures
```bash
# Run performance tests locally
python scripts/test_performance_degradation.py --threshold-ms 250

# Check WebSocket performance
python scripts/test_websocket_load.py
```

#### Documentation Drift
```bash
# Format documentation
mdformat docs spec

# Regenerate documentation bundle
python scripts/generate_docs_bundle.py

# Check bundle freshness
python scripts/generate_docs_bundle.py --check-only
```

#### UI Regression
```bash
# Rebuild frontend
cd frontend
npm ci
npm run build

# Run tests
npm test
```

### Local Pre-Commit Validation

Run the full CI suite locally before pushing:

```bash
# Backend checks
ruff check .
ruff format --check .
black --check .
SIM_MODE=1 pytest tests/

# Frontend checks
cd frontend
npm test
npm run build

# Performance validation
python scripts/test_performance_degradation.py --threshold-ms 250

# Documentation validation
python scripts/generate_docs_bundle.py --check-only
```

### CI Performance Metrics

Target CI pipeline execution times:
- **Lint and Format**: <2 minutes
- **Test Suite**: <5 minutes
- **UI Regression**: <3 minutes
- **Performance Validation**: <2 minutes
- **Total Pipeline**: <15 minutes

### Monitoring CI Health

Track CI health metrics:
- **Pass rate**: Target >95%
- **Pipeline duration**: Monitor for degradation
- **Flaky tests**: Investigate and fix intermittent failures
- **Resource usage**: Monitor GitHub Actions minutes

### Emergency Bypass Procedures

⚠️ **Use only in emergency situations**

If CI is blocking a critical hotfix:
1. Document the reason for bypass
2. Create a follow-up issue to address the failure
3. Get approval from maintainer
4. Use admin override to merge
5. Fix the issue immediately after deployment

**DO NOT** bypass CI for:
- Constitutional compliance failures
- Security vulnerabilities
- Performance regressions
- Test failures in affected code paths

## Notes
- All commands and scripts are designed for ARM64 (Raspberry Pi OS Bookworm).
- Avoid adding platform-specific dependencies.
- All V2 API endpoints follow constitutional audit logging requirements.
- Settings profiles use versioning to prevent concurrent modification conflicts.
- CI gates enforce constitutional compliance and quality standards per FR-013.
