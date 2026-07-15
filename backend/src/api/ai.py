from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..models import InferenceResult, InferenceTask, PerceptionSnapshot
from ..services.ai_service import (
    AIInferenceInputError,
    AIModelNotReadyError,
    AINoFrameAvailableError,
    AIService,
    AIServiceError,
    get_ai_service,
)
from ..services.camera_runtime import sync_external_ai_owner_state

router = APIRouter()


def _raise_ai_http_error(exc: Exception) -> None:
    if isinstance(exc, AIInferenceInputError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, AINoFrameAvailableError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, AIModelNotReadyError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, AIServiceError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="AI inference failed") from exc


@router.get("/api/v2/ai/status")
async def get_ai_status(
    ai_service: AIService = Depends(get_ai_service),
):
    """Return AI runtime, model readiness, and the process that owns inference."""
    try:
        await sync_external_ai_owner_state(ai_service)
        return await ai_service.get_ai_status()
    except Exception as exc:
        _raise_ai_http_error(exc)


@router.get("/api/v2/ai/perception/latest", response_model=PerceptionSnapshot)
async def get_latest_perception(
    ai_service: AIService = Depends(get_ai_service),
) -> PerceptionSnapshot:
    """Return the latest provenance- and freshness-qualified perception result."""
    if not ai_service.initialized:
        await ai_service.initialize()
    return ai_service.get_perception_snapshot()


@router.get("/api/v2/ai/results/recent", response_model=list[InferenceResult])
async def get_recent_results(
    limit: int = Query(default=10, ge=1, le=50),
    ai_service: AIService = Depends(get_ai_service),
):
    """Return recent inference results, newest first."""
    try:
        return await ai_service.get_recent_results(limit)
    except Exception as exc:
        _raise_ai_http_error(exc)


@router.post("/api/v2/ai/inference", response_model=InferenceResult)
async def run_uploaded_inference(
    request: Request,
    task: InferenceTask = Query(default=InferenceTask.OBSTACLE_DETECTION),
    confidence_threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    frame_id: str | None = Query(default=None),
    ai_service: AIService = Depends(get_ai_service),
):
    """Run uploaded-image inference in the embedded SIM/CI runtime.

    Hardware mode keeps inference in the standalone camera owner, so this
    diagnostic route returns 503 instead of starting a competing backend
    inference path. Read `/api/v2/ai/perception/latest` for hardware results.
    """
    try:
        image_bytes = await request.body()
        return await ai_service.infer_image_bytes(
            image_bytes,
            task=task,
            frame_id=frame_id,
            confidence_threshold=confidence_threshold,
        )
    except Exception as exc:
        _raise_ai_http_error(exc)


@router.post("/api/v2/ai/inference/latest", response_model=InferenceResult)
async def run_latest_frame_inference(
    task: InferenceTask = Query(default=InferenceTask.OBSTACLE_DETECTION),
    confidence_threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    ai_service: AIService = Depends(get_ai_service),
):
    """Run latest-frame inference in the embedded SIM/CI runtime.

    Hardware mode performs automatic sampled inference in the standalone
    camera owner, so this diagnostic route returns 503. Read
    `/api/v2/ai/perception/latest` for the latest hardware result.
    """
    try:
        return await ai_service.infer_latest_frame(
            task=task,
            confidence_threshold=confidence_threshold,
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
