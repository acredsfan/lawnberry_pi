from dataclasses import dataclass

from fastapi.testclient import TestClient

from backend.src.core.runtime import get_runtime
from backend.src.main import app
from backend.src.models.hardware_config import HardwareConfig
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
    command_gateway: object
    robohat: object | None
    safety_state: dict


def test_autonomy_readiness_endpoint_returns_stable_reason_codes(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 5 Model B Rev 1.0")
    hardware = HardwareConfig.model_validate(
        {
            "imu_type": "bno085-uart",
            "blade_controller": "ibt-4",
            "blade": {
                "controller": "ibt-4",
                "allow_autonomous": False,
                "pins": {"in1": 24, "in2": 25},
            },
        }
    )
    runtime = Runtime(
        hardware_config=hardware,
        command_gateway=FakeGateway(),
        robohat=None,
        safety_state={},
    )
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        resp = TestClient(app).get("/api/v2/autonomy/readiness")
    finally:
        app.dependency_overrides.pop(get_runtime, None)

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ready"] is False
    assert "BLADE_BACKEND_NOT_AUTONOMY_APPROVED" in payload["blocking_reason_codes"]
    assert payload["pin_report"]["ok"] is True
