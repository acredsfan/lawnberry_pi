# Agent Task: Make LawnBerry Operationally Ready for Autonomous Mowing

## Repository

`https://github.com/acredsfan/lawnberry_pi`

This task was prepared from the repository state inspected on **2026-06-23**. Reinspect the current default branch before editing because files may have changed.

Read and follow these repository instructions first:

1. `AGENTS.md`
2. `docs/developer-toolkit.md`
3. `.github/copilot-instructions.md`
4. `docs/firmware-contract.md`
5. `docs/hardware-integration.md`
6. `docs/OPERATIONS.md`
7. `docs/TESTING.md`
8. `spec/hardware.yaml`

At task start:

- Use the repository-prescribed discovery tools first.
- Run `git status --short` and preserve unrelated user changes.
- Inspect the current runtime configuration and architecture before editing.
- Keep production code optimized for Raspberry Pi OS on Raspberry Pi 5 and Raspberry Pi 4B.
- Use `SIM_MODE=1` only for tests and offline validation.
- Do not claim physical correctness without on-device evidence.

## Relationship to the separate navigation/geofence task

This is a **separate task** from the straight-line tracking and operating-area/geofence task in `AGENT_TASK_STRAIGHT_LINE_GEOFENCE.md`.

This task owns the remaining operational blockers for autonomous mowing:

- physical blade control and sequencing,
- live safety enforcement,
- command leases and firmware failsafes,
- true GPS sample freshness,
- sensor acquisition cadence and readiness,
- obstacle stopping distance,
- encoder telemetry,
- battery handling and return-home orchestration,
- scheduled mission dispatch,
- Raspberry Pi 4B and Raspberry Pi 5 hardware compatibility.

Do not undo or duplicate valid changes already made by the navigation/geofence task. This work must be merge-safe whether it runs before or after that task. Shared integration points such as `MissionExecutor`, `MotorCommandGateway`, GPS freshness, blade sequencing, and mission preflight must be adapted to the current branch rather than overwritten.

## Assignment

Implement and verify the smallest complete, maintainable solution that removes the remaining software blockers to **supervised autonomous mowing**.

The completed system must:

1. Control the real physical blade through one configured and acknowledged blade-control abstraction.
2. Keep the blade off unless the mower is actively traversing an explicitly authorized mowing leg.
3. Continuously enforce tilt, obstacle, localization, battery, thermal, watchdog, emergency-stop, and hardware-health conditions while a mission is running.
4. Stop the drive and blade when a command lease, critical sensor sample, or process heartbeat becomes stale.
5. Never treat a cached GPS reading as a new fix.
6. Keep critical safety sensing responsive even when GPS, Victron BLE, environmental, camera, or other slow services stall.
7. Use useful encoder telemetry at control-loop cadence instead of a five-second, directionless heartbeat.
8. Correctly start due scheduled missions through the same preflight and execution path as operator-started missions.
9. Handle low and critical battery conditions safely and execute return-home only through a verified navigation path.
10. Preserve Raspberry Pi 5 operation and provide a documented, tested, conflict-free Raspberry Pi 4B configuration.

Do not stop after writing a plan. Implement production code, firmware changes, tests, configuration, documentation, and validation evidence.

---

# Safety invariants

These invariants are mandatory and must be enforced in the final authorization/control layers, not only in the UI or mission planner.

## Motion invariant

> No nonzero autonomous drive command may remain active unless it has a current short-duration lease, current safety authorization, and a healthy command path. Lease expiration or uncertainty must produce neutral output.

## Blade invariant

> The physical blade must default to off and remain off unless a current mission state explicitly authorizes a mowing leg and every required safety check is healthy. Any fault, timeout, transition, pause, turn, transit, exception, or shutdown must command blade off.

## Sensor invariant

> Replaying or returning a cached sensor object must never make the sample appear fresh. Freshness is derived from the original hardware sample time or monotonically increasing sample identity.

## Hardware compatibility invariant

> The software must never silently remap GPIO pins or silently switch blade backends. The configured physical wiring must be validated against the detected Pi model, and any conflict must block blade-enabled autonomy with a clear error.

## Fail-closed invariant

> Missing or stale critical hardware, invalid platform configuration, unconfirmed stop/blade-off delivery, or an unknown control state must block or terminate autonomous mowing. Zero-speed and blade-off commands must remain deliverable during fault conditions.

---

# Confirmed current defects to fix

Treat these as root causes. Reverify them against the current branch before implementation.

## 1. Mission blade intent is not executed

`MissionWaypoint.blade_on` exists, but the mission executor does not reliably consume it to control a physical blade. Mission execution can therefore drive without mowing, and the code lacks safe sequencing around turns, transit, pause, abort, completion, and faults.

Relevant areas:

- `backend/src/models/mission.py`
- `backend/src/services/mission_executor.py`
- `backend/src/services/mission_service.py`
- `backend/src/control/command_gateway.py`

## 2. There are competing and incomplete blade-control paths

The project currently contains at least two blade paths:

- `BladeService` with `IBT4BladeDriver` on Pi GPIO.
- `RoboHATService.send_blade_command()` using the RP2040 firmware protocol.

