#!/usr/bin/env bash
# Quick diagnostics for GPIO line consumers on Raspberry Pi (Bookworm)
# Focus: identify processes holding BCM lines 22 and 23 (ToF XSHUT)
set -euo pipefail

PIN_A=${1:-22}
PIN_B=${2:-23}

which gpioinfo >/dev/null 2>&1 || { echo "gpioinfo not found"; exit 1; }

printf "\n--- gpioinfo (consumers for lines %s and %s) ---\n" "$PIN_A" "$PIN_B"
/usr/bin/gpioinfo | awk -v A="$PIN_A" -v B="$PIN_B" 'BEGIN{chip=""} /^gpiochip/{chip=$0} /^\tline/{ln=$2+0; if (ln==A||ln==B) print chip"\n"$0}'

printf "\n--- /dev/gpiochip* ---\n"
ls -l /dev/gpiochip* || true

printf "\n--- lsof /dev/gpiochip* (may need sudo) ---\n"
(lsof /dev/gpiochip* 2>/dev/null || true) | sed -n '1,120p'

if command -v sudo >/dev/null 2>&1; then
  printf "\n--- sudo lsof /dev/gpiochip* ---\n"
  (sudo lsof /dev/gpiochip* 2>/dev/null || true) | sed -n '1,120p'
  printf "\n--- sudo fuser -v /dev/gpiochip* ---\n"
  (sudo fuser -v /dev/gpiochip* 2>/dev/null || true)
fi

printf "\n--- ps -ef | grep -E '(pigpiod|libgpiod|lgpio|sensor_service|python|uvicorn)' ---\n"
ps -ef | grep -E '(pigpiod|libgpiod|lgpio|sensor_service|python|uvicorn)' | grep -v grep | sed -n '1,150p'

printf "\nHint: If you see consumer=lg on lines %s/%s, another lgpio-based process holds them.\n" "$PIN_A" "$PIN_B"
printf "Stop conflicting services (e.g., pigpiod) or remap XSHUT to free lines.\n"
