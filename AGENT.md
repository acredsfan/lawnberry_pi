# LawnBerryPi Developer Onboarding Guide

This document is the single place a new engineer should read before touching the code. It explains the project goals, architecture, local setup, and the day-to-day commands you will use while developing LawnBerryPi.

---

## 1. What You Are Building

LawnBerryPi is an autonomous lawn mower platform that runs on Raspberry Pi hardware. The system has two major halves:

1. **Python backend** (in `src/`): manages hardware, navigation, safety, power, scheduling, and exposes a FastAPI web API plus WebSocket streams.
2. **React web UI** (in `web-ui/`): a Material-UI based dashboard and control surface that talks to the backend over REST + WebSockets.

It targets **Raspberry Pi OS Bookworm (64-bit)**, Python 3.11, and Node.js 18+. Most modules are designed to run headlessly on the Pi, but you can also develop from a workstation and connect to the Pi for hardware-in-the-loop testing.

---

## 2. Repository Layout (read this once)

```
├── src/                      # Python backend
│   ├── hardware/             # Plugin system for sensors/actuators
│   ├── navigation/           # Path planning & map logic
│   ├── power_management/     # Battery + charging
│   ├── safety/               # Emergency stop, tilt, obstacle protection
│   ├── web_api/              # FastAPI + WebSocket entrypoints
│   └── ...                   # Other domain modules (vision, weather, etc.)
│
├── config/                   # YAML configuration (hardware, system params)
├── scripts/                  # Install, update, and maintenance utilities
├── tests/                    # Pytest suite with unit/integration markers
│
├── web-ui/                   # React/Vite frontend (TypeScript)
│   ├── src/components/       # Reusable UI/Map widgets
│   ├── src/pages/            # Dashboard, Maps, Settings, etc.
│   └── src/store/            # Redux Toolkit slices
│
├── docs/                     # User + developer documentation
└── README.md                 # High-level product overview
```

---

## 3. Prerequisites & Toolchain

### Hardware
- Raspberry Pi 4 or 5 (Bookworm 64-bit) with RoboHAT RP2040, RTK GPS, sensors, motors
- Optional: development PC running Linux/macOS/WSL for editing and UI work

### Software
- **Python 3.11** (managed via `pyenv` or system Python on Pi)
- **Node.js 18+** (for the web UI)
- **Poetry** *or* pip/venv (project currently uses `pip` with requirements files)
- Redis + SQLite are used by the backend; installer scripts provision them automatically on the Pi

### External keys
- Google Maps API key for the web UI (`REACT_APP_GOOGLE_MAPS_API_KEY`)
- OpenWeather API key (configured via backend environment variables)

---

## 4. First-Time Setup (Backend)

You can let the automation handle everything on a Pi, or bootstrap manually on your workstation.

### Option A – Pi installer (recommended for hardware work)
```bash
git clone https://github.com/acredsfan/lawnberry_pi.git lawnberry
cd lawnberry
bash scripts/install_lawnberry.sh
```
The installer detects hardware, installs Python dependencies, creates services, and runs smoke tests. Run `python3 scripts/first_run_wizard.py` afterwards for guided configuration.

### Option B – Manual dev environment
```bash
# from repo root
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```
Set environment variables (examples in `scripts/setup_environment.py`). Key variables:
- `LAWNERRY_ENV` (`development|production`)
- `OPENWEATHER_API_KEY`
- `MQTT_BROKER_URL` (if applicable)

Configuration lives in `config/`. Copy and customize YAML files as needed.

### Running the backend locally
```bash
# Activate virtualenv first
uvicorn src.web_api.main:app --host 0.0.0.0 --port 8000 --reload
```
WebSocket server is part of FastAPI; default WS endpoint is `ws://<host>:8000/api/ws`.

---

## 5. Web UI Setup

```bash
cd web-ui
npm install
cp .env.example .env  # create and edit values
# Ensure .env includes:
# REACT_APP_GOOGLE_MAPS_API_KEY=...
# VITE_API_URL=http://localhost:8000
# VITE_WS_URL=ws://localhost:8000/api/ws
npm run dev            # starts Vite on http://localhost:3000
```
For production:
```bash
npm run build
npm run preview        # locally serve the optimized bundle
```
When deploying on the Pi, serve the `web-ui/dist/` folder via nginx or the existing systemd service (`web-ui/index.html` entry point).

---

## 6. Everyday Commands (Backend)

