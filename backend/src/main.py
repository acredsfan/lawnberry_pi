from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.dashboard import router as dashboard_router
from .api.fusion import router as fusion_router
from .api.health import router as health_router
from .api.metrics import router as metrics_router
from .api.motors import router as motors_router
from .api.navigation import router as navigation_router
from .api.rest import router as rest_router, legacy_router as rest_legacy_router
from .services.websocket_hub import websocket_hub
from .api.routers import auth as auth_router
from .api.routers import telemetry as telemetry_router
from .api.routers import sensors as sensors_router
from .api.routers import maintenance as maintenance_router
from .api.rest_v1 import router as rest_v1_router
from .api.safety import router as safety_router
from .api.status import router as status_router
from .api.mission import router as mission_router
from .core.config_loader import ConfigLoader
from .nav.gps_degradation import GPSDegradationMonitor
from .services.robohat_service import initialize_robohat_service, shutdown_robohat_service
from .services.camera_stream_service import camera_service
from .middleware.correlation import register_correlation_middleware
from .middleware.security import register_security_middleware
from .middleware.rate_limiting import register_global_rate_limiter
from .middleware.input_validation import register_input_validation_middleware
from .middleware.sanitization import register_sanitization_middleware
from .middleware.api_key_auth import register_api_key_auth_middleware
from .core.env_validation import validate_environment
from .safety.safety_validator import validate_on_start
from .safety.safety_monitor import get_safety_monitor
from .safety.safety_triggers import set_safety_event_handler
import os
import logging

# Load .env early so secrets like NTRIP_* are available under systemd
try:
    from dotenv import load_dotenv
    # Load from project root working directory
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=False)
except Exception:
    # Safe to continue without .env
    pass

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Load configuration (hardware + safety limits) and attach to app.state
    loader = ConfigLoader()
    hardware_cfg, safety_limits = loader.get()
    app.state.config_loader = loader
    app.state.hardware_config = hardware_cfg
    app.state.safety_limits = safety_limits
    websocket_hub.bind_app_state(app.state)

    # Small boot hook: ensure dual VL53L0X are addressed uniquely via XSHUT (left 0x29, right default 0x30)
    try:
        if os.getenv("SIM_MODE", "0") == "0":
            tc = getattr(hardware_cfg, "tof_config", None)
            if tc and getattr(tc, "left_shutdown_gpio", None) is not None and getattr(tc, "right_shutdown_gpio", None) is not None:
                try:
                    # Lazy import to keep CI SIM-safe
                    from .drivers.sensors.vl53l0x_driver import ensure_pair_addressing  # type: ignore
                    right_addr = getattr(tc, "right_address", 0x30) or 0x30
                    ok = await ensure_pair_addressing(tc.left_shutdown_gpio, tc.right_shutdown_gpio, right_addr=int(right_addr))
                    _log.info(
                        "ToF XSHUT pair addressing %s (left_gpio=%s right_gpio=%s right_addr=0x%x)",
                        "completed" if ok else "skipped",
                        tc.left_shutdown_gpio,
                        tc.right_shutdown_gpio,
                        int(right_addr),
                    )
                except Exception as e:  # pragma: no cover - hardware dependent
                    _log.warning("ToF pair addressing failed: %s", e)
    except Exception:
        pass
    # Start GPS degradation monitor
    app.state.gps_deg_monitor = GPSDegradationMonitor()
    await app.state.gps_deg_monitor.start()

    # Validate safety limits at startup and attach report
    try:
        ok, report = validate_on_start(loader)
        app.state.safety_validation = report
    except Exception:
        _log.exception("Safety limits validation failed at startup")

    # Initialize safety monitor and wire interlock event bridge
    monitor = get_safety_monitor()
    async def _event_bridge(action, interlock):
        try:
            await monitor.handle_interlock_event(action, interlock)
        except Exception:
            pass

    # wrap event bridge to work with sync trigger calls
    def _handler(action, interlock):
        import asyncio as _asyncio
        try:
            loop = _asyncio.get_running_loop()
            loop.create_task(monitor.handle_interlock_event(action, interlock))
        except RuntimeError:
            _asyncio.run(monitor.handle_interlock_event(action, interlock))

    set_safety_event_handler(_handler)
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
    set_safety_event_handler(None)
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

# Validate environment early
try:
    if not validate_environment():
        _log.error("Environment validation failed; service will continue but endpoints may be restricted")
except Exception:
    _log.exception("Environment validation crashed")

# Middleware order: global limit -> input validation -> security -> API key -> correlation -> sanitization
register_global_rate_limiter(app)
register_input_validation_middleware(app)
register_security_middleware(app)
register_api_key_auth_middleware(app)
register_correlation_middleware(app)
register_sanitization_middleware(app)

app.include_router(rest_router, prefix="/api/v2")
app.include_router(auth_router.router, prefix="/api/v2")
app.include_router(telemetry_router.router, prefix="/api/v2")
app.include_router(sensors_router.router, prefix="/api/v2")
app.include_router(maintenance_router.router, prefix="/api/v2")
app.include_router(rest_legacy_router)
app.include_router(metrics_router)
app.include_router(status_router)
app.include_router(navigation_router)
app.include_router(motors_router, prefix="/api/v2")
app.include_router(safety_router, prefix="/api/v2")
app.include_router(fusion_router)
app.include_router(dashboard_router)
app.include_router(health_router)
app.include_router(mission_router)

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
