"""
Progress Tracking Router
Real-time mowing progress tracking and path history management.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from ..models import (
    MowingSession, PathPoint, ProgressUpdate, PathHistory, 
    CoverageArea, Position, SuccessResponse, PaginationParams, PaginatedResponse
)
from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError
from ..mqtt_bridge import MQTTBridge

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory storage for active sessions (in production, use database)
active_sessions: Dict[str, MowingSession] = {}
session_paths: Dict[str, List[PathPoint]] = {}
coverage_data: Dict[str, List[CoverageArea]] = {}

@router.post("/sessions", response_model=MowingSession)
async def start_mowing_session(
    pattern_id: Optional[str] = None,
    boundary_id: Optional[str] = None,
    total_area: float = 0,
    request: Request = None,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Start a new mowing session"""
    session_id = f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hash(current_user.get('username', 'unknown')) & 0xffff:04x}"
    
    session = MowingSession(
        session_id=session_id,
        start_time=datetime.utcnow(),
        total_area=total_area,
        pattern_id=pattern_id,
        boundary_id=boundary_id
    )
    
    active_sessions[session_id] = session
    session_paths[session_id] = []
    coverage_data[session_id] = []
    
    # Notify MQTT bridge about new session
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge if request else None
    if mqtt_bridge and mqtt_bridge.is_connected():
        await mqtt_bridge.publish_message(
            "mower/session/start",
            {
                "session_id": session_id,
                "start_time": session.start_time.isoformat(),
                "pattern_id": pattern_id,
                "boundary_id": boundary_id,
                "total_area": total_area
            },
            qos=1
        )
    
    logger.info(f"Started mowing session: {session_id}")
    return session