The Pi GPIO adapter in `backend/src/drivers/blade/ibt4_gpio.py` currently behaves as an in-memory stub rather than guaranteed physical GPIO control. The gateway uses `BladeService`, while the RoboHAT blade command is separate.

This must become one configured abstraction with explicit backend selection, real hardware behavior, acknowledged state, and identical safety semantics.

## 3. Live sensor data is not wired into continuous safety enforcement

`SafetyTriggerManager` supports tilt, obstacle, low battery, and high temperature, but normal hardware acquisition does not consistently call those triggers. Existing calls are primarily debug/test paths.

The mission executor also does not directly honor `obstacle_avoidance_active`, and the legacy path that zeroes `target_velocity` for obstacles returns early while mission execution is active.

Result: a live ToF or tilt condition can be visible in telemetry without reliably stopping a running mission.

Relevant areas:

- `backend/src/safety/safety_triggers.py`
- `backend/src/services/sensor_manager.py`
- `backend/src/services/navigation_service.py`
- `backend/src/services/mission_executor.py`
- `backend/src/control/command_gateway.py`

## 4. Mission motion can bypass the command gateway

The mission/navigation adapter currently reaches `NavigationService.set_speed()`, which can call the RoboHAT service directly. That bypasses the gateway where final safety authorization and command lifetime should live.

## 5. RoboHAT can refresh a stale nonzero PWM command

`RoboHATService` periodically refreshes its retained PWM command to prevent firmware fallback. If the mission loop hangs while the backend remains alive, a stale nonzero command can continue being repeated unless the retained command is explicitly neutralized by an independent lease expiry.

The RP2040 firmware also has a long control-source timeout rather than a short motion-command TTL.

## 6. Cached GPS readings can be treated as new fixes

The GPS driver and sensor interface intentionally return the last reading when a hardware read fails. `LocalizationService` currently refreshes its `last_gps_fix` time whenever a GPS object with coordinates is present, rather than proving that a new receiver sample arrived.

This can make a stale position appear fresh indefinitely.

## 7. Critical safety reads are coupled to slow aggregate telemetry

`SensorManager.read_all_sensors()` waits on GPS, IMU, ToF, environmental, and power work together. GPS may wait 1.5–2 seconds, and power/Victron reads may wait several seconds. This prevents a nominal “10 Hz” mission sensor pump from actually guaranteeing a high-rate tilt or obstacle response.

## 8. Sensor health/readiness is too permissive

Examples to correct:

- Some interfaces report `ONLINE` even when the concrete driver is unavailable or failed to connect.
- The manager considers itself initialized when any three sensors initialize, regardless of whether the critical autonomy sensors are the successful three.
- Mission start primarily checks the motor controller and does not require a complete autonomy-readiness profile.

## 9. The configured obstacle threshold is physically inadequate

The checked-in ToF threshold is approximately 0.102 m while navigation cruise speed is much higher than can safely stop inside that distance. A fixed four-inch threshold does not include sensing delay, control latency, braking, wheel slip, front overhang, or a safety allowance.

## 10. Encoder telemetry is too slow and incorrectly defined for control

Current firmware reports encoder counts primarily in a five-second heartbeat. Counts are unsigned, and the firmware increments on every transition while the backend assumes four ticks per revolution from four magnets. That can double the calculated RPM if each magnet produces two edges.

The mission executor runs stall/asymmetry logic at roughly 5 Hz, so five-second encoder updates cannot support those decisions.

## 11. Low-battery and return-home behavior are not a complete execution path

Battery thresholds exist but are not consistently wired to live mission safety. Return-home can populate navigation state without necessarily starting the real mission executor and command path. Direct fallback routes must not be treated as safe merely because a home coordinate exists.

## 12. Scheduled mission due detection is incorrect

The scheduler computes a future occurrence from the current time and then dispatches only when that future occurrence is less than or equal to the current time. That condition is effectively unreachable. Tests call the dispatch helper directly and do not prove that the due-detection loop fires.

The scheduler also records `last_run` even when mission startup fails, potentially suppressing retry for a full schedule cycle.

## 13. Pi 4B and Pi 5 pin assignments are not conflict-safe

Current documentation/configuration uses:

- Pi blade GPIO: 24 and 25.
- Pi 5 UART4 IMU: GPIO 12 and 13.
- Pi 4B documented UART4 alternative: GPIO 24 and 21.

Therefore, the current blade GPIO 24 conflicts with the documented Pi 4B UART4 IMU mapping.

The canonical spec also lists optional ToF right interrupt GPIO 12 while Pi 5 UART4 uses GPIO 12. Optional IRQ wiring must not be documented as simultaneously available on that profile.

The current mower is on a **Raspberry Pi 5**, and that working profile must remain supported. A real, conflict-free Raspberry Pi 4B profile must be added without silently changing physical pins.

---

# Required implementation

## A. Add an explicit platform and pin-allocation model

Create a focused platform/pin compatibility layer, for example:

- `backend/src/hardware/platform_profile.py`
- `backend/src/hardware/pin_registry.py`

Exact names may differ, but responsibilities must remain separate from individual drivers.

### Platform detection

Detect at least:

