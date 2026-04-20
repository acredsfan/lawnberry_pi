# lawnberry Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-20

## Active Technologies
- Python 3.11 (backend), TypeScript + Vue 3 (frontend) + FastAPI, Uvicorn, Pydantic v2, websockets, Vue 3 + Vite, Pinia, Leaflet/Google Maps SDK (001-integrate-hardware-and)
- Python 3.11.x (backend), TypeScript (frontend - existing) + FastAPI, Uvicorn, Pydantic v2, asyncio, python-periphery, lgpio, pyserial, websockets, Vue 3 (existing), Vite, Pinia (002-complete-engineering-plan)
- SQLite for configuration/state, JSON logs with rotation, file-based cache for weather data (002-complete-engineering-plan)

## Project Structure
```
backend/
frontend/
tests/
```

## Commands

```bash
# Run tests (non-hardware only — full suite hangs on hardware I/O)
cd /home/pi/lawnberry && python -m pytest tests/ -x -q -m "not hardware"

# Run a single test file
python -m pytest tests/test_navigation_service.py -x -q

# Lint
ruff check backend/src

# Restart backend
sudo systemctl restart lawnberry-backend

# Tail backend logs
journalctl -u lawnberry-backend -f --no-pager
# OR
tail -f /home/pi/lawnberry/backend/backend.log
```

⚠️ **Test suite hang warning:** `python -m pytest tests/` without `-m "not hardware"` will hang
indefinitely because some tests block on hardware I/O (serial ports, I2C). Always filter or
set a per-test timeout. `pytest-timeout` is NOT installed; add `--timeout=N` only if it is.

## Code Style
Python 3.11 (backend), TypeScript + Vue 3 (frontend): Follow standard conventions

## Recent Changes
- 002-complete-engineering-plan: Added Python 3.11.x (backend), TypeScript (frontend - existing) + FastAPI, Uvicorn, Pydantic v2, asyncio, python-periphery, lgpio, pyserial, websockets, Vue 3 (existing), Vite, Pinia
- 001-integrate-hardware-and: Added Python 3.11 (backend), TypeScript + Vue 3 (frontend) + FastAPI, Uvicorn, Pydantic v2, websockets, Vue 3 + Vite, Pinia, Leaflet/Google Maps SDK

## Workflow Guidance

**New to this project or returning after time away?**
Read these in order:
1. `.github/WORKFLOW_GUIDE.md` — **START HERE** — Maps every task type to the right agent/mode/skill
2. `docs/developer-toolkit.md` — Architecture, key files, subsystems, runtime ports
3. `.github/agents/ORCHESTRATOR-QUICK-START.md` — How to use intelligent task routing

**Debugging a specific issue?**
→ Use `/agent` and select **LawnBerry Workflow Orchestrator**
→ It auto-detects the problem type and routes to the right specialist

**Writing new code or tests?**
→ Use `shift+tab` to switch Chat Modes (tests.software, webui.feature, sensors.hardware, etc.)

## Reasoning for problem solving approach
- Think like a developer when solving this issue, when you think you know how to attack the problem, think it through before deploying and make targeted/precise edits to avoid unintentionally causing issues with another part of the program.
- If you are unsure about something, ask for clarification or more information.

## **IMPORTANT** Running CLI Commands
- Always ensure you use timeouts and error handling when running CLI commands from within the codebase to avoid hanging processes or unhandled exceptions.

## When to Ask for Help
- If you encounter unfamiliar technologies or libraries.
- If you are unsure about the architecture or design decisions.

## What to do after completing a task
- Review your code for adherence to style guidelines and best practices.
- Write or update unit tests to cover new functionality or changes.
- Document any new features or changes in the relevant documentation files.
- Restart the backend and frontend servers to ensure all changes are applied.
- Run the full test suite to verify that no existing functionality is broken.

## Tools Available for Agent Use
- Sequential Thinking MCP server
- Server-memory MCP server
- Python 3.11 environment
- TypeScript + Vue 3 environment
- FastAPI framework
- Uvicorn server
- Pydantic v2 for data validation
- Websockets library
- Vue 3 framework
- Vite build tool
- Pinia state management
- Leaflet and Google Maps SDKs for mapping functionalities

