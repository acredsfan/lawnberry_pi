# LawnBerry Pi Code Review Report
Date: 2026-04-23
Reviewer: Code Review Agent

## Summary
- 1 critical issue
- 3 high-priority issues
- 1 medium-priority issue
- 0 low-priority issues

All findings are safety-critical (motor / e-stop). No issues found in the recent Victron BLE non-blocking refactor (5691076), the navigation tank-turn fix (a3d6df8), or the `get_cached_telemetry` addition — the motor-chain contract `set_speed(ls, rs) → send_motor_command(rs_norm, ls_norm) → angular = (right_norm − left_norm)/2` traces correctly to a CW turn, and the swap is consistent end-to-end. The bugs below were already present before the recent commits but pattern-match the same "cached value used past its safety window" class of bug.

---

## Critical Issues

### 1. RoboHAT reconnect resumes pre-disconnect motion (watchdog re-applies stale non-zero PWM)
- **File:** `backend/src/services/robohat_service.py:513-526` (and `:435-470`, `:128`)
- **Severity:** Critical
- **Category:** Safety / Hardware

**Problem.** After a serial reconnect, `_send_safe_state_on_reconnect()` sends one `"pwm,1500,1500"` line over the wire but does **not** update the in-memory cache `self._last_pwm` (or `_last_pwm_at`). The watchdog refresh in `_maintain_usb_control()` then resumes ~1 s later and re-sends `self._last_pwm` — which still holds the *pre-disconnect* command:

```python
# robohat_service.py:513
async def _send_safe_state_on_reconnect(self) -> None:
    try:
        await self._send_line("pwm,1500,1500")
        await asyncio.sleep(0.05)
        await self._send_line("blade=off")
        # ❌ self._last_pwm and self._last_pwm_at are NOT reset here
```

```python
# robohat_service.py:466-470 — watchdog refresh
if (now - self._last_cmd_sent_at) >= 0.9:
    steer_us, thr_us = self._last_pwm   # still the old value!
    await self._send_line(f"pwm,{steer_us},{thr_us}")
```

Compare to `emergency_stop()` (line 850-853) and `_apply_estop_if_pending()` (line 888-891), both of which DO reset `_last_pwm`. The reconnect path was missed.

**Impact.** A USB cable jiggle, kernel ACM renumber, or transient firmware glitch while the mower is driving will:
1. Disconnect serial, drop motor PWM at the firmware (firmware has its own ~5 s timeout, hardware safe).
2. `_reconnect()` fires, sends one neutral PWM, marks `serial_connected = True`.
3. Within ≤ 0.9 s, the watchdog refreshes `_last_pwm = (e.g. 1675, 1675)` → mower **spontaneously resumes motion at the speed it had before the disconnect**, with no operator command. Blade was disabled but drive motors re-engage.

**Fix.** In `_send_safe_state_on_reconnect()` (line 513), reset the cached PWM after sending neutral:

```python
async def _send_safe_state_on_reconnect(self) -> None:
    try:
        await self._send_line("pwm,1500,1500")
        self._last_pwm = (1500, 1500)
        self._last_pwm_at = time.monotonic()
        await asyncio.sleep(0.05)
        await self._send_line("blade=off")
        logger.info("RoboHAT safe state applied after reconnect")
    except Exception as exc:
        logger.warning("Failed to apply safe state after RoboHAT reconnect: %s", exc)
```

Add a regression test in `tests/unit/test_robohat_service.py` that:
1. Sets `_last_pwm = (1675, 1675)`.
2. Calls `_send_safe_state_on_reconnect()`.
3. Asserts `_last_pwm == (1500, 1500)`.

---

## High-Priority Issues

### 2. Manual drive `duration_ms` is parsed and validated but never enforced
- **File:** `backend/src/api/rest.py:782-1090` (the `control_drive_v2` endpoint)
- **Severity:** High
- **Category:** Safety

**Problem.** The endpoint reads, type-checks, and range-clamps `duration_ms` (lines 853-863) but never schedules an auto-stop based on it. After `robohat.send_motor_command(left_speed, right_speed)` (line 1016) returns, the python-side has no further obligation — and the watchdog (`_maintain_usb_control`) refreshes the same non-zero PWM every 0.9 s indefinitely, defeating the firmware's ~5 s SERIAL_TIMEOUT (which is the only autonomous fail-safe).

There IS a working `_setup_command_timeout` in `backend/src/services/motor_service.py:393-403` that uses `command.timeout_ms` to schedule an `emergency_stop()` — but the v2 drive endpoint does **not** route through `MotorService`; it talks directly to `robohat_service`.