- Raspberry Pi 5
- Raspberry Pi 4B
- unknown/non-Pi test environment

Use a stable source such as `/proc/device-tree/model` on hardware. Allow a test-only/environment override so CI can test both profiles without pretending to be production hardware.

Do not scatter model-string checks throughout drivers.

### Typed blade configuration

Extend `HardwareConfig` and `ConfigLoader` with a typed blade configuration while preserving backward compatibility with the existing `blade_controller` key.

A suitable shape is:

```yaml
blade:
  controller: ibt-4           # ibt-4 | robohat-rp2040
  allow_autonomous: true
  spinup_seconds: 2.0
  shutdown_timeout_seconds: 1.0
  pins:
    in1: 24
    in2: 25
```

The exact schema can differ, but it must support:

- explicit controller/backend,
- explicit GPIO pins when Pi GPIO is selected,
- blade spin-up delay,
- command/ack timeout,
- whether that backend is authorized for autonomous use,
- health/readiness reporting.

### Supported platform profiles

Preserve the current Pi 5 profile:

- BNO085 UART4 on the Pi 5 mapping documented by the repository.
- Existing Pi 5 blade GPIO 24/25 remains a valid explicit configuration if the physical mower is wired that way.

Provide and test a conflict-free Pi 4B profile. Use **GPIO 26 and GPIO 27** for the Pi-GPIO IBT-4 blade profile unless current repository/hardware inspection finds a documented conflict that requires another pair. Document physical header pins and rewiring requirements. Do not silently substitute these pins at runtime.

Recommended examples:

- `config/hardware.pi5.example.yaml`
- `config/hardware.pi4.example.yaml`
- historical note: `hardware.local.yaml` overrides were supported when this plan was written; current runtime uses only ignored `config/hardware.yaml`.

### Pin registry and validation

Build a runtime pin-use registry from the detected platform plus active configured features. At minimum account for:

- IMU UART pins,
- blade GPIO pins,
- ToF XSHUT pins,
- any actually implemented ToF interrupt pins,
- other explicitly configured GPIO roles.

Requirements:

- Duplicate active allocation is a startup/readiness error.
- Return a structured reason such as `HARDWARE_PIN_CONFLICT` with both conflicting roles and pins.
- Do not silently disable one feature.
- Do not silently remap pins.
- Unknown platform plus platform-dependent pin mapping must block blade-enabled autonomy unless the user explicitly provides a validated profile.
- Update `spec/hardware.yaml`, `docs/hardware-integration.md`, and the feature matrix so Pi 4B and Pi 5 guidance is internally consistent.
- Either move the optional Pi 5 ToF-right IRQ away from GPIO 12 or clearly mark IRQ mode unsupported on the Pi 5 UART4 profile. Do not leave a contradictory canonical pin table.

## B. Create one canonical blade-controller abstraction

Define a protocol/interface used by every caller, with methods equivalent to:

```python
class BladeController(Protocol):
    async def initialize(self) -> bool: ...
    async def set_active(self, active: bool, *, reason: str) -> BladeResult: ...
    async def emergency_stop(self, *, reason: str) -> BladeResult: ...
    async def health(self) -> BladeHealth: ...
```

Use one factory selected from the typed hardware configuration.

### Backend 1: RoboHAT RP2040

Use the existing text protocol and `RoboHATService.send_blade_command()`.

Requirements:

- Wait for a positive blade acknowledgement rather than treating a successful serial write as physical confirmation.
- Track commanded and acknowledged state separately.
- Add timeout/error reason codes.
- Add a firmware-side blade command TTL/heartbeat so a backend crash or communication loss turns the blade off.
- Preserve drive/blade emergency stop behavior during reconnect and firmware reset.

### Backend 2: Pi GPIO IBT-4

Replace the in-memory GPIO stub with real, lazy-loaded Raspberry Pi GPIO output handling using an already supported hardware library from the project dependencies. Follow existing simulation-safety conventions.

Requirements:

- Both outputs are configured to the safe/off state before the driver reports initialized.
- Off means both control pins are in the documented safe state.
- Do not support blade reverse unless the hardware contract explicitly requires and safely defines it.
- Process shutdown and `emergency_stop()` drive both pins to off.
- Hardware import/setup failure must report the blade offline; never fall back to a simulated success in `SIM_MODE=0`.
- `SIM_MODE=1` remains deterministic and hardware-free.
- Expose actual configured pins and backend in health telemetry.

A Pi GPIO process cannot guarantee blade shutdown after every possible host/kernel/power failure. Preserve and strengthen documentation requiring a physical E-stop that cuts blade power. Do not claim software replaces that hardware control.

### Gateway integration

`MotorCommandGateway.dispatch_blade()` must use the configured canonical controller.

- Update shared blade state only after acknowledged success.
- Blade-off and emergency-stop commands must bypass ordinary “cannot enable while moving” checks.
- Emergency trigger must call the canonical blade controller even when the drive/RoboHAT path is unavailable.
- If drive and blade use the same RoboHAT, avoid duplicate/conflicting command paths.
- Add structured outcomes such as `BLADE_ACK_TIMEOUT`, `BLADE_CONTROLLER_OFFLINE`, and `BLADE_STOP_UNCONFIRMED`.

