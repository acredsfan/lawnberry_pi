from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from backend.src.models.hardware_config import HardwareConfig
from backend.src.services.autonomy_qualification_service import AutonomyQualificationError
from backend.src.services.autonomy_readiness_service import AutonomyReadinessService
from backend.src.services.blade_controller import BladeHealth


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
    def __init__(self, *, running: bool = True, sample_age_s: float = 0.1):
        self.running = running
        self.sample_age_s = sample_age_s

    def status_dict(self) -> dict:
        return {
            "running": self.running,
            "fast_loop_age_s": self.sample_age_s,
            "imu_sample_age_s": self.sample_age_s,
            "tof_left_sample_age_s": self.sample_age_s,
            "tof_right_sample_age_s": self.sample_age_s,
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


@dataclass
class Runtime:
    hardware_config: HardwareConfig
    command_gateway: object | None = FakeGateway()
    robohat: object | None = None
    safety_state: dict | None = None
    live_safety: object | None = FakeLiveSafety()
    qualification_service: object | None = field(default_factory=FakeQualification)


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
