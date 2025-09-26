import pytest
import httpx
from backend.src.main import app


@pytest.mark.asyncio
async def test_get_planning_jobs_returns_list():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/planning/jobs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_post_planning_job_creates_job():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "Morning Mow",
            "schedule": "08:00",
            "zones": ["front", "back"],
            "priority": 1
        }
        resp = await client.post("/api/v2/planning/jobs", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["name"] == "Morning Mow"
        assert body["zones"] == ["front", "back"]


@pytest.mark.asyncio
async def test_delete_planning_job_removes_job():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # First create a job
        payload = {
            "name": "Test Job",
            "schedule": "10:00", 
            "zones": ["test"]
        }
        create_resp = await client.post("/api/v2/planning/jobs", json=payload)
        job_id = create_resp.json()["id"]
        
        # Then delete it
        delete_resp = await client.delete(f"/api/v2/planning/jobs/{job_id}")
        assert delete_resp.status_code == 204
        
        # Verify it's gone by checking the list
        list_resp = await client.get("/api/v2/planning/jobs")
        job_ids = [job["id"] for job in list_resp.json()]
        assert job_id not in job_ids