## C. Implement complete mission blade sequencing

Adapt to the current mission/leg model, including any changes from the separate navigation task.

Required behavior:

1. Blade off before heading bootstrap.
2. Blade off during approach to the first mow segment.
3. Stop drive before enabling the blade.
4. Enable only for an explicit mowing leg.
5. Confirm blade-on acknowledgement.
6. Wait the configured spin-up interval while stopped.
7. Begin the authorized mowing leg.
8. Stop drive and turn blade off before turns, tank pivots, transit, avoidance, return-home, or recovery movement.
9. Blade off on waypoint/leg hold, pause, abort, completion, safety stop, command failure, localization fault, geofence fault, exception, task cancellation, or backend shutdown.
10. If blade-off cannot be confirmed, latch emergency, keep drive stopped, and fail the mission.

Clarify in the model/docs whether a waypoint blade field applies to the incoming or outgoing leg. Prefer explicit leg actions (`mow`, `transit`, `turn`, `bootstrap`, `return_home`) over ambiguous waypoint state if the separate navigation task already introduces them.

Do not enable a physical blade in automated tests.

## D. Route all autonomous motion through short command leases

Every autonomous drive command must pass through `MotorCommandGateway` as a `DriveCommand(source="mission", ...)` or the repository's updated equivalent.

### Gateway lease

Implement an authoritative generation-safe command lease:

- Each nonzero mission command receives a TTL compatible with the control-loop cadence, initially around 300–500 ms.
- A newer command supersedes the previous lease.
- Lease expiry sends neutral, updates the retained RoboHAT command to neutral, and records a structured safety reason.
- Expiry tasks must use a generation/token so an old task cannot stop a newer valid command.
- Zero commands remain immediately deliverable.
- Cancellation, exception, pause, abort, and mission finalization explicitly revoke the lease.
- The gateway must not claim success until the hardware command is acknowledged.

### RoboHAT firmware motion TTL

Add a second independent failsafe in `robohat-rp2040-code/code.py`:

- Record the time of the last valid PWM motion command.
- If a non-neutral command is not renewed within a short configured firmware timeout, immediately set neutral.
- Do not wait for the existing multi-second RC/serial-mode timeout.
- Emit a concise status/fault line that the backend parses.
- Keep the blade TTL independent but coordinated: communication loss must also turn the blade off.
- Preserve explicit RC enable/disable behavior and existing manual-control compatibility.

Update `docs/firmware-contract.md` with timing, status messages, and host expectations.

### RoboHAT keepalive

The backend RoboHAT keepalive may refresh only the currently authorized retained command. Once a lease expires, it must refresh neutral—not the previous nonzero PWM.

Add tests for event-loop cancellation and stale keepalive behavior.

## E. Fix GPS sample identity and freshness

A repeated cached `GpsReading` must retain its original hardware timestamp and identity.

Implement one clear source-of-truth mechanism, such as:

- receiver/source timestamp plus monotonic receipt time,
- a monotonically increasing `sample_id`,
- or both.

Requirements:

- The GPS driver creates a new identity only when it parses a genuinely new hardware sample.
- Returning `_last_read` does not mutate its timestamp or sample identity.
- `GPSSensorInterface` may return cached data for display, but marks/exposes its freshness accurately.
- `LocalizationService.last_gps_fix` advances only when a new valid GPS sample is accepted.
- Duplicate, old, no-fix, or invalid samples do not refresh authorization.
- Clock-domain handling is explicit; use monotonic time for internal age where practical.
- GPS diagnostics expose source sample time, receipt time, sample age, sample ID, fix type, and whether the current object is cached.

Add regressions for:

- repeated cached RTK reading,
- serial timeout returning `_last_read`,
- duplicate timestamp/sample ID,
- no-fix GGA after a valid fix,
- GPS recovery with a genuinely new sample.

## F. Decouple critical sensor acquisition from slow telemetry

Do not make tilt and obstacle safety wait for a full aggregate read.

Implement per-sensor acquisition/caching tasks in or adjacent to `SensorManager`, with one owner per physical device. Suggested cadences:

- IMU: sufficient to meet the configured 200 ms tilt cutoff with margin, preferably 20 Hz or the highest stable supported rate.
- ToF: at least 10 Hz with the current timing budget, preferably 15 Hz if hardware proves stable.
- Encoder status: 10–20 Hz from firmware.
- GPS: receiver cadence / approximately 1–5 Hz, without duplicate port readers.
- Power: approximately 1 Hz for safety voltage; slower history/BLE work may run independently.
- Environmental: slow cadence.

The exact architecture can differ, but these conditions are mandatory:

- Only one code path owns each hardware port/device.
- Safety consumers read timestamped caches without waiting on Victron, camera, environmental, or unrelated drivers.
- `read_all_sensors()` becomes a fast snapshot operation or is no longer used by the critical safety loop.
- A slow/failing power or GPS driver cannot delay fresh IMU/ToF processing.
- Start/stop/shutdown lifecycle is explicit and tested.
- Cached records include sample timestamps and stale status.

## G. Add an autonomy readiness service and fail-closed preflight

