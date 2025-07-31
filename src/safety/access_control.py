"""
Safety Access Control System
Implements tiered access control for safety configuration with user training integration
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class SafetyAccessLevel(Enum):
    """Safety access levels with increasing privileges"""
    BASIC = "basic"
    ADVANCED = "advanced"
    TECHNICIAN = "technician"


class TrainingModule(Enum):
    """Available training modules"""
    BASIC_SAFETY = "basic_safety"
    ADVANCED_CONFIGURATION = "advanced_configuration"
    SENSOR_SYSTEMS = "sensor_systems"
    EMERGENCY_PROCEDURES = "emergency_procedures"
    MAINTENANCE_SAFETY = "maintenance_safety"
    SYSTEM_DIAGNOSTICS = "system_diagnostics"


@dataclass
class TrainingRecord:
    """Training completion record"""
    module: TrainingModule
    completed_at: datetime
    score: float
    expires_at: Optional[datetime] = None
    certificate_id: str = ""


@dataclass
class SafetyUserProfile:
    """User profile with safety access and training"""
    username: str
    access_level: SafetyAccessLevel
    training_records: List[TrainingRecord] = field(default_factory=list)
    experience_hours: float = 0.0
    safety_violations: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_training_update: datetime = field(default_factory=datetime.now)
    
    def has_training(self, module: TrainingModule) -> bool:
        """Check if user has completed required training"""
        for record in self.training_records:
            if record.module == module:
                if record.expires_at is None or record.expires_at > datetime.now():
                    return True
        return False
    
    def get_training_score(self, module: TrainingModule) -> Optional[float]:
        """Get training score for a module"""
        for record in self.training_records:
            if record.module == module:
                if record.expires_at is None or record.expires_at > datetime.now():
                    return record.score
        return None


class SafetyAccessController:
    """Controls access to safety features based on user level and training"""
    
    def __init__(self):
        self.user_profiles: Dict[str, SafetyUserProfile] = {}
        self.access_requirements = self._define_access_requirements()
        self.training_content = self._define_training_content()
        
    def _define_access_requirements(self) -> Dict[SafetyAccessLevel, Dict[str, Any]]:
        """Define access requirements for each level"""
        return {
            SafetyAccessLevel.BASIC: {
                "required_training": [TrainingModule.BASIC_SAFETY],
                "min_experience_hours": 0,
                "max_safety_violations": 5,
                "configurable_parameters": [
                    "emergency_stop_distance",
                    "person_safety_radius",
                    "pet_safety_radius",
                    "boundary_safety_margin",
                    "enable_weather_safety",
                    "enable_vision_safety"
                ],
                "feature_access": [
                    "basic_mowing_patterns",
                    "standard_boundary_control",
                    "basic_weather_monitoring",
                    "emergency_stop",
                    "basic_status_monitoring"
                ]
            },
            SafetyAccessLevel.ADVANCED: {
                "required_training": [
                    TrainingModule.BASIC_SAFETY,
                    TrainingModule.ADVANCED_CONFIGURATION,
                    TrainingModule.SENSOR_SYSTEMS
                ],
                "min_experience_hours": 20,
                "max_safety_violations": 2,
                "configurable_parameters": [
                    "max_safe_tilt_angle",
                    "min_safe_ground_clearance",
                    "collision_threshold_g",
                    "sensor_fusion_weights",
                    "adaptive_safety_thresholds",
                    "performance_vs_safety_balance",
                    "sensor_conflict_resolution"
                ],
                "feature_access": [
                    "advanced_mowing_patterns",
                    "sensor_fusion_configuration",
                    "performance_optimization",
                    "advanced_weather_adaptation",
                    "predictive_safety_features",
                    "custom_safety_profiles"
                ]
            },
            SafetyAccessLevel.TECHNICIAN: {
                "required_training": [
                    TrainingModule.BASIC_SAFETY,
                    TrainingModule.ADVANCED_CONFIGURATION,
                    TrainingModule.SENSOR_SYSTEMS,
                    TrainingModule.EMERGENCY_PROCEDURES,
                    TrainingModule.MAINTENANCE_SAFETY,
                    TrainingModule.SYSTEM_DIAGNOSTICS
                ],
                "min_experience_hours": 50,
                "max_safety_violations": 0,
                "configurable_parameters": [
                    "emergency_response_time_ms",
                    "safety_update_rate_hz",
                    "sensor_calibration_parameters",
                    "hardware_safety_overrides",
                    "diagnostic_safety_parameters",
                    "maintenance_lockout_overrides"
                ],
                "feature_access": [
                    "full_system_diagnostics",
                    "hardware_configuration",
                    "sensor_calibration",
                    "emergency_overrides",
                    "maintenance_mode_access",
                    "safety_system_debugging",
                    "firmware_safety_parameters"
                ]
            }
        }
    
    def _define_training_content(self) -> Dict[TrainingModule, Dict[str, Any]]:
        """Define training module content and requirements"""
        return {
            TrainingModule.BASIC_SAFETY: {
                "title": "Basic Safety Operations",
                "description": "Fundamental safety concepts and basic system operation",
                "duration_minutes": 30,
                "passing_score": 80.0,
                "expires_months": 12,
                "topics": [
                    "Emergency stop procedures",
                    "Personal protective equipment",
                    "Basic hazard recognition",
                    "Standard operating procedures",
                    "Boundary setup and validation"
                ]
            },
            TrainingModule.ADVANCED_CONFIGURATION: {
                "title": "Advanced Safety Configuration",
                "description": "Performance vs safety trade-offs and advanced parameters",
                "duration_minutes": 60,
                "passing_score": 85.0,
                "expires_months": 6,
                "topics": [
                    "Safety parameter optimization",
                    "Performance trade-off analysis",
                    "Risk assessment procedures",
                    "Advanced boundary configuration",
                    "Weather-based safety adjustments"
                ]
            },
            TrainingModule.SENSOR_SYSTEMS: {
                "title": "Sensor Systems and Fusion",
                "description": "Understanding sensor integration and fusion algorithms",
                "duration_minutes": 90,
                "passing_score": 90.0,
                "expires_months": 6,
                "topics": [
                    "Multi-sensor fusion principles",
                    "Sensor conflict resolution",
                    "Predictive obstacle detection",
                    "Environmental sensor integration",
                    "Sensor diagnostics and validation"
                ]
            },
            TrainingModule.EMERGENCY_PROCEDURES: {
                "title": "Emergency Response Procedures",
                "description": "Comprehensive emergency response and escalation procedures",
                "duration_minutes": 45,
                "passing_score": 95.0,
                "expires_months": 6,
                "topics": [
                    "Emergency escalation procedures",
                    "Remote shutdown protocols",
                    "Emergency contact systems",
                    "Incident documentation",
                    "Recovery procedures"
                ]
            },
            TrainingModule.MAINTENANCE_SAFETY: {
                "title": "Maintenance Safety Procedures",
                "description": "Safe maintenance practices and system lockouts",
                "duration_minutes": 75,
                "passing_score": 90.0,
                "expires_months": 12,
                "topics": [
                    "Lockout/tagout procedures",
                    "Blade safety protocols",
                    "Battery safety procedures",
                    "Diagnostic safety measures",
                    "Maintenance scheduling"
                ]
            },
            TrainingModule.SYSTEM_DIAGNOSTICS: {
                "title": "System Diagnostics and Troubleshooting",
                "description": "Advanced diagnostics and safety system validation",
                "duration_minutes": 120,
                "passing_score": 85.0,
                "expires_months": 6,
                "topics": [
                    "Safety system diagnostics",
                    "Sensor validation procedures",
                    "Performance monitoring",
                    "Troubleshooting methodologies",
                    "System health assessment"
                ]
            }
        }
    
    async def register_user(self, username: str, initial_level: SafetyAccessLevel = SafetyAccessLevel.BASIC) -> bool:
        """Register a new user with safety access profile"""
        if username in self.user_profiles:
            logger.warning(f"User {username} already exists in safety access system")
            return False
        
        self.user_profiles[username] = SafetyUserProfile(
            username=username,
            access_level=initial_level
        )
        
        logger.info(f"Registered user {username} with {initial_level.value} safety access")
        return True
    
    async def check_parameter_access(self, username: str, parameter: str) -> bool:
        """Check if user can modify a specific safety parameter"""
        profile = self.user_profiles.get(username)
        if not profile:
            logger.warning(f"User {username} not found in safety access system")
            return False
        
        # Check if user meets requirements for their access level
        if not await self._validate_access_requirements(profile):
            logger.warning(f"User {username} does not meet requirements for {profile.access_level.value} access")
            return False
        
        # Check if parameter is allowed for this access level
        requirements = self.access_requirements[profile.access_level]
        return parameter in requirements["configurable_parameters"]
    
    async def check_feature_access(self, username: str, feature: str) -> bool:
        """Check if user can access a specific safety feature"""
        profile = self.user_profiles.get(username)
        if not profile:
            return False
        
        if not await self._validate_access_requirements(profile):
            return False
        
        requirements = self.access_requirements[profile.access_level]
        return feature in requirements["feature_access"]
    
    async def _validate_access_requirements(self, profile: SafetyUserProfile) -> bool:
        """Validate that user meets all requirements for their access level"""
        requirements = self.access_requirements[profile.access_level]
        
        # Check training requirements
        for required_module in requirements["required_training"]:
            if not profile.has_training(required_module):
                return False
        
        # Check experience requirements
        if profile.experience_hours < requirements["min_experience_hours"]:
            return False
        
        # Check safety violations
        if profile.safety_violations > requirements["max_safety_violations"]:
            return False
        
        return True
    
    async def complete_training(self, username: str, module: TrainingModule, score: float) -> bool:
        """Record training completion for a user"""
        profile = self.user_profiles.get(username)
        if not profile:
            return False
        
        training_info = self.training_content[module]
        if score < training_info["passing_score"]:
            logger.warning(f"User {username} failed training {module.value} with score {score}")
            return False
        
        # Calculate expiration date
        expires_at = None
        if training_info.get("expires_months"):
            expires_at = datetime.now() + timedelta(days=training_info["expires_months"] * 30)
        
        # Remove any existing record for this module
        profile.training_records = [r for r in profile.training_records if r.module != module]
        
        # Add new training record
        record = TrainingRecord(
            module=module,
            completed_at=datetime.now(),
            score=score,
            expires_at=expires_at,
            certificate_id=f"{username}_{module.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        profile.training_records.append(record)
        profile.last_training_update = datetime.now()
        
        logger.info(f"User {username} completed training {module.value} with score {score}")
        
        # Check if user can be promoted to higher access level
        await self._check_access_level_promotion(profile)
        
        return True
    
    async def _check_access_level_promotion(self, profile: SafetyUserProfile):
        """Check if user can be promoted to a higher access level"""
        current_level = profile.access_level
        
        # Try to promote to higher levels
        levels = [SafetyAccessLevel.BASIC, SafetyAccessLevel.ADVANCED, SafetyAccessLevel.TECHNICIAN]
        current_index = levels.index(current_level)
        
        for i in range(current_index + 1, len(levels)):
            test_level = levels[i]
            profile.access_level = test_level
            
            if await self._validate_access_requirements(profile):
                logger.info(f"User {profile.username} promoted to {test_level.value} access level")
                return
            else:
                # Revert to previous level
                profile.access_level = current_level
                break
    
    async def record_safety_violation(self, username: str, violation_type: str, description: str):
        """Record a safety violation for a user"""
        profile = self.user_profiles.get(username)
        if not profile:
            return
        
        profile.safety_violations += 1
        logger.warning(f"Safety violation recorded for user {username}: {violation_type} - {description}")
        
        # Check if user needs to be demoted
        await self._check_access_level_demotion(profile)
    
    async def _check_access_level_demotion(self, profile: SafetyUserProfile):
        """Check if user needs to be demoted due to violations"""
        if not await self._validate_access_requirements(profile):
            # Demote to lower level
            levels = [SafetyAccessLevel.TECHNICIAN, SafetyAccessLevel.ADVANCED, SafetyAccessLevel.BASIC]
            current_index = levels.index(profile.access_level)
            
            for i in range(current_index + 1, len(levels)):
                test_level = levels[i]
                profile.access_level = test_level
                
                if await self._validate_access_requirements(profile):
                    logger.warning(f"User {profile.username} demoted to {test_level.value} access level")
                    return
    
    async def get_user_status(self, username: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive user safety access status"""
        profile = self.user_profiles.get(username)
        if not profile:
            return None
        
        requirements = self.access_requirements[profile.access_level]
        is_qualified = await self._validate_access_requirements(profile)
        
        missing_training = []
        for required_module in requirements["required_training"]:
            if not profile.has_training(required_module):
                missing_training.append(required_module.value)
        
        return {
            "username": profile.username,
            "access_level": profile.access_level.value,
            "is_qualified": is_qualified,
            "experience_hours": profile.experience_hours,
            "safety_violations": profile.safety_violations,
            "training_records": [
                {
                    "module": record.module.value,
                    "completed_at": record.completed_at.isoformat(),
                    "score": record.score,
                    "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                    "is_valid": record.expires_at is None or record.expires_at > datetime.now()
                }
                for record in profile.training_records
            ],
            "missing_training": missing_training,
            "configurable_parameters": requirements["configurable_parameters"],
            "feature_access": requirements["feature_access"]
        }
    
    async def get_training_modules(self) -> Dict[str, Any]:
        """Get all available training modules"""
        return {
            module.value: {
                "title": content["title"],
                "description": content["description"],
                "duration_minutes": content["duration_minutes"],
                "passing_score": content["passing_score"],
                "expires_months": content.get("expires_months"),
                "topics": content["topics"]
            }
            for module, content in self.training_content.items()
        }
