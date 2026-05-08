from fastapi import APIRouter, Depends, HTTPException

from ..core.runtime import RuntimeContext, get_runtime
from ..models.mission import Mission, MissionCreationRequest, MissionStatus
from ..services.mission_service import (
    MissionConflictError,
    MissionNotFoundError,
    MissionStateError,
    MissionValidationError,
)

router = APIRouter()


def _raise_mission_http_error(error: Exception) -> None:
    if isinstance(error, MissionValidationError):
        raise HTTPException(status_code=400, detail=str(error))
    if isinstance(error, MissionNotFoundError):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, (MissionConflictError, MissionStateError)):
        raise HTTPException(status_code=409, detail=str(error))
    raise HTTPException(status_code=500, detail=str(error))


@router.post("/api/v2/missions/create", response_model=Mission)
async def create_mission(
    request: MissionCreationRequest,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Create a new mission."""
    mission_service = runtime.mission_service
    try:
        mission = await mission_service.create_mission(request.name, request.waypoints)
        return mission
    except Exception as e:
        _raise_mission_http_error(e)


@router.post("/api/v2/missions/{mission_id}/start")
async def start_mission(
    mission_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Start a mission."""
    mission_service = runtime.mission_service
    try:
        await mission_service.start_mission(mission_id)
        return {"status": "Mission started"}
    except Exception as e:
        _raise_mission_http_error(e)


@router.post("/api/v2/missions/{mission_id}/pause")
async def pause_mission(
    mission_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Pause a mission."""
    mission_service = runtime.mission_service
    try:
        await mission_service.pause_mission(mission_id)
        return {"status": "Mission paused"}
    except Exception as e:
        _raise_mission_http_error(e)


@router.post("/api/v2/missions/{mission_id}/resume")
async def resume_mission(
    mission_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Resume a paused mission."""
    mission_service = runtime.mission_service
    try:
        await mission_service.resume_mission(mission_id)
        return {"status": "Mission resumed"}
    except Exception as e:
        _raise_mission_http_error(e)


@router.post("/api/v2/missions/{mission_id}/abort")
async def abort_mission(
    mission_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Abort a mission."""
    mission_service = runtime.mission_service
    try:
        await mission_service.abort_mission(mission_id)
        return {"status": "Mission aborted"}
    except Exception as e:
        _raise_mission_http_error(e)


@router.get("/api/v2/missions/list", response_model=list[Mission])
async def list_missions(
    runtime: RuntimeContext = Depends(get_runtime),
):
    """List all saved missions."""
    mission_service = runtime.mission_service
    return await mission_service.list_missions()


@router.get("/api/v2/missions/{mission_id}/status", response_model=MissionStatus)
async def get_mission_status(
    mission_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Get the status of a mission."""
    mission_service = runtime.mission_service
    try:
        status = await mission_service.get_mission_status(mission_id)
        return status
    except Exception as e:
        _raise_mission_http_error(e)


@router.get("/api/v2/missions/{mission_id}", response_model=Mission)
async def get_mission(
    mission_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Get a mission by ID."""
    mission_service = runtime.mission_service
    try:
        return mission_service._require_mission(mission_id)
    except Exception as e:
        _raise_mission_http_error(e)
