from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from backend.src.models.hardware_config import HardwareConfig
from backend.src.models.mission import Mission, MissionLegType, MissionWaypoint
from backend.src.models.navigation_state import Position
from backend.src.services.autonomy_qualification_service import AutonomyQualificationError
from backend.src.services.autonomy_readiness_service import AutonomyReadinessService
from backend.src.services.blade_controller import BladeHealth
from backend.src.services.localization_service import CanonicalPose


class FakeBladeController:
    async def initialize(self) -> bool:
        return True

    async def health(self) -> BladeHealth:
        return BladeHealth(
            backend="ibt-4",
            online=True,
            initialized=True,
            commanded_active=False,
            acknowledged_active=False,
            allow_autonomous=True,
            pins={"in1": 24, "in2": 25},
        )


class FakeGateway:
    def _get_blade_controller(self):
        return FakeBladeController()


class FakeLiveSafety:
    def __init__(
        self,
        *,
        running: bool = True,
        sample_age_s: float = 0.1,
        tof_owner_running: bool = True,
    ):
        self.running = running
        self.sample_age_s = sample_age_s
        self.tof_owner_running = tof_owner_running

    def status_dict(self) -> dict:
        return {
            "running": self.running,
            "fast_loop_age_s": self.sample_age_s,
            "imu_sample_age_s": self.sample_age_s,
            "tof_left_sample_age_s": self.sample_age_s,
            "tof_right_sample_age_s": self.sample_age_s,
            "tof_acquisition_owner_running": self.tof_owner_running,
            "tof_left_failure_rate": 0.0,
            "tof_right_failure_rate": 0.0,
            "tof_left_window_samples": 10,
            "tof_right_window_samples": 10,
            "faults": [],
        }


class FakeQualification:
    def assert_current(self):
        return SimpleNamespace(record=SimpleNamespace(record_id="qualification-ok"))


class BlockingQualification:
    def assert_current(self):
        evaluation = SimpleNamespace(
            reason_codes=["QUALIFICATION_EVIDENCE_MISSING"],
            remediation={
                "QUALIFICATION_EVIDENCE_MISSING": "Run qualification.",
            },
        )
        raise AutonomyQualificationError(evaluation)


class FakeLocalization:
    imu_valid = True

    def canonical_pose(self) -> CanonicalPose:
        position = Position(latitude=39.1, longitude=-84.1, accuracy=0.03)
        return CanonicalPose(
            body_center=position,
            antenna_position=position,
            heading_deg=90.0,
            heading_source="imu",
            position_source="gps",
            accuracy_m=0.03,
            gps_sample_id=42,
            sample_monotonic_s=100.0,
            gps_fix_age_s=0.1,
            rtk_status="RTK_FIXED",
            antenna_correction_state="applied",
            dead_reckoning_active=False,
            cached=False,
        )


class FakeOperatingArea:
    valid = True
    validity_state = "valid"
    revision_hash = "revision-1"
    source = "test"

    def __init__(self, *, path_safe: bool = True):
        self.path_safe = path_safe

    def path_is_safe(self, positions, margin_m=0.0):
        return self.path_safe and len(positions) >= 2 and margin_m > 0


class FakeNavigation:
    autonomous_max_gps_fix_age_s = 2.0
    autonomous_max_gps_accuracy_m = 0.25
    coverage_endpoint_clearance_m = 0.25

    def __init__(self, *, path_safe: bool = True):
        self.area = FakeOperatingArea(path_safe=path_safe)
        self.navigation_state = SimpleNamespace(
            obstacle_avoidance_active=False,
            obstacle_map=[],
        )

    def get_operating_area_snapshot(self):
        return self.area


class FakeWeather:
    async def get_current_async(self, **_kwargs):
        return {"source": "test", "temperature_c": 20.0, "humidity_percent": 40.0}

    def get_planning_advice(self, _current):
        return {"advice": "proceed", "reasons": []}


class FakeEnergy:
    def admission_snapshot(self, *, mission):
        return {"admitted": bool(mission.waypoints), "soc_percent": 80.0}


@dataclass
class Runtime:
    hardware_config: HardwareConfig
    command_gateway: object | None = FakeGateway()
    robohat: object | None = None
    safety_state: dict | None = None
    live_safety: object | None = FakeLiveSafety()
    qualification_service: object | None = field(default_factory=FakeQualification)


def _mission_runtime(hardware: HardwareConfig, *, path_safe: bool = True):
    mission_service = SimpleNamespace(mission_statuses={})
    return SimpleNamespace(
        hardware_config=hardware,
        command_gateway=FakeGateway(),
        robohat=None,
        safety_state={},
        live_safety=FakeLiveSafety(),
        qualification_service=FakeQualification(),
        localization=FakeLocalization(),
        navigation=FakeNavigation(path_safe=path_safe),
        mission_service=mission_service,
        weather_service=FakeWeather(),
        energy_service=FakeEnergy(),
    )


def _mission() -> Mission:
    return Mission(
        name="Front yard",
        waypoints=[
            MissionWaypoint(
                lat=39.100001,
                lon=-84.100001,
                leg_type=MissionLegType.MOW,
                blade_on=True,
            )
        ],
        created_at="2026-07-15T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_readiness_blocks_pi4_pin_conflict(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 4 Model B Rev 1.5")
    hardware = HardwareConfig.model_validate(
        {
            "imu_type": "bno085-uart",
            "blade_controller": "ibt-4",
            "blade": {
                "controller": "ibt-4",
                "allow_autonomous": True,
                "pins": {"in1": 24, "in2": 25},
            },
        }
    )

    report = await AutonomyReadinessService(Runtime(hardware, safety_state={})).evaluate()

    assert not report.ready
    assert "HARDWARE_PIN_CONFLICT" in report.blocking_reason_codes


