"""
Main FastAPI Application
Entry point for the web API backend with comprehensive routing and middleware setup.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import time
import os  # Added for environment variable override (LAWNBERY_UI_DIR)
import re
import json
from pathlib import Path  # added for static asset detection
from fastapi.responses import RedirectResponse, FileResponse  # updated for serving UI
from fastapi.staticfiles import StaticFiles


from .config import get_settings
from .auth import get_current_user, AuthManager, set_auth_manager
from .routers import (
    system, sensors, navigation, patterns, 
    configuration, maps, weather, power, websocket, progress, rc_control, google_maps, camera,
    public_config
)
from .routers import auth_routes
from .middleware import RateLimitMiddleware, RequestLoggingMiddleware
from .mqtt_bridge import MQTTBridge
from .exceptions import (
    APIException,
    api_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)


# Application lifecycle management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown"""
    settings = get_settings()
    
    # Initialize logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting web API backend...")
    
    # Initialize Redis client for caching
    try:
        from redis.asyncio import Redis
        redis_client = Redis.from_url(
            f"redis://{settings.redis.host}:{settings.redis.port}/{settings.redis.db}",
            password=settings.redis.password,
            max_connections=settings.redis.max_connections
        )
        # Cap Redis ping to 1s to avoid startup hangs when Redis is unreachable
        try:
            await asyncio.wait_for(redis_client.ping(), timeout=1.0)
        except asyncio.TimeoutError:
            raise TimeoutError("Redis ping timed out (>1s)")
        app.state.redis_client = redis_client
        logger.info("Redis client initialized successfully")
    except Exception as e:
        logger.warning(f"Redis initialization failed: {e}. Caching will be disabled.")
        app.state.redis_client = None
    
    # Initialize MQTT bridge with a short connection timeout to avoid blocking startup
    mqtt_bridge = MQTTBridge(settings.mqtt)
    async def _safe_startup(coro, name: str, timeout: float):
        try:
            await asyncio.wait_for(coro, timeout=timeout)
            logger.info(f"{name} startup complete")
        except asyncio.TimeoutError:
            logger.warning(f"Timed out waiting for {name} startup (>{timeout}s); continuing")
        except Exception as e:
            logger.warning(f"Error during {name} startup: {e}")

    await _safe_startup(mqtt_bridge.connect(), "MQTT bridge", 2.0)
    app.state.mqtt_bridge = mqtt_bridge

    # Integrate MQTT bridge with WebSocket manager for real-time data
    from .routers.websocket import setup_websocket_mqtt_integration
    setup_websocket_mqtt_integration(mqtt_bridge)

    # Initialize shared hardware interface for camera access in API process
    try:
        import os
        # When API owns the camera, instruct hardware service not to, by setting env in its unit
        # Use absolute import to avoid relative import errors when running under uvicorn/module
        from src.hardware.hardware_interface import create_hardware_interface  # type: ignore
        cfg_path = os.path.join(os.environ.get('PYTHONPATH', '/opt/lawnberry').split(os.pathsep)[0], 'config', 'hardware.yaml')
        hw = create_hardware_interface(cfg_path, shared=True)
        # Initialize minimally and start camera capture for streaming; bounded time
        try:
            await asyncio.wait_for(hw.initialize(), timeout=8.0)
        except Exception:
            pass
        app.state.system_manager = type('SysMgr', (), {
            'hardware_interface': hw,
            'camera_manager': getattr(hw, 'camera_manager', None)
        })()
        # Ensure camera capture running
        cam = getattr(hw, 'camera_manager', None)
        if cam:
            try:
                await asyncio.wait_for(cam.start_capture(), timeout=2.0)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"API hardware/camera init skipped: {e}")
    
    # Initialize auth manager and register globally for dependency helpers
    auth_manager = AuthManager(settings.auth)
    await auth_manager.initialize()
    app.state.auth_manager = auth_manager
    try:
        set_auth_manager(auth_manager)
    except Exception as e:
        logger.warning(f"Failed to set global auth manager: {e}")
    
    logger.info("Web API backend startup complete")
    
    yield
    
    # Cleanup
    logger.info("Shutting down web API backend...")

    async def _safe_shutdown(coro, name: str, timeout: float):
        try:
            await asyncio.wait_for(coro, timeout=timeout)
            logger.info(f"{name} shutdown complete")
        except asyncio.TimeoutError:
            logger.warning(f"Timed out waiting for {name} shutdown (>{timeout}s); continuing")
        except Exception as e:
            logger.warning(f"Error during {name} shutdown: {e}")

    # MQTT disconnect (may block if broker unresponsive) - cap at 5s
    await _safe_shutdown(mqtt_bridge.disconnect(), "MQTT bridge", 5.0)

    # Close Redis connection (cap at 3s)
    if hasattr(app.state, 'redis_client') and app.state.redis_client:
        await _safe_shutdown(app.state.redis_client.close(), "Redis client", 3.0)

    logger.info("Web API backend shutdown complete")


