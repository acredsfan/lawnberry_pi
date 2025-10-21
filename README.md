# LawnBerry Pi v2 🌱🤖

**Professional Autonomous Mowing System with 1980s Cyberpunk Interface**

Target platform: Raspberry Pi OS Lite Bookworm (64-bit) on Raspberry Pi 5 (16 GB) with Python 3.11.x, with graceful degradation validated on Raspberry Pi 4B (4–8 GB).

## 🚀 Quick Start

The LawnBerry Pi v2 system is now fully operational with hardware integration and real-time telemetry streaming.

### System Architecture
- **Backend**: FastAPI with hardware sensor integration (`backend/`)
- **Frontend**: Vue.js 3 with professional 1980s cyberpunk theme (`frontend/`)
- **Real-time**: WebSocket streaming at 5Hz for live telemetry
- **Hardware**: Raspberry Pi with I2C sensors (GPS, IMU, battery monitoring)

### Getting Started
```bash
# Backend (Terminal 1)
cd backend
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (Terminal 2)  
cd frontend
npm run dev -- --host 0.0.0.0 --port 3001
```

### System Status
- ✅ **Hardware Integration**: Real sensor data streaming from Pi hardware
- ✅ **Professional UI**: 1980s cyberpunk design with Orbitron fonts and neon effects
- ✅ **Real-time Telemetry**: Live GPS, battery, IMU data at 5Hz via WebSocket
- ✅ **Production Ready**: Complete system validated on Raspberry Pi hardware

### Documentation
- Setup Guide: `docs/installation-setup-guide.md`
- Contributing Guide: `CONTRIBUTING.md` (includes TODO policy)
- Feature Specifications: `specs/004-lawnberry-pi-v2/`
- System Architecture: See `memory/agent_journal.md` for technical details
- Testing: `tests/` (unit, integration, contract tests)

### Access Points
- **Frontend**: http://192.168.50.215:3001 (or your Pi's IP)
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **WebSocket**: ws://localhost:8000/api/v2/ws/telemetry

The system provides a complete real-time dashboard for autonomous lawn mowing operations with professional-grade user experience and full hardware integration.