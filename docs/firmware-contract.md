# Firmware/RoboHAT Contract

This document describes the text-protocol contract between the Pi backend and the
RoboHAT RP2040 CircuitPython firmware. It is the reference for `MotorCommandGateway`
correctness and for HIL test design.

## Command Protocol

All commands are newline-terminated ASCII strings sent over USB CDC serial
(baud 115200, or UART equivalents).

| Command | Effect | Ack |
|---------|--------|-----|
| `pwm,<steer_us>,<throttle_us>` | Set motor PWM (1500 = stop, range ~1000–2000) | `PWM_OK` or `OK` within ack_timeout |
| `blade=on` | Engage blade motor | `OK` |
| `blade=off` | Disengage blade motor | `OK` |
| `rc=disable` | Switch to USB control mode | `USB_CONTROL` or `OK` |
| `rc=enable` | Return control to RC receiver | `OK` |

## Acknowledgement Policy

- **Ack timeout:** 350 ms (configurable via `send_motor_command` `ack_timeout` param).
- **Retry policy:** No automatic retry on ack timeout. The gateway returns `TIMED_OUT`
  and the caller is responsible for deciding whether to retry.
- `send_motor_command` uses `_wait_for_pwm_ack` which counts ack events after the
  command is sent. Only acks that arrive after the command is issued are counted.

## Firmware Version

The firmware emits a version banner on USB connect, matching:

```
firmware: <major>.<minor>.<patch>
```

The gateway reads this at startup and exposes it via `RoboHATStatus.firmware_version`.
Supported versions are listed in `MotorCommandGateway.SUPPORTED_FIRMWARE_VERSIONS`.
If the version is `None` (not yet received) or not in the supported set, `dispatch_drive`
and `dispatch_blade` return `FIRMWARE_UNKNOWN` or `FIRMWARE_INCOMPATIBLE` outcomes and
do not dispatch to hardware.

## Hardware Emergency Stop Latch

The firmware has an independent watchdog that halts motors if no command is received
within ~5 seconds (SERIAL_TIMEOUT). This is independent of the software gateway.

Hardware-side estop paths (not dependent on the Pi being healthy):
1. Physical RC emergency button (if wired to RC channel 5 / failsafe)
2. Firmware SERIAL_TIMEOUT watchdog: motors halt if the Pi stops sending commands
3. Power cut to the MDDRC10 motor controller

Software-side `emergency_stop()` sends `pwm,1500,1500` + `blade=off`. This is the
*software* stop path; it does not assert a hardware latch. The gateway holds `_estop_pending`
if the stop is sent while serial is disconnected, and re-sends on reconnect.

## Version Compatibility Matrix

| Firmware version | Supported | Notes |
|---|---|---|
| 1.0.0 | Yes | Initial protocol |
| 1.1.0 | Yes | Added blade=on/off |
| 1.2.0 | Yes | USB timeout behaviour changed |
| 1.2.1 | Yes | Bug fix |
| < 1.0.0 or unknown | No | Gateway returns FIRMWARE_UNKNOWN/INCOMPATIBLE |