## Hardware currently installed
- Raspberry Pi 5 16GB
- Custom RoboHAT MM1
- Cytron MDDRC10 Motor Driver connected to RoboHAT MM1
- Sparkfun ZED-F9P RTK GPS Module connected via USB
- BME280 Environmental Sensor
- 2x VL53L0X Time-of-Flight Distance Sensors
- 2x 12V Worm Gear DC Motors
- 2x Hall Effect Sensors connected to RoboHAT MM1 Encoder Inputs
- BNO085 IMU connected via UART4
- IBT-4 Motor Driver connected to 997 DC Motor for Blade Control
- 12V 30Ah LiFePO4 Battery
- Google Coral USB Accelerator
- Victron SmartSolar MPPT 75/15 Solar Charger connected via victron-ble over BLE
- INA3221 Power Monitor connected via I2C
- RP2040-Zero is the microcontroller on the RoboHAT MM1

## Hardware connections
- GPS Module connected via USB
- BME280 Environmental Sensor connected via I2C
- VL53L0X Distance Sensors connected via I2C
- DC Motors connected to RoboHAT MM1 via the MDDRC10 Motor Driver - RoboHAT sends serial commands to MDDRC10 to control motors
- Hall Effect Sensors connected to RoboHAT MM1 Encoder Inputs
- BNO085 IMU connected via UART4
- IBT-4 Motor Driver connected to GPIO 24 and 25 for PWM control of the Blade Motor
- Google Coral USB Accelerator connected via USB
- RoboHAT MM1 connected to Raspberry Pi via GPIO header and USB to RP2040-Zero

## Additional Notes
- Ensure to follow best practices for both backend and frontend development.
- Regularly update dependencies to maintain security and performance.

## Serial Port Assignments (FIXED — do not auto-detect)

| Device | Port | Notes |
|--------|------|-------|
| RoboHAT RP2040 (USB CDC) | `/dev/robohat` → `/dev/ttyACM0` | Primary motor controller path |
| BNO085 IMU | `/dev/ttyAMA4` | **NEVER probe/scan this port — corrupts IMU state** |
| ZED-F9P GPS | `/dev/lawnberry-gps` | USB, RTK |
| Hardware UART to RP2040 | `/dev/serial0` (ttyAMA0) | Firmware not yet deployed; do NOT confuse with IMU |

**Do NOT auto-detect or probe `/dev/ttyAMA4`** — opening it without the correct baud/protocol
corrupts the BNO085 sensor state and requires a power cycle.

## BNO085 IMU — Critical Facts

- Driver uses **Game Rotation Vector** (`game_quaternion`): gyro + accelerometer fusion only.
  **There is NO magnetometer in the heading output.** Motor EMI does NOT affect it.
- Convention: **ZYX aerospace / right-hand z-up** — positive yaw = CCW rotation.
  This is **opposite** to compass convention (CW = increasing bearing).
- The correct heading formula is: `adjusted_yaw = (-raw_yaw + imu_yaw_offset_degrees) % 360.0`
  (note the **negation** of raw_yaw — without it, CW turns decrease heading and navigation diverges)
- `imu_yaw_offset_degrees: 0.0` in `config/hardware.yaml` — the IMU is forward-facing and does
  not require mounting offset. The formula `(-raw_yaw + offset) % 360` alone handles the ZYX→compass
  convention conversion. **Do not change this value without understanding the heading oscillation root
  cause.** A 180° offset would invert all directions and cause navigation convergence failure.

## Motor / Navigation Direction Conventions

- **Motor Wiring Note**: Physical motors are wired with left/right swapped at MDDRC10 level.
  **Two-part compensation exists:**
  1. Navigation service swaps left_speed/right_speed assignments in both blended and tank-turn modes (lines 520-560)
  2. RoboHAT arcade mix inverts the sign: `angular = -(left_norm - right_norm) / 2.0` (line 835 of robohat_service.py)
  
  **CRITICAL**: These two pieces work together. Removing or changing only ONE breaks the system:
  - If you remove arcade inversion but keep navigation swap → joystick turns backward
  - If you remove navigation swap but keep arcade inversion → navigation turns backward
  - Both must be kept in sync. Changes to motor call arguments require changes to both
  
