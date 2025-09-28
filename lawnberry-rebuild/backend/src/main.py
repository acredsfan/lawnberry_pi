from fastapi import FastAPI
from contextlib import asynccontextmanager
from .api.rest import router as rest_router, websocket_hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await websocket_hub.start_telemetry_loop()
    yield
    # Shutdown
    await websocket_hub.stop_telemetry_loop()


app = FastAPI(
    title="LawnBerry Pi v2",
    description="Autonomous robotic lawn mower backend API",
    version="2.0.0",
    lifespan=lifespan
)

app.include_router(rest_router, prefix="/api/v2")

# Add v1 API router for contract compliance
from .api.rest_v1 import router as rest_v1_router
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
    return {"status": "healthy", "service": "lawnberry-backend"}