@pytest.mark.asyncio
async def test_readiness_accepts_pi5_explicit_profile(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 5 Model B Rev 1.0")
    hardware = HardwareConfig.model_validate(
        {
            "imu_type": "bno085-uart",
            "blade_controller": "ibt-4",
            "blade": {
                "controller": "ibt-4",
                "allow_autonomous": True,
                "pins": {"in1": 24, "in2": 25},
            },
        }
    )

    report = await AutonomyReadinessService(Runtime(hardware, safety_state={})).evaluate()

    assert report.ready
    assert report.blade is not None
    assert report.blade["qualification_record_id"] == "qualification-ok"


@pytest.mark.asyncio
async def test_readiness_blocks_missing_live_safety_loop(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 5 Model B Rev 1.0")
    hardware = HardwareConfig.model_validate(
        {
            "imu_type": "bno085-uart",
            "blade_controller": "ibt-4",
            "blade": {
                "controller": "ibt-4",
                "allow_autonomous": True,
                "pins": {"in1": 24, "in2": 25},
            },
        }
    )

    report = await AutonomyReadinessService(
        Runtime(hardware, safety_state={}, live_safety=None)
    ).evaluate()

    assert not report.ready
    assert "LIVE_SAFETY_LOOP_HEALTHY" in report.blocking_reason_codes


@pytest.mark.asyncio
async def test_readiness_blocks_missing_qualification_evidence(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 5 Model B Rev 1.0")
    hardware = HardwareConfig.model_validate(
        {
            "imu_type": "bno085-uart",
            "blade_controller": "ibt-4",
            "blade": {
                "controller": "ibt-4",
                "allow_autonomous": True,
                "pins": {"in1": 24, "in2": 25},
            },
        }
    )

    report = await AutonomyReadinessService(
        Runtime(
            hardware,
            safety_state={},
            qualification_service=BlockingQualification(),
        )
    ).evaluate()

    assert not report.ready
    assert "QUALIFICATION_EVIDENCE_MISSING" in report.blocking_reason_codes


@pytest.mark.asyncio
async def test_readiness_blocks_stale_live_safety_sample(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 5 Model B Rev 1.0")
    hardware = HardwareConfig.model_validate(
        {
            "imu_type": "bno085-uart",
            "blade_controller": "ibt-4",
            "blade": {
                "controller": "ibt-4",
                "allow_autonomous": True,
                "pins": {"in1": 24, "in2": 25},
            },
        }
    )

    report = await AutonomyReadinessService(
        Runtime(hardware, safety_state={}, live_safety=FakeLiveSafety(sample_age_s=2.0))
    ).evaluate()

    assert not report.ready
    assert "LIVE_SAFETY_LOOP_HEALTHY" in report.blocking_reason_codes


@pytest.mark.asyncio
async def test_readiness_blocks_missing_tof_acquisition_owner(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 5 Model B Rev 1.0")
    hardware = HardwareConfig.model_validate(
        {
            "imu_type": "bno085-uart",
            "blade_controller": "ibt-4",
            "blade": {
                "controller": "ibt-4",
                "allow_autonomous": True,
                "pins": {"in1": 24, "in2": 25},
            },
        }
    )

    report = await AutonomyReadinessService(
        Runtime(
            hardware,
            safety_state={},
            live_safety=FakeLiveSafety(tof_owner_running=False),
        )
    ).evaluate()

    assert not report.ready
    assert "TOF_ACQUISITION_OWNER_HEALTHY" in report.blocking_reason_codes


@pytest.mark.asyncio
async def test_mission_admission_snapshot_contains_all_canonical_facts(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 5 Model B Rev 1.0")
    hardware = HardwareConfig.model_validate(
        {
            "imu_type": "bno085-uart",
            "blade_controller": "ibt-4",
            "blade": {
                "controller": "ibt-4",
                "allow_autonomous": True,
                "pins": {"in1": 24, "in2": 25},
            },
        }
    )

    report = await AutonomyReadinessService(_mission_runtime(hardware)).evaluate(
        mission=_mission()
    )

    assert report.ready
    assert report.snapshot["localization"]["rtk_status"] == "RTK_FIXED"
    assert report.snapshot["operating_area"]["revision"] == "revision-1"
    assert report.snapshot["path"]["safe"] is True
    assert report.snapshot["weather"]["advice"]["advice"] == "proceed"
    assert report.snapshot["energy"]["admitted"] is True


@pytest.mark.asyncio
async def test_mission_admission_fails_closed_when_path_is_not_safe(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 5 Model B Rev 1.0")
    hardware = HardwareConfig.model_validate(
        {
            "imu_type": "bno085-uart",
            "blade_controller": "ibt-4",
            "blade": {
                "controller": "ibt-4",
                "allow_autonomous": True,
                "pins": {"in1": 24, "in2": 25},
            },
        }
    )

    report = await AutonomyReadinessService(
        _mission_runtime(hardware, path_safe=False)
    ).evaluate(mission=_mission())

    assert not report.ready
    assert "MISSION_PATH_SAFE" in report.blocking_reason_codes
