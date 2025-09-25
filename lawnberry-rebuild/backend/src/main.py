from fastapi import FastAPI
from .api.rest import router as rest_router

app = FastAPI(title="LawnBerry Pi v2")
app.include_router(rest_router, prefix="/api/v2")
