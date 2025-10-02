# Quickstart – LawnBerry Pi v2 Hardware Integration & UI Completion

Follow this walkthrough to validate the feature end-to-end on Raspberry Pi OS Lite Bookworm. Use a Raspberry Pi 5 (16 GB) first, then repeat the abbreviated validation on a Raspberry Pi 4B (4–8 GB) for graceful degradation checks.

## 1. Environment Preparation
1. Ensure all hardware is wired per `docs/hardware-overview.md` and `docs/hardware-feature-matrix.md`.
2. Flash Raspberry Pi OS Lite Bookworm (64-bit) and apply system updates.
3. Install project dependencies:
   ```bash
   cd /home/pi/lawnberry
   make deps  # or invoke provided setup script if available
   ```
4. Activate Coral/Hailo accelerators only if installed; otherwise rely on CPU fallback.
5. Confirm RoboHAT RP2040 has `robohat-rp2040-code/code.py` flashed and connected via UART/USB.

## 2. Launch Services
1. Start backend (FastAPI) and WebSocket hub:
   ```bash
   cd backend
   uvicorn src.main:app --host 0.0.0.0 --port 8081
   ```
2. In a new terminal, start the Vue 3 frontend:
   ```bash
   cd frontend
   npm install
   npm run dev -- --host 0.0.0.0 --port 3001
   ```
3. Optional: start simulation mode (if hardware unavailable) via `SIM_MODE=1` environment variable.

## 3. Telemetry Validation
1. Open Dashboard at `http://<pi-ip>:3001` and verify live power, GPS, IMU, ToF, and camera feeds.
2. Verify the RoboHAT handshake and telemetry latency endpoints:
    ```bash
    curl -s http://<pi-ip>:8081/api/v2/hardware/robohat | jq
    curl -s -X POST http://<pi-ip>:8081/api/v2/telemetry/ping -H 'Content-Type: application/json' \
       -d '{"component_id":"power","sample_count":10}' | jq
    ```
3. Run automated telemetry check:
   ```bash
   cd /home/pi/lawnberry
   pytest tests/contract/test_telemetry.py -k "live"
   ```
4. Execute performance guardrail script:
   ```bash
   python scripts/test_performance_degradation.py --target 0.25
   ```
5. Capture exported telemetry snapshot and store in verification artifacts directory.

## 4. Map Setup Workflow
1. Navigate to **Map Setup** page.
2. Place markers for Home, AM Sun, PM Sun; draw boundary and exclusion polygons.
3. Save configuration and verify success toast plus backend acknowledgment in logs.
4. Check SQLite `map_zones` entries:
   ```bash
   sqlite3 /home/pi/lawnberry/data/lawnberry.db "SELECT id, zone_type FROM map_zones;"
   ```
5. Switch to OSM fallback by revoking/blanking Google Maps key; confirm UI gracefully falls back.

## 5. Control Page Commands
1. On **Control** page, toggle manual drive commands; observe mower response and telemetry echo.
2. Engage blade and emergency stop, verifying UI status badges and audit log entries.
3. Confirm backend logs show RoboHAT firmware version and watchdog heartbeats.

## 6. Settings Page & Configuration Persistence
1. Open **Settings** page; ensure Hardware, Network, Telemetry, Simulation, AI Acceleration, Branding panels load.
2. Change telemetry cadence to 7 Hz, toggle simulation mode, and save.
3. Verify `/config/system.json` and SQLite `system_config` updated atomically.
4. Reopen page to confirm persisted state; toggle settings back to defaults afterward.

## 7. Documentation Sign-off
1. Rebuild Docs Hub bundle:
   ```bash
   python scripts/generate_docs_bundle.py  # if provided; otherwise run docs build instructions
   ```
2. Review updated docs within the web UI and verify `offline_available` metadata in manifest.
3. Capture screenshots or PDF exports for verification artifacts.

## 8. Graceful Degradation on Raspberry Pi 4B
1. Repeat critical steps 2–6 on a Raspberry Pi 4B (4–8 GB).
2. Run `python scripts/test_performance_degradation.py --target 0.35 --device pi4` to ensure latency target is ≤350 ms.
3. Document any UI effects (reduced FPS, disabled animations) in verification artifacts.

## 9. Finalize Evidence
1. Aggregate telemetry logs, performance reports, and UI media in `verification_artifacts/001-integrate-hardware-and/`.
2. Update `AGENT_JOURNAL.md` with outcomes, latency measurements, and outstanding issues (if any).
3. Prepare for `/tasks` and subsequent implementation by ensuring CI pipelines receive recorded artifacts.

## Completion Criteria
- Dashboard shows healthy telemetry with ≤250 ms latency on Pi 5 and ≤350 ms on Pi 4B.
- Map, Control, and Settings pages function end-to-end with audited persistence.
- Documentation bundle updated and accessible offline.
- Verification artifacts collected and referenced to requirements FR-001…FR-016.
```}