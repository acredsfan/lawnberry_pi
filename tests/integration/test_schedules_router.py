"""Integration tests for /api/v2/schedules alias router (T9)."""
import httpx
import pytest

from backend.src.main import app

BASE = "http://test"


def _transport():
    return httpx.ASGITransport(app=app)


@pytest.mark.asyncio
async def test_post_schedule_visible_at_planning_jobs_endpoint():
    """A schedule created via POST /schedules must appear in GET /planning/jobs."""
    async with httpx.AsyncClient(transport=_transport(), base_url=BASE) as client:
        payload = {
            "name": "Evening Mow",
            "schedule": "18:00",
            "zones": ["back"],
            "priority": 2,
            "enabled": True,
        }
        create_resp = await client.post("/api/v2/schedules", json=payload)
        assert create_resp.status_code == 201, create_resp.text
        body = create_resp.json()
        assert "id" in body
        job_id = body["id"]
        assert body["name"] == "Evening Mow"
        assert body["zones"] == ["back"]
        assert body["enabled"] is True

        # Verify visible at /planning/jobs
        list_resp = await client.get("/api/v2/planning/jobs")
        assert list_resp.status_code == 200
        ids = [j["id"] for j in list_resp.json()]
        assert job_id in ids, f"{job_id!r} not found in /planning/jobs list: {ids}"

        # Cleanup
        await client.delete(f"/api/v2/schedules/{job_id}")


@pytest.mark.asyncio
async def test_enable_disable_toggles_persisted_state():
    """disable then enable toggles enabled field persistently."""
    async with httpx.AsyncClient(transport=_transport(), base_url=BASE) as client:
        # Create
        payload = {
            "name": "Toggle Test",
            "schedule": "07:00",
            "zones": ["front"],
            "priority": 1,
            "enabled": True,
        }
        create_resp = await client.post("/api/v2/schedules", json=payload)
        assert create_resp.status_code == 201, create_resp.text
        job_id = create_resp.json()["id"]

        # Disable
        dis_resp = await client.post(f"/api/v2/schedules/{job_id}/disable")
        assert dis_resp.status_code == 200, dis_resp.text

        # Verify disabled
        get_resp = await client.get(f"/api/v2/schedules/{job_id}")
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["enabled"] is False

        # Enable
        en_resp = await client.post(f"/api/v2/schedules/{job_id}/enable")
        assert en_resp.status_code == 200, en_resp.text

        # Verify enabled
        get_resp2 = await client.get(f"/api/v2/schedules/{job_id}")
        assert get_resp2.status_code == 200, get_resp2.text
        assert get_resp2.json()["enabled"] is True

        # Cleanup
        await client.delete(f"/api/v2/schedules/{job_id}")


@pytest.mark.asyncio
async def test_list_schedules_returns_list():
    """GET /schedules always returns a list."""
    async with httpx.AsyncClient(transport=_transport(), base_url=BASE) as client:
        resp = await client.get("/api/v2/schedules")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_schedule_not_found():
    """GET /schedules/{id} with unknown id returns 404."""
    async with httpx.AsyncClient(transport=_transport(), base_url=BASE) as client:
        resp = await client.get("/api/v2/schedules/nonexistent-id-xyz")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_schedule_removes_record():
    """DELETE /schedules/{id} removes the record (204) and it no longer appears."""
    async with httpx.AsyncClient(transport=_transport(), base_url=BASE) as client:
        payload = {"name": "Delete Me", "schedule": "09:00", "zones": [], "priority": 1}
        create_resp = await client.post("/api/v2/schedules", json=payload)
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/v2/schedules/{job_id}")
        assert del_resp.status_code == 204

        # Gone from list
        list_resp = await client.get("/api/v2/schedules")
        assert job_id not in [j["id"] for j in list_resp.json()]


@pytest.mark.asyncio
async def test_delete_nonexistent_schedule_returns_404():
    """DELETE /schedules/{id} with unknown id returns 404."""
    async with httpx.AsyncClient(transport=_transport(), base_url=BASE) as client:
        resp = await client.delete("/api/v2/schedules/nonexistent-id-xyz")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_put_schedule_updates_fields():
    """PUT /schedules/{id} updates mutable fields."""
    async with httpx.AsyncClient(transport=_transport(), base_url=BASE) as client:
        payload = {"name": "Original", "schedule": "10:00", "zones": ["z1"], "priority": 1}
        create_resp = await client.post("/api/v2/schedules", json=payload)
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        update_resp = await client.put(
            f"/api/v2/schedules/{job_id}",
            json={"name": "Updated", "schedule": "11:00", "zones": ["z2"], "priority": 3},
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["name"] == "Updated"
        assert updated["schedule"] == "11:00"
        assert updated["zones"] == ["z2"]
        assert updated["priority"] == 3

        # Cleanup
        await client.delete(f"/api/v2/schedules/{job_id}")
