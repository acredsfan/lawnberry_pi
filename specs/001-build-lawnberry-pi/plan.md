# Implementation Plan: LawnBerry Pi v2

**Branch**: `001-build-lawnberry-pi` | **Date**: 2025-09-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/home/pi/lawnberry_pi/specs/001-build-lawnberry-pi/spec.md`

## Summary
Primary requirement: Build an autonomous LawnBerry mower with real-time monitoring, safety interlocks, and retro web UI while honoring fixed hardware mappings. Technical approach: FastAPI backend with WebSocket hub, tiered AI acceleration runners, Picamera2→GStreamer video, SQLite persistence, and systemd-managed services on Raspberry Pi OS Bookworm.

## Technical Context
**Language/Version**: Python 3.11.x (constitutional requirement)  
**Primary Dependencies**: FastAPI, websockets, structlog, pydantic, Picamera2, python-periphery, sqlite-utils, React+Vite  
**Modules Covered**: `rtk_gps_f9p` (USB) + `ntrip_client`, `gps_neo8m_alt` (UART), `imu_bno085` (UART4), `env_bme280` (I2C 0x76), `tof_l` (0x29) & `tof_r` (0x30), `oled_ssd1306` (0x3C), `power_ina3221` (0x40; Ch1 battery, Ch2 unused, Ch3 solar), `blade_control_ibt4` (GPIO24/25 tilt+e-stop), `motor_ctrl_mddrc10_robohat` (preferred) with hall encoders, `motor_ctrl_l298n_alt`, `camera_stream_picam2_gst`, AI runners (`coral_runner` in isolated `venv-coral`, `hailo_runner`, `cpu_tflite_runner`), `websocket_hub`, FastAPI backend, retro web UI.  
**WebUI Routes**: `/dashboard`, `/map-setup`, `/manual`, `/mow-plan`, `/ai-train`, `/settings`, `/docs` with shared layout, low-latency camera embed (`/video.mjpeg`), telemetry graphs, joystick/gamepad support, map drawing, AI gallery, and documentation portal.  
**Branding Assets**: Web UI MUST incorporate `LawnBerryPi_logo.png`, `LawnBerryPi_icon2.png`, and the robot pin icon (`LawnBerryPi_Pin.png` → published as `frontend/public/assets/robot-pin.png`) while aligning color tokens with the 80s techno/retro palette across layout, favicon, splash screens, and manifest metadata.  
**API Contracts**: REST endpoints under `/api` for health, telemetry snapshot, map config CRUD, job lifecycle, weather (BME280 + OpenWeatherMap), manual drive/blade controls, E-Stop, AI dataset management, settings (GET/POST), video URL discovery, and test execution.  
**WebSocket Topics**: `/ws` broadcasting `telemetry` (5–10 Hz), `events`, `map`, `ai`, and `logs` channels with structured JSON payloads and rate limiting.  
**Telemetry Schema**: Snapshot includes mode, E-Stop, power (battery/solar), GPS fix (including RTK), IMU tilt/heading, environment, motors, blade RPM, Wi-Fi RSSI, and job progress metrics (progress %, ETA, area m²).  
**Persistence**: SQLite tables for configuration (`config`, `settings`), geospatial data (`geo` storing boundary/no-go/points GeoJSON), job history (`jobs`, `runs`), telemetry rollups, AI images with tags, and UI branding metadata.  
**Simulation**: `SIM_MODE=1` enables simulated drivers for GPS (both configs), IMU, BME280, ToF, blade, motor (both drive configs), power, and synthetic telemetry/event feeds for full end-to-end testing.  
**Networking**: Wi-Fi primary runtime transport; Ethernet bench-only.  
**Storage**: SQLite for telemetry, faults, and configuration; filesystem for logs/video.  
**Testing**: pytest-asyncio, simulation-backed integration tests, contract tests for WebSocket/REST, hardware abstraction unit tests.  
**Performance Goals**: Telemetry <100 ms, emergency stop <10 ms, Picamera2 stream 720p@15 fps, AI inference Coral <50 ms / Hailo <100 ms / CPU TFLite <200 ms.  
**Constraints**: ARM64 only, single HAT stack (RoboHAT OR Hailo), Coral USB isolated environment, ban `pycoral`/`edgetpu` in main env, systemd services, documentation-as-contract.  
**Scale/Scope**: Single mower unit with modular services, full docs/tests/install scripts/migration note.

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- ✅ **Platform Exclusivity**: Python 3.11, RPi OS Bookworm (ARM64), Pi 5/4B only
- ✅ **AI Acceleration Hierarchy**: coral_runner (isolated venv), hailo_runner, cpu_tflite_runner fallback
- ✅ **Code Quality Gates**: uv lock, ruff/black/mypy, pytest-asyncio, src/ layout
- ✅ **Documentation-as-Contract**: Will update /docs and /spec, load hardware.yaml/agent_rules.md
- ✅ **Runtime Standards**: systemd units, .env via dotenv, Picamera2, periphery+lgpio, pyserial
- ✅ **Hardware Compliance**: Support BNO085 (UART4), VL53L0X (0x29/0x30), BME280 (0x76), SSD1306 (0x3C), INA3221 (0x40 fixed channels), ZED-F9P USB RTK (preferred) OR Neo-8M UART (alt), RoboHAT→MDDRC10 drive (preferred) OR L298N fallback, IBT-4 blade driver, Wi-Fi-first networking
- ✅ **Test-Driven Development**: TDD with contract/integration/unit tests, hardware interface tests

## Project Structure

### Documentation (this feature)
```
specs/001-build-lawnberry-pi/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
# Option 2: Web application (backend + frontend detected)
src/lawnberry/
├── models/              # Pydantic data models
├── services/            # Business logic services
├── api/                 # FastAPI endpoints
├── core/               # WebSocket hub, config
└── runners/            # AI acceleration runners

