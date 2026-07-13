import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from .api.ai import router as ai_router
from .api.autonomy import router as autonomy_router
from .api.boundary import capture_router, parcel_router
from .api.boundary import router as boundary_router
from .api.boundary import verification_router as boundary_verification_router
from .api.dashboard import router as dashboard_router
from .api.docs import router as docs_router
from .api.fusion import router as fusion_router
from .api.health import router as health_router
from .api.metrics import router as metrics_router
from .api.mission import router as mission_router
from .api.motors import router as motors_router
from .api.navigation import router as navigation_router
from .api.rest import legacy_router as rest_legacy_router
from .api.rest import router as rest_router
from .api.rest_v1 import router as rest_v1_router
from .api.routers import auth as auth_router
from .api.routers import camera as camera_router
from .api.routers import maintenance as maintenance_router
from .api.routers import planning as planning_router
from .api.routers import power as power_router
from .api.routers import sensors as sensors_router
from .api.routers import settings as settings_router
from .api.routers import telemetry as telemetry_router
from .api.routers import weather as weather_router
from .api.run_summary import router as run_summary_router
from .api.safety import router as safety_router
from .api.status import router as status_router
from .core.config_loader import get_config_loader
from .core.env_validation import validate_environment
from .core.state_manager import AppState
from .middleware.api_key_auth import register_api_key_auth_middleware
from .middleware.correlation import register_correlation_middleware
from .middleware.deprecation import register_deprecation_middleware
from .middleware.input_validation import register_input_validation_middleware
from .middleware.rate_limiting import register_global_rate_limiter
from .middleware.sanitization import register_sanitization_middleware
from .middleware.security import register_security_middleware
from .nav.gps_degradation import GPSDegradationMonitor
from .safety.safety_monitor import get_safety_monitor
from .safety.safety_triggers import set_safety_event_handler
from .safety.safety_validator import validate_on_start
from .services.ai_service import get_ai_service
from .services.camera_stream_service import camera_service
from .services.jobs_service import jobs_service as _jobs_service_singleton
from .services.mission_service import get_mission_service
from .services.navigation_service import NavigationService
from .services.power_history_service import init_power_history_service
from .services.power_manager import init_power_manager
from .services.robohat_service import initialize_robohat_service, shutdown_robohat_service
from .services.websocket_hub import websocket_hub

# Load .env early so secrets like NTRIP_* are available under systemd
try:
    from dotenv import load_dotenv

    # Load from project root working directory
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=False)
except Exception:
    # Safe to continue without .env
    pass

_log = logging.getLogger(__name__)


