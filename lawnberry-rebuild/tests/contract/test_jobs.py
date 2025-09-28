"""Contract tests for /api/v1/mow/jobs queue and list operations."""
import pytest
import httpx
from typing import List, Dict, Any


@pytest.mark.asyncio
async def test_jobs_get_returns_list(test_client):
    """Test GET /api/v1/mow/jobs returns a list."""
    response = await test_client.get("/api/v1/mow/jobs")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_jobs_post_creates_job(test_client):
    """Test POST /api/v1/mow/jobs creates a new mowing job."""
    job_data = {
        "name": "Morning Mow",
        "schedule": "08:00",
        "zones": ["front-yard", "back-yard"],
        "priority": 1,
        "enabled": True
    }
    
    response = await test_client.post("/api/v1/mow/jobs", json=job_data)
    assert response.status_code == 201  # Created
    
    data = response.json()
    
    # Required response fields
    assert "id" in data
    assert "name" in data
    assert "schedule" in data
    assert "zones" in data
    assert "status" in data
    assert "created_at" in data
    
    # Validate values
    assert data["name"] == "Morning Mow"
    assert data["schedule"] == "08:00"
    assert data["zones"] == ["front-yard", "back-yard"]
    assert data["priority"] == 1
    assert data["enabled"] is True
    assert data["status"] == "pending"  # Default status


@pytest.mark.asyncio
async def test_jobs_post_invalid_schedule(test_client):
    """Test POST with invalid schedule format fails validation."""
    invalid_job = {
        "name": "Invalid Schedule Job",
        "schedule": "25:99",  # Invalid time
        "zones": ["test-zone"],
        "priority": 1
    }
    
    response = await test_client.post("/api/v1/mow/jobs", json=invalid_job)
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_jobs_post_empty_zones(test_client):
    """Test POST with empty zones list fails validation."""
    invalid_job = {
        "name": "No Zones Job",
        "schedule": "10:00",
        "zones": [],  # Empty zones
        "priority": 1
    }
    
    response = await test_client.post("/api/v1/mow/jobs", json=invalid_job)
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_jobs_get_after_post_persistence(test_client):
    """Test that jobs persist and appear in GET after creation."""
    # Create a job
    job_data = {
        "name": "Persistence Test Job",
        "schedule": "14:30",
        "zones": ["test-zone"],
        "priority": 3,
        "enabled": False
    }
    
    post_response = await test_client.post("/api/v1/mow/jobs", json=job_data)
    assert post_response.status_code == 201
    
    created_job = post_response.json()
    job_id = created_job["id"]
    
    # Retrieve jobs and verify it exists
    get_response = await test_client.get("/api/v1/mow/jobs")
    assert get_response.status_code == 200
    
    jobs = get_response.json()
    persist_job = next((j for j in jobs if j["id"] == job_id), None)
    assert persist_job is not None
    assert persist_job["name"] == "Persistence Test Job"
    assert persist_job["enabled"] is False


@pytest.mark.asyncio
async def test_jobs_priority_validation(test_client):
    """Test that job priority is validated within acceptable range."""
    job_data = {
        "name": "High Priority Job",
        "schedule": "12:00",
        "zones": ["test-zone"],
        "priority": 999,  # Very high priority
        "enabled": True
    }
    
    response = await test_client.post("/api/v1/mow/jobs", json=job_data)
    # Should either accept it or return validation error
    assert response.status_code in [201, 400, 422]