- `steer_us > 1500µs` → right turn (CW physically)
- `steer_us < 1500µs` → left turn (CCW physically)
- RoboHAT serial command: `pwm,<steer_us>,<throttle_us>`
- Dead zone: ~80µs around neutral (1500µs). Commands inside ±80µs are too weak to move on grass.
- When diagnosing motor issues: distinguish *what the code sends* (serial log `[USB]`) from
  *what the hardware does* (physical observation). `serial_connected: False` in software state
  does NOT mean the device is physically absent — it may mean USB error -71 (bad cable).

## Motor Control Debugging Flowchart

When the mower exhibits incorrect motor behavior (turns backward, asymmetric wheels, wiggling), follow this systematic approach:

**1. Test Joystick Control First (Isolates Code Path)**
```bash
# Right turn (should have left_motor > right_motor)
curl -X POST http://localhost:8081/api/v2/control/drive \
  -H "Content-Type: application/json" \
  -d '{"throttle": 0.0, "turn": 0.5}'

# Response should show: {"left_motor_speed":0.5,"right_motor_speed":-0.5,"safety_status":"OK"}
# If backward: left < right, then problem is in arcade mix or robohat

# Left turn (should have right_motor > left_motor)
curl -X POST http://localhost:8081/api/v2/control/drive \
  -H "Content-Type: application/json" \
  -d '{"throttle": 0.0, "turn": -0.5}'
```

**2. Test Motor Status (Hardware Connection)**
```bash
curl -s http://localhost:8081/api/v2/hardware/robohat | grep -o '"motor_status":"[^"]*"'
# Should show "idle" or current PWM values, NOT an error
```

**3. Check Navigation Logs During Mission (Isolated Code Path)**
```bash
# Run mission and watch these logs:
tail -f /home/pi/lawnberry/logs/lawnberry.log | grep "NAV_CONTROL"
# Look for: "target_bearing=XXX current_heading=YYY error=±Z"
# If error direction is wrong (turning away from target), navigation path has issue
```

**4. Diagnose the Root Cause**
- **Joystick inverted, Navigation correct**: Problem in arcade mix inversion (line 835 robohat_service.py) or RoboHAT
- **Navigation inverted, Joystick correct**: Problem in navigation's left/right swap (lines 520-560 navigation_service.py)
- **Both inverted**: Both layers have the wrong sign — look for recent changes that modified both simultaneously
- **Joystick correct, Mission wiggles**: Navigation swap is wrong but arcade mix is right — asymmetric compensation

**Remember**: Never change one compensation layer without verifying the other still works.

## Backend Startup Gotchas with Motor Changes

Motor control code runs during systemd service startup (navigation service initialization). Changes that cause hangs:

- **Swapping motor argument order** in `send_motor_command()` calls — may break initialization if navigation service calls motor functions during `__init__`
- **Changing function signatures** in `RoboHATService.send_motor_command()` — lifespan setup may parse or call this before full backend is ready
- **Adding new motor API endpoints** — ensure they don't require navigation service state that isn't initialized yet

**Safe Pattern for Motor Changes:**
1. Run `pytest tests/test_robohat_service.py tests/test_navigation_service.py -xvs` first
2. If tests pass, restart backend: `sudo systemctl restart lawnberry-backend && sleep 5 && curl http://localhost:8081/api/v2/status`
3. If status endpoint hangs (no response after 5s), backend is stuck in startup — check recent motor changes immediately

## Hardware Diagnostics Quick Reference

**Mower not responding to turn commands?** Use this checklist:

1. **Is the command reaching the hardware?**
   ```bash
   # Check motor status shows commands are being sent
   curl -s http://localhost:8081/api/v2/hardware/robohat | grep -o '"watchdog_latency_ms":[0-9.]*'
   # If > 1000ms or shows error, RoboHAT is not responding
   ```

2. **Is the command mathematically correct?**
   ```bash
   # Test via API and inspect the calculated speeds
   curl -s -X POST http://localhost:8081/api/v2/control/drive \
     -H "Content-Type: application/json" \
     -d '{"throttle": 0.0, "turn": 0.5}'
   # For right turn: left_motor_speed should be > right_motor_speed
   ```