# Create FastAPI application
def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = get_settings()
    
    app = FastAPI(
        title="Lawnberry Mower API",
        description="REST API for autonomous lawn mower control and monitoring",
        version="1.0.0",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
        openapi_url="/api/openapi.json" if settings.debug else None,
        lifespan=lifespan
    )
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    
    # Add exception handlers
    # Correct exception handler mapping and comprehensive handlers for validation and general errors
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    from fastapi.exceptions import RequestValidationError  # local import to avoid unused at top
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Simple health check endpoint"""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "version": "1.0.0"
        }
    
    # API meta endpoint (renamed to avoid collision with real mower status route below)
    @app.get("/api/v1/meta")
    async def api_meta(request: Request):
        """Meta/application status (distinct from mower runtime status)."""
        mqtt_bridge = getattr(request.app.state, 'mqtt_bridge', None)
        return {
            "api_version": "1.0.0",
            "service": "lawnberry-api",
            "status": "operational",
            "timestamp": time.time(),
            "mqtt_connected": mqtt_bridge.is_connected() if mqtt_bridge else False,
            "uptime": time.time() - getattr(app.state, 'start_time', time.time())
        }

    # Note: Previously there was a legacy placeholder route at /api/v1/status declared here.
    # That caused the real status route (declared later) to be shadowed due to route ordering.
    # We remove the placeholder to ensure the real status endpoint is active and returns live sensor data.
    
    # Mock mower status endpoint for frontend development
    @app.get("/api/v1/mock/status")
    async def mock_mower_status():
        """Mock mower status data for frontend development"""
        import random
        import math
        
        # Create realistic mock data with some variation
        now = time.time()
        base_lat, base_lng = 40.7128, -74.0060  # NYC coordinates
        
        # Add some realistic movement over time
        time_offset = (now % 3600) / 3600  # Hour cycle
        lat_offset = math.sin(time_offset * 2 * math.pi) * 0.001  # ~100m variation
        lng_offset = math.cos(time_offset * 2 * math.pi) * 0.001
        
        return {
            "state": random.choice(["idle", "mowing", "charging", "returning"]),
            "position": {
                "lat": base_lat + lat_offset,
                "lng": base_lng + lng_offset,
                "heading": (now % 360),
                "accuracy": random.uniform(2, 8)
            },
            "battery": {
                "level": max(20, 100 - (now % 7200) / 72),  # 2-hour discharge cycle
                "voltage": random.uniform(23.8, 25.2),
                "current": random.uniform(1.2, 2.5),
                "charging": random.choice([True, False]),
                "timeRemaining": random.randint(60, 240)
            },
            "sensors": {
                "imu": {
                    "orientation": {
                        "x": random.uniform(-0.1, 0.1),
                        "y": random.uniform(-0.1, 0.1), 
                        "z": random.uniform(-0.1, 0.1)
                    },
                    "acceleration": {
                        "x": random.uniform(-0.5, 0.5),
                        "y": random.uniform(-0.5, 0.5),
                        "z": random.uniform(9.7, 9.9)
                    },
                    "gyroscope": {
                        "x": random.uniform(-0.05, 0.05),
                        "y": random.uniform(-0.05, 0.05),
                        "z": random.uniform(-0.05, 0.05)
                    },
                    "temperature": random.uniform(30, 40)
                },
                "tof": {
                    "left": random.uniform(0.5, 2.0),
                    "right": random.uniform(0.5, 2.0)
                },
                "environmental": {
                    "temperature": random.uniform(20, 30),
                    "humidity": random.uniform(40, 80),
                    "pressure": random.uniform(1000, 1020)
                },
                "power": {
                    "voltage": random.uniform(23.8, 25.2),
                    "current": random.uniform(1.2, 2.5),
                    "power": random.uniform(30, 60)
                }
            },
            "coverage": {
                "totalArea": 1000,
                "coveredArea": min(1000, (now % 14400) / 14.4),  # 4-hour coverage cycle
                "percentage": min(100, (now % 14400) / 144)
            },
            "lastUpdate": now,
            "location_source": "gps",
            "connected": True
        }
    
    # Real mower status endpoint using sensor data from MQTT
    @app.get("/api/v1/status")
    async def real_mower_status(request: Request):
        """Real mower status data from hardware sensors via MQTT"""
        mqtt_bridge = getattr(request.app.state, 'mqtt_bridge', None)
        
        if not mqtt_bridge or not mqtt_bridge.is_connected():
            # Fallback to mock data if MQTT not available
            return await mock_mower_status()
        
        try:
            # Get sensor data from MQTT cache
            gps_data = mqtt_bridge.get_cached_data("sensors/gps/data") or {}
            imu_data = mqtt_bridge.get_cached_data("sensors/imu/data") or {}
            tof_data = mqtt_bridge.get_cached_data("sensors/tof/data") or {}
            env_data = mqtt_bridge.get_cached_data("sensors/environmental/data") or {}
            power_data = mqtt_bridge.get_cached_data("power/battery") or {}
            health_data = mqtt_bridge.get_cached_data("system/health") or {}
            
            # ToF fallback logic: if aggregated topic missing or zero, try per-ToF topics
            def _tof_value_meters() -> Dict[str, float]:
                # Prefer aggregated distances if present and non-zero
                left_raw = tof_data.get("left_distance")
                right_raw = tof_data.get("right_distance")
                left_val = float(left_raw) if left_raw is not None else 0.0
                right_val = float(right_raw) if right_raw is not None else 0.0

                def _mm_to_meters(v: float) -> float:
                    # Treat clearly out-of-range small values as already meters
                    # Our sensor_service publishes ~500-1000 for 0.5-1.0m, so >=5 likely mm.
                    return v / 1000.0 if v >= 5.0 else v

                if left_val > 0.0 or right_val > 0.0:
                    return {
                        "left": _mm_to_meters(left_val),
                        "right": _mm_to_meters(right_val),
                    }

                # Fallback to per-sensor topics
                left_topic = mqtt_bridge.get_cached_data("sensors/tof/left") or {}
                right_topic = mqtt_bridge.get_cached_data("sensors/tof/right") or {}

                l_mm = float(left_topic.get("distance_mm", 0.0) or 0.0)
                r_mm = float(right_topic.get("distance_mm", 0.0) or 0.0)

                return {
                    "left": _mm_to_meters(l_mm),
                    "right": _mm_to_meters(r_mm),
                }

            # Determine mower state based on available data
            state = "idle"  # Default state
            if power_data.get("charging", False):
                state = "charging"
            elif gps_data.get("latitude", 0) != 0 and imu_data.get("acceleration", {}).get("x", 0) > 0.1:
                state = "mowing"
            
            tof_values = _tof_value_meters()

            # Build status response from real sensor data
            return {
                "state": state,
                "position": {
                    "lat": gps_data.get("latitude", 0.0),
                    "lng": gps_data.get("longitude", 0.0),
                    "heading": imu_data.get("orientation", {}).get("yaw", 0.0),
                    "accuracy": gps_data.get("accuracy", 0.0)
                },
                "battery": {
                    "level": power_data.get("battery_level", 0.0),
                    "voltage": power_data.get("battery_voltage", 0.0),
                    "current": power_data.get("battery_current", 0.0),
                    "charging": power_data.get("charging", False),
                    "timeRemaining": max(0, int(power_data.get("battery_level", 0) * 2))  # Rough estimate
                },
                "sensors": {
                    "imu": {
                        "orientation": imu_data.get("orientation", {"x": 0, "y": 0, "z": 0}),
                        "acceleration": imu_data.get("acceleration", {"x": 0, "y": 0, "z": 0}),
                        "gyroscope": imu_data.get("gyroscope", {"x": 0, "y": 0, "z": 0}),
                        "temperature": imu_data.get("temperature", 0.0)
                    },
                    "tof": {
                        "left": tof_values.get("left", 0.0),
                        "right": tof_values.get("right", 0.0)
                    },
                    "environmental": {
                        "temperature": env_data.get("temperature", 0.0),
                        "humidity": env_data.get("humidity", 0.0),
                        "pressure": env_data.get("pressure", 0.0)
                    },
                    "power": {
                        "voltage": power_data.get("battery_voltage", 0.0),
                        "current": power_data.get("battery_current", 0.0),
                        "power": power_data.get("battery_voltage", 0.0) * power_data.get("battery_current", 0.0)
                    }
                },
                "coverage": {
                    "totalArea": 1000,  # This would come from navigation service
                    "coveredArea": 450,  # This would come from navigation service 
                    "percentage": 45.0
                },
                "lastUpdate": time.time(),
                "location_source": "gps" if gps_data.get("satellites", 0) > 3 else "dead_reckoning",
                "connected": True
            }
            
        except Exception as e:
            # Log error and fallback to mock data
            logging.getLogger(__name__).error(f"Error getting real status data: {e}")
            return await mock_mower_status()
    
    # Simple connectivity test endpoint
    @app.get("/api/v1/test")
    async def test_connectivity():
        """Simple test endpoint for debugging frontend connectivity"""
        return {
            "message": "Backend is reachable",
            "timestamp": time.time(),
            "cors_enabled": True
        }
    
    # Ping endpoint for health checks
    @app.get("/api/v1/ping")
    @app.head("/api/v1/ping")
    async def ping():
        """Simple ping endpoint for health checks"""
        return {"status": "ok", "timestamp": time.time()}
    
    # ---- Robust Static UI Mount (multi-path + env override) ----
    # Some deployments run from /opt/lawnberry while development occurs in workspace.
    # We attempt several candidate locations AND allow LAWNBERY_UI_DIR override.
    candidates = []
    env_override = os.getenv("LAWNBERY_UI_DIR")
    if env_override:
        candidates.append(Path(env_override).expanduser())
    # Primary (current working tree)
    candidates.append(Path("web-ui") / "dist")
    # Installed copy under /opt
    candidates.append(Path("/opt/lawnberry/web-ui/dist"))
    # Relative to this file (in case CWD differs)
    candidates.append(Path(__file__).resolve().parent.parent.parent / "web-ui" / "dist")
    mounted = False
    chosen_path = None
    class SPAStaticFiles(StaticFiles):
        """StaticFiles that falls back to index.html for unknown non-asset routes (SPA support)."""
        def __init__(self, directory: str, index_path: Path):
            super().__init__(directory=directory, html=True)
            self._index_path = index_path

        async def get_response(self, path: str, scope):  # type: ignore[override]
            response = await super().get_response(path, scope)
            # If not found and it's a client-side route (no dot in last segment), serve index.html
            if response.status_code == 404:
                # Paths like assets/... should keep 404 so the browser can handle missing files
                last_segment = path.rsplit('/', 1)[-1]
                if '.' not in last_segment:  # treat as client route
                    return FileResponse(self._index_path)
            return response

    for c in candidates:
        index_file = c / "index.html"
        if index_file.exists():
            try:
                # Manual SPA routing instead of StaticFiles mount to guarantee deep link fallback.
                # This avoids mount precedence issues that prevented /ui/* paths from being intercepted.
                chosen_path = c
                mounted = True

                def _cache_headers(resp: Response, immutable: bool = False):
                    # Immutable long-cache for hashed assets, no-cache for HTML shell
                    resp.headers["Cache-Control"] = (
                        "public, max-age=31536000, immutable" if immutable else "no-cache"
                    )
                    return resp

                def _is_hashed(name: str) -> bool:
                    return bool(re.search(r"-[0-9a-f]{6,}\.(?:js|css|png|svg|webp|jpg|jpeg)$", name))

                @app.get("/", include_in_schema=False)
                async def root_index():  # type: ignore
                    return _cache_headers(FileResponse(index_file), immutable=False)

                @app.head("/", include_in_schema=False)
                async def root_index_head():  # type: ignore
                    return _cache_headers(Response(status_code=200), immutable=False)

                @app.get("/ui", include_in_schema=False)
                async def ui_redirect():  # type: ignore
                    return RedirectResponse(url="/ui/", status_code=302)

                @app.get("/ui/", include_in_schema=False)
                async def ui_index():  # type: ignore
                    return _cache_headers(FileResponse(index_file), immutable=False)

                @app.head("/ui/", include_in_schema=False)
                async def ui_index_head():  # type: ignore
                    return _cache_headers(Response(status_code=200), immutable=False)

                def _safe_asset_path(rel: str) -> Path:
                    # Prevent path traversal
                    rel = rel.lstrip("/")
                    candidate = (chosen_path / rel).resolve()
                    if not str(candidate).startswith(str(chosen_path.resolve())):
                        raise HTTPException(status_code=403, detail="Forbidden")
                    return candidate

                @app.get("/ui/assets/{asset_path:path}", include_in_schema=False)
                async def ui_assets(asset_path: str):  # type: ignore
                    p = _safe_asset_path(f"assets/{asset_path}")
                    if not p.exists():
                        raise HTTPException(status_code=404, detail="Asset Not Found")
                    return _cache_headers(FileResponse(p), immutable=_is_hashed(p.name))

                @app.head("/ui/assets/{asset_path:path}", include_in_schema=False)
                async def ui_assets_head(asset_path: str):  # type: ignore
                    p = _safe_asset_path(f"assets/{asset_path}")
                    if not p.exists():
                        raise HTTPException(status_code=404, detail="Asset Not Found")
                    return _cache_headers(Response(status_code=200), immutable=_is_hashed(p.name))

                @app.get("/ui/{full_path:path}", include_in_schema=False)
                async def ui_catch_all(full_path: str):  # type: ignore
                    p = _safe_asset_path(full_path)
                    if p.exists() and p.is_file():
                        return _cache_headers(FileResponse(p), immutable=_is_hashed(p.name))
                    return _cache_headers(FileResponse(index_file), immutable=False)

                @app.head("/ui/{full_path:path}", include_in_schema=False)
                async def ui_catch_all_head(full_path: str):  # type: ignore
                    p = _safe_asset_path(full_path)
                    if p.exists() and p.is_file():
                        return _cache_headers(Response(status_code=200), immutable=_is_hashed(p.name))
                    return _cache_headers(Response(status_code=200), immutable=False)

                logging.getLogger(__name__).info(f"Mounted SPA manual router at /ui from {c}")
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed setting up manual UI routes from {c}: {e}")
            if mounted:
                break
    if not mounted:
        logging.getLogger(__name__).info("No web UI dist located (candidates checked: %s)" % ", ".join(str(p) for p in candidates))
    else:
        # Expose a tiny version endpoint to help frontend verify sync
        @app.get("/ui-version")
        async def ui_version():  # type: ignore
            ts = 0
            try:
                ts = int(chosen_path.stat().st_mtime)
            except Exception:
                pass
            return {"mounted_path": str(chosen_path), "mtime": ts}

        # Redirect common top-level SPA routes missing /ui prefix
        _raw_routes = ["/dashboard", "/maps", "/navigation", "/rc-control", "/settings", "/training", "/documentation"]
        for _r in _raw_routes:
            @app.api_route(_r, methods=["GET", "HEAD"], include_in_schema=False)
            async def _redir_spa(request: Request, route=_r):  # type: ignore
                return RedirectResponse(url=f"/ui{route}", status_code=302)

        # Asset fallback when user visits without /ui prefix
        @app.api_route("/assets/{asset_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        async def _asset_fallback(asset_path: str):  # type: ignore
            return RedirectResponse(url=f"/ui/assets/{asset_path}", status_code=302)

        @app.api_route("/registerSW.js", methods=["GET", "HEAD"], include_in_schema=False)
        async def _sw_fallback():  # type: ignore
            return RedirectResponse(url="/ui/registerSW.js", status_code=302)

        @app.api_route("/manifest.webmanifest", methods=["GET", "HEAD"], include_in_schema=False)
        async def _manifest_fallback():  # type: ignore
            return RedirectResponse(url="/ui/manifest.webmanifest", status_code=302)

        # FINAL SPA FALLBACK: Any GET under /ui/* not matching an existing static asset
        # should serve index.html so client-side routing can resolve. This supplements
        # the StaticFiles subclass in cases where Starlette routing returns a 404
        # before our overridden get_response fallback is applied (observed with
        # deep links like /ui/maps returning JSON 404).
        index_path = chosen_path / "index.html"
        if index_path.exists():
            @app.get("/ui/{full_path:path}", include_in_schema=False)
            async def ui_spa_catch_all(full_path: str):  # type: ignore
                if any(full_path.endswith(ext) for ext in (".js", ".css", ".map", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webmanifest")):
                    raise HTTPException(status_code=404, detail="Asset Not Found")
                return _cache_headers(FileResponse(index_path), immutable=False)

            @app.head("/ui/{full_path:path}", include_in_schema=False)
            async def ui_spa_catch_all_head(full_path: str):  # type: ignore
                if any(full_path.endswith(ext) for ext in (".js", ".css", ".map", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webmanifest")):
                    raise HTTPException(status_code=404, detail="Asset Not Found")
                return _cache_headers(Response(status_code=200), immutable=False)
    
    # Include routers
    app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
    # Auth endpoints (login/logout/me)
    app.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
    app.include_router(sensors.router, prefix="/api/v1/sensors", tags=["sensors"])
    app.include_router(navigation.router, prefix="/api/v1/navigation", tags=["navigation"])
    app.include_router(patterns.router, prefix="/api/v1/patterns", tags=["patterns"])
    app.include_router(configuration.router, prefix="/api/v1/config", tags=["configuration"])
    app.include_router(maps.router, prefix="/api/v1/maps", tags=["maps"])
    app.include_router(google_maps.router, prefix="/api/v1/google-maps", tags=["google-maps"])
    app.include_router(weather.router, prefix="/api/v1/weather", tags=["weather"])
    app.include_router(power.router, prefix="/api/v1/power", tags=["power"])
    app.include_router(progress.router, prefix="/api/v1/progress", tags=["progress"])
    app.include_router(rc_control.router, prefix="/api/v1/rc", tags=["rc_control"])
    # Public runtime config for UI (safe values only)
    app.include_router(public_config.router, prefix="/api/v1/public", tags=["public"])
    app.include_router(camera.router, prefix="/api/v1", tags=["camera"])
    app.include_router(websocket.router, prefix="/ws", tags=["websocket"])
    
    # Store start time
    app.state.start_time = time.time()
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