Create one service used by operator starts, scheduled starts, resumes, and return-home, for example:

- `backend/src/services/autonomy_readiness_service.py`

Return a typed report containing checks, severity, reason codes, remediation, and timestamp.

At minimum require for blade-enabled autonomous mowing:

- known supported Pi platform/profile,
- no GPIO/pin conflicts,
- compatible RoboHAT firmware,
- motor controller connected and acknowledged,
- command gateway and command-lease watchdog healthy,
- blade controller initialized and healthy,
- emergency latch clear,
- critical safety supervisor running,
- fresh GPS sample with required accuracy/fix quality,
- usable heading source/alignment,
- fresh left and right ToF sensors,
- fresh battery voltage above configured start threshold,
- valid mission/path and operating area from the separate navigation task,
- no active safety interlocks.

Do not use “three of five sensors initialized” as autonomy readiness.

Add a read-only endpoint such as:

`GET /api/v2/autonomy/readiness`

Mission start must run the same service immediately before changing status to running. Resume and scheduled start must use the same gate. Return stable non-500 reason codes.

Suggested reason codes:

- `UNSUPPORTED_PLATFORM`
- `HARDWARE_PIN_CONFLICT`
- `MOTOR_CONTROLLER_OFFLINE`
- `FIRMWARE_INCOMPATIBLE`
- `BLADE_CONTROLLER_OFFLINE`
- `BLADE_BACKEND_NOT_AUTONOMY_APPROVED`
- `SAFETY_SUPERVISOR_OFFLINE`
- `GPS_SAMPLE_STALE`
- `GPS_FIX_INADEQUATE`
- `HEADING_UNAVAILABLE`
- `TOF_LEFT_STALE`
- `TOF_RIGHT_STALE`
- `BATTERY_TELEMETRY_STALE`
- `BATTERY_TOO_LOW_TO_START`
- `ACTIVE_SAFETY_INTERLOCK`

If the frontend mission planner is changed, surface the report without duplicating safety logic in TypeScript.

## H. Implement a continuous safety supervisor

Create a dedicated service that consumes timestamped sensor caches and gateway/runtime state independently of the mission loop.

It must continuously evaluate at least:

### Tilt

- Use live IMU roll and pitch.
- Apply configured threshold and minimal, justified debounce.
- Meet the configured cutoff budget with margin.
- On violation: blade off, drive neutral, latch safety/emergency state, fail/stop the mission.

### Obstacles

- Require both ToF sensors to be healthy and fresh for autonomous motion.
- Distinguish a valid “no target/out of range” sample from sensor failure/staleness.
- Apply dynamic stopping clearance described below.
- Initial safe behavior is stop-and-latch or stop-and-require-resume. Do not invent an unverified avoidance maneuver.

### Battery

- Require fresh battery voltage.
- Apply hysteresis and a short time debounce to avoid reacting to one transient sample while still respecting critical cutoff.
- Low battery: blade off and stop mowing; optionally begin verified return-home if reserve and path requirements pass.
- Critical battery: immediate blade off, neutral, and latched safety stop.

### Temperature

- Apply configured high-temperature limit to a clearly defined sensor/source.
- Stale/missing temperature should not masquerade as healthy if temperature is required by configuration.

### Control health

- Command lease expired.
- RoboHAT disconnected or firmware recovery active.
- Blade acknowledgement stale/unknown while commanded on.
- Safety supervisor heartbeat/watchdog failure.

### Localization/geofence integration

Consume the separate navigation task's localization and operating-area fault state. Do not reimplement path geometry here.

### Stop semantics

The supervisor must invoke final gateway/controller stop actions. Merely setting a Boolean or telemetry field is insufficient.

Blade off and drive neutral must be idempotent and remain available while interlocks are active.

## I. Replace the fixed obstacle threshold with a stopping-distance model

Use current ground speed or a conservative commanded-speed fallback.

At minimum calculate:

```text
required_clearance =
    speed * total_detection_and_control_latency
  + speed² / (2 * conservative_deceleration)
  + front_footprint_or_sensor_offset
  + fixed_margin
```

Configuration must include validated values for:

- worst-case sensor/control latency,
- conservative deceleration,
- front overhang/sensor offset,
- fixed obstacle margin,
- minimum clearance floor,
- stale-sample timeout.

Requirements:

- Higher speed produces a larger required clearance.
- An unknown speed uses a conservative value.
- The checked-in default must no longer be approximately four inches at normal mowing speed.
- Provide a cautious initial default and document a blade-off field calibration procedure to measure stopping distance on grass.
- Cap early field tests to a low speed until measured values are entered.

## J. Upgrade encoder telemetry and odometry inputs

Update both RP2040 firmware and backend parsing.

### Firmware

- Emit compact encoder telemetry at 10–20 Hz without flooding serial or delaying PWM acknowledgements.
- Count one defined edge per magnet pulse, or explicitly configure ticks per revolution to match the chosen edge strategy.
- Do not leave firmware counting both edges while backend assumes four ticks/revolution.
- Because the encoders are single-channel, derive sign from the currently commanded wheel direction and clearly document this limitation.
- Include sample interval or timestamp so RPM calculation is deterministic.
- Continue publishing cumulative counts for recovery/diagnostics.

