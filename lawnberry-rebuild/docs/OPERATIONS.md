# LawnBerry Pi v2 - Operations Guide

This document summarizes common operational procedures and API references relevant to day-to-day use on Raspberry Pi OS (64-bit, Bookworm).

## Services
- Backend API (FastAPI/Uvicorn): port 8001
- Web UI (Vite dev): port 3000 (proxy to /api → /api/v2)
- WebSocket: ws://127.0.0.1:8001/api/v2/ws/telemetry

## Health & Status
- GET http://127.0.0.1:8001/health → { status: "healthy" }
- GET http://127.0.0.1:8001/api/v2/dashboard/status → system status
- GET http://127.0.0.1:8001/api/v2/dashboard/telemetry → telemetry snapshot

## Map & Planning
- GET/POST http://127.0.0.1:8001/api/v2/map/zones
- GET/PUT http://127.0.0.1:8001/api/v2/map/locations
- GET/POST/DELETE http://127.0.0.1:8001/api/v2/planning/jobs

## Control
- POST http://127.0.0.1:8001/api/v2/control/drive
- POST http://127.0.0.1:8001/api/v2/control/blade
- POST http://127.0.0.1:8001/api/v2/control/emergency-stop

## AI
- GET http://127.0.0.1:8001/api/v2/ai/datasets
- POST http://127.0.0.1:8001/api/v2/ai/datasets/{datasetId}/export

## Settings
- GET http://127.0.0.1:8001/api/v2/settings/system
- PUT http://127.0.0.1:8001/api/v2/settings/system

## Systemd
See systemd/*.service and systemd/install_services.sh for installation.

## Notes
- All commands and scripts are designed for ARM64 (Raspberry Pi OS Bookworm).
- Avoid adding platform-specific dependencies.
