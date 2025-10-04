import pytest


@pytest.mark.asyncio
async def test_manual_teleop_endpoint_validates_input(test_client):
    try:
        from backend.src.api.motors import router as _router  # noqa: F401
    except Exception:
        pytest.skip("Teleop API not implemented yet")

    # Valid input
    resp = await test_client.post("/api/v2/motors/drive", json={"throttle": 0.5, "turn": -0.5})
    assert resp.status_code in (200, 501)
    data = resp.json()
    assert "pwm" in data or "message" in data or "detail" in data

    # Invalid input (out of range)
    resp2 = await test_client.post("/api/v2/motors/drive", json={"throttle": 2.0, "turn": 0.0})
    assert resp2.status_code in (400, 422)
