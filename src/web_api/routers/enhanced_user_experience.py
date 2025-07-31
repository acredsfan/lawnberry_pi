"""
Enhanced User Experience Router
Provides improved UI responsiveness, mobile compatibility, and user onboarding
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, WebSocket, BackgroundTasks
from pydantic import BaseModel, Field
import json
from pathlib import Path

from ..auth import get_current_user, get_user_permissions
from ..models import APIResponse
from ..middleware import rate_limit, validate_input


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ux", tags=["user-experience"])


# Data Models
class UserPreferences(BaseModel):
    """User preference settings"""
    theme: str = Field(default="auto", pattern="^(light|dark|auto)$")
    language: str = Field(default="en", pattern="^[a-z]{2}$")
    units: str = Field(default="metric", pattern="^(metric|imperial)$")
    notifications_enabled: bool = True
    sound_enabled: bool = True
    mobile_optimized: bool = False
    dashboard_layout: Dict[str, Any] = Field(default_factory=dict)
    quick_actions: List[str] = Field(default_factory=list)
    accessibility_options: Dict[str, Any] = Field(default_factory=dict)


class OnboardingStep(BaseModel):
    """Onboarding step information"""
    step_id: str
    title: str
    description: str
    completed: bool = False
    required: bool = True
    estimated_time_minutes: int = 5
    prerequisites: List[str] = Field(default_factory=list)
    help_url: Optional[str] = None


class OnboardingProgress(BaseModel):
    """User onboarding progress"""
    user_id: str
    started_at: datetime
    last_updated: datetime
    current_step: str
    completed_steps: List[str] = Field(default_factory=list)
    skipped_steps: List[str] = Field(default_factory=list)
    completion_percentage: float = 0.0
    estimated_time_remaining: int = 0


class HelpContent(BaseModel):
    """Contextual help content"""
    content_id: str
    title: str
    content: str
    content_type: str = Field(pattern="^(text|html|markdown|video)$")
    category: str
    tags: List[str] = Field(default_factory=list)
    related_features: List[str] = Field(default_factory=list)
    last_updated: datetime
    view_count: int = 0


class UserFeedback(BaseModel):
    """User feedback submission"""
    feedback_type: str = Field(pattern="^(bug|feature|improvement|general)$")
    title: str = Field(min_length=5, max_length=100)
    description: str = Field(min_length=10, max_length=1000)
    category: str
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    user_contact: Optional[str] = None
    attachments: List[str] = Field(default_factory=list)


class UIComponent(BaseModel):
    """UI component configuration"""
    component_id: str
    component_type: str
    position: Dict[str, int]
    size: Dict[str, int]
    visible: bool = True
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)
    permissions: List[str] = Field(default_factory=list)


class DashboardLayout(BaseModel):
    """Dashboard layout configuration"""
    layout_id: str
    name: str
    description: str
    components: List[UIComponent]
    is_default: bool = False
    responsive_breakpoints: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


# Enhanced User Experience Service
class EnhancedUXService:
    """Service for enhanced user experience features"""
    
    def __init__(self):
        self.user_preferences: Dict[str, UserPreferences] = {}
        self.onboarding_progress: Dict[str, OnboardingProgress] = {}
        self.help_content: Dict[str, HelpContent] = {}
        self.dashboard_layouts: Dict[str, DashboardLayout] = {}
        self.feedback_submissions: List[UserFeedback] = []
        
        # Load default content
        self._load_default_help_content()
        self._load_default_onboarding_steps()
        self._load_default_dashboard_layouts()
    
    def _load_default_help_content(self):
        """Load default help content"""
        default_help = [
            HelpContent(
                content_id="dashboard_overview",
                title="Dashboard Overview",
                content="The dashboard provides a real-time view of your lawn mower's status and key metrics.",
                content_type="html",
                category="getting_started",
                tags=["dashboard", "overview"],
                related_features=["status", "metrics"],
                last_updated=datetime.now(),
                view_count=0
            ),
            HelpContent(
                content_id="safety_features",
                title="Safety Features",
                content="Learn about the comprehensive safety features that protect your lawn mower and surroundings.",
                content_type="html",
                category="safety",
                tags=["safety", "features"],
                related_features=["emergency_stop", "boundary_detection"],
                last_updated=datetime.now(),
                view_count=0
            ),
            HelpContent(
                content_id="mowing_patterns",
                title="Mowing Patterns",
                content="Discover different mowing patterns available and how to customize them for your lawn.",
                content_type="html",
                category="operations",
                tags=["patterns", "mowing"],
                related_features=["pattern_selection", "custom_patterns"],
                last_updated=datetime.now(),
                view_count=0
            )
        ]
        
        for help_item in default_help:
            self.help_content[help_item.content_id] = help_item
    
    def _load_default_onboarding_steps(self):
        """Load default onboarding steps"""
        self.default_onboarding_steps = [
            OnboardingStep(
                step_id="welcome",
                title="Welcome to LawnBerry",
                description="Get started with your autonomous lawn mower system",
                estimated_time_minutes=2,
                required=False
            ),
            OnboardingStep(
                step_id="safety_setup",
                title="Safety Configuration",
                description="Configure safety settings and emergency procedures",
                estimated_time_minutes=10,
                required=True,
                help_url="/help/safety_features"
            ),
            OnboardingStep(
                step_id="boundary_mapping",
                title="Boundary Mapping",
                description="Define your lawn boundaries and no-go zones",
                estimated_time_minutes=15,
                required=True,
                prerequisites=["safety_setup"]
            ),
            OnboardingStep(
                step_id="hardware_setup",
                title="Hardware Setup",
                description="Configure and test hardware components",
                estimated_time_minutes=20,
                required=True,
                prerequisites=["safety_setup"]
            ),
            OnboardingStep(
                step_id="pattern_selection",
                title="Mowing Pattern Selection",
                description="Choose and customize your mowing patterns",
                estimated_time_minutes=8,
                required=False,
                prerequisites=["boundary_mapping", "hardware_setup"]
            ),
            OnboardingStep(
                step_id="schedule_setup",
                title="Schedule Configuration",
                description="Set up your mowing schedule",
                estimated_time_minutes=5,
                required=False,
                prerequisites=["pattern_selection"]
            ),
            OnboardingStep(
                step_id="first_test_run",
                title="First Test Run",
                description="Perform a supervised test run",
                estimated_time_minutes=30,
                required=True,
                prerequisites=["boundary_mapping", "hardware_setup"]
            )
        ]
    
    def _load_default_dashboard_layouts(self):
        """Load default dashboard layouts"""
        default_layout = DashboardLayout(
            layout_id="default",
            name="Default Layout",
            description="Standard dashboard layout for most users",
            components=[
                UIComponent(
                    component_id="status_panel",
                    component_type="status",
                    position={"x": 0, "y": 0},
                    size={"width": 6, "height": 4}
                ),
                UIComponent(
                    component_id="map_view",
                    component_type="map",
                    position={"x": 6, "y": 0},
                    size={"width": 6, "height": 8}
                ),
                UIComponent(
                    component_id="battery_status",
                    component_type="battery",
                    position={"x": 0, "y": 4},
                    size={"width": 3, "height": 2}
                ),
                UIComponent(
                    component_id="weather_widget",
                    component_type="weather",
                    position={"x": 3, "y": 4},
                    size={"width": 3, "height": 2}
                )
            ],
            is_default=True,
            responsive_breakpoints={
                "mobile": {"columns": 2, "max_width": 768},
                "tablet": {"columns": 4, "max_width": 1024},
                "desktop": {"columns": 12, "max_width": None}
            },
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self.dashboard_layouts["default"] = default_layout
    
    async def get_user_preferences(self, user_id: str) -> UserPreferences:
        """Get user preferences"""
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = UserPreferences()
        return self.user_preferences[user_id]
    
    async def update_user_preferences(self, user_id: str, preferences: UserPreferences) -> bool:
        """Update user preferences"""
        try:
            self.user_preferences[user_id] = preferences
            # Save to persistent storage
            await self._save_user_preferences(user_id, preferences)
            return True
        except Exception as e:
            logger.error(f"Failed to update user preferences: {e}")
            return False
    
    async def get_onboarding_progress(self, user_id: str) -> OnboardingProgress:
        """Get user onboarding progress"""
        if user_id not in self.onboarding_progress:
            progress = OnboardingProgress(
                user_id=user_id,
                started_at=datetime.now(),
                last_updated=datetime.now(),
                current_step="welcome"
            )
            self.onboarding_progress[user_id] = progress
        
        return self.onboarding_progress[user_id]
    
    async def update_onboarding_progress(self, user_id: str, step_id: str, completed: bool = True, skipped: bool = False) -> OnboardingProgress:
        """Update onboarding progress"""
        progress = await self.get_onboarding_progress(user_id)
        
        if completed and step_id not in progress.completed_steps:
            progress.completed_steps.append(step_id)
        elif skipped and step_id not in progress.skipped_steps:
            progress.skipped_steps.append(step_id)
        
        # Update completion percentage
        total_steps = len(self.default_onboarding_steps)
        completed_count = len(progress.completed_steps)
        progress.completion_percentage = (completed_count / total_steps) * 100
        
        # Find next step
        next_step = self._find_next_onboarding_step(progress)
        if next_step:
            progress.current_step = next_step.step_id
            progress.estimated_time_remaining = sum(
                step.estimated_time_minutes 
                for step in self.default_onboarding_steps
                if step.step_id not in progress.completed_steps + progress.skipped_steps
            )
        
        progress.last_updated = datetime.now()
        
        return progress
    
    def _find_next_onboarding_step(self, progress: OnboardingProgress) -> Optional[OnboardingStep]:
        """Find the next available onboarding step"""
        for step in self.default_onboarding_steps:
            if step.step_id in progress.completed_steps or step.step_id in progress.skipped_steps:
                continue
            
            # Check prerequisites
            if all(prereq in progress.completed_steps for prereq in step.prerequisites):
                return step
        
        return None
    
    async def get_contextual_help(self, feature: str, user_level: str = "basic") -> List[HelpContent]:
        """Get contextual help for a feature"""
        relevant_help = []
        
        for help_item in self.help_content.values():
            if feature in help_item.related_features or feature in help_item.tags:
                relevant_help.append(help_item)
                help_item.view_count += 1
        
        return relevant_help
    
    async def search_help_content(self, query: str) -> List[HelpContent]:
        """Search help content"""
        results = []
        query_lower = query.lower()
        
        for help_item in self.help_content.values():
            if (query_lower in help_item.title.lower() or 
                query_lower in help_item.content.lower() or
                any(query_lower in tag.lower() for tag in help_item.tags)):
                results.append(help_item)
        
        # Sort by relevance (view count for now)
        results.sort(key=lambda x: x.view_count, reverse=True)
        
        return results
    
    async def submit_feedback(self, user_id: str, feedback: UserFeedback) -> str:
        """Submit user feedback"""
        feedback_id = f"feedback_{len(self.feedback_submissions) + 1:06d}"
        
        # Add metadata
        feedback_with_meta = {
            "id": feedback_id,
            "user_id": user_id,
            "submitted_at": datetime.now(),
            "status": "submitted",
            **feedback.dict()
        }
        
        self.feedback_submissions.append(feedback_with_meta)
        
        # Log feedback
        logger.info(f"User feedback submitted: {feedback_id} - {feedback.title}")
        
        return feedback_id
    
    async def get_dashboard_layout(self, user_id: str, layout_id: Optional[str] = None) -> DashboardLayout:
        """Get dashboard layout for user"""
        if layout_id and layout_id in self.dashboard_layouts:
            return self.dashboard_layouts[layout_id]
        
        # Return user's custom layout or default
        user_prefs = await self.get_user_preferences(user_id)
        if "custom_layout" in user_prefs.dashboard_layout:
            # Build custom layout from preferences
            pass
        
        return self.dashboard_layouts["default"]
    
    async def _save_user_preferences(self, user_id: str, preferences: UserPreferences):
        """Save user preferences to persistent storage"""
        # Implementation would save to database or file
        pass


# Initialize service
ux_service = EnhancedUXService()


# API Endpoints

@router.get("/preferences", response_model=APIResponse[UserPreferences])
async def get_user_preferences(current_user: dict = Depends(get_current_user)):
    """Get user preferences"""
    try:
        preferences = await ux_service.get_user_preferences(current_user["id"])
        return APIResponse(success=True, data=preferences)
    except Exception as e:
        logger.error(f"Failed to get user preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to get preferences")


@router.put("/preferences", response_model=APIResponse[bool])
async def update_user_preferences(
    preferences: UserPreferences,
    current_user: dict = Depends(get_current_user)
):
    """Update user preferences"""
    try:
        success = await ux_service.update_user_preferences(current_user["id"], preferences)
        return APIResponse(success=success, data=success)
    except Exception as e:
        logger.error(f"Failed to update user preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to update preferences")


@router.get("/onboarding/progress", response_model=APIResponse[OnboardingProgress])
async def get_onboarding_progress(current_user: dict = Depends(get_current_user)):
    """Get user onboarding progress"""
    try:
        progress = await ux_service.get_onboarding_progress(current_user["id"])
        return APIResponse(success=True, data=progress)
    except Exception as e:
        logger.error(f"Failed to get onboarding progress: {e}")
        raise HTTPException(status_code=500, detail="Failed to get onboarding progress")


@router.post("/onboarding/step/{step_id}/complete", response_model=APIResponse[OnboardingProgress])
async def complete_onboarding_step(
    step_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Mark onboarding step as complete"""
    try:
        progress = await ux_service.update_onboarding_progress(current_user["id"], step_id, completed=True)
        return APIResponse(success=True, data=progress)
    except Exception as e:
        logger.error(f"Failed to complete onboarding step: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete step")


