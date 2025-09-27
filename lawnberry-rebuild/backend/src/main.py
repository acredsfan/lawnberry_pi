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


# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "lawnberry-backend"}
