"""Global test configuration for LawnBerry Pi v2."""
import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator
import asyncio

# Ensure SIM_MODE=1 for all tests unless explicitly overridden
os.environ.setdefault("SIM_MODE", "1")


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables and configurations."""
    # Ensure simulation mode for tests
    os.environ["SIM_MODE"] = "1"
    # Set test database path if needed
    os.environ.setdefault("DB_PATH", ":memory:")
    # Reduce log noise in tests
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    
    yield
    
    # Cleanup if necessary
    pass


@pytest_asyncio.fixture
async def test_client():
    """Create a test client for the FastAPI application."""
    from backend.src.main import app
    import httpx
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client