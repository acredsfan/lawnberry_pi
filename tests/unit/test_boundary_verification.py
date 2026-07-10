from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.src.control.commands import CommandStatus
from backend.src.models import NavigationMode, Position
from backend.src.models.mission import Mission, MissionLifecycleStatus, MissionStatus
from backend.src.models.sensor_data import GpsReading
from backend.src.services.boundary_paths import MOWING_BOUNDARY_CONFIRMED, boundary_file
from backend.src.services.boundary_verification import BoundaryVerificationService
from backend.src.services.geofence_buffer import save_safe_boundary
from backend.src.services.operating_area_service import load_operating_area_snapshot
from backend.src.services.parcel_boundary import BoundaryValidationError


def _square(lat: float = 40.0, lon: float = -75.0, size: float = 0.0004):
    return [
        {"latitude": lat, "longitude": lon},
        {"latitude": lat, "longitude": lon + size},
        {"latitude": lat + size, "longitude": lon + size},
        {"latitude": lat + size, "longitude": lon},
    ]


class FakeMissionService:
    def __init__(self):
        self.missions: dict[str, Mission] = {}
        self.statuses: dict[str, MissionStatus] = {}
        self.start_kwargs: dict | None = None

    async def create_mission(self, name, waypoints):
        mission = Mission(name=name, waypoints=waypoints, created_at=datetime.now(UTC).isoformat())
        self.missions[mission.id] = mission
        self.statuses[mission.id] = MissionStatus(
            mission_id=mission.id,
            status=MissionLifecycleStatus.IDLE,
            total_waypoints=1,
        )
        return mission

    async def start_mission(self, mission_id, **kwargs):
        self.start_kwargs = kwargs
        self.statuses[mission_id].status = MissionLifecycleStatus.RUNNING

    async def get_mission_status(self, mission_id):
        return self.statuses[mission_id]

    async def abort_mission(self, mission_id):
        self.statuses[mission_id].status = MissionLifecycleStatus.ABORTED


class SequenceGps:
    def __init__(self, latitude: float, longitude: float):
        now = datetime.now(UTC)
        self.samples = [
            GpsReading(
                latitude=latitude + index * 1e-10,
                longitude=longitude - index * 1e-10,
                accuracy=0.02,
                speed=0.0,
                rtk_status="RTK_FIXED",
                sample_id=index + 1,
                timestamp=now + timedelta(milliseconds=200 * index),
            )
            for index in range(8)
        ]
        self.index = 0

    @property
    def last_reading(self):
        reading = self.samples[min(self.index, len(self.samples) - 1)]
        self.index += 1
        return reading


class FakeNavigation:
    def __init__(self, snapshot):
        center = Position(latitude=40.0002, longitude=-74.9998, accuracy=0.02)
        self.snapshot = snapshot
        self.navigation_state = SimpleNamespace(
            navigation_mode=NavigationMode.IDLE,
            current_position=center,
            last_gps_fix=datetime.now(UTC),
            dead_reckoning_active=False,
            heading=90.0,
            obstacle_avoidance_active=False,
        )
        self.mower_footprint_radius_m = 0.35
        self.geofence_safety_allowance_m = 0.10
        self.autonomous_max_gps_fix_age_s = 2.0
        self.autonomous_max_gps_accuracy_m = 0.25
        self.stop_calls = 0

    def get_operating_area_snapshot(self):
        return self.snapshot

    async def stop_navigation(self):
        self.stop_calls += 1
        self.navigation_state.navigation_mode = NavigationMode.IDLE
        return True


class FakeGateway:
    async def dispatch_blade(self, command):
        assert command.active is False
        return SimpleNamespace(status=CommandStatus.ACCEPTED)


def _runtime(snapshot):
    nav = FakeNavigation(snapshot)
    missions = FakeMissionService()
    gps = SequenceGps(nav.navigation_state.current_position.latitude, nav.navigation_state.current_position.longitude)
    return SimpleNamespace(
        navigation=nav,
        mission_service=missions,
        command_gateway=FakeGateway(),
        blade_state={"active": False},
        safety_state={"emergency_stop_active": False},
        sensor_manager=SimpleNamespace(gps=gps),
        hardware_config=SimpleNamespace(
            gps_antenna_offset_forward_m=0.0,
            gps_antenna_offset_right_m=0.0,
        ),
    )


