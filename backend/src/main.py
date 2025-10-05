from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.dashboard import router as dashboard_router
from .api.fusion import router as fusion_router
from .api.metrics import router as metrics_router
from .api.motors import router as motors_router
from .api.navigation import router as navigation_router
from .api.rest import router as rest_router
from .api.rest import websocket_hub
from .api.rest_v1 import router as rest_v1_router
from .api.safety import router as safety_router
from .api.status import router as status_router
from .core.config_loader import ConfigLoader
from .nav.gps_degradation import GPSDegradationMonitor
from .services.robohat_service import initialize_robohat_service, shutdown_robohat_service
from .services.camera_stream_service import camera_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Load configuration (hardware + safety limits) and attach to app.state
    loader = ConfigLoader()
    hardware_cfg, safety_limits = loader.get()
    app.state.config_loader = loader
    app.state.hardware_config = hardware_cfg
    app.state.safety_limits = safety_limits
    # Start GPS degradation monitor
    app.state.gps_deg_monitor = GPSDegradationMonitor()
    await app.state.gps_deg_monitor.start()
    # Initialize hardware services (best-effort; keep SIM-safe)
    try:
        await initialize_robohat_service()
    except Exception:
        pass
    try:
        await camera_service.initialize()
        await camera_service.start_streaming()
    except Exception:
        pass
    await websocket_hub.start_telemetry_loop()
    yield
    # Shutdown
    if getattr(app.state, "gps_deg_monitor", None):
        await app.state.gps_deg_monitor.stop()
    await websocket_hub.stop_telemetry_loop()
    try:
        await camera_service.shutdown()
    except Exception:
        pass
    try:
        await shutdown_robohat_service()
    except Exception:
        pass


app = FastAPI(
    title="LawnBerry Pi v2",
    description="Autonomous robotic lawn mower backend API",
    version="2.0.0",
    lifespan=lifespan
)

app.include_router(rest_router, prefix="/api/v2")
app.include_router(metrics_router)
app.include_router(status_router)
app.include_router(navigation_router)
app.include_router(motors_router, prefix="/api/v2")
app.include_router(safety_router, prefix="/api/v2")
app.include_router(fusion_router)
app.include_router(dashboard_router)

app.include_router(rest_v1_router, prefix="/api/v1")


# Root endpoint with API information
@app.get("/")
def root():
    return {
        "service": "LawnBerry Pi v2 Backend API",
        "version": "2.0.0",
        "status": "running",
        "api_docs": "/docs",
        "api_redoc": "/redoc",
        "api_endpoints": {
            "health": "/health",
            "api_v2": "/api/v2",
            "websocket_telemetry": "/api/v2/ws/telemetry"
        },
        "key_endpoints": [
            "/api/v2/health/liveness",
            "/api/v2/health/readiness",
            "/api/v2/dashboard/status",
            "/api/v2/dashboard/telemetry",
            "/api/v2/docs/list"
        ]
    }


# Health check endpoint
@app.get("/health")
def health_check():
    # Minimal subsystem reporting; will be wired to real services in later tasks
    return {
        "status": "healthy",
        "service": "lawnberry-backend",
        "message_bus": {"status": "unknown"},
        "drivers": {"status": "unknown"},
        "persistence": {"status": "unknown"},
        "safety": {"status": "unknown"},
    }
