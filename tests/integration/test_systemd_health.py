import httpx
import pytest

from backend.src.main import app


@pytest.mark.asyncio
async def test_health_liveness_ok():
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
		resp = await client.get("/api/v2/health/liveness")
		assert resp.status_code == 200
		body = resp.json()
		assert body.get("status") == "ok"
		assert body.get("service") == "lawnberry-backend"
		assert isinstance(body.get("uptime_seconds"), (int, float))
		assert body.get("uptime_seconds") >= 0


@pytest.mark.asyncio
async def test_health_readiness_database_ok():
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
		resp = await client.get("/api/v2/health/readiness")
		assert resp.status_code == 200
		body = resp.json()
		assert "components" in body
		db = body["components"].get("database")
		assert isinstance(db, dict)
		assert db.get("ok") is True
		assert body.get("ready") is True
		assert body.get("status") == "ready"
		telemetry = body["components"].get("telemetry")
		assert isinstance(telemetry, dict)
		assert telemetry.get("state") in {"idle", "running"}

