# Tasks (Mirror) — LawnBerry Pi v2 On-Device Extensions

Note: This is a repo-local mirror to track on-device tasks while the upstream feature directory lives at `/home/pi/lawnberry/specs/004-lawnberry-pi-v2/`. Keep numbering consistent with the upstream file and add new tasks below. This file focuses on the additional on-device hardware integration and validation.

## Phase 3.8: Status Adjustments

- [x] T095 Docs drift detection CI step
      File: /home/pi/lawnberry/lawnberry-rebuild/.github/workflows/docs-drift.yml

## Phase 3.9: Hardware Integration & On-Device Validation

- [x] T101 Hardware self-test service + REST endpoint + docs + test (skipped by default)
      Files: 
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/hw_selftest.py
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest.py (GET /api/v2/system/selftest)
      - /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_hardware_selftest.py
      - /home/pi/lawnberry/lawnberry-rebuild/docs/TESTING.md (on-device section)

- [ ] T102 Wire SensorManager to real hardware behind SIM_MODE (0=hardware, 1=simulation)
      Files:
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/sensor_manager.py
      Notes:
      - Use lazy imports (`smbus2`, `pyserial`) and short, non-blocking reads
      - Provide safe fallbacks if devices are missing; log and continue
      - Add tests gated by `RUN_HW_TESTS=1`

- [ ] T103 Safety interlocks (E-Stop GPIO) service integration
      Files:
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/safety_service.py (new)
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest.py (ensure E-Stop state reflects GPIO)
      Notes:
      - Choose ARM64-friendly library (RPi.GPIO or gpiozero) and guard imports
      - Provide mock adapter for CI/tests (no hardware)

- [ ] T104 Motor controller wiring (RoboHAT/Cytron; L298N fallback)
      Files:
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/motor_service.py
      Notes:
      - Abstract driver interface; implement PWM output for controllers
      - Add RUN_HW_TESTS-gated basic spin test with safeguards (no blade)

- [ ] T105 Camera stream health check and IPC validation
      Files:
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/camera_client.py
      - /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_camera_health.py
      Notes:
      - Verify camera-stream.service responds; add timeouts and retries

- [x] T106 Health probes endpoints (liveness/readiness) and tests (Systemd)
      Files:
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest.py (GET /health/liveness, /health/readiness)
      - /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_systemd_health.py
      Notes:
      - Liveness: app loop responsive; Readiness: persistence, telemetry hub, optional hardware

- [ ] T107 Boot order validation for systemd units
      Files:
      - /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_systemd_boot_order.py
      - /home/pi/lawnberry/lawnberry-rebuild/systemd/*.service (adjust After/Wants as needed)
      Notes:
      - Ensure database before backend, sensors before backend as appropriate

- [ ] T108 Battery calibration & thresholds validation script
      Files:
      - /home/pi/lawnberry/lawnberry-rebuild/scripts/battery_calibration.py
      - /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_battery_calibration.py
      Notes:
      - Reads INA3221 samples to compute offsets; stores to config/persistence

- [ ] T109 Field telemetry validation mode
      Files:
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/telemetry_hub.py
      - /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_field_telemetry.py
      Notes:
      - When enabled, logs actual ranges and flags out-of-bounds readings

- [ ] T110 WebSocket telemetry uses SensorManager when SIM_MODE=0
      Files:
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/telemetry_hub.py
      - /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest.py (settings toggle)
      - /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_websocket_api.py (extend cadence check)
      Notes:
      - Toggle between simulated and hardware-backed telemetry seamlessly

## Dependencies
- T101 precedes T102–T110
- T102 precedes T110 (hardware telemetry)
- T106 precedes T107 (probes exposed before boot validation tests)
- Hardware-gated tests must be optional via env vars (RUN_HW_TESTS=1)
