# Motor and Heading Diagnostics

LawnBerry does not expose raw progressive-stiffness or autonomous heading-validation motion
endpoints. Those historical paths bypassed the canonical motor authorization boundary and could
report success without proving a safe result. All motion diagnostics now use the same manual session,
`MotorCommandGateway`, safety interlocks, and short command leases as normal operator control.

This guide describes supported checks. It does not authorize unattended motion or replace the
physical autonomy qualification process.

## Non-motion checks

Run these first on port `8081`:

```bash
curl -s http://127.0.0.1:8081/api/v2/system/info | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/hardware/robohat | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/sensors/encoders | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/sensors/imu/status | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/sensors/gps/status | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/autonomy/readiness | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/autonomy/qualification | python -m json.tool
```

Treat unavailable, stale, simulated, or unknown fields as unavailable evidence. Do not infer healthy
hardware from an HTTP 200 response alone.

## Manual drive checks

1. Secure the mower, raise the drive wheels, keep blade power disconnected, and make the independent
   intervention control immediately reachable.
2. Obtain a server-issued manual-control session through the UI or
   `POST /api/v2/control/manual-unlock`. Browser-only or invented session IDs are rejected.
3. Use the Control UI or `POST /api/v2/control/drive` for short, low-speed commands. Release the
   joystick or send a zero vector after every check.
4. Verify forward/reverse and left/right polarity, encoder direction, immediate neutral output, and
   lease timeout through direct observation. A successful API response is not physical evidence.
5. If any command, acknowledgement, heading sample, safety state, or stop result is uncertain, use the
   independent cutoff and stop the test.

Do not test a suspected mechanical stall by automatically ramping effort. De-energize the mower and
inspect wheel freedom, debris, wiring, motor current limits, and encoder feedback instead.

## Preset-turn check

`POST /api/v2/control/preset-turn` is the only supported closed-loop turn diagnostic. It requires a
valid manual session and fresh IMU heading, renews short gateway leases while turning, and commands
neutral in a `finally` cleanup. Hardware mode fails closed when heading is unavailable; it does not
fall back to an open-loop timed turn.

Use only the Control UI during supervised physical testing. Start with the lowest practical speed and
smallest angle, wheels raised. Confirm the returned `source` is `hardware`, `method` is `imu`, and
`ok` is true, then compare `actual_degrees` with direct observation. Simulation results prove only the
software path.

## Heading investigation

Do not change `imu_yaw_offset_degrees` to mask a navigation error. Preserve the documented conversion:

```text
adjusted_yaw = (-raw_yaw + imu_yaw_offset_degrees) % 360.0
```

When heading is missing or disagrees with travel:

1. Check GPS status for fresh unique RTK-grade samples and inspect the reported course over ground.
2. Check IMU status for fresh game-rotation reports and the current reset generation.
3. Inspect `data/calibration.json` and, when diagnosing an upgrade, the legacy
   `data/imu_alignment.json` without rewriting acquisition timestamps.
4. Run the normal blade-off mission heading bootstrap in a verified center-yard clearance envelope.
   It derives GPS COG from real displacement, stages the alignment, and persists it only after a
   gateway-acknowledged stop.
5. Investigate antenna geometry, wheel slip, mounting orientation, and magnetic interference before
   changing ignored hardware configuration.

## Qualification handoff

Physical drive, timeout, obstacle, heading, and blade-circuit evidence must be recorded through
`scripts/run_autonomy_qualification.py`. The runner never energizes hazardous stages automatically.
See `docs/OPERATIONS.md` and `docs/autonomous-mowing-readiness.md` for the staged checklist, evidence
binding, cleanup requirements, and invalidation rules.
