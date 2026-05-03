# Firmware / RoboHAT Command-and-Ack Contract

This document is the authoritative reference for the text-protocol contract between
the Pi backend (`MotorCommandGateway` + `RoboHATService`) and the RoboHAT RP2040
CircuitPython firmware. It defines what the gateway depends on and what the firmware
must guarantee.

**Last updated:** 2026-05-01

---

## Command Protocol

All commands are newline-terminated ASCII strings sent over USB CDC or hardware UART
serial at 115200 baud.

| Command | Effect | Firmware ack |
|---|---|---|
| `pwm,<steer_us>,<throttle_us>` | Set motor PWM. 1500 µs = stop; range 1000–2000 µs. | `[USB] PWM …` line |
| `blade=on` | Engage blade motor relay | `[USB] Blade: ON` |
| `blade=off` | Disengage blade motor relay | `[USB] Blade: OFF` |
| `rc=disable` | Switch to USB control mode; firmware ignores RC receiver | `[USB] RC disabled` or status heartbeat with `rc_enabled: false` |
| `rc=enable` | Return control authority to RC receiver | `[USB] RC enabled` |

### PWM Mapping

The `_mix_arcade_to_pwm` function in `RoboHATService` converts differential left/right
wheel speeds (−1.0 .. 1.0) to steer/throttle PWM microseconds. The MDDRC10 motor driver
has a dead band; values below ±80 µs from center produce no wheel motion.

---

## Ack Timeout and Retry Policy

| Constant | Value | Location |
|---|---|---|
| `ACK_TIMEOUT_S` | 0.35 s | `backend/src/control/command_gateway.py` |
| `ACK_RETRY_COUNT` | 0 | `backend/src/control/command_gateway.py` |

- The firmware typically acks a PWM command within 5–50 ms over USB CDC.
- `_wait_for_pwm_ack` waits up to `ACK_TIMEOUT_S` using `asyncio.Event` notification
  (not fixed-interval polling) so response latency equals the actual serial round-trip.
- `ACK_RETRY_COUNT = 0`: on ack timeout, `dispatch_drive` returns `CommandStatus.ACK_FAILED`
  immediately. The caller (navigation loop or REST endpoint) decides whether to retry.
- No retry is the conservative default: unacknowledged motor commands on a mower are
  ambiguous (firmware may have executed but the ack was lost), so stopping is safer than
  re-issuing.

---

## Firmware Version

The firmware emits a boot banner on USB CDC connect in one of these forms:

```
▶ LawnBerry RoboHAT firmware v1.2.3
▶ firmware:1.2.3 ready
▶ v1.3.0
```

`RoboHATService._process_line` extracts the semver with `_FIRMWARE_VERSION_RE`
(`r"\bv?(\d+\.\d+(?:\.\d+)*)\b"`) and stores the clean string on
`RoboHATStatus.firmware_version`.

The `MotorCommandGateway` checks `firmware_version` before every `dispatch_drive` and
`dispatch_blade` call when hardware is connected:

- `firmware_version is None` → `CommandStatus.FIRMWARE_UNKNOWN` (banner not yet received)
- `firmware_version not in SUPPORTED_FIRMWARE_VERSIONS` → `CommandStatus.FIRMWARE_INCOMPATIBLE`

### Version Compatibility Matrix

| Firmware version | Supported | Notes |
|---|---|---|
| 1.0.0 | Yes | Initial protocol |
| 1.1.0 | Yes | Added `blade=on`/`blade=off` |
| 1.2.0 | Yes | USB timeout behavior change |
| 1.2.1 | Yes | Bug fix — encoder tick race condition |
| 1.3.0 | Yes | Added encoder position in heartbeat |
| < 1.0.0 | No | `FIRMWARE_INCOMPATIBLE` |
| unknown | No | `FIRMWARE_UNKNOWN` (not yet received) |

To add a new supported version: update `SUPPORTED_FIRMWARE_VERSIONS` in
`backend/src/control/command_gateway.py` and add a row to this table in the same PR.

---

## Hardware Emergency Stop Latch

The firmware has **independent** stop paths that do not depend on the Pi process being
healthy. These are **not** the same as the software gateway emergency stop.

### Firmware-Side Stop Paths

1. **SERIAL_TIMEOUT watchdog (~5 s):** If the Pi stops sending any command within
   ~5 seconds, the firmware drops back to RC mode and the motor controller de-energizes
   (safe state). The watchdog is fed by the backend's `_maintain_usb_control` loop which
   sends a keepalive PWM refresh every ~0.9 s.

2. **RC failsafe:** If a physical RC receiver is wired and the transmitter signal is lost,
   the firmware reverts to failsafe (typically stop). The RC failsafe channel is configured
   on the RC transmitter and firmware side — not in the backend.

3. **Physical power cut:** Cutting 12 V to the MDDRC10 motor driver stops motors
   immediately regardless of firmware or Pi state.

4. **Hardware estop button (if wired):** If the operator has wired an estop button to
   RC channel 5 or a firmware GPIO, the firmware handles it independently of the backend.

### Software-Side Estop (Gateway)

`gateway.trigger_emergency()` sends `pwm,1500,1500` + `blade=off` over serial and sets
the software latch. This is the **in-process** stop path. If the Pi process hangs, crashes,
or the serial connection is lost before the command arrives, the firmware SERIAL_TIMEOUT
watchdog is the fallback.

The `_estop_pending` flag in `RoboHATService` queues an estop for re-delivery on serial
reconnect so the firmware reaches a safe state as soon as the serial link is restored.

### HIL Validation

Hardware-in-the-loop (HIL) tests for firmware-side estop behavior are opt-in and
separated from CI-safe tests. To run them:

```bash
SIM_MODE=0 uv run pytest tests/hil/ -v -k "estop"
```

These tests require a connected RoboHAT and physical access to the mower.

---

## Implementation References

| Symbol | File |
|---|---|
| `SUPPORTED_FIRMWARE_VERSIONS` | `backend/src/control/command_gateway.py` |
| `ACK_TIMEOUT_S` | `backend/src/control/command_gateway.py` |
| `ACK_RETRY_COUNT` | `backend/src/control/command_gateway.py` |
| `RoboHATStatus.firmware_version` | `backend/src/services/robohat_service.py` |
| `RoboHATService.get_firmware_version()` | `backend/src/services/robohat_service.py` |
| `_FIRMWARE_VERSION_RE` | `backend/src/services/robohat_service.py` |
| `HealthService._evaluate_firmware()` | `backend/src/core/health.py` |
