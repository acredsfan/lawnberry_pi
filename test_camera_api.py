#!/usr/bin/env python3
"""
Simplified Web API for Camera Testing
Minimal FastAPI app to test camera streaming functionality.
"""

import time
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the camera router
from src.web_api.routers.camera import router as camera_router

app = FastAPI(
    title="Lawnberry Camera Test API",
    description="Minimal API for testing camera functionality",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

# API status endpoint
@app.get("/api/v1/status")
async def api_status():
    return {
        "api_version": "1.0.0",
        "status": "operational",
        "timestamp": time.time(),
        "mqtt_connected": False,  # Simplified for testing
        "camera_available": True
    }

# Ping endpoint
@app.get("/api/v1/ping")
async def ping():
    return {"status": "ok", "timestamp": time.time()}

# Include camera router
app.include_router(camera_router, prefix="/api/v1", tags=["camera"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
