"""Integration tests for planning jobs persistence.

Verifies that planning jobs survive 'app restart' (a new TestClient context)
by being stored in SQLite via persistence.save_planning_job / load_planning_jobs.
"""

import pytest
from starlette.testclient import TestClient

from backend.src.main import app
from backend.src.core.persistence import persistence


@pytest.fixture(autouse=True)
def _clean_planning_jobs():
    """Remove all planning jobs from the DB before and after each test."""
    for job in persistence.load_planning_jobs():
        persistence.delete_planning_job(job["id"])
    yield
    for job in persistence.load_planning_jobs():
        persistence.delete_planning_job(job["id"])


def test_create_job_survives_app_restart():
    """A job POSTed via one TestClient is visible to a fresh TestClient.

    Jobs are backed by SQLite, so a new TestClient context (simulated restart)
    must still see previously created jobs via persistence.load_planning_jobs().
    """
    payload = {
        "name": "Persistence Test Job",
        "schedule": "06:30",
        "zones": ["zone-a", "zone-b"],
        "priority": 2,
        "enabled": True,
    }

    # First client — create the job
    with TestClient(app) as client1:
        resp = client1.post("/api/v2/planning/jobs", json=payload)
        assert resp.status_code == 201
        job_id = resp.json()["id"]
        assert job_id

    # Second client — simulates app restart; job must still be present
    with TestClient(app) as client2:
        resp2 = client2.get("/api/v2/planning/jobs")
        assert resp2.status_code == 200
        job_ids = [j["id"] for j in resp2.json()]
        assert job_id in job_ids, f"Expected {job_id!r} in {job_ids}"


def test_delete_job_404_after_delete():
    """A job that has been DELETEd must not appear in subsequent GET list."""
    payload = {
        "name": "Delete Me",
        "schedule": "22:00",
        "zones": ["zone-c"],
        "priority": 1,
        "enabled": False,
    }

    with TestClient(app) as client:
        # Create
        create_resp = client.post("/api/v2/planning/jobs", json=payload)
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        # Delete
        delete_resp = client.delete(f"/api/v2/planning/jobs/{job_id}")
        assert delete_resp.status_code == 204

        # Verify gone from list
        list_resp = client.get("/api/v2/planning/jobs")
        assert list_resp.status_code == 200
        job_ids = [j["id"] for j in list_resp.json()]
        assert job_id not in job_ids, f"Job {job_id!r} still present after delete"
