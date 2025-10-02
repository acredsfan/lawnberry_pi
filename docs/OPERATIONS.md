# LawnBerry Pi v2 - Operations Guide

This document summarizes common operational procedures and API references relevant to day-to-day use on Raspberry Pi OS (64-bit, Bookworm).

## Services
- Backend API (FastAPI/Uvicorn): port 8001
- Web UI (Vite dev): port 3000 (proxy to /api → /api/v2)
- WebSocket: ws://127.0.0.1:8001/api/v2/ws/telemetry

## Health & Status
- GET http://127.0.0.1:8001/health → { status: "healthy" }
- GET http://127.0.0.1:8001/api/v2/dashboard/status → system status
- GET http://127.0.0.1:8001/api/v2/dashboard/telemetry → telemetry snapshot
- GET http://127.0.0.1:8001/api/v2/telemetry/stream → telemetry stream
- GET http://127.0.0.1:8001/api/v2/telemetry/export → export telemetry data

## Map & Planning
- GET/POST http://127.0.0.1:8001/api/v2/map/zones
- GET/PUT http://127.0.0.1:8001/api/v2/map/locations
- GET/PUT http://127.0.0.1:8001/api/v2/map/configuration → map configuration CRUD
- POST http://127.0.0.1:8001/api/v2/map/fallback → trigger provider fallback
- GET/POST/DELETE http://127.0.0.1:8001/api/v2/planning/jobs

## Control
- POST http://127.0.0.1:8001/api/v2/control/drive
- POST http://127.0.0.1:8001/api/v2/control/blade
- POST http://127.0.0.1:8001/api/v2/control/emergency-stop
- GET http://127.0.0.1:8001/api/v2/control/robohat-status → RoboHAT status

## AI
- GET http://127.0.0.1:8001/api/v2/ai/datasets
- POST http://127.0.0.1:8001/api/v2/ai/datasets/{datasetId}/export

## Settings
- GET/PUT http://127.0.0.1:8001/api/v2/settings → settings profile management
- GET http://127.0.0.1:8001/api/v2/docs/bundle → offline documentation bundle
- POST http://127.0.0.1:8001/api/v2/verification-artifacts → upload verification artifacts

## Systemd
See systemd/*.service and systemd/install_services.sh for installation.

## WebSocket Topics
The V2 API provides WebSocket subscriptions for real-time data:
- `telemetry`: Real-time sensor and system telemetry data
- `control`: Control command echoes and lockout status
- `maps`: Map updates and provider status changes
- `ai`: AI processing results and status updates

Connect to ws://127.0.0.1:8001/api/v2/ws/telemetry and send:
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
curl -X POST http://127.0.0.1:8001/api/v2/telemetry/export \
  -H "Content-Type: application/json" \
  -d '{"start_time": "2025-01-01T00:00:00Z", "end_time": "2025-01-31T23:59:59Z", "format": "json"}'
```

## Offline Documentation
Generate offline documentation bundle:
```bash
cd /home/pi/lawnberry
python scripts/generate_docs_bundle.py
# Output: verification_artifacts/docs-bundle/lawnberry-docs-{timestamp}.tar.gz
```

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
cd frontend && npm run test:unit
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
npm run test:unit
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
npm run test:unit
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