def _maybe_attach_telemetry_capture(nav_service) -> None:
    """If LAWNBERRY_CAPTURE_PATH is set, attach a JSONL telemetry capture.

    No-op when the env var is unset or empty. Errors during attach are logged
    but do not abort startup — capture is a diagnostic, not a safety dependency.
    """
    path = os.environ.get("LAWNBERRY_CAPTURE_PATH", "").strip()
    if not path:
        return
    try:
        from .diagnostics.capture import TelemetryCapture

        capture = TelemetryCapture(path)
        nav_service.attach_capture(capture)
        _log.info("Telemetry capture enabled: %s", path)
    except Exception as exc:
        _log.warning("Failed to enable telemetry capture at %s: %s", path, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Load configuration via the singleton — app.state.config_loader IS the
    # singleton so update_limits() correctly busts its cache on PUT /settings/safety.
    loader = get_config_loader()
    hardware_cfg, safety_limits = loader.get()
    app.state.config_loader = loader
    app.state.hardware_config = hardware_cfg
    app.state.safety_limits = safety_limits
    shared_state = AppState.get_instance()
    shared_state.hardware_config = hardware_cfg
    websocket_hub.bind_app_state(app.state)

    # Small boot hook: ensure dual VL53L0X are addressed uniquely via XSHUT (left 0x29, right default 0x30)
    try:
        if os.getenv("SIM_MODE", "0") == "0":
            tc = getattr(hardware_cfg, "tof_config", None)
            if (
                tc
                and getattr(tc, "left_shutdown_gpio", None) is not None
                and getattr(tc, "right_shutdown_gpio", None) is not None
            ):
                try:
                    # Lazy import to keep CI SIM-safe
                    from .drivers.sensors.vl53l0x_driver import (
                        ensure_pair_addressing,  # type: ignore
                    )

                    right_addr = getattr(tc, "right_address", 0x30) or 0x30
                    ok = await ensure_pair_addressing(
                        tc.left_shutdown_gpio, tc.right_shutdown_gpio, right_addr=int(right_addr)
                    )
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
    monitor.set_websocket_hub(websocket_hub)  # inject hub — breaks circular import

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
        await initialize_robohat_service(hardware_config=hardware_cfg)
    except Exception:
        pass
    try:
        nav_service = NavigationService.get_instance()
        _maybe_attach_telemetry_capture(nav_service)
        mission_service = get_mission_service(
            nav_service, websocket_hub=websocket_hub
        )
        await asyncio.wait_for(mission_service.recover_persisted_missions(), timeout=30.0)
    except TimeoutError:
        _log.error("Mission recovery timed out after 30 s; continuing startup")
    except Exception:
        _log.exception("Mission recovery failed during startup")
    # Start the job scheduler (module-level singleton; idempotent if already running).
    try:
        await _jobs_service_singleton.start_scheduler()
        _log.info("JobsService scheduler started")
    except Exception:
        _log.exception("JobsService scheduler startup failed")
    try:
        await camera_service.initialize()
        await camera_service.start_streaming()
    except Exception:
        pass
    try:
        await get_ai_service().initialize()
    except Exception:
        _log.exception("AI service initialization failed")
    await websocket_hub.start_telemetry_loop()

    # Build the typed RuntimeContext once all services are up. This is
    # consumed by safety-critical routers via Depends(get_runtime).
    # See docs/superpowers/plans/2026-04-26-runtime-context.md.
    # `sensor_manager` is a property on RuntimeContext that reads AppState
    # live (Issue #44 / docs/runtime-context.md), so it is not passed here.
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.core import globals as global_state
    from backend.src.core.persistence import persistence
    from backend.src.core.runtime import RuntimeContext
    from backend.src.services.robohat_service import get_robohat_service

    _robohat = get_robohat_service()
    _command_gateway = MotorCommandGateway(
        safety_state=global_state._safety_state,
        blade_state=global_state._blade_state,
        client_emergency=global_state._client_emergency,
        robohat=_robohat,
        persistence=persistence,
        websocket_hub=websocket_hub,
        config_loader=loader,
    )

    # Set up and start the software watchdog (Blueprint A)
    from backend.src.safety.estop_handler import EstopHandler
    from backend.src.safety.motor_authorization import MotorAuthorization
    from backend.src.safety.watchdog import Watchdog

    class GatewayEstopHandler(EstopHandler):
        def __init__(self, auth: MotorAuthorization, gateway: Any) -> None:
            super().__init__(auth)
            self._gateway = gateway
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None

        def trigger_estop(self, reason: str = "unknown") -> None:
            super().trigger_estop(reason)
            loop = self._loop
            if loop is not None and loop.is_running():
                from backend.src.control.commands import EmergencyTrigger
                asyncio.run_coroutine_threadsafe(
                    self._gateway.trigger_emergency(
                        EmergencyTrigger(reason=reason, source="safety_trigger")
                    ),
                    loop
                )
            else:
                try:
                    from backend.src.core.robot_state_manager import get_robot_state_manager
                    get_robot_state_manager().set_emergency_stop(True, reason)
                    self._gateway._blade_state["active"] = False
                except Exception:
                    pass

    _auth = MotorAuthorization()
    _auth.authorize()
    _estop_handler = GatewayEstopHandler(_auth, _command_gateway)
    _watchdog_timeout_ms = getattr(safety_limits, "watchdog_timeout_ms", 1000) or 1000
    _watchdog = Watchdog(_estop_handler, timeout_ms=_watchdog_timeout_ms)
    # watchdog is started after all sync init below — see comment before yield
    app.state.watchdog = _watchdog
    _command_gateway.set_watchdog(_watchdog)

    _hb_interval_s = (_watchdog_timeout_ms / 1000.0) / 4.0

    async def _watchdog_heartbeat_loop() -> None:
        try:
            while True:
                _watchdog.heartbeat()
                await asyncio.sleep(_hb_interval_s)
        except asyncio.CancelledError:
            pass

    # Construct LocalizationService when not running in legacy navigation mode.
    # USE_LEGACY_NAVIGATION=1 keeps NavigationService running its original code path.
    _localization_service = None
    if os.getenv("USE_LEGACY_NAVIGATION", "0") != "1":
        from backend.src.services.localization_service import (
            build_localization_service_from_config,
        )
        _localization_service = build_localization_service_from_config()
        nav_service.attach_localization(_localization_service)
        _log.info("LocalizationService constructed and attached to NavigationService")
    else:
        _log.info("USE_LEGACY_NAVIGATION=1: running legacy NavigationService code path")

    # --- Repository construction (§5) ---
    from pathlib import Path as _Path

    from backend.src.repositories import (
        CalibrationRepository,
        MapRepository,
        MissionRepository,
        SettingsRepository,
        TelemetryRepository,
    )

    _data_dir_env = os.getenv("LAWN_DATA_DIR", "").strip()
    _db_path_env = os.getenv("DB_PATH", "").strip()

    if _db_path_env:
        _db_path = _Path(_db_path_env)
        _data_dir = _db_path.parent
    elif _data_dir_env:
        _data_dir = _Path(_data_dir_env)
        _db_path = _data_dir / "lawnberry.db"
    else:
        _data_dir = _Path(os.getcwd()) / "data"
        _db_path = _data_dir / "lawnberry.db"

    _map_repo = MapRepository(db_path=_db_path)
    _mission_repo = MissionRepository(db_path=_db_path)
    _settings_repo = SettingsRepository(db_path=_db_path)
    _calibration_repo = CalibrationRepository(calibration_path=_data_dir / "calibration.json")
    _telemetry_repo = TelemetryRepository(db_path=_db_path)

    # One repository owns alignment for both localization updates and mission admission.
    if _localization_service is not None:
        _localization_service.attach_calibration_repository(_calibration_repo)
    nav_service.attach_calibration_repository(_calibration_repo)

    # Wire MapRepository into the already-constructed NavigationService singleton.
    # This lets _load_boundaries_from_zones() read persisted zones instead of
    # the deprecated _zones_store global in rest.py.
    nav_service.attach_map_repository(_map_repo)
    nav_service.attach_command_gateway(_command_gateway)

    # Wire MissionRepository into the already-constructed MissionService singleton.
    get_mission_service(nav_service, mission_repository=_mission_repo)

    # --- EventStore construction (W1-3) ---
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import PersistenceMode

    _raw_mode = os.environ.get("LAWNBERRY_PERSISTENCE_MODE", "summary").lower()
    try:
        _persistence_mode = PersistenceMode(_raw_mode)
    except ValueError:
        _log.warning(
            "Unknown LAWNBERRY_PERSISTENCE_MODE=%r; defaulting to 'summary'", _raw_mode
        )
        _persistence_mode = PersistenceMode.SUMMARY

    event_store = EventStore(persistence=persistence, mode=_persistence_mode)
    _log.info("Event persistence mode: %s", _persistence_mode.value)

    # --- PlanningService construction ---
    from backend.src.services.planning_service import get_planning_service as _get_planning_svc
    _planning_svc = _get_planning_svc()
    _planning_svc.set_map_repository(_map_repo)

    app.state.runtime = RuntimeContext(
        config_loader=loader,
        hardware_config=hardware_cfg,
        safety_limits=safety_limits,
        navigation=nav_service,
        mission_service=mission_service,
        safety_state=global_state._safety_state,
        blade_state=global_state._blade_state,
        robohat=_robohat,
        websocket_hub=websocket_hub,
        persistence=persistence,
        command_gateway=_command_gateway,
        localization=_localization_service,
        watchdog=_watchdog,
        map_repository=_map_repo,
        mission_repository=_mission_repo,
        settings_repository=_settings_repo,
        calibration_repository=_calibration_repo,
        telemetry_repository=_telemetry_repo,
        event_store=event_store,
        persistence_mode=_persistence_mode.value,
        jobs_service=_jobs_service_singleton,
        planning_service=_planning_svc,
    )
    from backend.src.services.autonomy_qualification_service import (
        AutonomyQualificationService,
    )

    _qualification_service = AutonomyQualificationService(app.state.runtime)
    app.state.runtime.qualification_service = _qualification_service
    if hasattr(app.state.runtime.command_gateway, "set_qualification_service"):
        app.state.runtime.command_gateway.set_qualification_service(_qualification_service)
    if hasattr(_jobs_service_singleton, "set_qualification_service"):
        _jobs_service_singleton.set_qualification_service(_qualification_service)
    try:
        from backend.src.safety.live_safety_coordinator import LiveSafetyCoordinator

        _live_safety = LiveSafetyCoordinator(app.state.runtime)
        app.state.runtime.live_safety = _live_safety
        app.state.live_safety = _live_safety
        await _live_safety.start()
        _log.info("LiveSafetyCoordinator started")
    except Exception:
        _log.exception("LiveSafetyCoordinator startup failed")
    # Wire MissionService and WebSocketHub into JobsService for scheduled dispatch.
    _jobs_service_singleton.set_mission_service(mission_service)
    _jobs_service_singleton.set_websocket_hub(websocket_hub)
    _log.info("JobsService: MissionService and WebSocketHub wired for scheduled dispatch")

    # Attach EventStore to services that emit events.
    if hasattr(app.state.runtime.mission_service, "set_event_store"):
        app.state.runtime.mission_service.set_event_store(event_store)
    if hasattr(app.state.runtime.command_gateway, "set_event_store"):
        app.state.runtime.command_gateway.set_event_store(
            event_store, run_id="", mission_id=""
        )
    _fw = None
    if app.state.runtime.robohat:
        _fw = getattr(app.state.runtime.robohat.status, "firmware_version", None)
    _log.info(
        "RuntimeContext ready: navigation=%s mission=%s robohat=%s firmware=%s",
        type(app.state.runtime.navigation).__name__,
        type(app.state.runtime.mission_service).__name__,
        type(app.state.runtime.robohat).__name__ if app.state.runtime.robohat else "none",
        _fw or "not_yet_received",
    )

    # --- Startup config report (§5) ---
    from backend.src.core.startup_report import build_startup_report as _build_report

    _startup_report = _build_report(
        hardware_path=loader.hardware_path,
        limits_path=loader.limits_path,
        calibration_path=_data_dir / "calibration.json",
        secrets_keys=["ntrip_password", "google_api_key", "api_key", "device_key"],
        hardware_config=hardware_cfg,
        safety_limits=safety_limits,
        source_metadata=loader.source_metadata(),
    )
    app.state.startup_config_report = _startup_report

    # Start the watchdog monitor only after all synchronous init is complete.
    # Timeout enforcement stays disarmed until drive/blade control arms it, so
    # idle startup or telemetry stalls cannot create a spurious watchdog E-stop.
    # create_task schedules the heartbeat coroutine; asyncio.sleep(0) yields to the
    # event loop so the task runs once (calling heartbeat()) before the watchdog thread
    # starts. This keeps the first armed interval from inheriting stale startup time.
    _watchdog_heartbeat_task = asyncio.create_task(
        _watchdog_heartbeat_loop(), name="watchdog_heartbeat"
    )
    app.state.watchdog_heartbeat_task = _watchdog_heartbeat_task
    await asyncio.sleep(0)  # let heartbeat task run once before watchdog timer starts
    await _watchdog.start()

    # Start Power History logging and Power Manager.
    # These are initialised here (after persistence is ready and _db_path is known)
    # and stored on app.state so the shutdown block can tear them down cleanly.
    try:
        _power_history_svc = init_power_history_service(persistence)
        await _power_history_svc.start()
        _power_manager = init_power_manager(_power_history_svc)
        await _power_manager.start()
        app.state.power_history_service = _power_history_svc
        app.state.power_manager = _power_manager
        _log.info("PowerHistoryService and PowerManager started")
    except Exception:
        _log.exception("Power management services failed to start (non-fatal)")

    yield
    # Shutdown
    try:
        if getattr(app.state, "live_safety", None):
            await app.state.live_safety.stop()
    except Exception:
        _log.exception("LiveSafetyCoordinator shutdown failed")
    try:
        if getattr(app.state, "power_manager", None):
            await app.state.power_manager.stop()
        if getattr(app.state, "power_history_service", None):
            await app.state.power_history_service.stop()
    except Exception:
        pass
    if getattr(app.state, "watchdog_heartbeat_task", None):
        app.state.watchdog_heartbeat_task.cancel()
        try:
            await app.state.watchdog_heartbeat_task
        except asyncio.CancelledError:
            pass
    if getattr(app.state, "watchdog", None):
        await app.state.watchdog.stop()
    set_safety_event_handler(None)
    if getattr(app.state, "gps_deg_monitor", None):
        await app.state.gps_deg_monitor.stop()
    await websocket_hub.stop_telemetry_loop()
    try:
        await _jobs_service_singleton.stop_scheduler()
        _log.info("JobsService scheduler stopped")
    except Exception:
        _log.exception("JobsService scheduler shutdown failed")
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
    lifespan=lifespan,
)

