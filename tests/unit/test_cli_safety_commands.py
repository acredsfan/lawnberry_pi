import pytest

from backend.src.api.rest import _safety_state
from backend.src.cli import safety_commands
from backend.src.main import app as fastapi_app


@pytest.mark.asyncio
async def test_safety_status_cli_helper_uses_api():
    # Default state should be nominal (emergency_stop_active False)
    _safety_state["emergency_stop_active"] = False
    res = await safety_commands.safety_status(app=fastapi_app, base_url="http://test")
    assert res["ok"] is True
    assert res["safety_state"] in ["nominal", "emergency_stop"]


@pytest.mark.asyncio
async def test_clear_estop_cli_helper_requires_force():
    # Activate emergency, then attempt clear without force
    _safety_state["emergency_stop_active"] = True
    # Without force/confirmation => 422
    res = await safety_commands.clear_estop(app=fastapi_app, force=False, base_url="http://test")
    assert res["status_code"] == 422
    assert _safety_state["emergency_stop_active"] is True

    # With force/confirmation => clears
    res2 = await safety_commands.clear_estop(app=fastapi_app, force=True, base_url="http://test")
    assert res2["status_code"] == 200
    assert res2["body"]["status"] == "EMERGENCY_CLEARED"
    assert _safety_state["emergency_stop_active"] is False
