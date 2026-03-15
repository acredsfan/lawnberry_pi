---
name: sim-hardware-validation
description: 'Use for LawnBerry Pi simulation vs real-hardware validation. Covers SIM_MODE selection, .env and config checks, simulation-safe test-first workflow, hardware preflight expectations, and avoiding false claims that local success proves on-device behavior.'
argument-hint: 'What subsystem should be validated in simulation or on hardware?'
user-invocable: true
---

# Simulation vs Hardware Validation

## What this skill does

This skill keeps validation honest by separating simulation-safe checks from true hardware validation on the Pi.

## When to use

- before running backend tests or startup checks
- when a task touches GPIO, serial, I2C, camera, RoboHAT, GPS, IMU, ToF, or blade control
- when a bug report says "works locally" but hardware behavior is unclear
- when onboarding a maintainer who might assume backend startup equals hardware success

## Procedure

1. Classify the task:
   - simulation-safe: pure backend/frontend logic, contracts, UI flows, docs, most unit tests
   - hardware-sensitive: motor/blade control, camera ownership, serial/GPIO/I2C/UART, sensor timing, field telemetry
2. Make the mode explicit.
   - prefer `SIM_MODE=1` for laptops, CI, and first-pass validation
   - use `SIM_MODE=0` only when real hardware access is intended and prepared
3. Check runtime prerequisites.
   - confirm whether a project-root `.env` is required
   - read `config/hardware.yaml`, `config/limits.yaml`, and relevant secrets/example files
   - verify hardware expectations in `docs/hardware-integration.md` and `spec/hardware.yaml`
4. Validate in the safest order.
   - run focused simulation-safe tests first
   - only then perform hardware-aware checks if the task truly requires them
   - keep hardware validation targeted; do not treat best-effort startup as field proof
5. Record what was and was not validated.

## Things to watch closely

- unset `SIM_MODE` currently behaves like hardware mode in some startup paths
- lazy imports can make local startup look healthier than real device readiness
- camera ownership is centralized; avoid duplicate device opens
- hardware regressions require checking `.env`, serial devices, I2C/UART wiring, and Pi-specific service state

## Completion checks

- the chosen mode is explicit in the work summary
- simulation-safe validation happened before any hardware claims
- `.env` and config prerequisites were checked when relevant
- the final report distinguishes tested logic from untested real-hardware assumptions
