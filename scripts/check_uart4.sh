#!/usr/bin/env bash
# LawnBerryPi - UART4 prerequisite checker (Bookworm/Pi 5)
# Purpose: Check if dtoverlay=uart4 and enable_uart=1 are present in boot config.
# Behavior: Prints guidance to add the overlay and reboot if missing.
# All operations are read-only and timeout-protected.

set -euo pipefail

# Colors (fallback if not tty)
if [ -t 1 ]; then
  BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
else
  BLUE=''; GREEN=''; YELLOW=''; RED=''; NC=''
fi

info() { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Determine boot config path (Bookworm vs legacy)
BOOT_CONFIG="/boot/firmware/config.txt"
if [ ! -f "$BOOT_CONFIG" ] && [ -f "/boot/config.txt" ]; then
  BOOT_CONFIG="/boot/config.txt"
fi

info "Checking UART4 prerequisite in ${BOOT_CONFIG}"

# Timeout-safe grep helper
has_line() {
  local pattern="$1"
  timeout 3s bash -lc "grep -q '^${pattern}$' '${BOOT_CONFIG}'" 2>/dev/null
}

missing=0
if has_line "dtoverlay=uart4"; then
  info "Found: dtoverlay=uart4"
else
  warn "Missing: dtoverlay=uart4"
  missing=1
fi

# enable_uart should be 1 for reliability
if has_line "enable_uart=1"; then
  info "Found: enable_uart=1"
else
  # If enable_uart exists but not 1, call that out; else recommend adding
  if timeout 3s bash -lc "grep -q '^enable_uart=' '${BOOT_CONFIG}'" 2>/dev/null; then
    warn "Found: enable_uart set but not 1; recommend setting enable_uart=1"
  else
    warn "Missing: enable_uart=1"
  fi
  missing=1
fi

# Device presence (often requires reboot)
if timeout 2s ls -l /dev/ttyAMA4 >/dev/null 2>&1; then
  success "/dev/ttyAMA4 present"
else
  info "/dev/ttyAMA4 not present (may require reboot after adding overlay)"
fi

if [ "$missing" -eq 0 ]; then
  success "UART4 prerequisite satisfied. You can run the installer."
  exit 0
fi

cat <<EOF

Next steps to enable UART4 (copy-paste):

sudo sh -c 'grep -q "^dtoverlay=uart4$" ${BOOT_CONFIG} || echo dtoverlay=uart4 >> ${BOOT_CONFIG}'
sudo sh -c 'grep -q "^enable_uart=1$" ${BOOT_CONFIG} || ( \
  grep -q "^enable_uart=" ${BOOT_CONFIG} && sed -i "s/^enable_uart=.*/enable_uart=1/" ${BOOT_CONFIG} || echo enable_uart=1 >> ${BOOT_CONFIG} \
)'
sync
sudo reboot

After reboot, re-run:
  bash scripts/install_lawnberry.sh
EOF

exit 2
