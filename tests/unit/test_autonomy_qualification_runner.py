from __future__ import annotations

from types import SimpleNamespace

from backend.src.models.autonomy_qualification import QualificationStageStatus
from scripts import run_autonomy_qualification as runner


def _qualification_context(record: dict | None = None) -> dict:
    payload = {
        "context": {
            "commit_sha": "a1d01df07fe4bbb7868b951bd92758971afa9a48",
            "git_tree_dirty": False,
            "hardware_config_hash": "hardware-hash",
            "limits_hash": "limits-hash",
            "runtime_identity_hash": "runtime-hash",
            "pi_model": "Raspberry Pi 5",
            "hostname_hash": "hostname-hash",
            "machine_id_hash": "machine-hash",
            "os_release": "Raspberry Pi OS",
            "sim_mode": False,
            "robohat_firmware_version": "fw-test",
        },
        "reason_codes": [],
    }
    if record is not None:
        payload["record"] = record
    return payload


def test_runner_cleanup_commands_after_stage_exception(monkeypatch):
    created_clients = []

    class FakeApiClient:
        def __init__(self, base_url: str, timeout_s: float):
            self.posts = []
            created_clients.append(self)

        def get(self, path: str):
            if path == "/api/v2/autonomy/qualification":
                return _qualification_context()
            if path == "/api/v2/sensors/health":
                raise RuntimeError("sensor API unavailable")
            return {}

        def post(self, path: str, payload: dict):
            self.posts.append((path, payload))
            return {}

    monkeypatch.setattr(runner, "ApiClient", FakeApiClient)
    args = SimpleNamespace(
        base_url="http://127.0.0.1:8081",
        timeout_s=1.0,
        stage=["sensor_freshness"],
        operator_confirmed=False,
        operator="aaron",
        notes="unit test",
        store=False,
    )

    record = runner.run(args)

    assert record.status == QualificationStageStatus.FAILED
    assert any(stage.reason_code == "STAGE_API_ERROR" for stage in record.stages)
    assert record.stages[-1].stage_id == "cleanup"
    assert record.stages[-1].status == QualificationStageStatus.PASSED
    assert created_clients[0].posts == [
        ("/api/v2/control/drive", runner.DRIVE_NEUTRAL_PAYLOAD),
        ("/api/v2/control/blade", runner.BLADE_OFF_PAYLOAD),
    ]


def test_non_destructive_passes_remain_partial_not_physical_qualification(monkeypatch):
    class FakeApiClient:
        def __init__(self, base_url: str, timeout_s: float):
            self.posts = []

        def get(self, path: str):
            if path == "/api/v2/autonomy/qualification":
                return _qualification_context()
            if path == "/api/v2/hardware/robohat":
                return {"serial_connected": True, "motor_controller_ok": True}
            if path == "/api/v2/sensors/health":
                return {"gps": {"status": "online"}, "imu": {"status": "online"}}
            return {}

        def post(self, path: str, payload: dict):
            self.posts.append((path, payload))
            return {}

    monkeypatch.setattr(runner, "ApiClient", FakeApiClient)
    args = SimpleNamespace(
        base_url="http://127.0.0.1:8081",
        timeout_s=1.0,
        stage=None,
        operator_confirmed=False,
        operator="aaron",
        notes="unit test",
        store=False,
    )

    record = runner.run(args)

    assert record.status == QualificationStageStatus.INTERRUPTED
    assert all(stage.status == QualificationStageStatus.PASSED for stage in record.stages)


def test_operator_can_record_artifact_backed_physical_result_without_actuation(monkeypatch):
    context = _qualification_context()["context"]
    prior_stages = [
        {
            "stage_id": stage_id,
            "status": "passed",
            "summary": "passed earlier",
        }
        for stage_id in runner.NON_DESTRUCTIVE_STAGES
    ]
    prior_record = {**context, "stages": prior_stages}

    class FakeApiClient:
        def __init__(self, base_url: str, timeout_s: float):
            self.posts = []

        def get(self, path: str):
            if path == "/api/v2/autonomy/qualification":
                return _qualification_context(prior_record)
            return {}

        def post(self, path: str, payload: dict):
            self.posts.append((path, payload))
            return {}

    monkeypatch.setattr(runner, "ApiClient", FakeApiClient)
    args = SimpleNamespace(
        base_url="http://127.0.0.1:8081",
        timeout_s=1.0,
        stage=["wheels_raised_drive"],
        stage_result=["wheels_raised_drive=passed"],
        artifact_id=["wheels_raised_drive=artifact-1"],
        physical_intervention="verified master power cutoff",
        fresh=False,
        operator_confirmed=True,
        operator="aaron",
        notes="unit test",
        store=False,
    )

    record = runner.run(args)
    stage = next(item for item in record.stages if item.stage_id == "wheels_raised_drive")

    assert stage.status == QualificationStageStatus.PASSED
    assert stage.artifact_ids == ["artifact-1"]
    assert stage.measurements["physical_intervention_mechanism"] == (
        "verified master power cutoff"
    )
    assert record.status == QualificationStageStatus.INTERRUPTED


def test_physical_pass_without_artifact_or_cutoff_is_rejected(monkeypatch):
    context = _qualification_context()["context"]
    prior_record = {
        **context,
        "stages": [
            {"stage_id": stage_id, "status": "passed", "summary": "passed earlier"}
            for stage_id in runner.NON_DESTRUCTIVE_STAGES
        ],
    }

    class FakeApiClient:
        def __init__(self, base_url: str, timeout_s: float):
            pass

        def get(self, path: str):
            return _qualification_context(prior_record)

        def post(self, path: str, payload: dict):
            return {}

    monkeypatch.setattr(runner, "ApiClient", FakeApiClient)
    args = SimpleNamespace(
        base_url="http://127.0.0.1:8081",
        timeout_s=1.0,
        stage=["wheels_raised_drive"],
        stage_result=["wheels_raised_drive=passed"],
        artifact_id=None,
        physical_intervention="",
        fresh=False,
        operator_confirmed=True,
        operator="aaron",
        notes="unit test",
        store=False,
    )

    record = runner.run(args)
    stage = next(item for item in record.stages if item.stage_id == "wheels_raised_drive")

    assert stage.status == QualificationStageStatus.FAILED
    assert stage.reason_code == "PHYSICAL_EVIDENCE_INCOMPLETE"