@router.post("/onboarding/step/{step_id}/skip", response_model=APIResponse[OnboardingProgress])
async def skip_onboarding_step(
    step_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Skip onboarding step"""
    try:
        progress = await ux_service.update_onboarding_progress(current_user["id"], step_id, completed=False, skipped=True)
        return APIResponse(success=True, data=progress)
    except Exception as e:
        logger.error(f"Failed to skip onboarding step: {e}")
        raise HTTPException(status_code=500, detail="Failed to skip step")


@router.get("/help/contextual/{feature}", response_model=APIResponse[List[HelpContent]])
async def get_contextual_help(
    feature: str,
    user_level: str = "basic",
    current_user: dict = Depends(get_current_user)
):
    """Get contextual help for a feature"""
    try:
        help_content = await ux_service.get_contextual_help(feature, user_level)
        return APIResponse(success=True, data=help_content)
    except Exception as e:
        logger.error(f"Failed to get contextual help: {e}")
        raise HTTPException(status_code=500, detail="Failed to get help content")


@router.get("/help/search", response_model=APIResponse[List[HelpContent]])
async def search_help_content(
    q: str,
    current_user: dict = Depends(get_current_user)
):
    """Search help content"""
    try:
        results = await ux_service.search_help_content(q)
        return APIResponse(success=True, data=results)
    except Exception as e:
        logger.error(f"Failed to search help content: {e}")
        raise HTTPException(status_code=500, detail="Failed to search help content")


@router.post("/feedback", response_model=APIResponse[str])
async def submit_feedback(
    feedback: UserFeedback,
    current_user: dict = Depends(get_current_user)
):
    """Submit user feedback"""
    try:
        feedback_id = await ux_service.submit_feedback(current_user["id"], feedback)
        return APIResponse(success=True, data=feedback_id, message="Feedback submitted successfully")
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit feedback")


@router.get("/dashboard/layout", response_model=APIResponse[DashboardLayout])
async def get_dashboard_layout(
    layout_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get dashboard layout"""
    try:
        layout = await ux_service.get_dashboard_layout(current_user["id"], layout_id)
        return APIResponse(success=True, data=layout)
    except Exception as e:
        logger.error(f"Failed to get dashboard layout: {e}")
        raise HTTPException(status_code=500, detail="Failed to get dashboard layout")


@router.websocket("/ws/ux-updates")
async def websocket_ux_updates(websocket: WebSocket):
    """WebSocket for real-time UX updates"""
    await websocket.accept()
    
    try:
        while True:
            # Send periodic updates
            await asyncio.sleep(5)
            
            # Send UI performance metrics
            metrics = {
                "type": "performance_metrics",
                "data": {
                    "load_time": 250,  # ms
                    "render_time": 16,  # ms
                    "memory_usage": 45.2,  # MB
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            await websocket.send_json(metrics)
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()


# Mobile optimization endpoints
@router.get("/mobile/optimizations", response_model=APIResponse[Dict[str, Any]])
async def get_mobile_optimizations(current_user: dict = Depends(get_current_user)):
    """Get mobile-specific optimizations"""
    try:
        optimizations = {
            "touch_targets": {
                "minimum_size": 44,  # pixels
                "spacing": 8
            },
            "lazy_loading": {
                "enabled": True,
                "threshold": 50  # pixels from viewport
            },
            "data_compression": {
                "enabled": True,
                "level": "medium"
            },
            "offline_mode": {
                "enabled": True,
                "cache_duration": 3600  # seconds
            },
            "reduced_animations": {
                "enabled": False,  # Based on user preference
                "respect_system_setting": True
            }
        }
        
        return APIResponse(success=True, data=optimizations)
    except Exception as e:
        logger.error(f"Failed to get mobile optimizations: {e}")
        raise HTTPException(status_code=500, detail="Failed to get mobile optimizations")


@router.get("/accessibility/options", response_model=APIResponse[Dict[str, Any]])
async def get_accessibility_options(current_user: dict = Depends(get_current_user)):
    """Get accessibility options"""
    try:
        options = {
            "high_contrast": False,
            "large_text": False,
            "screen_reader_support": True,
            "keyboard_navigation": True,
            "voice_commands": False,
            "color_blind_friendly": True,
            "reduced_motion": False,
            "focus_indicators": True
        }
        
        return APIResponse(success=True, data=options)
    except Exception as e:
        logger.error(f"Failed to get accessibility options: {e}")
        raise HTTPException(status_code=500, detail="Failed to get accessibility options")


@router.post("/analytics/interaction", response_model=APIResponse[bool])
async def track_user_interaction(
    interaction_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Track user interaction for UX analytics"""
    try:
        # Log interaction for analytics
        logger.info(f"User interaction: {interaction_data.get('action')} on {interaction_data.get('component')}")
        
        # Store in analytics system
        # This would be implemented based on analytics requirements
        
        return APIResponse(success=True, data=True)
    except Exception as e:
        logger.error(f"Failed to track interaction: {e}")
        raise HTTPException(status_code=500, detail="Failed to track interaction")