# Validate environment early
try:
    if not validate_environment():
        _log.error(
            "Environment validation failed; service will continue but endpoints may be restricted"
        )
except Exception:
    _log.exception("Environment validation crashed")

# Middleware order: global limit -> input validation -> security -> API key -> correlation -> sanitization -> deprecation
register_global_rate_limiter(app)
register_input_validation_middleware(app)
register_security_middleware(app)
register_api_key_auth_middleware(app)
register_correlation_middleware(app)
register_sanitization_middleware(app)
register_deprecation_middleware(app)

app.include_router(rest_router, prefix="/api/v2")
app.include_router(autonomy_router)
app.include_router(auth_router.router, prefix="/api/v2")
app.include_router(telemetry_router.router, prefix="/api/v2")
app.include_router(sensors_router.router, prefix="/api/v2")
app.include_router(maintenance_router.router, prefix="/api/v2")
app.include_router(camera_router.router, prefix="/api/v2")
app.include_router(weather_router.router, prefix="/api/v2")
app.include_router(planning_router.router, prefix="/api/v2")
app.include_router(settings_router.router, prefix="/api/v2")
app.include_router(power_router.router)
app.include_router(parcel_router, prefix="/api/v2")
app.include_router(capture_router, prefix="/api/v2")
app.include_router(boundary_router, prefix="/api/v2")
app.include_router(boundary_verification_router, prefix="/api/v2")
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
app.include_router(ai_router)
app.include_router(docs_router)
app.include_router(run_summary_router)

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
            "websocket_telemetry": "/api/v2/ws/telemetry",
        },
        "key_endpoints": [
            "/api/v2/health/liveness",
            "/api/v2/health/readiness",
            "/api/v2/dashboard/status",
            "/api/v2/dashboard/telemetry",
            "/api/v2/docs/list",
        ],
    }
