"""Global test configuration for LawnBerry Pi v2."""
import os
import sys
from pathlib import Path
import pytest
import pytest_asyncio
from typing import AsyncGenerator
import asyncio

# Ensure repository root on sys.path for 'backend' imports and compat stubs
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Make optional dependency stubs importable in all tests (bcrypt, pyotp, google, psutil)
compat_stubs = ROOT / "backend" / "src" / "compat_stubs"
if compat_stubs.exists():
    p = str(compat_stubs)
    if p not in sys.path:
        sys.path.insert(0, p)

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