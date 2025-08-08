#!/usr/bin/env bash
# Lightweight health/readiness probe for lawnberry-api
# Uses timeouts to avoid hanging.
set -euo pipefail
BASE_URL="${1:-http://127.0.0.1:8000}" 

fail() { echo "HEALTH_CHECK_FAIL: $1" >&2; exit 1; }

# Liveness
status_json=$(timeout 5s curl -fsS "$BASE_URL/health" || true)
[ -n "$status_json" ] || fail "No /health response"

# Meta
meta_json=$(timeout 5s curl -fsS "$BASE_URL/api/v1/meta" || true)
[ -n "$meta_json" ] || fail "No /api/v1/meta response"

# Basic field checks
echo "$meta_json" | grep -q '"status"' || fail "Meta missing status"
echo "$meta_json" | grep -q '"api_version"' || fail "Meta missing api_version"

echo "OK"
