#!/usr/bin/env bash
set -euo pipefail

# Constitutional compliance checks for LawnBerry Pi v2
# Platform: Raspberry Pi OS Bookworm (64-bit)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC} $1"; }
fail() { echo -e "${RED}FAIL${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}WARN${NC} $1"; }

# 1) OS/Arch check
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" ]]; then
  fail "This project targets ARM64 only (detected: $ARCH)"
else
  pass "Architecture is ARM64 ($ARCH)"
fi

# 2) Python version
if command -v python3 >/dev/null 2>&1; then
  PV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  pass "Python detected: $PV"
else
  fail "Python3 is not installed"
fi

# 3) Node version
if command -v node >/dev/null 2>&1; then
  NV=$(node -v)
  pass "Node detected: $NV"
else
  fail "Node is not installed"
fi

# 4) No disallowed packages (example: pycoral/edgetpu in main env)
if python3 -c 'import importlib,sys; sys.exit(0 if not importlib.util.find_spec("pycoral") else 1)'; then
  pass "pycoral not present in main environment"
else
  fail "pycoral detected in main environment (violates isolation policy)"
fi

# 5) Systemd files present
if [[ -f "systemd/lawnberry-backend.service" ]]; then
  pass "systemd units present"
else
  warn "systemd units missing (expected under systemd/)"
fi

# 6) Tests directory present
if [[ -d "tests" ]]; then
  pass "tests/ directory present"
else
  fail "tests/ directory missing"
fi

# 7) Journal file present
if [[ -f ".specify/memory/AGENT_JOURNAL.md" ]]; then
  pass "Agent journal present"
else
  warn "Agent journal missing"
fi

exit 0
