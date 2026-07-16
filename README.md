# LawnBerry Pi v2 🌱🤖

**Professional Autonomous Mowing System with 1980s Cyberpunk Interface**

Target platform: Raspberry Pi OS Lite Bookworm (64-bit) on Raspberry Pi 5 (16 GB) with Python 3.11.x, with graceful degradation validated on Raspberry Pi 4B (4–8 GB).

Returning to the project after time away? Start with `docs/developer-toolkit.md` for the maintainer-first architecture map, workflow guide, and immediate focus areas.

## 🚀 Quick Start

The LawnBerry Pi v2 system is operational for development, simulation, and supervised on-device validation with hardware integration and real-time telemetry streaming. It is not considered unattended-autonomous or production-ready until current physical qualification evidence passes for the deployed commit, hardware configuration, safety limits, runtime identity, and RoboHAT firmware.

### System Architecture
- **Backend**: FastAPI with hardware sensor integration (`backend/`)
- **Frontend**: Vue.js 3 with professional 1980s cyberpunk theme (`frontend/`)
- **Real-time**: WebSocket streaming at 5Hz for live telemetry
- **Hardware**: Raspberry Pi with I2C sensors (GPS, IMU, battery monitoring)

### Getting Started
```bash
# Backend (Terminal 1, laptop / simulation mode)
cd backend
SIM_MODE=1 python -m uvicorn src.main:app --host 0.0.0.0 --port 8081 --reload

# Camera owner (Terminal 1, manual on-device / hardware mode)
cd /home/pi/lawnberry
SIM_MODE=0 LAWNBERRY_CAMERA_SOCKET=/tmp/lawnberry-camera.sock \
  python -m backend.src.services.camera_stream_service

# Backend (Terminal 2, manual on-device / hardware mode)
cd /home/pi/lawnberry
SIM_MODE=0 LAWNBERRY_CAMERA_SOCKET=/tmp/lawnberry-camera.sock \
  python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081

# Frontend (next terminal)
cd frontend
npm run dev -- --host 0.0.0.0 --port 3000
```

These are the local development defaults. On-device/systemd deployments use the same backend/frontend ports (`8081` and `3000`), while Playwright preview-based E2E runs use port `4173`.
For normal on-device operation, prefer
`sudo systemctl start lawnberry-camera.service lawnberry-backend.service`. Never run the manual camera owner while the
camera service is active; the live device must have exactly one owner.

Important: if you do **not** set `SIM_MODE`, the backend currently behaves like hardware mode and will attempt device
initialization. On a non-Pi machine this usually degrades gracefully, but it is noisier than running pure simulation.

### Hardware Configuration

- `spec/hardware.yaml` is the tracked supported-hardware specification.
- `config/hardware.pi5.example.yaml` and `config/hardware.pi4.example.yaml` are complete tracked templates.
- `config/hardware.yaml` is the single ignored runtime hardware file and may contain node-specific secrets.
- Fresh clones can run in `SIM_MODE=1` without creating `config/hardware.yaml`.

Create or validate the runtime file on a Pi:

```bash
uv run python scripts/manage_hardware_config.py ensure --profile auto
uv run python scripts/manage_hardware_config.py ensure --profile pi5
uv run python scripts/manage_hardware_config.py validate
uv run python scripts/manage_hardware_config.py migrate-legacy --profile auto
```

### System Status
- ✅ **Hardware Integration**: Real sensor data streaming from Pi hardware
- ✅ **Professional UI**: 1980s cyberpunk design with Orbitron fonts and neon effects
- ✅ **Real-time Telemetry**: Live GPS, battery, IMU data at 5Hz via WebSocket
- ⚠️ **Two-Phase Autonomy Qualification Required**: Schema-v2 separates
  `blade_off_diagnostic`, `supervised_blade_test_prerequisite`, and `full_blade_autonomy`.
  Ordinary blade commands, blade-capable missions, and schedules require the final level with current,
  artifact-backed `supervised_blade_enabled` evidence. Simulation, replay, mocks, and a successful permit API
  call do not count as physical evidence.
- 🔒 **Supervised Blade Test Disabled by Default**: Permit issuance ships with `supervised_test_enabled: false`
  and zero TTL, duration, and speed bounds. Aaron must approve mower-specific bounds and the physical test plan
  before those values change or any blade-enabled test is attempted.

### Mission Planner
- ✅ Interactive Mission Planner UI is available under the "Mission Planner" navigation item.
- Click on the map to add waypoints, reorder them in the sidebar, set blade and speed per waypoint, then Create and Start the mission.
- Mission status and completion percentage are shown live; you can Pause, Resume, or Abort at any time.

### Documentation
- Developer Toolkit: `docs/developer-toolkit.md` — best starting point for returning maintainers and developers
- Copilot Customizations Guide: `docs/copilot-customizations-guide.md` — prompts, skills, agents, chat modes, hooks, and how to use them
- Simulation vs Hardware Modes: `docs/simulation-vs-hardware-modes.md` — explains `SIM_MODE=1`, `SIM_MODE=0`, and what unset `SIM_MODE` actually does
- Setup Guide: `docs/installation-setup-guide.md`
- GPS RTK Configuration: `docs/gps-ntrip-setup.md` (centimeter-level accuracy)
- Hardware Integration: `docs/hardware-integration.md`
- Operations Guide: `docs/OPERATIONS.md`
- Two-phase qualification operations, emergency recovery, migration, and Aaron's physical checklist:
  `docs/OPERATIONS.md#two-phase-autonomy-qualification`
- Contributing Guide: `CONTRIBUTING.md` (includes TODO policy)
- Feature Specifications: `spec/hardware.yaml` (canonical hardware baseline), `spec/agent_rules.md`
- System Architecture: See `docs/code_structure_overview.md` for subsystem and callable-interface orientation
- Testing: `tests/` (unit, integration, contract tests)

### Access Points
- **Frontend**: http://192.168.50.215:3000 (or your Pi's IP)
- **Backend API**: http://localhost:8081
- **API Docs**: http://localhost:8081/docs (Swagger UI)
- **WebSocket**: ws://localhost:8081/api/v2/ws/telemetry

The system provides a complete real-time dashboard for mower operations with professional-grade user experience and hardware integration. Autonomous mowing claims require retained, current qualification evidence and Aaron's approval for each hazardous test stage.
