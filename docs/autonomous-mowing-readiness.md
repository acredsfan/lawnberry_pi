# Autonomous Mowing Readiness

This document records the current software gates for supervised autonomous mowing.
It is not a substitute for field validation with the blade physically disabled.

## Software Gates

- `GET /api/v2/autonomy/readiness` returns platform, pin-allocation, blade-controller,
  motor-controller, and safety-interlock checks with stable reason codes.
- Blade-enabled autonomy is blocked unless the configured `blade:` backend has
  `allow_autonomous: true`, initializes successfully, and has no active GPIO conflict.
- The current Pi 5 mower profile may explicitly use IBT-4 GPIO 24/25.
- The Pi 4B UART4 IMU profile conflicts with GPIO 24, so the documented Pi 4B blade
  profile uses GPIO 26/27 and requires physical rewiring.
- Mission drive commands use short backend leases; stale mission commands are neutralized.
- RP2040 firmware independently neutralizes stale serial motion and turns blade output off
  when command renewal stops.
- GPS cached samples retain their original sample identity and do not refresh localization
  freshness authorization.
- Obstacle clearance is based on speed, latency, braking, front offset, and fixed margin
  fields in `config/limits.yaml`.
- Live mission admission captures one report containing the exact qualification, controller,
  fresh RTK pose, heading, operating-area revision, full-path, obstacle, weather, conflict, and
  energy-reserve facts used for the decision. Missing wiring or evaluation errors fail closed.
- GPS quality is mission-owned and progresses through `nominal`, `hold`, `dead_reckoning`,
  `recovering`, and bounded `terminal` states. Non-nominal state holds the blade off; the motor
  gateway also enforces the degraded speed cap, and recovery requires consecutive live samples.

## Safe Hardware Validation

Run these only on Raspberry Pi OS with the mower secured.

### Phase 1: Platform and Pins

1. Start backend in hardware mode.
2. Call `GET /api/v2/autonomy/readiness`.
3. Confirm Pi 5 current wiring reports no pin conflict.
4. Confirm a Pi 4B profile using GPIO 24/25 reports `HARDWARE_PIN_CONFLICT`.
5. Confirm the Pi 4B GPIO 26/27 profile reports no pin conflict after rewiring.

### Phase 2: Drive Lease, Wheels Raised

1. Raise drive wheels.
2. Send a mission-style nonzero command through the backend.
3. Stop renewing it.
4. Verify neutral output within the configured backend TTL.
5. Interrupt the backend command loop and verify RP2040 serial motion TTL neutralizes output.

### Phase 3: Blade Output, Blade Power Disconnected

1. Disconnect blade motor power or use a safe indicator load.
2. Verify boot initializes output off.
3. Verify configured backend controls only the expected output pins.
4. Verify blade TTL, pause, abort, E-stop, backend shutdown, serial disconnect, and firmware reset
   all leave output off.
5. Confirm physical E-stop cuts blade power independently of software.

### Phase 4: Sensors, Blade Disabled

1. Trigger tilt and verify drive/blade stop latency.
2. Place obstacles at increasing distances and verify dynamic stop clearance.
3. Disconnect each ToF sensor and verify autonomy blocks or stops.
4. Interrupt GPS updates while leaving the last coordinate visible; verify autonomy blocks on stale sample.
5. Simulate low and critical battery thresholds with a safe test source.
