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
    configuration, maps, weather, power, websocket, progress, rc_control, google_maps
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
        import aioredis
        redis_client = aioredis.from_url(
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