### Backend

- Add typed encoder sample state with age/freshness.
- Parse the high-rate firmware record.
- Use one canonical `ticks_per_revolution` configuration.
- Compute signed wheel RPM and, where appropriate, linear wheel velocity.
- Do not arm motor-stall, wheel-spin, asymmetry, or odometry decisions using stale encoder samples.
- Correctly reset baselines after reconnect, firmware reset, and `enc=zero`.

### Testing

Test:

- one magnet pulse equals one configured tick,
- forward and reverse sign,
- left/right independence,
- stale sample rejection,
- reconnect/reset baseline,
- expected RPM from a known pulse stream,
- no false stall while encoder telemetry is temporarily unavailable.

## K. Correct scheduled mission due detection and retry semantics

Fix `JobsService` so persisted planning jobs actually fire.

Requirements:

- Determine the most recent scheduled occurrence that is due, not only the next occurrence after now.
- Dispatch when `last_successful_run < due_occurrence <= now`.
- Correctly handle timezone, day-of-week, DST gaps, and folds.
- Prevent duplicate dispatch across scheduler ticks or backend restarts.
- Record `last_run`/`last_successful_run` only after mission start is accepted.
- On preflight/start failure, retain a structured failure and bounded retry/backoff rather than suppressing the job for an entire schedule period.
- Scheduled dispatch must use the same `AutonomyReadinessService` and mission start path as operator starts.
- Add an explicit setting for unattended/scheduled autonomous starts, defaulting to disabled unless an existing repository setting already provides this control.
- A disabled unattended mode may create/queue a mission but must not begin motion.
- Do not broaden this task into multi-zone execution unless necessary; current single-zone scheduling is sufficient.

Tests must exercise the real scheduler due-detection path, not only `_dispatch_scheduled_job()` directly.

## L. Implement safe low-battery and return-home orchestration

Battery handling must use fresh measured voltage and configured thresholds.

### Low battery

- Stop the mowing leg.
- Command blade off and confirm it.
- Revoke the current drive lease.
- Decide whether return-home is allowed based on reserve, current localization, operating-area/path validity, controller health, and current safety state.

### Critical battery

- Immediate blade off and neutral.
- Latch safety stop.
- Do not attempt return-home.

### Return-home

- Execute through the real `MissionService`/`MissionExecutor` and command gateway.
- Use a verified path from the separate operating-area task.
- Blade must remain off for the complete return.
- Do not claim “returning home” merely by changing navigation state.
- Do not fall back to a direct route when safe route generation fails.
- If return-home cannot start safely, remain stopped and expose a clear reason.

Add tests for low threshold, critical threshold, stale battery data, sag debounce/hysteresis, safe return accepted, and return blocked.

## M. Harden emergency, shutdown, and exception behavior

Ensure all of these paths deliver neutral and blade off through the configured controllers:

- global emergency trigger,
- hardware/safety trigger,
- mission pause,
- mission abort,
- mission completion,
- exception and cancellation,
- backend lifespan shutdown,
- RoboHAT disconnect/reconnect,
- RP2040 firmware reset,
- command lease expiry,
- safety supervisor failure.

Requirements:

- Emergency is latched even if hardware confirmation fails.
- Hardware confirmation status remains visible.
- Drive and blade stop attempts are independent; one failure must not skip the other.
- On reconnect, safe state is applied before the controller is marked ready.
- Blade state is never inferred solely from the shared UI dictionary.
- Add finalizers/context management so task cancellation cannot bypass safe shutdown.

---

# Required automated tests

Do not weaken, skip, or xfail safety tests. Use deterministic clocks/fakes where needed.

## 1. Pi platform and pin compatibility

Test all of the following:

- Pi 5 UART4 plus blade GPIO 24/25 is accepted when no active optional IRQ conflicts.
- Pi 4B UART4 plus blade GPIO 24/25 is rejected with `HARDWARE_PIN_CONFLICT`.
- Pi 4B UART4 plus blade GPIO 26/27 is accepted.
- Pi 5 UART4 plus ToF-right IRQ GPIO 12 is rejected if both are enabled.
- Unknown platform behavior is fail closed for platform-dependent autonomous blade control.
- No runtime path silently changes pins.

## 2. Real blade abstraction

With fakes/adapters, verify:

- hardware-mode GPIO setup failure is offline, not simulated success,
- initialization forces off,
- enable acknowledgement updates state,
- failed enable leaves state off,
- emergency stop always attempts off,
- pause/abort/completion/exception all turn off,
- turn/transit legs never enable,
- spin-up occurs while drive is stopped,
- unconfirmed off latches emergency and stops motion.

## 3. Command leases

Verify:

- mission command expires to neutral,
- renewed command survives only the latest lease,
- old expiry task cannot stop a newer command,
- task cancellation neutralizes output,
- retained RoboHAT keepalive becomes neutral after expiry,
- firmware motion TTL neutralizes stale motion,
- firmware blade TTL turns blade off,
- stop/blade-off remain accepted during an interlock.

## 4. GPS freshness

Verify:

