# LawnBerry Pi v2 🌱🤖

**Professional Autonomous Mowing System with 1980s Cyberpunk Interface**

Target platform: Raspberry Pi OS Lite Bookworm (64-bit) on Raspberry Pi 5 (16 GB) with Python 3.11.x, with graceful degradation validated on Raspberry Pi 4B (4–8 GB).

Returning to the project after time away? Start with `docs/developer-toolkit.md` for the maintainer-first architecture map, workflow guide, and immediate focus areas.

## 🚀 Quick Start

The LawnBerry Pi v2 system is now fully operational with hardware integration and real-time telemetry streaming.

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

# Backend (Terminal 1, on-device / hardware mode)
cd backend
SIM_MODE=0 python -m uvicorn src.main:app --host 0.0.0.0 --port 8081 --reload

# Frontend (Terminal 2)  
cd frontend
npm run dev -- --host 0.0.0.0 --port 3000
```

These are the local development defaults. On-device/systemd deployments use the same backend/frontend ports (`8081` and `3000`), while Playwright preview-based E2E runs use port `4173`.

Important: if you do **not** set `SIM_MODE`, the backend currently behaves like hardware mode and will attempt device
initialization. On a non-Pi machine this usually degrades gracefully, but it is noisier than running pure simulation.

### System Status
- ✅ **Hardware Integration**: Real sensor data streaming from Pi hardware
- ✅ **Professional UI**: 1980s cyberpunk design with Orbitron fonts and neon effects
- ✅ **Real-time Telemetry**: Live GPS, battery, IMU data at 5Hz via WebSocket
- ✅ **Production Ready**: Complete system validated on Raspberry Pi hardware

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
- Contributing Guide: `CONTRIBUTING.md` (includes TODO policy)
- Feature Specifications: `spec/hardware.yaml` (canonical hardware baseline), `spec/agent_rules.md`
- System Architecture: See `docs/code_structure_overview.md` for subsystem and callable-interface orientation
- Testing: `tests/` (unit, integration, contract tests)

### Access Points
- **Frontend**: http://192.168.50.215:3000 (or your Pi's IP)
- **Backend API**: http://localhost:8081
- **API Docs**: http://localhost:8081/docs (Swagger UI)
- **WebSocket**: ws://localhost:8081/api/v2/ws/telemetry

The system provides a complete real-time dashboard for autonomous lawn mowing operations with professional-grade user experience and full hardware integration.