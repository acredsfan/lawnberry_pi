from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..models import InferenceResult, InferenceTask
from ..services.ai_service import (
    AINoFrameAvailableError,
    AIInferenceInputError,
    AIModelNotReadyError,
    AIService,
    AIServiceError,
    get_ai_service,
)


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
    """Return AI runtime and model status."""
    try:
        return await ai_service.get_ai_status()
    except Exception as exc:
        _raise_ai_http_error(exc)


@router.get("/api/v2/ai/results/recent", response_model=List[InferenceResult])
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
    confidence_threshold: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    frame_id: Optional[str] = Query(default=None),
    ai_service: AIService = Depends(get_ai_service),
):
    """Run AI inference against an uploaded image."""
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
    confidence_threshold: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    ai_service: AIService = Depends(get_ai_service),
):
    """Run AI inference against the latest camera frame."""
    try:
        return await ai_service.infer_latest_frame(
            task=task,
            confidence_threshold=confidence_threshold,
        )
    except Exception as exc:
        _raise_ai_http_error(exc)