- cached object repetition does not refresh fix age,
- duplicate sample ID does not refresh,
- new sample does refresh,
- no-fix does not refresh,
- mission/readiness transitions from healthy to stale at the configured age,
- UI can still display last known position while autonomy is blocked.

## 5. Sensor cadence and isolation

Use controlled slow fakes:

- a 4-second Victron read does not delay IMU or ToF cache updates,
- tilt is processed inside the configured cutoff budget,
- ToF sample age remains within budget,
- only one task owns each hardware interface,
- shutdown cancels tasks cleanly,
- missing driver reports offline/error.

## 6. Live safety supervisor

Verify each input causes actual drive/blade actions:

- tilt,
- obstacle,
- stale left ToF,
- stale right ToF,
- stale GPS/localization fault,
- low battery,
- critical battery,
- high temperature,
- RoboHAT disconnect,
- blade acknowledgement loss,
- supervisor heartbeat failure.

## 7. Dynamic obstacle clearance

Verify:

- required clearance increases with speed,
- high-speed command is stopped farther away than low-speed command,
- stale/unknown speed uses a conservative result,
- valid no-target is distinct from stale sensor,
- configured latency/deceleration changes the result predictably.

## 8. Encoder firmware/backend contract

Verify the pulse/RPM and freshness cases specified in section J. Include parser regression tests for the exact firmware record format.

## 9. Scheduler

Verify:

- a due job is detected through `_check_and_dispatch_planning_jobs()`,
- a future job does not fire,
- a previously successful occurrence does not duplicate,
- failed start retries according to policy and does not mark success,
- timezone and DST behavior,
- scheduled motion is blocked when unattended mode is disabled,
- scheduled start uses the same readiness gate.

## 10. Battery and return-home

Verify:

- low battery stops mowing and blade,
- critical battery does not attempt return,
- return-home remains blade off,
- unsafe/unavailable return path leaves mower stopped,
- return-home uses the real executor and gateway,
- stale voltage blocks blade-enabled autonomy.

## 11. API/contract tests

Add contract coverage for:

- autonomy readiness endpoint,
- stable reason codes,
- start/resume failures returning useful non-500 responses,
- scheduled-autonomy enable/disable behavior,
- hardware pin conflict visibility,
- blade-controller health/status.

---

# Suggested files and architecture touchpoints

Use current repository conventions rather than blindly creating these exact files. Likely areas include:

- `backend/src/models/hardware_config.py`
- `backend/src/models/safety_limits.py`
- `backend/src/models/sensor_data.py`
- `backend/src/core/config_loader.py`
- `backend/src/core/runtime.py`
- `backend/src/main.py`
- `backend/src/control/commands.py`
- `backend/src/control/command_gateway.py`
- `backend/src/drivers/blade/ibt4_gpio.py`
- `backend/src/services/blade_service.py`
- `backend/src/services/robohat_service.py`
- `backend/src/services/sensor_manager.py`
- `backend/src/services/localization_service.py`
- `backend/src/services/navigation_service.py`
- `backend/src/services/mission_executor.py`
- `backend/src/services/mission_service.py`
- `backend/src/services/jobs_service.py`
- `backend/src/safety/safety_triggers.py`
- new focused platform, readiness, and safety-supervisor modules
- `robohat-rp2040-code/code.py`
- `config/hardware.yaml`
- `config/limits.yaml`
- `spec/hardware.yaml`
- `docs/firmware-contract.md`
- `docs/hardware-integration.md`
- `docs/OPERATIONS.md`
- `docs/TESTING.md`
- `docs/code_structure_overview.md`

Avoid placing all new logic in `navigation_service.py`, `rest.py`, or `main.py`. Keep policy, hardware adapters, and mission orchestration separate.

---

# Configuration requirements

Add typed, documented fields rather than magic constants. Likely additions include:

- blade backend and pins,
- blade spin-up and shutdown timeout,
- blade autonomy approval,
- drive command TTL,
- firmware motion/blade TTL,
- critical sensor stale thresholds,
- obstacle reaction latency,
- conservative deceleration,
- front overhang/sensor offset,
- obstacle fixed margin/minimum clearance,
- encoder ticks per revolution and telemetry period,
- battery low/critical debounce and hysteresis,
- scheduled autonomous start enablement.

Preserve existing local override behavior. Do not commit private hardware keys, NTRIP credentials, Victron secrets, tokens, or local runtime artifacts.

Configuration migration must be backward compatible where reasonably possible, but an ambiguous or unsafe legacy configuration must fail with actionable remediation rather than silently guessing.

---

# Validation commands

Run targeted tests first, then broad non-hardware validation according to `AGENTS.md`.

```bash
SIM_MODE=1 python -m pytest tests/unit/ -x -q -m "not hardware"
SIM_MODE=1 python -m pytest tests/integration/ -x -q -m "not hardware"
SIM_MODE=1 python -m pytest tests/contract/ -x -q -m "not hardware"
SIM_MODE=1 python -m pytest tests/ -x -q -m "not hardware"
python -m ruff check backend/src tests
python -m py_compile robohat-rp2040-code/code.py
bash scripts/check_docs_drift.sh
```

If frontend/API types change:

```bash
cd frontend
npm ci
npm run type-check
npm test
npm run build
```

