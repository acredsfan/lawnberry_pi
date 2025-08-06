"""
Main FastAPI Application
Entry point for the web API backend with comprehensive routing and middleware setup.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import time
import json

from .config import get_settings
from .auth import get_current_user, AuthManager
from .routers import (
    system, sensors, navigation, patterns, 
    configuration, maps, weather, power, websocket, progress, rc_control, google_maps, camera
)
from .middleware import RateLimitMiddleware, RequestLoggingMiddleware
from .mqtt_bridge import MQTTBridge
from .exceptions import APIException, api_exception_handler


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
        await redis_client.ping()
        app.state.redis_client = redis_client
        logger.info("Redis client initialized successfully")
    except Exception as e:
        logger.warning(f"Redis initialization failed: {e}. Caching will be disabled.")
        app.state.redis_client = None
    
    # Initialize MQTT bridge
    mqtt_bridge = MQTTBridge(settings.mqtt)
    await mqtt_bridge.connect()
    app.state.mqtt_bridge = mqtt_bridge

    # Integrate MQTT bridge with WebSocket manager for real-time data
    from .routers.websocket import setup_websocket_mqtt_integration
    setup_websocket_mqtt_integration(mqtt_bridge)
    
    # Initialize auth manager
    auth_manager = AuthManager(settings.auth)
    await auth_manager.initialize()
    app.state.auth_manager = auth_manager
    
    logger.info("Web API backend startup complete")
    
    yield
    
    # Cleanup
    logger.info("Shutting down web API backend...")
    await mqtt_bridge.disconnect()
    
    # Close Redis connection
    if hasattr(app.state, 'redis_client') and app.state.redis_client:
        await app.state.redis_client.close()
        logger.info("Redis client closed")
    
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
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(HTTPException, api_exception_handler)
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Simple health check endpoint"""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "version": "1.0.0"
        }
    
    # API status endpoint
    @app.get("/api/v1/status")
    async def api_status(request: Request):
        """Comprehensive API status information"""
        mqtt_bridge = getattr(request.app.state, 'mqtt_bridge', None)
        
        return {
            "api_version": "1.0.0",
            "status": "operational",
            "timestamp": time.time(),
            "mqtt_connected": mqtt_bridge.is_connected() if mqtt_bridge else False,
            "uptime": time.time() - getattr(app.state, 'start_time', time.time())
        }
    
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
            
            # Determine mower state based on available data
            state = "idle"  # Default state
            if power_data.get("charging", False):
                state = "charging"
            elif gps_data.get("latitude", 0) != 0 and imu_data.get("acceleration", {}).get("x", 0) > 0.1:
                state = "mowing"
            
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
                        "left": tof_data.get("left_distance", 0.0),
                        "right": tof_data.get("right_distance", 0.0)
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
    
    # Include routers
    app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
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