**Impact.** If the operator's browser tab crashes, the WebSocket drops, network MTU stalls, or the joystick `setTimeout` chain in `frontend/src/views/ControlView.vue:1348-1361` is interrupted, the mower keeps moving in the last commanded direction. The frontend's `MOVEMENT_REPEAT_INTERVAL_MS` ticker is the *only* thing stopping it.

**Fix.** Add a server-side auto-stop. Suggested pattern: keep a single module-level `_drive_timeout_task` that gets cancelled and re-armed on each accepted drive command. On expiry, send `robohat.send_motor_command(0.0, 0.0)`.

```python
# in rest.py — module scope
_drive_timeout_task: asyncio.Task | None = None

# inside control_drive_v2, after a successful send_motor_command:
global _drive_timeout_task
if _drive_timeout_task and not _drive_timeout_task.done():
    _drive_timeout_task.cancel()
# duration_ms == 0 means "honour client tick" — clamp to a hard ceiling anyway
auto_stop_ms = duration_ms if duration_ms > 0 else 500
async def _auto_stop():
    try:
        await asyncio.sleep(auto_stop_ms / 1000.0)
        await robohat.send_motor_command(0.0, 0.0)
        logger.warning("Manual drive duration expired (%d ms); motors stopped", auto_stop_ms)
    except asyncio.CancelledError:
        pass
_drive_timeout_task = asyncio.create_task(_auto_stop())
```

(The `_drive_timeout_task` reference must be retained — assignment to a module global accomplishes this; otherwise the task can be garbage-collected mid-flight per the asyncio docs.)

Add an integration test that sends one drive command and verifies `_last_pwm` returns to `(1500, 1500)` within `duration_ms + 100 ms`.

---

### 3. Queued e-stop is silently dropped on runtime reconnect; `clear_emergency` doesn't reset `_estop_pending`
- **File:** `backend/src/services/robohat_service.py:528-602` (`_reconnect`), `:863-876` (`clear_emergency`), `:883-892` (`_apply_estop_if_pending`)
- **Severity:** High
- **Category:** Safety

**Problem.** `_apply_estop_if_pending()` is only awaited from `start()` (line 277). The runtime reconnect path (`_reconnect()` at line 528) never calls it. Meanwhile, `clear_emergency()` (line 863) never sets `_estop_pending = False`.

Combined failure mode: operator presses e-stop while serial is briefly disconnected → `emergency_stop()` line 839-842 sets `_estop_pending = True` and returns False. Serial reconnects → safe state sent, `serial_connected = True`, but `_apply_estop_if_pending()` is **not** called. `_estop_pending` stays True forever.

From this state, two bad outcomes are possible:
- (a) Per Issue #1 above, the watchdog re-applies the stale non-zero PWM. The mower moves even though the operator pressed e-stop.
- (b) `send_motor_command()` (line 789-791) refuses every subsequent command because `_estop_pending` is True. Operator presses "Clear E-stop" — `clear_emergency()` clears the firmware-side RC but leaves `_estop_pending = True` in Python — so motor commands stay rejected forever, with the operator getting no clear indication why.

**Impact.** Operator's safety-critical input is silently lost. After a transient serial blip during an e-stop, the mower can either resume motion (via #1) or become permanently inert with no software path to recovery short of a service restart.

**Fix.** Two coupled changes:

1. In `_reconnect()` (line 581), call `_apply_estop_if_pending()` immediately after `_send_safe_state_on_reconnect()` and before setting `serial_connected = True`:

```python
if await self._probe_firmware_response():
    await self._send_safe_state_on_reconnect()
    await self._apply_estop_if_pending()      # <-- add this line
    self.status.serial_connected = True
    ...
```

2. In `clear_emergency()` (line 863-876), clear the queued flag after the firmware ack:

```python
ok = await self._send_line("rc=disable")
if ok:
    self._estop_pending = False               # <-- add this line
    self.status.last_error = None
else:
    self.status.last_error = "clear_emergency_failed"
return ok
```

---

### 4. `emergency_stop()` returns False without queueing the e-stop when USB-control ack times out
- **File:** `backend/src/services/robohat_service.py:836-849`
- **Severity:** High
- **Category:** Safety

**Problem.**

```python
async def emergency_stop(self) -> bool:
    if not self.serial_conn or not self.serial_conn.is_open or not self.running:
        self._estop_pending = True            # path A: queues
        return False

    usb_ready = await self._ensure_usb_control(timeout=0.6, retries=2)
    if not usb_ready:
        logger.critical("Emergency stop failed closed: ...")
        # ❌ path B: does NOT set _estop_pending; does NOT zero _last_pwm
        return False
    ok = await self._send_line("pwm,1500,1500")
    self._last_pwm = (1500, 1500)
    ...
```

