"""FastAPI application initialization and configuration.

This module sets up the FastAPI application with WebSocket endpoints,
middleware, and configuration management for the LawnBerry Pi v2 system.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

import structlog
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from lawnberry.core.websocket_hub import websocket_hub
from lawnberry.models.websocket_events import MessageType


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    logger.info("Starting LawnBerry API application")
    
    # Start WebSocket hub telemetry loops
    await websocket_hub.start_telemetry_loop()
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down LawnBerry API application")
    await websocket_hub.stop_telemetry_loop()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="LawnBerry Pi API",
        description="Autonomous mower controller API for Raspberry Pi",
        version="2.0.0",
        lifespan=lifespan
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        stats = websocket_hub.get_stats()
        return {
            "status": "healthy",
            "version": "2.0.0",
            "websocket_stats": stats
        }
    
    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """Main WebSocket endpoint for real-time communication."""
        client_id = None
        try:
            client_id = await websocket_hub.connect_client(websocket)
            
            while True:
                data = await websocket.receive_text()
                await websocket_hub.handle_client_message(client_id, data)
                
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected", client_id=client_id)
        except Exception as e:
            logger.error("WebSocket error", client_id=client_id, error=str(e))
        finally:
            if client_id:
                await websocket_hub.disconnect_client(client_id)
    
    # Include API routers
    from .dashboard import router as dashboard_router
    from .manual import router as manual_router  
    from .telemetry import router as telemetry_router
    
    app.include_router(dashboard_router)
    app.include_router(manual_router)
    app.include_router(telemetry_router)
    
    @app.get("/api/v1/websocket/stats")
    async def get_websocket_stats():
        """Get WebSocket hub statistics."""
        return websocket_hub.get_stats()
    
    @app.post("/api/v1/websocket/broadcast")
    async def broadcast_message(topic: str, data: Dict[str, Any]):
        """Broadcast message to WebSocket topic."""
        count = await websocket_hub.broadcast_to_topic(topic, data)
        return {"success": True, "clients_reached": count}
    
    return app


def main() -> None:
    """Main entry point for the application."""
    # Configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "0") == "1"
    log_level = os.getenv("LOG_LEVEL", "INFO").lower()
    
    logger.info("Starting LawnBerry FastAPI server", 
               host=host, port=port, debug=debug, log_level=log_level)
    
    app = create_app()
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        reload=debug
    )