def _prepare_area(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))
    points = _square()
    confirmed_path = boundary_file(MOWING_BOUNDARY_CONFIRMED)
    confirmed_path.parent.mkdir(parents=True, exist_ok=True)
    confirmed_path.write_text(
        json.dumps({"coordinates": points, "created_at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    save_safe_boundary(points, buffer_meters=0.05)
    return points, load_operating_area_snapshot()


@pytest.mark.asyncio
async def test_boundary_verification_uses_safe_standoff_and_diagnostic_mission(
    tmp_path,
    monkeypatch,
):
    points, snapshot = _prepare_area(tmp_path, monkeypatch)
    runtime = _runtime(snapshot)
    service = BoundaryVerificationService(
        rtk_min_samples=3,
        rtk_duration_s=0.2,
        rtk_interval_s=0.01,
    )

    session = await service.start(
        points,
        runtime,
        operator_confirmed=True,
        blade_physically_disabled=True,
        route_clear_confirmed=True,
        physical_intervention="Master cutoff within reach",
    )

    first = session["points"][0]
    target = Position(
        latitude=first["approach"]["latitude"],
        longitude=first["approach"]["longitude"],
    )
    assert snapshot.distance_to_boundary(target) == pytest.approx(0.55, abs=0.02)
    assert first["approach"] != first["reference"]

    traveling = await service.next_point(runtime)

    assert traveling["points"][0]["status"] == "traveling"
    assert runtime.mission_service.start_kwargs == {
        "blade_off_diagnostic": True,
        "reuse_heading_alignment": True,
    }
    mission_id = traveling["active_mission_id"]
    mission = runtime.mission_service.missions[mission_id]
    assert all(not waypoint.blade_on for waypoint in mission.waypoints)
    assert mission.waypoints[0].lat == pytest.approx(first["approach"]["latitude"])

    runtime.mission_service.statuses[mission_id].status = MissionLifecycleStatus.COMPLETED
    arrived = await service.status(runtime)
    assert arrived["points"][0]["status"] == "arrived"

    confirmed = await service.confirm_point(runtime)
    evidence = confirmed["points"][0]["evidence"]
    assert confirmed["points"][0]["status"] == "confirmed"
    assert evidence["stationary_rtk"]["accepted_count"] == 3
    assert evidence["averaged_antenna_coordinate"] is not None
    assert evidence["body_center_coordinate"] is not None
    assert evidence["drive_stopped"] is True
    assert evidence["blade_off_confirmed"] is True


@pytest.mark.asyncio
async def test_boundary_verification_requires_explicit_physical_acknowledgements(
    tmp_path,
    monkeypatch,
):
    points, snapshot = _prepare_area(tmp_path, monkeypatch)
    service = BoundaryVerificationService()

    with pytest.raises(BoundaryValidationError, match="acknowledgements"):
        await service.start(
            points,
            _runtime(snapshot),
            operator_confirmed=True,
            blade_physically_disabled=False,
            route_clear_confirmed=True,
            physical_intervention="Master cutoff within reach",
        )


@pytest.mark.asyncio
async def test_recovered_running_leg_becomes_interrupted_not_confirmable(
    tmp_path,
    monkeypatch,
):
    points, snapshot = _prepare_area(tmp_path, monkeypatch)
    runtime = _runtime(snapshot)
    service = BoundaryVerificationService()
    await service.start(
        points,
        runtime,
        operator_confirmed=True,
        blade_physically_disabled=True,
        route_clear_confirmed=True,
        physical_intervention="Master cutoff within reach",
    )
    traveling = await service.next_point(runtime)
    mission_id = traveling["active_mission_id"]
    runtime.mission_service.statuses[mission_id].status = MissionLifecycleStatus.PAUSED

    recovered = BoundaryVerificationService()
    status = await recovered.status(runtime)

    assert status["points"][0]["status"] == "interrupted"
    with pytest.raises(BoundaryValidationError, match="arrived"):
        await recovered.confirm_point(runtime)


@pytest.mark.asyncio
async def test_recovered_created_but_unstarted_leg_becomes_interrupted(
    tmp_path,
    monkeypatch,
):
    points, snapshot = _prepare_area(tmp_path, monkeypatch)
    runtime = _runtime(snapshot)
    service = BoundaryVerificationService()
    session = await service.start(
        points,
        runtime,
        operator_confirmed=True,
        blade_physically_disabled=True,
        route_clear_confirmed=True,
        physical_intervention="Master cutoff within reach",
    )
    mission = await runtime.mission_service.create_mission(
        "Unstarted verification leg",
        [],
    )
    session["target_index"] = 0
    session["active_mission_id"] = mission.id
    session["points"][0]["status"] = "starting"
    session["points"][0]["mission_id"] = mission.id
    service._write(session)

    recovered = await BoundaryVerificationService().status(runtime)

    assert recovered["points"][0]["status"] == "interrupted"
    assert recovered["target_index"] is None
