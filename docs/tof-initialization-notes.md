# ToF Sensor Initialization Modes

The mower uses two VL53L0X ToF sensors that both power up at I2C address `0x29`. To avoid address conflicts, the ToF manager uses the GPIO `XSHUT` pins to bring up sensors one at a time and set one to `0x30`.

Behavior:

- Default (auto): Use GPIO `XSHUT` sequencing to assign addresses (`left` → `0x29`, `right` → `0x30`). If GPIO is unavailable/claimed but both `0x29` and `0x30` are already present on the I2C bus (e.g., after a successful prior assignment), the manager will fall back to a no-GPIO init and proceed.
- Always no-GPIO: Set `LAWNBERY_TOF_NO_GPIO=always` to force no-GPIO init. This requires both `0x29` and `0x30` to already be present; otherwise initialization fails. Useful when you have guaranteed pre-assigned addresses and want to avoid touching GPIO.
- Never no-GPIO: Set `LAWNBERY_TOF_NO_GPIO=never` to require GPIO sequencing and address assignment on every startup.

Env vars:

- `LAWNBERY_TOF_NO_GPIO`: `auto` (default) | `always` | `never`
- `LAWNBERY_TOF_REQUIRED_GOOD_READS`: consecutive good reads required before sensor is considered healthy (default 3)
- `LAWNBERY_TOF_GOOD_READ_AGE_S`: max age in seconds for last good read (default 10)

Wiring (default):

- `tof_left`: `shutdown_pin` GPIO 22, target address `0x29`
- `tof_right`: `shutdown_pin` GPIO 23, target address `0x30`

Notes:

- On cold power-up, both sensors are at `0x29`. GPIO `XSHUT` sequencing is required at least once to move one to `0x30`. Afterwards, the manager can use the no-GPIO path if both addresses remain assigned.
- The manager verifies sensors by a read attempt and tracks a short streak of valid (non-zero, in-range) measurements before marking a sensor as healthy.

GPIO handling and resilience:

- The GPIO wrapper prefers `lgpio` (Pi 5 compatible) and falls back to `RPi.GPIO`.
- It now automatically reopens the chip and retries the last operation if it detects an "unknown/bad handle" condition.
- `GPIOManager` uses short retry/backoff for `setup_pin` and `write_pin` when encountering transient "GPIO busy/in use" errors, with strict timeouts to prevent hangs.
- Cleanup is per‑pin: components free only the pins they configured instead of calling global `GPIO.cleanup()`, which can close shared handles unexpectedly.

Troubleshooting:

- Unknown handle errors: mitigated by the auto‑reopen logic in the GPIO wrapper; if still seen, ensure no external processes force cleanup of GPIO while services are active.
- GPIO busy on XSHUT (GPIO 22/23): indicates contention. Stop potential claimants before tests:
	- `systemctl --user stop lawnberry-*`
	- `sudo systemctl stop pigpiod`
	- The manager retries briefly, but a cold reboot can help clear kernel state if pins remain stuck.
- No‑GPIO mode: safe only when both `0x29` and `0x30` are already present on the bus. In `auto` mode the manager will fall back to no‑GPIO when both are detected.
