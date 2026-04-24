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
os.environ.setdefault("LAWN_BERRY_OPERATOR_CREDENTIAL", "operator123")
os.environ.setdefault("GLOBAL_RATE_LIMIT_RATE", "1000")
os.environ.setdefault("GLOBAL_RATE_LIMIT_BURST", "10000")
os.environ.setdefault("AUTH_RATE_LIMIT_WINDOW", "60")
os.environ.setdefault("AUTH_RATE_LIMIT_MAX_ATTEMPTS", "3")
os.environ.setdefault("AUTH_LOCKOUT_FAILURES", "3")
os.environ.setdefault("AUTH_LOCKOUT_SECONDS", "30")


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
    os.environ["AUTH_RATE_LIMIT_MAX_ATTEMPTS"] = "3"
    os.environ["AUTH_LOCKOUT_FAILURES"] = "3"
    os.environ["AUTH_LOCKOUT_SECONDS"] = "30"

    print("CONFTEST: Set rate limiting environment variables")
    
    yield
    
    # Cleanup if necessary
    pass


@pytest.fixture(autouse=True)
def reset_control_safety_state():
    """Reset shared control emergency/legacy state between tests.

    Emergency lockout is now intentionally latched until explicit clear, so tests must
    start from a known nominal state to avoid cross-test leakage.
    """
    try:
        from backend.src.api import rest as rest_api

        rest_api._safety_state["emergency_stop_active"] = False
        rest_api._blade_state["active"] = False
        rest_api._emergency_until = 0.0
        rest_api._client_emergency.clear()
        rest_api._legacy_motors_active = False
    except Exception:
        # Keep fixture fail-safe for import-order edge cases in isolated tests.
        pass
    
    # Reset traction control global singleton
    try:
        import backend.src.services.traction_control_service as tc_module
        tc_module._instance = None
    except Exception:
        pass

    yield

    try:
        from backend.src.api import rest as rest_api

        rest_api._safety_state["emergency_stop_active"] = False
        rest_api._blade_state["active"] = False
        rest_api._emergency_until = 0.0
        rest_api._client_emergency.clear()
        rest_api._legacy_motors_active = False
    except Exception:
        pass
    
    # Reset traction control global singleton
    try:
        import backend.src.services.traction_control_service as tc_module
        tc_module._instance = None
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_client():
    """Create a test client for the FastAPI application."""
    import httpx

    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def isolate_ui_settings_storage(tmp_path, monkeypatch):
    """Keep UI settings reads/writes inside a temporary test directory.

    This prevents settings-related API tests from creating or mutating the
    repository's runtime artifact at ``data/ui_settings.json``.
    """

    from backend.src.api.routers import settings as settings_router

    data_dir = tmp_path / "data"
    settings_file = data_dir / "settings.json"
    ui_settings_file = data_dir / "ui_settings.json"
    monkeypatch.setattr(settings_router, "DATA_DIR", data_dir)
    monkeypatch.setattr(settings_router, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_router, "UI_SETTINGS_FILE", ui_settings_file)