Do not report success if tests pass by replacing hardware-mode failures with simulated values.

---

# Required safe hardware validation documentation

Document these steps, but do not activate the physical blade autonomously as part of agent-run validation.

## Phase 1: Platform and pin validation

On both supported profiles or representative devices:

1. Confirm detected model is correct.
2. Print the active pin-allocation report.
3. Verify Pi 5 current wiring passes.
4. Verify Pi 4B conflict profile is rejected.
5. Verify the documented Pi 4B GPIO 26/27 blade profile passes after physical rewiring.
6. Confirm no optional ToF IRQ conflicts with UART4.

## Phase 2: Drive lease with wheels raised

1. Raise drive wheels safely.
2. Send a short mission-style command.
3. Stop renewing it.
4. Verify gateway neutralizes it within TTL.
5. Stop the backend or interrupt the mission loop.
6. Verify RP2040 firmware independently neutralizes motion.
7. Confirm retained keepalive never resurrects the stale command.

## Phase 3: Blade output without blade power

Disconnect blade motor power or use a safe indicator/load.

1. Verify boot initializes off.
2. Verify configured backend controls the expected output.
3. Verify command TTL turns output off.
4. Verify pause, abort, E-stop, backend shutdown, serial disconnect, and firmware reset all result in off.
5. Confirm the physical E-stop cuts actual blade power independently of software.

## Phase 4: Safety sensors, blade physically disabled

1. Use low-speed wheel testing.
2. Trigger tilt and verify stop latency.
3. Place an obstacle at increasing distances and validate dynamic stop clearance.
4. Disconnect each ToF sensor and verify autonomy stops/blocks.
5. Interrupt GPS updates while leaving the last coordinate visible; verify autonomy blocks on stale sample.
6. Simulate low and critical battery thresholds using a safe test source/fake adapter.

## Phase 5: Encoder validation

1. Confirm each wheel count changes independently.
2. Rotate one wheel one measured revolution and verify configured ticks/revolution.
3. Verify direction sign in forward and reverse commands.
4. Verify 10–20 Hz telemetry and realistic RPM.

Only after all blade-off phases pass repeatedly should an operator separately authorize a supervised cutting test.

---

# Deliverables

Provide all of the following:

1. Focused production code changes.
2. RP2040 firmware changes and updated contract documentation.
3. Typed configuration/schema updates with migration support.
4. Pi 4B and Pi 5 example profiles and pin-conflict validation.
5. Automated unit, integration, and contract tests.
6. Updated operator/developer/hardware documentation.
7. A completion report containing:
   - root causes fixed,
   - files changed,
   - architecture decisions,
   - exact commands and test results,
   - Pi 4B and Pi 5 compatibility evidence,
   - remaining hardware-only uncertainty,
   - exact safe on-device validation steps.

Do not leave vague TODOs. Do not silently preserve a fail-open compatibility path. Do not claim unattended autonomous mowing is production-safe based only on simulation.

---

# Definition of done

- [ ] One configured canonical blade abstraction is used by all mission, manual, emergency, and shutdown paths.
- [ ] Pi GPIO blade control performs real hardware I/O in hardware mode and never silently simulates success.
- [ ] Blade state changes require acknowledgement and expose commanded versus confirmed state.
- [ ] Mission blade sequencing keeps the blade off for bootstrap, approach, turns, transit, holds, return-home, and faults.
- [ ] Unconfirmed blade-off latches emergency and keeps drive stopped.
- [ ] Every autonomous drive command uses a short generation-safe gateway lease.
- [ ] RP2040 firmware independently neutralizes stale drive commands and turns off a stale blade command.
- [ ] RoboHAT keepalive cannot resurrect an expired command.
- [ ] Cached GPS readings cannot refresh `last_gps_fix`.
- [ ] Critical sensor acquisition is decoupled from slow telemetry and meets freshness/cadence targets.
- [ ] Missing or failed hardware is reported offline/error rather than simulated online in hardware mode.
- [ ] A single autonomy readiness service gates operator start, resume, scheduled start, and return-home.
- [ ] Live tilt, obstacle, battery, temperature, controller, and sensor-staleness faults cause actual drive/blade actions.
- [ ] Obstacle clearance is speed/stopping-distance based rather than a fixed four-inch threshold.
- [ ] Encoder telemetry is high-rate, correctly scaled, freshness-aware, and direction-aware within single-channel limitations.
- [ ] Scheduled due detection fires the correct occurrence and records success only after mission start acceptance.
- [ ] Low battery stops mowing and invokes return-home only when a verified safe return is available.
- [ ] Critical battery immediately stops without attempting return.
- [ ] Current Raspberry Pi 5 operation remains supported.
- [ ] Raspberry Pi 4B has a documented and tested conflict-free GPIO profile.
- [ ] Pi model/pin conflicts fail closed with actionable errors and no silent remapping.
- [ ] Canonical docs no longer claim GPIO 12 can simultaneously serve Pi 5 UART4 and ToF IRQ.
- [ ] Targeted and broad non-hardware tests pass.
- [ ] Firmware syntax/contract validation passes.
- [ ] Safe hardware-validation instructions and evidence are complete.