3. **Is the motor physically wired correctly?**
   - Left wheel should connect to MDDRC10 "right" port
   - Right wheel should connect to MDDRC10 "left" port
   - (They are swapped intentionally at the driver level)

4. **Check RoboHAT serial connection:**
   ```bash
   ls -l /dev/robohat /dev/ttyACM0
   # Both should exist and be readable. If missing, RoboHAT USB cable may be loose
   ```

5. **Check motor logs for delivery errors:**
   ```bash
   tail -50 /home/pi/lawnberry/logs/lawnberry.log | grep -i "motor\|pwm\|robohat"
   # Look for "Failed to deliver motor command" or serial errors
   ```

**Key distinction**: If API returns correct speeds but motors don't move → hardware issue (cable, driver, or RoboHAT firmware). If API returns inverted speeds → code issue (one of the two compensation layers is wrong).

## Python Bytecode Cache

After editing any `.py` file that runs as a **systemd service** (watchdog, backend), clear the
bytecode cache or the service will keep running old code from `__pycache__`:

```bash
find /home/pi/lawnberry -name "*.pyc" -delete
find /home/pi/lawnberry -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
sudo systemctl restart lawnberry-backend
```

Alternatively, set `PYTHONDONTWRITEBYTECODE=1` in the systemd unit environment.

## Maintainer handbook usage

- Treat `docs/developer-toolkit.md` as the maintainer-facing orientation document for this repository.
- At the start of substantial maintenance, planning, roadmap, runtime-contract, hardware-scope, simulation-vs-hardware, or subsystem-maturity work, read `docs/developer-toolkit.md` and follow its guidance.
- When changes affect runtime behavior, supported hardware scope, subsystem maturity, immediate-focus priorities, the 2-week execution plan, or high-level next steps, update `docs/developer-toolkit.md` in the same pass.
- Do not treat `docs/developer-toolkit.md` as optional background reading; use it to keep implementation, prioritization, and documentation aligned for returning maintainers.

## Automated code structure documentation sync

To keep our developer docs accurate, the Copilot Agent must automatically update `docs/code_structure_overview.md` whenever structural code changes occur (new/removed files, added/removed functions, or signature changes) in these areas:

- `backend/src/**` (Python services, nav algorithms, CLI, tools)
- `frontend/src/**` (TypeScript/Vue services, composables, utils)
- `scripts/**` and `.specify/scripts/**` (Ops tooling)

Agent workflow requirements:

1) Detect change triggers
	- On any PR or commit that touches the paths above, or when explicitly asked to “regenerate code structure overview,” run the scan.

2) Scan workspace for callable interfaces
	- Python: list module-level functions and public class methods (exclude private names starting with `_` unless necessary for clarity). Capture argument names and defaults from signatures.
	- TypeScript: list exported functions and exported const arrow functions; include argument names and basic types when present.
	- Shell scripts: list defined shell functions when they exist; otherwise mark as CLI entrypoint.

3) Infer subsystem category
	- Use directory and filename hints (e.g., `services/` → backend services; `nav/` → Navigation; `composables/` or `services/` in frontend → Frontend; `scripts/` → Ops/DevOps).

4) Update the document in place
	- Rewrite sections and tables in `docs/code_structure_overview.md` to reflect the current state. Preserve section ordering and headings; replace table rows as needed.
	- Ensure each entry contains: relative path, 1–2 sentence purpose, subsystem category, and callable interfaces with argument signatures.

5) Validate
	- Re-read changed files to confirm the listed signatures match the source.
	- Keep lines <= 120 chars where practical for readability.

6) Commit
	- Include the doc update in the same PR as the code change, or push as a follow-up commit titled: `docs: update code_structure_overview.md (auto)`. 

Template cues the Agent should preserve:
- Group by subsystem with Markdown tables per group.
- Prefer public APIs; mark clearly when listing internal helpers for context.

This directive is persistent. Any code change affecting callable interfaces must be accompanied by an updated `docs/code_structure_overview.md` generated by the Agent.
