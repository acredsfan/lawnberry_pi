import httpx
import pytest

from backend.src.main import app


@pytest.mark.asyncio
async def test_get_planning_jobs_returns_list():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/planning/jobs")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "Morning Mow",
            "schedule": "08:00",
            "zones": ["front", "back"],
            "priority": 1,
            "enabled": True
        }
        resp = await client.post("/api/v2/planning/jobs", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["name"] == "Morning Mow"
        assert body["zones"] == ["front", "back"]
        assert body["enabled"] is True


@pytest.mark.asyncio
async def test_delete_planning_job_removes_job():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # First create a job
                payload = {
                        "name": "Test Job",
                        "schedule": "12:00",
                        "zones": ["test"],
                        "priority": 1,
                        "enabled": True
                }
                create_resp = await client.post("/api/v2/planning/jobs", json=payload)
                assert create_resp.status_code == 201
                job_id = create_resp.json()["id"]
        
                # Then delete it
                delete_resp = await client.delete(f"/api/v2/planning/jobs/{job_id}")
                assert delete_resp.status_code == 204
        
                # Verify it's gone by checking the list
                list_resp = await client.get("/api/v2/planning/jobs")
                jobs = list_resp.json()
                job_ids = [job["id"] for job in jobs]
                assert job_id not in job_ids


@pytest.mark.asyncio
async def test_delete_nonexistent_job_returns_404():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.delete("/api/v2/planning/jobs/nonexistent-id")
                assert resp.status_code == 404
