#!/usr/bin/env bash
set -euo pipefail

# Validate that required MCP servers for agents are installed and start cleanly.

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

ok() {
  echo "[OK] $*"
}

warn() {
  echo "[WARN] $*"
}

probe_server() {
  local label="$1"
  shift

  local log_file
  log_file="$(mktemp -t ${label}.mcp.XXXXXX.log)"

  set +e
  timeout 4s "$@" >"$log_file" 2>&1
  local rc=$?
  set -e

  case "$rc" in
    124)
      ok "$label started (timeout used intentionally)"
      ;;
    0)
      # Some servers may exit 0 when invoked without stdio transport wiring.
      warn "$label exited immediately with rc=0 (check logs if tools are still unavailable)"
      ;;
    *)
      echo "--- ${label} log ---" >&2
      sed -n '1,120p' "$log_file" >&2 || true
      fail "$label failed to start (rc=$rc)"
      ;;
  esac

  rm -f "$log_file"
}

PI_CONTROL_CMD="/home/pi/.local/bin/pi-control-mcp"
FORGEMIND_NODE="/home/pi/.nvm/versions/node/v22.20.0/bin/node"
FORGEMIND_ENTRY="/home/pi/ForgeMind/mcp_server/dist/index.js"
SEMBLE_PY="/home/pi/.local/share/mcp/semble/.venv/bin/python"
SEMBLE_ENTRY="/home/pi/.local/share/mcp/semble/serve_semble_mcp.py"

[[ -x "$PI_CONTROL_CMD" ]] || fail "pi-control-mcp not executable at $PI_CONTROL_CMD"
[[ -x "$FORGEMIND_NODE" ]] || fail "Node executable not found at $FORGEMIND_NODE"
[[ -f "$FORGEMIND_ENTRY" ]] || fail "ForgeMind MCP entry not found at $FORGEMIND_ENTRY"
[[ -x "$SEMBLE_PY" ]] || fail "Semble venv python not executable at $SEMBLE_PY"
[[ -f "$SEMBLE_ENTRY" ]] || fail "Semble MCP wrapper missing at $SEMBLE_ENTRY"

probe_server "pi-control" "$PI_CONTROL_CMD" --config /home/pi/pi-control-mcp/pi-control.toml --transport stdio --enable-tier3
probe_server "forgemind" "$FORGEMIND_NODE" "$FORGEMIND_ENTRY"
probe_server "semble" "$SEMBLE_PY" "$SEMBLE_ENTRY"

ok "MCP tooling validation completed"
