# Safety Contract API (FR-012)

This document specifies the minimal interfaces and behaviors required for safety across the LawnBerry Pi system.

## Emergency Stop Interface
- Trigger: POST /api/v2/control/emergency
- Clear: POST /api/v2/control/emergency_clear { confirmation: true }
- Latency: E-stop activation must propagate to all motion controllers in <100 ms.
- Behavior:
  - Immediately stop drive and blade motors
  - Latch emergency_stop_active until cleared with explicit operator confirmation
  - Blade remains OFF after clear; interlocks must be revalidated before motion

## Interlock Validation Interface
- Interlocks: emergency_stop, tilt_detected, low_battery, geofence_violation, obstacle_detected, watchdog_timeout
- Validator module: backend/src/safety/interlock_validator.py
- Behavior:
  - Any active interlock blocks motor and blade commands
  - Interlocks require explicit clear once conditions are safe

## Watchdog Heartbeat Protocol
- Watchdog monitors control heartbeat and platform subsystems
- On heartbeat timeout: trigger emergency stop
- Configurable timeout (SafetyLimits.watchdog_timeout_ms) with constitutional minimums

## Recovery Workflow
- Clear E-stop requires operator confirmation (UI button or CLI `lawnberry safety clear-estop --force`)
- System must return to a safe default state (blade OFF) and revalidate interlocks before accepting commands

## Platform Compliance
- SIM_MODE must provide equivalent safety semantics without accessing GPIO
- Hardware-specific actions (GPIO, serial) must be guarded and fail-safe
