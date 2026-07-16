from __future__ import annotations

import ipaddress
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request

from ..control.commands import (
    BladeCommand,
    CommandStatus,
    DriveCommand,
    SupervisedQualificationCommandContext,
)
from ..core.client_identity import client_ip
from ..core.runtime import RuntimeContext, get_runtime
from ..models.autonomy_qualification import (
    AutonomyQualificationRecord,
    SupervisedTestBladeRequest,
    SupervisedTestCompleteRequest,
    SupervisedTestDriveRequest,
    SupervisedTestPermitIssueRequest,
    SupervisedTestPermitIssueResponse,
    SupervisedTestPermitStatus,
    SupervisedTestPermitTokenRequest,
    SupervisedTestRevokeRequest,
)
from ..models.user_session import UserSession
from ..services.autonomy_qualification_service import (
    AutonomyQualificationError,
    AutonomyQualificationService,
    SupervisedTestPermitError,
)
from ..services.autonomy_readiness_service import AutonomyReadinessService
from ..services.mission_service import MissionConflictError
from .routers.auth import require_session

router = APIRouter(prefix="/api/v2/autonomy", tags=["autonomy"])


def _qualification_service(runtime: RuntimeContext) -> AutonomyQualificationService:
    return getattr(runtime, "qualification_service", None) or AutonomyQualificationService(
        runtime
    )


def _require_local_operator(request: Request) -> None:
    address = client_ip(request)
    try:
        parsed = ipaddress.ip_address(address or "")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Local operator network required") from exc
    if not (parsed.is_loopback or parsed.is_private or parsed.is_link_local):
        raise HTTPException(status_code=403, detail="Local operator network required")


def _permit_conflict(exc: SupervisedTestPermitError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "reason_code": exc.reason_code,
            "permit": exc.status.model_dump(mode="json"),
        },
    )


def _command_conflict(outcome: object) -> HTTPException:
    return HTTPException(status_code=409, detail=asdict(outcome))


@router.get("/readiness")
async def get_autonomy_readiness(runtime: RuntimeContext = Depends(get_runtime)):
    service = AutonomyReadinessService(runtime)
    report = await service.evaluate(require_blade=True)
    return report.to_dict()


@router.get("/qualification")
async def get_autonomy_qualification(runtime: RuntimeContext = Depends(get_runtime)):
    return _qualification_service(runtime).evaluate().model_dump(mode="json")


@router.post("/qualification/evidence", status_code=201)
async def create_autonomy_qualification_evidence(
    record: AutonomyQualificationRecord,
    runtime: RuntimeContext = Depends(get_runtime),
):
    service = _qualification_service(runtime)
    try:
        service.save_record(record)
    except AutonomyQualificationError as exc:
        raise HTTPException(
            status_code=409,
            detail=exc.evaluation.model_dump(mode="json"),
        ) from exc
    return record.model_dump(mode="json")


@router.get(
    "/qualification/supervised-test/permit",
    response_model=SupervisedTestPermitStatus,
)
async def get_supervised_test_permit(
    session: UserSession = Depends(require_session),
    runtime: RuntimeContext = Depends(get_runtime),
):
    del session
    return _qualification_service(runtime).supervised_test_permit_status()


@router.post(
    "/qualification/supervised-test/permit",
    status_code=201,
    response_model=SupervisedTestPermitIssueResponse,
)
async def issue_supervised_test_permit(
    body: SupervisedTestPermitIssueRequest,
    request: Request,
    session: UserSession = Depends(require_session),
    runtime: RuntimeContext = Depends(get_runtime),
):
    _require_local_operator(request)
    service = _qualification_service(runtime)
    mission_service = runtime.mission_service
    try:
        async with mission_service.lifecycle_lock:
            mission_service.assert_idle_for_supervised_test()
            runtime.command_gateway.assert_actuators_idle_for_supervised_test()
            return service.issue_supervised_test_permit(
                operator_id=session.username,
                operator_session_id=session.session_id,
                operator_confirmed=body.operator_confirmed,
                local_supervision_confirmed=body.local_supervision_confirmed,
                physical_intervention_mechanism=body.physical_intervention_mechanism,
            )
    except SupervisedTestPermitError as exc:
        raise _permit_conflict(exc) from exc
    except AutonomyQualificationError as exc:
        raise HTTPException(
            status_code=409,
            detail=exc.evaluation.model_dump(mode="json"),
        ) from exc
    except MissionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        if str(exc) == "SUPERVISED_TEST_ACTUATORS_NOT_IDLE":
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise


@router.post(
    "/qualification/supervised-test/permit/activate",
    response_model=SupervisedTestPermitStatus,
)
async def activate_supervised_test_permit(
    body: SupervisedTestPermitTokenRequest,
    request: Request,
    session: UserSession = Depends(require_session),
    runtime: RuntimeContext = Depends(get_runtime),
):
    _require_local_operator(request)
    service = _qualification_service(runtime)
    mission_service = runtime.mission_service
    try:
        async with mission_service.lifecycle_lock:
            mission_service.assert_idle_for_supervised_test()
            runtime.command_gateway.assert_actuators_idle_for_supervised_test()
            status = service.activate_supervised_test_permit(
                permit_token=body.permit_token.get_secret_value(),
                operator_session_id=session.session_id,
            )
            runtime.command_gateway.arm_supervised_permit_deadline(
                status.remaining_seconds
            )
            return status
    except SupervisedTestPermitError as exc:
        raise _permit_conflict(exc) from exc
    except MissionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        if str(exc) == "SUPERVISED_TEST_ACTUATORS_NOT_IDLE":
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise


@router.post("/qualification/supervised-test/drive")
async def supervised_test_drive(
    body: SupervisedTestDriveRequest,
    request: Request,
    session: UserSession = Depends(require_session),
    runtime: RuntimeContext = Depends(get_runtime),
):
    _require_local_operator(request)
    outcome = await runtime.command_gateway.dispatch_drive(
        DriveCommand(
            left=body.left_normalized,
            right=body.right_normalized,
            source="supervised_qualification",
            duration_ms=body.duration_ms,
            qualification=SupervisedQualificationCommandContext(
                permit_token=body.permit_token.get_secret_value(),
                operator_session_id=session.session_id,
            ),
        ),
        request=request,
    )
    if outcome.status != CommandStatus.ACCEPTED:
        raise _command_conflict(outcome)
    return asdict(outcome)


@router.post("/qualification/supervised-test/blade")
async def supervised_test_blade(
    body: SupervisedTestBladeRequest,
    request: Request,
    session: UserSession = Depends(require_session),
    runtime: RuntimeContext = Depends(get_runtime),
):
    _require_local_operator(request)
    target_velocity = getattr(
        getattr(runtime.navigation, "navigation_state", None),
        "target_velocity",
        0.0,
    )
    outcome = await runtime.command_gateway.dispatch_blade(
        BladeCommand(
            active=body.active,
            source="supervised_qualification",
            motors_active=abs(float(target_velocity or 0.0)) > 1e-6,
            qualification=SupervisedQualificationCommandContext(
                permit_token=body.permit_token.get_secret_value(),
                operator_session_id=session.session_id,
            ),
        ),
        request=request,
    )
    if outcome.status != CommandStatus.ACCEPTED:
        raise _command_conflict(outcome)
    return asdict(outcome)


@router.post(
    "/qualification/supervised-test/complete",
    response_model=SupervisedTestPermitStatus,
)
async def complete_supervised_test(
    body: SupervisedTestCompleteRequest,
    request: Request,
    session: UserSession = Depends(require_session),
    runtime: RuntimeContext = Depends(get_runtime),
):
    _require_local_operator(request)
    drive = await runtime.command_gateway.dispatch_drive(
        DriveCommand(left=0.0, right=0.0, source="qualification_cleanup", duration_ms=0),
        request=request,
    )
    blade = await runtime.command_gateway.dispatch_blade(
        BladeCommand(active=False, source="qualification_cleanup"),
        request=request,
    )
    cleanup_confirmed = bool(
        body.cleanup_confirmed
        and drive.status == CommandStatus.ACCEPTED
        and blade.status == CommandStatus.ACCEPTED
    )
    try:
        status = _qualification_service(runtime).complete_supervised_test_permit(
            permit_token=body.permit_token.get_secret_value(),
            operator_session_id=session.session_id,
            cleanup_confirmed=cleanup_confirmed,
            cleanup_evidence={
                "drive_audit_id": drive.audit_id,
                "drive_status": drive.status.value,
                "blade_audit_id": blade.audit_id,
                "blade_status": blade.status.value,
            },
        )
        runtime.command_gateway.clear_supervised_permit_deadline()
        return status
    except SupervisedTestPermitError as exc:
        raise _permit_conflict(exc) from exc


@router.post(
    "/qualification/supervised-test/revoke",
    response_model=SupervisedTestPermitStatus,
)
async def revoke_supervised_test_permit(
    body: SupervisedTestRevokeRequest,
    request: Request,
    session: UserSession = Depends(require_session),
    runtime: RuntimeContext = Depends(get_runtime),
):
    del session
    await runtime.command_gateway.dispatch_drive(
        DriveCommand(left=0.0, right=0.0, source="qualification_revoke", duration_ms=0),
        request=request,
    )
    await runtime.command_gateway.dispatch_blade(
        BladeCommand(active=False, source="qualification_revoke"),
        request=request,
    )
    runtime.command_gateway.clear_supervised_permit_deadline()
    return _qualification_service(runtime).revoke_supervised_test_permit(
        f"SUPERVISED_TEST_OPERATOR_REVOKED:{body.reason}"
    )
