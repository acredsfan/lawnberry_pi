"""HTTP contracts for the local, authenticated supervised-test capability."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from backend.src.api import autonomy as autonomy_api
from backend.src.control.commands import (
    BladeOutcome,
    CommandStatus,
    DriveOutcome,
)
from backend.src.core.client_identity import CANONICAL_CLIENT_IP_HEADER
from backend.src.core.runtime import get_runtime
from backend.src.main import app
from backend.src.models.autonomy_qualification import (
    SupervisedTestPermitIssueResponse,
    SupervisedTestPermitState,
    SupervisedTestPermitStatus,
)
from backend.src.models.user_session import UserSession

TOKEN = "qualification-secret-token-0123456789abcdef"


class _QualificationService:
    def __init__(self) -> None:
        self.issue_calls: list[dict[str, object]] = []
        self.activate_calls: list[dict[str, object]] = []
        self.complete_calls: list[dict[str, object]] = []
        self.revoke_calls: list[str] = []
        self.status = SupervisedTestPermitStatus(
            state=SupervisedTestPermitState.ISSUED,
            permit_id_hash="0123456789abcdef",
            qualification_record_id="qualification-record",
            issued_at="2026-07-16T12:00:00+00:00",
            expires_at="2026-07-16T12:00:10+00:00",
            remaining_seconds=10.0,
            max_speed_mps=0.2,
            max_duration_seconds=20.0,
            intervention_confirmed=True,
        )

    def supervised_test_permit_status(self):
        return self.status

    def issue_supervised_test_permit(self, **kwargs):
        self.issue_calls.append(kwargs)
        return SupervisedTestPermitIssueResponse(
            permit_token=TOKEN,
            status=self.status,
        )

    def activate_supervised_test_permit(self, **kwargs):
        self.activate_calls.append(kwargs)
        return self.status.model_copy(
            update={"state": SupervisedTestPermitState.ACTIVE, "remaining_seconds": 20.0}
        )

    def complete_supervised_test_permit(self, **kwargs):
        self.complete_calls.append(kwargs)
        return self.status.model_copy(
            update={
                "state": SupervisedTestPermitState.COMPLETED,
                "remaining_seconds": 0.0,
                "cleanup_confirmed": True,
                "receipt_id": "cleanup-receipt",
            }
        )

    def revoke_supervised_test_permit(self, reason: str):
        self.revoke_calls.append(reason)
        return self.status.model_copy(
            update={
                "state": SupervisedTestPermitState.REVOKED,
                "remaining_seconds": 0.0,
                "terminal_reason_code": reason,
            }
        )


class _MissionOwner:
    def __init__(self) -> None:
        self.lifecycle_lock = asyncio.Lock()
        self.idle_checks = 0

    def assert_idle_for_supervised_test(self) -> None:
        self.idle_checks += 1


class _Gateway:
    def __init__(self) -> None:
        self.idle_checks = 0
        self.drive_commands = []
        self.blade_commands = []
        self.deadlines: list[float] = []
        self.deadline_clears = 0

    def assert_actuators_idle_for_supervised_test(self) -> None:
        self.idle_checks += 1

    def arm_supervised_permit_deadline(self, seconds: float) -> None:
        self.deadlines.append(seconds)

    def clear_supervised_permit_deadline(self) -> None:
        self.deadline_clears += 1

    async def dispatch_drive(self, command, request=None):
        del request
        self.drive_commands.append(command)
        return DriveOutcome(
            status=CommandStatus.ACCEPTED,
            audit_id="drive-audit",
            status_reason=None,
            active_interlocks=[],
            watchdog_latency_ms=1.0,
        )

    async def dispatch_blade(self, command, request=None):
        del request
        self.blade_commands.append(command)
        return BladeOutcome(
            status=CommandStatus.ACCEPTED,
            audit_id="blade-audit",
            status_reason=None,
        )


def _runtime():
    qualification = _QualificationService()
    gateway = _Gateway()
    mission_owner = _MissionOwner()
    runtime = SimpleNamespace(
        qualification_service=qualification,
        command_gateway=gateway,
        mission_service=mission_owner,
        navigation=SimpleNamespace(
            navigation_state=SimpleNamespace(target_velocity=0.0)
        ),
    )
    return runtime, qualification, gateway, mission_owner


def _session() -> UserSession:
    return UserSession(session_id="canonical-session", username="aaron")


async def _client(*, remote_ip: str | None = None):
    headers = {}
    if remote_ip is not None:
        headers[CANONICAL_CLIENT_IP_HEADER] = remote_ip
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 43210))
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=headers,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/v2/autonomy/qualification/supervised-test/permit", None),
        (
            "POST",
            "/api/v2/autonomy/qualification/supervised-test/permit",
            {
                "operator_confirmed": True,
                "local_supervision_confirmed": True,
                "physical_intervention_mechanism": "master cutoff within reach",
            },
        ),
        (
            "POST",
            "/api/v2/autonomy/qualification/supervised-test/permit/activate",
            {"permit_token": TOKEN},
        ),
        (
            "POST",
            "/api/v2/autonomy/qualification/supervised-test/drive",
            {
                "permit_token": TOKEN,
                "left_normalized": 0.1,
                "right_normalized": 0.1,
                "duration_ms": 100,
            },
        ),
        (
            "POST",
            "/api/v2/autonomy/qualification/supervised-test/blade",
            {"permit_token": TOKEN, "active": True},
        ),
        (
            "POST",
            "/api/v2/autonomy/qualification/supervised-test/complete",
            {"permit_token": TOKEN, "cleanup_confirmed": True},
        ),
        (
            "POST",
            "/api/v2/autonomy/qualification/supervised-test/revoke",
            {"reason": "operator_requested"},
        ),
    ],
)
async def test_every_permit_endpoint_requires_canonical_authenticated_session(
    method,
    path,
    body,
):
    runtime, _, _, _ = _runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        async with await _client() as client:
            response = await client.request(method, path, json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,body",
    [
        (
            "/api/v2/autonomy/qualification/supervised-test/permit",
            {
                "operator_confirmed": True,
                "local_supervision_confirmed": True,
                "physical_intervention_mechanism": "master cutoff within reach",
            },
        ),
        (
            "/api/v2/autonomy/qualification/supervised-test/permit/activate",
            {"permit_token": TOKEN},
        ),
        (
            "/api/v2/autonomy/qualification/supervised-test/drive",
            {
                "permit_token": TOKEN,
                "left_normalized": 0.1,
                "right_normalized": 0.1,
                "duration_ms": 100,
            },
        ),
        (
            "/api/v2/autonomy/qualification/supervised-test/blade",
            {"permit_token": TOKEN, "active": True},
        ),
        (
            "/api/v2/autonomy/qualification/supervised-test/complete",
            {"permit_token": TOKEN, "cleanup_confirmed": True},
        ),
    ],
)
async def test_hazardous_permit_operations_reject_nonlocal_network(path, body):
    runtime, qualification, gateway, _ = _runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[autonomy_api.require_session] = _session
    try:
        async with await _client(remote_ip="8.8.8.8") as client:
            response = await client.post(path, json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert qualification.issue_calls == []
    assert qualification.activate_calls == []
    assert qualification.complete_calls == []
    assert gateway.drive_commands == []
    assert gateway.blade_commands == []


@pytest.mark.asyncio
async def test_issue_binds_canonical_session_and_embedded_status_is_redacted():
    runtime, qualification, gateway, mission_owner = _runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[autonomy_api.require_session] = _session
    body = {
        "operator_confirmed": True,
        "local_supervision_confirmed": True,
        "physical_intervention_mechanism": "master cutoff within reach",
    }
    try:
        async with await _client(remote_ip="192.168.1.50") as client:
            response = await client.post(
                "/api/v2/autonomy/qualification/supervised-test/permit",
                json=body,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["permit_token"] == TOKEN
    assert "permit_token" not in payload["status"]
    assert TOKEN not in json.dumps(payload["status"])
    assert qualification.issue_calls == [
        {
            "operator_id": "aaron",
            "operator_session_id": "canonical-session",
            **body,
        }
    ]
    assert mission_owner.idle_checks == 1
    assert gateway.idle_checks == 1


@pytest.mark.asyncio
async def test_status_never_returns_reusable_token_or_intervention_description():
    runtime, _, _, _ = _runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[autonomy_api.require_session] = _session
    try:
        async with await _client() as client:
            response = await client.get(
                "/api/v2/autonomy/qualification/supervised-test/permit"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "permit_token" not in serialized
    assert TOKEN not in serialized
    assert "master cutoff" not in serialized


@pytest.mark.asyncio
async def test_drive_and_blade_sources_are_server_owned_even_with_spoofed_fields():
    runtime, _, gateway, _ = _runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[autonomy_api.require_session] = _session
    try:
        async with await _client(remote_ip="192.168.1.50") as client:
            drive = await client.post(
                "/api/v2/autonomy/qualification/supervised-test/drive",
                json={
                    "permit_token": TOKEN,
                    "left_normalized": 0.1,
                    "right_normalized": 0.1,
                    "duration_ms": 100,
                    "source": "manual",
                    "operator_session_id": "attacker-session",
                },
            )
            blade = await client.post(
                "/api/v2/autonomy/qualification/supervised-test/blade",
                json={
                    "permit_token": TOKEN,
                    "active": True,
                    "source": "mission",
                    "operator_session_id": "attacker-session",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert drive.status_code == 200
    assert blade.status_code == 200
    drive_command = gateway.drive_commands[-1]
    blade_command = gateway.blade_commands[-1]
    assert drive_command.source == "supervised_qualification"
    assert blade_command.source == "supervised_qualification"
    assert drive_command.qualification.permit_token == TOKEN
    assert blade_command.qualification.permit_token == TOKEN
    assert drive_command.qualification.operator_session_id == "canonical-session"
    assert blade_command.qualification.operator_session_id == "canonical-session"


@pytest.mark.asyncio
async def test_remote_authenticated_operator_can_revoke_but_cannot_actuate():
    """Revocation is intentionally remote-safe; it only commands neutral/blade-off."""
    runtime, qualification, gateway, _ = _runtime()
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[autonomy_api.require_session] = _session
    try:
        async with await _client(remote_ip="8.8.8.8") as client:
            response = await client.post(
                "/api/v2/autonomy/qualification/supervised-test/revoke",
                json={"reason": "unsafe_condition"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert gateway.drive_commands[-1].left == 0.0
    assert gateway.drive_commands[-1].right == 0.0
    assert gateway.blade_commands[-1].active is False
    assert qualification.revoke_calls == [
        "SUPERVISED_TEST_OPERATOR_REVOKED:unsafe_condition"
    ]