tests/
├── contract/           # API contract tests
├── integration/        # Service integration tests
└── unit/              # Unit tests

frontend/
├── src/
│   ├── components/     # React components
│   ├── pages/         # Main UI pages
│   └── services/      # WebSocket/API clients
└── tests/

systemd/               # Service definitions
scripts/               # Installation and setup
```

**Structure Decision**: Option 2 (Web application) - FastAPI backend + React frontend detected

## Phase 0: Outline & Research
No NEEDS CLARIFICATION items detected in Technical Context. All technology choices specified by user in arguments.

**Research Tasks**:
1. FastAPI + WebSocket patterns for telemetry/control hub with Wi-Fi-first networking
2. AI acceleration hierarchy integrations: isolated Coral USB workflows, Hailo SDK, CPU TFLite fallbacks
3. Dual GPS driver architecture (USB ZED-F9P with NTRIP vs UART Neo-8M) and runtime selection strategy
4. Motor controller abstraction covering RoboHAT→Cytron MDDRC10 (preferred) and L298N alternative with hall encoder feedback
5. Sensor interface stack for BNO085 (UART4), VL53L0X pair, BME280, SSD1306, INA3221 fixed channel mapping
6. Retro 80s web UI patterns with Picamera2→GStreamer overlays and simulation visualisation hooks
7. Systemd orchestration & install scripts honoring SIM_MODE toggles and coral venv isolation
8. Branding integration plan covering logo/icon placement, favicon generation, and color token derivation from `LawnBerryPi_logo.png` / `LawnBerryPi_icon2.png`
9. WebSocket topic architecture and rate limiting for telemetry/events/map/ai/log streams
10. REST API schema design for map config, job lifecycle, AI dataset export, and manual control commands (guarding safety interlocks)
11. Map tooling research: Google Maps vs Leaflet fallback, polygon validation, and custom pin asset pipeline (`LawnBerryPi_Pin.png` → web asset)
12. Web Gamepad API + keyboard control handling with safety constraints for manual control UI
13. AI image collection gallery management (tagging, export to COCO/YOLO, lightweight training triggers) on constrained hardware

**Research.md Generation**: Technology decisions, integration patterns, and implementation approaches.

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

**Entity Extraction**: Derive data-model fields capturing dual GPS modes, drive controller choice, INA3221 channel invariants, UI branding metadata, telemetry snapshot schema, map geometry (boundary/no-go points), job status, AI dataset records, and settings → data-model.md
**API Contract Generation**: REST spec covering `/api/health`, `/api/telemetry`, map config CRUD, job lifecycle, weather (BME280 + OpenWeatherMap), manual drive/blade, E-Stop, AI dataset management, settings, tests; WebSocket topics for telemetry/events/map/ai/logs with message formats → /contracts/
**Contract Test Generation**: Test files asserting telemetry schema integrity across simulation and real hardware paths, map validation payloads, and AI dataset export endpoints
**Integration Scenarios**: Map user stories, module selections (GPS/drive/AI tiers), branded UI experiences (logo/icon placement, color mode toggles), and API key setup (Google Maps, OpenWeatherMap) → quickstart.md
**Agent Context Update**: Run update-agent-context.sh for copilot integration

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, .github/copilot-instructions.md

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

- **Task Generation Strategy**:
- Multi-service architecture: mower-core, camera-stream, webui honoring Wi-Fi-only runtime
- TDD approach: Contract tests → Simulation-backed integration tests → Hardware drivers & API contracts
- Module-based development: hardware interfaces (GPS variants, sensors, power, motion), AI runners, blade control, retro UI with mandated branding assets
- API & WebSocket implementation: FastAPI routes for telemetry, map config, job lifecycle, manual control, AI dataset management, settings/tests plus `/ws` topics
- Frontend build integration: Retro WebUI with telemetry, power mapping, module selectors, page-specific UX (dashboard, map setup, manual control, mow plan, AI train, settings, docs), consistent logo/icon usage, and camera stream abstraction

**Ordering Strategy**:
- Setup: Project structure, dependency locks, constitutional guards
- Tests: Contract schemas, simulation fixtures, hardware abstraction unit tests
- Core: WebSocket hub, telemetry flow, AI runner interfaces
- Modules: GPS (F9P/NTRIP vs Neo-8M alt), sensors, power monitor (fixed channels), motion + blade control options
- AI: Runner implementations with isolation + fallbacks
- Frontend: Retro WebUI with telemetry, power mapping, module selectors
- Integration: Systemd units, install scripts, SIM_MODE toggles
- Deployment: Documentation, migration tooling, hardware manifest verification

**Estimated Output**: 35-40 numbered, ordered tasks covering full system implementation

## Complexity Tracking
*No constitutional violations identified*

## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented

---
*Based on Constitution v1.2.0 - See `/home/pi/lawnberry_pi/v2/lawnberry-v2/.specify/memory/constitution.md`*
