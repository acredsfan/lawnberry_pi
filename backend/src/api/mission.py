from fastapi import APIRouter, Depends, HTTPException
from typing import List
from ..services.mission_service import MissionService, get_mission_service
from ..models.mission import Mission, MissionCreationRequest, MissionStatus

router = APIRouter()

@router.post("/api/v2/missions/create", response_model=Mission)
async def create_mission(
    request: MissionCreationRequest,
    mission_service: MissionService = Depends(get_mission_service),
):
    """Create a new mission."""
    try:
        mission = await mission_service.create_mission(request.name, request.waypoints)
        return mission
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/v2/missions/{mission_id}/start")
async def start_mission(
    mission_id: str,
    mission_service: MissionService = Depends(get_mission_service),
):
    """Start a mission."""
    try:
        await mission_service.start_mission(mission_id)
        return {"status": "Mission started"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/api/v2/missions/{mission_id}/pause")
async def pause_mission(
    mission_id: str,
    mission_service: MissionService = Depends(get_mission_service),
):
    """Pause a mission."""
    try:
        await mission_service.pause_mission(mission_id)
        return {"status": "Mission paused"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/api/v2/missions/{mission_id}/resume")
async def resume_mission(
    mission_id: str,
    mission_service: MissionService = Depends(get_mission_service),
):
    """Resume a paused mission."""
    try:
        await mission_service.resume_mission(mission_id)
        return {"status": "Mission resumed"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/api/v2/missions/{mission_id}/abort")
async def abort_mission(
    mission_id: str,
    mission_service: MissionService = Depends(get_mission_service),
):
    """Abort a mission."""
    try:
        await mission_service.abort_mission(mission_id)
        return {"status": "Mission aborted"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/api/v2/missions/{mission_id}/status", response_model=MissionStatus)
async def get_mission_status(
    mission_id: str,
    mission_service: MissionService = Depends(get_mission_service),
):
    """Get the status of a mission."""
    try:
        status = await mission_service.get_mission_status(mission_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/api/v2/missions/list", response_model=List[Mission])
async def list_missions(
    mission_service: MissionService = Depends(get_mission_service),
):
    """List all saved missions."""
    return await mission_service.list_missions()