Path B (USB control ack times out within 0.6 s × 2 retries) is the case where the firmware is alive on the wire but unresponsive to control-handoff prompts. The function returns False without:
- queueing the e-stop, and
- zeroing `_last_pwm`.

The `_maintain_usb_control` watchdog therefore continues refreshing the previous non-zero `_last_pwm` at 0.9 s intervals.

**Impact.** Operator pressed e-stop; the mower keeps moving with no further escalation in the python layer.

**Fix.** Always queue and always zero the cache so the watchdog refresh becomes harmless:

```python
if not usb_ready:
    logger.critical("Emergency stop failed closed: USB control acknowledgement unavailable")
    self._estop_pending = True                # queue for retry
    self._last_pwm = (1500, 1500)             # neutral on next watchdog tick
    self._last_pwm_at = time.monotonic()
    self.status.motor_controller_ok = False
    self.status.last_error = self.status.last_error or "usb_control_unavailable"
    return False
```

Note this fix depends on Issue #3's fix (so the queued e-stop is actually applied on the next reconnect/recovery).

---

## Medium-Priority Issues

### 5. GPS autoprobe can open the RoboHAT USB CDC port and reset the RP2040
- **File:** `backend/src/drivers/sensors/gps_driver.py:166-244`
- **Severity:** Medium
- **Category:** Hardware contract

**Problem.** The lazy-open block enumerates candidates including `/dev/ttyACM0`, `/dev/ttyACM1`, and the glob `/dev/ttyACM*` (lines 191-204). It then calls `serial.Serial(dev, baud, timeout=0.25)` on each. Opening a CDC-ACM port on Linux asserts DTR by default, which **resets** RP2040-class boards (the RoboHAT) — i.e. exactly the same DTR-reset hazard the project explicitly avoids for `/dev/ttyAMA4` (BNO085). Unlike the RoboHAT exclusion list in `robohat_service._known_excluded_devices()`, the GPS driver has no symmetric exclusion of the RoboHAT port.

Trigger conditions:
1. GPS serial is currently `None` (initial open or after a `to_thread` close on error).
2. The user-configured GPS device or `GPS_DEVICE` env var is missing/wrong.
3. Real GPS happens to be on a higher-numbered ACM than the RoboHAT, so the loop tries the RoboHAT first.

**Impact.** The probe write of NMEA detection bytes can reboot the RP2040 mid-mission, dropping motor PWM and forcing a reconnect dance (and per Issue #1, possibly resuming stale motion afterwards).

**Fix.** Mirror the RoboHAT exclusion strategy in `gps_driver._read_hardware_blocking()` — refuse to probe any device that resolves to the RoboHAT serial path. The cheapest fix is to reuse the existing helper:

```python
from ..services.robohat_service import _known_excluded_devices  # circular import risk;
                                                                # consider moving the helper to a shared module
excluded = _known_excluded_devices() | {"/dev/robohat"}
candidates = [c for c in candidates
              if c not in excluded and os.path.realpath(c) not in excluded]
```

Alternatively, open ACM ports with `dsrdtr=False, rtscts=False` and a manual DTR clear before write. The exclusion-list approach is safer and consistent with the rest of the codebase.

---

## Notes for Implementer

- All four high/critical fixes touch `backend/src/services/robohat_service.py`. They should land together — Issues #1, #3, #4 are interlocking failure modes around the `_last_pwm` cache and the `_estop_pending` flag, and fixing only one leaves the system in an inconsistent state.
- New regression tests should go in `tests/unit/test_robohat_service.py`. There is already a contract-style test for `set_speed` arg-swapping in `tests/unit/test_navigation_service.py` — model the new tests after that.
- For Issue #2, the test fixture should mock `robohat.send_motor_command` and assert the auto-stop call sequence.
- Validation steps after fixes (per project's `sim-hardware-validation` policy): in SIM_MODE, run `pytest tests/unit/test_robohat_service.py tests/unit/test_navigation_service.py -v`. Real-hardware validation should specifically reproduce: (a) USB unplug/replug while driving → confirm mower stays stopped; (b) e-stop during transient disconnect → confirm clear/recover sequence works; (c) joystick command followed by 1 s of silence → confirm motors stop within `duration_ms + 100 ms`.
- Nothing flagged in Victron BLE refactor (5691076) or navigation tank-turn fix (a3d6df8). The motor-chain swap contract is consistent across `navigation_service.set_speed` ↔ `robohat_service.send_motor_command` ↔ `_mix_arcade_to_pwm`, and the v2 manual drive endpoint produces the same PWM polarity for a "right" command as the navigation tank-turn does for `turn_sign=+1`.
