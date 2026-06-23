from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.runtime import RuntimeContext, get_runtime
from ..services.autonomy_readiness_service import AutonomyReadinessService

router = APIRouter(prefix="/api/v2/autonomy", tags=["autonomy"])


@router.get("/readiness")
async def get_autonomy_readiness(runtime: RuntimeContext = Depends(get_runtime)):
    service = AutonomyReadinessService(runtime)
    report = await service.evaluate(require_blade=True)
    return report.to_dict()