@router.get("/sessions/{session_id}", response_model=MowingSession)
async def get_mowing_session(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get mowing session details"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return active_sessions[session_id]

@router.get("/sessions", response_model=PaginatedResponse)
async def list_mowing_sessions(
    pagination: PaginationParams = Depends(),
    active_only: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """List mowing sessions"""
    sessions = list(active_sessions.values())
    
    if active_only:
        sessions = [s for s in sessions if s.end_time is None]
    
    # Sort by start time (newest first)
    sessions.sort(key=lambda x: x.start_time, reverse=True)
    
    # Apply pagination
    total = len(sessions)
    start_idx = pagination.offset
    end_idx = start_idx + pagination.size
    paginated_sessions = sessions[start_idx:end_idx]
    
    return PaginatedResponse(
        items=paginated_sessions,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=(total + pagination.size - 1) // pagination.size if total > 0 else 1
    )

@router.post("/sessions/{session_id}/end", response_model=MowingSession)
async def end_mowing_session(
    session_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """End a mowing session"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    session.end_time = datetime.utcnow()
    session.time_elapsed = int((session.end_time - session.start_time).total_seconds())
    
    # Calculate final statistics
    path_points = session_paths.get(session_id, [])
    if path_points:
        # Calculate total distance
        total_distance = 0
        for i in range(1, len(path_points)):
            prev_point = path_points[i-1]
            curr_point = path_points[i]
            distance = calculate_distance(
                prev_point.position.latitude, prev_point.position.longitude,
                curr_point.position.latitude, curr_point.position.longitude
            )
            total_distance += distance
        
        session.distance_traveled = total_distance
        
        # Calculate average speed
        if session.time_elapsed > 0:
            session.average_speed = total_distance / session.time_elapsed
        
        # Calculate efficiency (coverage vs distance)
        if total_distance > 0 and session.total_area > 0:
            session.efficiency = min(100, (session.covered_area / session.total_area) * 100)
    
    # Notify MQTT bridge
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    if mqtt_bridge and mqtt_bridge.is_connected():
        await mqtt_bridge.publish_message(
            "mower/session/end",
            {
                "session_id": session_id,
                "end_time": session.end_time.isoformat(),
                "statistics": {
                    "time_elapsed": session.time_elapsed,
                    "covered_area": session.covered_area,
                    "coverage_percentage": session.coverage_percentage,
                    "distance_traveled": session.distance_traveled,
                    "average_speed": session.average_speed,
                    "efficiency": session.efficiency
                }
            },
            qos=1
        )
    
    logger.info(f"Ended mowing session: {session_id}")
    return session

@router.post("/progress", response_model=SuccessResponse)
async def update_progress(
    progress: ProgressUpdate,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Update mowing progress"""
    session_id = progress.session_id
    
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    
    # Update session with progress data
    session.coverage_percentage = progress.coverage_percentage
    session.time_elapsed = progress.time_elapsed
    session.current_activity = progress.current_activity
    session.estimated_time_remaining = progress.estimated_time_remaining
    
    # Calculate covered area from percentage
    if session.total_area > 0:
        session.covered_area = (progress.coverage_percentage / 100) * session.total_area
    
    # Add to path history
    path_point = PathPoint(
        position=progress.position,
        activity=progress.current_activity,
        battery_level=progress.battery_level,
        timestamp=datetime.utcnow()
    )
    
    if session_id not in session_paths:
        session_paths[session_id] = []
    
    session_paths[session_id].append(path_point)
    
    # Limit path history to prevent memory issues
    if len(session_paths[session_id]) > 10000:
        session_paths[session_id] = session_paths[session_id][-5000:]  # Keep last 5000 points
    
    # Broadcast progress update via WebSocket
    background_tasks.add_task(broadcast_progress_update, progress, request)
    
    return SuccessResponse(message="Progress updated successfully")

@router.get("/sessions/{session_id}/path", response_model=PathHistory)
async def get_session_path(
    session_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get path history for a session"""
    if session_id not in session_paths:
        raise HTTPException(status_code=404, detail="Session path not found")
    
    path_points = session_paths[session_id]
    
    # Filter by time range if specified
    if start_time or end_time:
        filtered_points = []
        for point in path_points:
            if start_time and point.timestamp < start_time:
                continue
            if end_time and point.timestamp > end_time:
                continue
            filtered_points.append(point)
        path_points = filtered_points
    
    # Calculate total distance
    total_distance = 0
    for i in range(1, len(path_points)):
        prev_point = path_points[i-1]
        curr_point = path_points[i]
        distance = calculate_distance(
            prev_point.position.latitude, prev_point.position.longitude,
            curr_point.position.latitude, curr_point.position.longitude
        )
        total_distance += distance
    
    session = active_sessions.get(session_id)
    return PathHistory(
        session_id=session_id,
        points=path_points,
        total_distance=total_distance,
        start_time=session.start_time if session else datetime.utcnow(),
        end_time=session.end_time if session else None
    )

@router.get("/sessions/{session_id}/coverage", response_model=List[CoverageArea])
async def get_session_coverage(
    session_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get coverage areas for a session"""
    if session_id not in coverage_data:
        return []
    
    return coverage_data[session_id]

@router.get("/current", response_model=Optional[MowingSession])
async def get_current_session(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get currently active mowing session"""
    for session in active_sessions.values():
        if session.end_time is None:
            return session
    return None

# Helper functions
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in meters using Haversine formula"""
    import math
    
    R = 6371000  # Earth's radius in meters
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat / 2) * math.sin(delta_lat / 2) +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(delta_lon / 2) * math.sin(delta_lon / 2))
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

async def broadcast_progress_update(progress: ProgressUpdate, request: Request):
    """Broadcast progress update to WebSocket clients"""
    try:
        # Import here to avoid circular imports
        from .websocket import ws_manager
        
        message = {
            "type": "progress_update",
            "topic": "mower/progress",
            "data": {
                "session_id": progress.session_id,
                "position": {
                    "lat": progress.position.latitude,
                    "lng": progress.position.longitude
                },
                "coverage_percentage": progress.coverage_percentage,
                "time_elapsed": progress.time_elapsed,
                "battery_level": progress.battery_level,
                "current_activity": progress.current_activity,
                "estimated_time_remaining": progress.estimated_time_remaining
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await ws_manager.broadcast(message, "mower/progress")
        
    except Exception as e:
        logger.error(f"Error broadcasting progress update: {e}")
