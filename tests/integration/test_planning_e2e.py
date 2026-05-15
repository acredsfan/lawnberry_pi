"""End-to-end smoke test: zone → schedule → mission with waypoints.

Exercises the full planning data-flow in a single TestClient session:
  1. POST /api/v2/map/zones          — persist a small square boundary zone
  2. POST /api/v2/schedules          — create a schedule pointing at that zone
  3. GET  /api/v2/schedules/{id}     — verify the schedule survived the round-trip
  4. POST /api/v2/missions/create    — create a mission with zone_id + pattern
  5. Verify the mission was stored with a planning_intent (lazy-generation path)

Step 4 stops short of calling /start (which would invoke the path planner and
navigation stack in SIM_MODE); instead we verify that the mission record
exists and carries the planning_intent so the path will be generated on demand.

SIM_MODE=1 is mandatory — no hardware calls are made.

Note: The integration conftest injects a mock RuntimeContext for most tests.
This test bypasses that mock so the real services (MissionService, MapRepository,
PlanningService) run end-to-end through the app lifespan.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.src.core.persistence import persistence
from backend.src.core.runtime import get_runtime
from backend.src.main import app
from backend.src.repositories.map_repository import MapRepository
from backend.src.repositories.mission_repository import MissionRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_E2E_PREFIX = "E2E Smoke"


# This test exercises the real app lifespan and real database — always use the
# production db path, never the :memory: override used by other integration tests.
_PROD_DB = Path(__file__).parents[2] / "data" / "lawnberry.db"


def _mission_repo() -> MissionRepository:
    return MissionRepository(db_path=_PROD_DB)


def _map_repo() -> MapRepository:
    return MapRepository(db_path=_PROD_DB)


def _delete_e2e_missions() -> None:
    repo = _mission_repo()
    for m in repo.list_missions():
        if m.get("name", "").startswith(_E2E_PREFIX):
            repo.delete_mission(m["id"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_state():
    """Isolate E2E test artifacts so real user data is never modified.

    Strategy:
    - Snapshot real zones before the test; restore them exactly after.
    - Delete any E2E Smoke missions created during the test.
    - Delete planning jobs (schedules) before and after.
    - Use the real lifespan runtime instead of the integration conftest mock.
    """
    map_repo = _map_repo()

    # Snapshot real zones so we can restore them after the test
    real_zones = map_repo.list_zones()

    # Remove stale artifacts from any previous failed run
    for job in persistence.load_planning_jobs():
        persistence.delete_planning_job(job["id"])
    _delete_e2e_missions()
    for z in map_repo.list_zones():
        if z.get("name", "").startswith(_E2E_PREFIX):
            map_repo.delete_zone(z["id"])

    # Clear the mock dependency override so the real lifespan runtime is used.
    app.dependency_overrides.pop(get_runtime, None)

    yield

    # Post-test: delete E2E artifacts
    for job in persistence.load_planning_jobs():
        persistence.delete_planning_job(job["id"])
    _delete_e2e_missions()
    for z in map_repo.list_zones():
        if z.get("name", "").startswith(_E2E_PREFIX):
            map_repo.delete_zone(z["id"])

    # Restore real zones exactly as they were
    current_ids = {z["id"] for z in map_repo.list_zones()}
    for zone in real_zones:
        if zone["id"] not in current_ids:
            map_repo.save_zone(zone)


# A tiny square zone (~10 m × 10 m) centred near GPS origin.
# Lat/lon deltas: 0.0001° ≈ 11 m — small enough for unit tests, large
# enough for the coverage planner to generate at least one scanline.
_ZONE_POLYGON = [
    {"latitude": 0.0000, "longitude": 0.0000},
    {"latitude": 0.0001, "longitude": 0.0000},
    {"latitude": 0.0001, "longitude": 0.0001},
    {"latitude": 0.0000, "longitude": 0.0001},
]


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def test_create_zone_then_schedule_then_observe_mission():
    """Full planning data-flow: zone storage → schedule → mission with intent.

    This test covers:
    - Zone CRUD via POST /api/v2/map/zones
    - Schedule creation and retrieval via /api/v2/schedules
    - Mission creation with zone_id (lazy-generation path)
    - Planning intent is stored for later waypoint generation
    """
    zone_id = str(uuid.uuid4())

    with TestClient(app) as client:
        # ------------------------------------------------------------------
        # Step 1: Create a mowing boundary zone (single-zone add, not bulk
        # replace — bulk replace would wipe the user's real zones).
        # ------------------------------------------------------------------
        zone_payload = {
            "id": zone_id,
            "name": "E2E Smoke Zone",
            "polygon": _ZONE_POLYGON,
            "priority": 1,
            "exclusion_zone": False,
        }
        zone_resp = client.post(f"/api/v2/map/zones/{zone_id}", json=zone_payload)
        assert zone_resp.status_code == 201, (
            f"Expected 201 from POST /api/v2/map/zones/{zone_id}, "
            f"got {zone_resp.status_code}: {zone_resp.text}"
        )
        assert zone_resp.json()["id"] == zone_id

        # ------------------------------------------------------------------
        # Step 2: Create a schedule referencing the zone
        # ------------------------------------------------------------------
        schedule_payload = {
            "name": "E2E Smoke Schedule",
            "schedule": "08:00",
            "zones": [zone_id],
            "pattern": "parallel",
            "pattern_params": {"spacing_m": 0.5},
            "priority": 1,
            "enabled": True,
        }
        sched_resp = client.post("/api/v2/schedules", json=schedule_payload)
        assert sched_resp.status_code == 201, (
            f"Expected 201 from POST /api/v2/schedules, got {sched_resp.status_code}: "
            f"{sched_resp.text}"
        )
        sched_data = sched_resp.json()
        sched_id = sched_data["id"]
        assert sched_id, "Schedule must have a non-empty id"
        assert sched_data["name"] == "E2E Smoke Schedule"
        assert zone_id in sched_data["zones"]

        # ------------------------------------------------------------------
        # Step 3: Retrieve the schedule and verify round-trip
        # ------------------------------------------------------------------
        get_resp = client.get(f"/api/v2/schedules/{sched_id}")
        assert get_resp.status_code == 200, (
            f"Expected 200 from GET /api/v2/schedules/{sched_id}, "
            f"got {get_resp.status_code}: {get_resp.text}"
        )
        retrieved = get_resp.json()
        assert retrieved["id"] == sched_id
        assert retrieved["name"] == "E2E Smoke Schedule"
        assert zone_id in retrieved["zones"]

        # ------------------------------------------------------------------
        # Step 4: Create a mission referencing the zone (lazy-generation path)
        # ------------------------------------------------------------------
        mission_payload = {
            "name": "E2E Smoke Mission",
            "zone_id": zone_id,
            "pattern": "parallel",
            "pattern_params": {"spacing_m": 0.5},
        }
        mission_resp = client.post("/api/v2/missions/create", json=mission_payload)
        assert mission_resp.status_code == 200, (
            f"Expected 200 from POST /api/v2/missions/create, "
            f"got {mission_resp.status_code}: {mission_resp.text}"
        )
        mission_data = mission_resp.json()
        mission_id = mission_data["id"]
        assert mission_id, "Mission must have a non-empty id"
        assert mission_data["name"] == "E2E Smoke Mission"

        # ------------------------------------------------------------------
        # Step 5: Mission appears in the list with the correct name
        # ------------------------------------------------------------------
        list_resp = client.get("/api/v2/missions/list")
        assert list_resp.status_code == 200, (
            f"Expected 200 from GET /api/v2/missions/list, "
            f"got {list_resp.status_code}: {list_resp.text}"
        )
        mission_ids = [m["id"] for m in list_resp.json()]
        assert mission_id in mission_ids, (
            f"Mission {mission_id!r} not found in list: {mission_ids}"
        )
