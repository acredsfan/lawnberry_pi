from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

from ...services.weather_service import weather_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/weather/current")
async def get_current_weather(
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
):
    """Get current weather data from sensors or external API."""
    try:
        weather_data = await weather_service.get_current_async(
            latitude=latitude,
            longitude=longitude,
        )
        return weather_data
    except Exception as e:
        logger.error(f"Failed to get current weather: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/weather/planning")
async def get_planning_advice(
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
):
    """Get mowing planning advice based on current weather."""
    try:
        current = await weather_service.get_current_async(
            latitude=latitude,
            longitude=longitude,
        )
        advice = weather_service.get_planning_advice(current)
        return {
            "current": current,
            "advice": advice,
        }
    except Exception as e:
        logger.error(f"Failed to get planning advice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weather/planning-advice")
async def get_planning_advice_contract(
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
):
    """Contract-friendly planning advice payload."""
    try:
        current = await weather_service.get_current_async(
            latitude=latitude,
            longitude=longitude,
        )
        advice = weather_service.get_planning_advice(current)
        return {
            "advice": advice.get("advice", "insufficient-data"),
            "reasons": advice.get("reasons", []),
            "current": current,
        }
    except Exception as e:
        logger.error(f"Failed to get contract planning advice: {e}")
        raise HTTPException(status_code=500, detail=str(e))
