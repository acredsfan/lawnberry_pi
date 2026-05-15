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
    # TODO(v2): enforce in-memory DB for integration/contract tests to prevent fixture leakage - Issue #1
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
    def _do_reset():
        # Reset via gateway if runtime is available (Phase D+)
        try:
            from backend.src.main import app
            gw = getattr(getattr(app.state, "runtime", None), "command_gateway", None)
            if gw is not None:
                gw.reset_for_testing()
                return
        except Exception:
            pass
        # Fallback: direct dict reset (unit tests without lifespan)
        try:
            from backend.src.api import rest as rest_api

            rest_api._safety_state["emergency_stop_active"] = False
            rest_api._blade_state["active"] = False
            rest_api._emergency_until = 0.0
            rest_api._client_emergency.clear()
            rest_api._legacy_motors_active = False
        except Exception:
            pass

    _do_reset()

    # Reset traction control global singleton
    try:
        import backend.src.services.traction_control_service as tc_module
        tc_module._instance = None
    except Exception:
        pass

    # Reset NavigationService singleton + its emergency latch state.
    # Some earlier tests latch the emergency stop or seed mission state on the
    # singleton; without this reset, subsequent nav tests fail spuriously
    # (e.g. test_go_to_waypoint_* aborting on a stale emergency-stop latch).
    try:
        import backend.src.services.navigation_service as nav_module
        nav_module.NavigationService._instance = None
    except Exception:
        pass

    # Reset auth state (active sessions, password hash)
    try:
        from backend.src.services.auth_service import primary_auth_service
        from backend.src.models.auth_security_config import AuthSecurityConfig
        from backend.src.core import globals as global_state
        from backend.src.api import rest as rest_api

        primary_auth_service.active_sessions.clear()
        primary_auth_service.config = AuthSecurityConfig()  # Reset to defaults (no password_hash)
        primary_auth_service._failed_attempts.clear()
        primary_auth_service._invalidated_session_ids.clear()

        # Also reset the global state copy
        global_state._security_settings = AuthSecurityConfig()

        # Also update the rest module's reference if it has one
        if hasattr(rest_api, '_security_settings'):
            rest_api._security_settings = AuthSecurityConfig()
    except Exception:
        pass

    yield

    _do_reset()

    # Reset traction control global singleton
    try:
        import backend.src.services.traction_control_service as tc_module
        tc_module._instance = None
    except Exception:
        pass

    # Reset NavigationService singleton (post-test cleanup mirror of pre-test).
    try:
        import backend.src.services.navigation_service as nav_module
        nav_module.NavigationService._instance = None
    except Exception:
        pass

    # Reset auth state after test
    try:
        from backend.src.services.auth_service import primary_auth_service
        from backend.src.models.auth_security_config import AuthSecurityConfig
        from backend.src.core import globals as global_state
        from backend.src.api import rest as rest_api
        
        primary_auth_service.active_sessions.clear()
        primary_auth_service.config = AuthSecurityConfig()  # Reset to defaults (no password_hash)
        primary_auth_service._failed_attempts.clear()
        primary_auth_service._invalidated_session_ids.clear()
        
        # Also reset the global state copy
        global_state._security_settings = AuthSecurityConfig()
        
        # Also update the rest module's reference if it has one
        if hasattr(rest_api, '_security_settings'):
            rest_api._security_settings = AuthSecurityConfig()
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

    Also clears app.state.runtime.settings_repository for the duration of each
    test so that _get_settings_repository() (called directly, bypassing
    dependency_overrides) falls back to the isolated file path rather than the
    shared data/lawnberry.db that is left behind by TestClient lifespan tests.
    """

    from backend.src.api.routers import settings as settings_router

    data_dir = tmp_path / "data"
    settings_file = data_dir / "settings.json"
    ui_settings_file = data_dir / "ui_settings.json"
    monkeypatch.setattr(settings_router, "DATA_DIR", data_dir)
    monkeypatch.setattr(settings_router, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_router, "UI_SETTINGS_FILE", ui_settings_file)

    # Temporarily clear the settings_repository on app.state.runtime (if one
    # was wired by a previous TestClient lifespan test).  monkeypatch restores
    # the original value automatically after the test.
    try:
        from backend.src.main import app as _main_app
        _runtime = getattr(_main_app.state, "runtime", None)
        if _runtime is not None and getattr(_runtime, "settings_repository", None) is not None:
            monkeypatch.setattr(_runtime, "settings_repository", None)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def reset_app_state_runtime_and_overrides():
    """Reset app.dependency_overrides between tests.

    Without this, a test that sets `app.dependency_overrides[get_runtime] = ...`
    leaks the override into every subsequent test in the session. We clear
    after each test, regardless of whether the test cleared it explicitly.

    `app.state.runtime` is NOT cleared here — lifespan rebuilds it on the
    next TestClient startup, but if a test ran without TestClient (just
    imports `app`), there is nothing to rebuild and clearing here would
    just hide bugs.
    """
    try:
        from backend.src.main import app
    except Exception:
        # If main.py fails to import (e.g. during very early collection),
        # the other reset fixtures will surface that; this one is a no-op.
        yield
        return

    yield

    try:
        app.dependency_overrides.clear()
    except Exception:
        pass