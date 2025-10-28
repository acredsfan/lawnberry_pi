"""Global test configuration for LawnBerry Pi v2."""
import asyncio
import importlib
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

collect_ignore = [
    "unit/test_health_endpoints.py",
    # Avoid module name collision with integration/test_auth_security_levels.py
    "unit/test_auth_security_levels.py",
]


def pytest_ignore_collect(collection_path, config):  # pragma: no cover - hook signature
    try:
        rel = str(collection_path)
        return (
            collection_path.match("tests/unit/test_health_endpoints.py")
            or collection_path.match("tests/unit/test_auth_security_levels.py")
        )
    except AttributeError:
        return False

# Ensure repository root on sys.path for 'backend' imports and compat stubs
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Make optional dependency stubs importable in all tests (bcrypt, pyotp, google, psutil)
compat_stubs = ROOT / "backend" / "src" / "compat_stubs"


def _ensure_optional_dependency(module_name: str) -> None:
    if module_name in sys.modules:
        return
    try:
        importlib.import_module(module_name)
        return
    except ImportError:
        if compat_stubs.exists():
            stub_path = str(compat_stubs)
            if stub_path not in sys.path:
                sys.path.insert(0, stub_path)
            importlib.import_module(module_name)


for optional_module in ("bcrypt", "pyotp", "google", "jwt", "psutil", "timezonefinder"):
    try:
        _ensure_optional_dependency(optional_module)
    except ImportError:
        # Allow missing optional dependencies when no stub is present.
        pass

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

    # Make rate limiters permissive for testing
    os.environ["GLOBAL_RATE_LIMIT_RATE"] = "1000"
    os.environ["GLOBAL_RATE_LIMIT_BURST"] = "10000"
    os.environ["AUTH_RATE_LIMIT_WINDOW"] = "60"
    os.environ["AUTH_RATE_LIMIT_MAX_ATTEMPTS"] = "1000"
    os.environ["AUTH_LOCKOUT_FAILURES"] = "1000"
    os.environ["AUTH_LOCKOUT_SECONDS"] = "0"

    print("CONFTEST: Set rate limiting environment variables")
    
    yield
    
    # Cleanup if necessary
    pass


@pytest_asyncio.fixture
async def test_client():
    """Create a test client for the FastAPI application."""
    import httpx

    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client