Testing and quality gates:
```bash
python -m pytest tests/ --cov=src --cov-report=html -v
python -m pytest -m "unit" tests/
python -m pytest tests/test_hardware_interface.py::TestI2CManager -v

black --line-length=100 src/ tests/
isort --profile=black --line-length=100 src/ tests/
flake8 --max-line-length=100 src/ tests/
mypy src/ --ignore-missing-imports
bandit -r src/ --severity-level medium
pre-commit run --all-files
```
Security & hygiene:
```bash
safety check --json
vulture --min-confidence=80 src/
```
For Redis-backed queues or MQTT integrations, use the simulators in `tests/fixtures/` or run `docker-compose` (see `docs/development/docker.md` if present).

---

## 7. Key Services & How They Talk

- **HardwareInterface (`src/system_integration/service_orchestrator.py`)**: orchestrates hardware plugins async.
- **State Machine (`src/system_integration/state_machine.py`)**: central mower workflow (idle → mowing → docked).
- **Navigation → Maps**: Map/GPS data exposed through the `/maps` API; frontend fetches boundaries, positions, and renders via Leaflet/Google Maps components.
- **WebSockets**: Single multiplexed stream delivering mower status, sensor packets, navigation updates, notifications. Check `src/web_api/websocket` for event types.
- **Configuration**: YAML + environment. Use `ConfigManager` utilities in `src/configuration/` to load/validate.

Understanding these modules first will save you hours.

---

## 8. Adding or Updating Hardware Plugins

1. Implement a subclass of `HardwarePlugin` (see `src/hardware/plugin_system.py`).
2. Declare required managers (`required_managers` property) and provide `initialize`, `shutdown`, and `read_data`/`control` methods.
3. Register the plugin in `config/hardware.yaml` under the `plugins` list.
4. Write unit tests with mocks in `tests/hardware/` and, if necessary, integration tests behind the `hardware` pytest marker.
5. Update documentation in `docs/hardware-overview.md`.

---

## 9. Frontend Notes

- Global state uses Redux Toolkit; slices are in `web-ui/src/store/slices/`.
- Map-related logic lives in `web-ui/src/pages/Maps.tsx` plus components in `src/components/MapContainer/`.
- When adjusting layouts, update `index.css` for global themes and `Layout/` for navigation changes.
- Run `npm run lint` and `npm run test` (if configured) before commits.
- The build pipeline produces chunked assets; ensure any new dependencies are Pi-friendly.

---

## 10. Deployment & Services

Systemd services (created by the installer) typically include:
- `lawnberry-backend.service` – starts the FastAPI app with Uvicorn
- `lawnberry-ui.service` or nginx site – serves the built web UI
- `lawnberry-worker.service` – optional background jobs (sensor polling, navigation loops)

Check `scripts/` for service definitions and use `sudo systemctl status lawnberry-backend` while debugging on the Pi.

For OTA-style updates:
```bash
bash scripts/update_lawnberry.sh        # preserves config, pulls latest
```
To completely remove:
```bash
bash scripts/uninstall_lawnberry.sh
```

---

## 11. Debugging Tips

- Use `scripts/hardware_detection.py` to verify sensors before running the full stack.
- Web UI stuck? Clear `web-ui/dist` and rebuild, then hard refresh (Ctrl+Shift+R).
- If the backend appears unresponsive, tail logs: `journalctl -u lawnberry-backend -f` or run the app in foreground.
- Enable mock mode (frontend) by setting `VITE_USE_MOCKS=true`; backend has mock data helpers in `src/mock_data/`.
- Watch for websocket disconnects; the frontend reconnection logic logs to the browser console.

---

## 12. Documentation You Should Know Exists

- `docs/installation-guide.md` – full Pi provisioning walkthrough
- `docs/first-time-setup.md` – calibrating boundaries, safety checks
- `docs/user-manual.md` – handy for understanding user-visible features
- `docs/troubleshooting-guide.md` – common runtime issues
- `scripts/README.md` – details of automation scripts

Whenever you add features, update the relevant doc so field operators are never surprised.

---

## 13. Working Agreements & Style

- Python formatting: **Black** with 100 char lines, imports with **isort** (black profile).
- Type hints: encouraged; keep mypy happy.
- Tests: include unit coverage for new logic and integration tests if hardware interaction is touched.
- Frontend: adhere to existing Material-UI patterns; keep components composable.
- No secrets in the repo. Use `.env`, `config/secrets.yaml`, or environment variables.
- Clean up temporary files and feature flags before opening PRs.

---

## 14. Quick Checklist For Your First PR

1. Backend virtualenv active, dependencies installed (`pip install -r requirements-dev.txt`).
2. Frontend dependencies installed (`npm install`).
3. Run backend unit tests + linters.
4. Run `npm run build` to ensure UI compiles.
5. Update documentation or changelog if behavior changed.
6. Smoke test combined stack locally or on the Pi (start backend, run `npm run dev`, verify key flows).

If you get stuck, search the repo, skim `docs/`, or ask the team—this guide should help orient you quickly.

Happy mowing! 🌱
