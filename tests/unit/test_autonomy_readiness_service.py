from dataclasses import dataclass

import pytest

from backend.src.models.hardware_config import HardwareConfig
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


@dataclass
class Runtime:
    hardware_config: HardwareConfig
    command_gateway: object | None = FakeGateway()
    robohat: object | None = None
    safety_state: dict | None = None


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

