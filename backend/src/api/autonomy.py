from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..core.runtime import RuntimeContext, get_runtime
from ..models.autonomy_qualification import AutonomyQualificationRecord
from ..services.autonomy_qualification_service import (
    AutonomyQualificationError,
    AutonomyQualificationService,
)
from ..services.autonomy_readiness_service import AutonomyReadinessService

router = APIRouter(prefix="/api/v2/autonomy", tags=["autonomy"])


@router.get("/readiness")
async def get_autonomy_readiness(runtime: RuntimeContext = Depends(get_runtime)):
    service = AutonomyReadinessService(runtime)
    report = await service.evaluate(require_blade=True)
    return report.to_dict()


@router.get("/qualification")
async def get_autonomy_qualification(runtime: RuntimeContext = Depends(get_runtime)):
    service = getattr(runtime, "qualification_service", None) or AutonomyQualificationService(runtime)
    return service.evaluate().model_dump(mode="json")


@router.post("/qualification/evidence", status_code=201)
async def create_autonomy_qualification_evidence(
    record: AutonomyQualificationRecord,
    runtime: RuntimeContext = Depends(get_runtime),
):
    service = getattr(runtime, "qualification_service", None) or AutonomyQualificationService(runtime)
    try:
        service.save_record(record)
    except AutonomyQualificationError as exc:
        raise HTTPException(
            status_code=409,
            detail=exc.evaluation.model_dump(mode="json"),
        ) from exc
    return record.model_dump(mode="json")
