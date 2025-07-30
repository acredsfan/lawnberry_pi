"""
State Manager
Manages operational state persistence and recovery
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timedelta
from enum import Enum

from .cache_manager import CacheManager
from .database_manager import DatabaseManager
from .models import OperationalState, DataType


class SystemState(Enum):
    """System operational states"""
    STARTING = "starting"
    IDLE = "idle"
    MOWING = "mowing"
    NAVIGATING = "navigating"
    CHARGING = "charging"
    ERROR = "error"
    EMERGENCY_STOP = "emergency_stop"
    MAINTENANCE = "maintenance"
    SHUTTING_DOWN = "shutting_down"


class OperationMode(Enum):
    """Operation modes"""
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    SCHEDULED = "scheduled"
    ECO = "eco"
    HIGH_PERFORMANCE = "high_performance"
    SAFETY = "safety"


class StateManager:
    """Manages system state persistence and recovery"""
    
    def __init__(self, cache_manager: CacheManager, db_manager: DatabaseManager):
        self.logger = logging.getLogger(__name__)
        self.cache = cache_manager
        self.db = db_manager
        
        # Current system state
        self._current_state: Optional[OperationalState] = None
        self._state_lock = asyncio.Lock()
        
        # State transition tracking
        self._state_history: List[Dict[str, Any]] = []
        self._max_history = 100
        
        # Recovery data
        self._recovery_data: Dict[str, Any] = {}
        self._session_id = None
        
        # Persistence settings
        self._persist_interval = 5  # seconds
        self._persist_task: Optional[asyncio.Task] = None
        
        # State validation
        self._valid_transitions = {
            SystemState.STARTING: [SystemState.IDLE, SystemState.ERROR],
            SystemState.IDLE: [SystemState.MOWING, SystemState.CHARGING, SystemState.MAINTENANCE, 
                              SystemState.EMERGENCY_STOP, SystemState.SHUTTING_DOWN],
            SystemState.MOWING: [SystemState.IDLE, SystemState.NAVIGATING, SystemState.CHARGING,
                               SystemState.EMERGENCY_STOP, SystemState.ERROR],
            SystemState.NAVIGATING: [SystemState.MOWING, SystemState.IDLE, SystemState.CHARGING,
                                   SystemState.EMERGENCY_STOP, SystemState.ERROR],
            SystemState.CHARGING: [SystemState.IDLE, SystemState.MOWING, SystemState.EMERGENCY_STOP],
            SystemState.ERROR: [SystemState.IDLE, SystemState.MAINTENANCE, SystemState.EMERGENCY_STOP],
            SystemState.EMERGENCY_STOP: [SystemState.IDLE, SystemState.ERROR, SystemState.SHUTTING_DOWN],
            SystemState.MAINTENANCE: [SystemState.IDLE, SystemState.ERROR],
            SystemState.SHUTTING_DOWN: []
        }
        
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize state manager"""
        try:
            # Generate session ID
            self._session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Try to recover previous state
            await self._recover_state()
            
            # Start persistence task
            self._persist_task = asyncio.create_task(self._persistence_loop())
            
            self._initialized = True
            self.logger.info(f"State manager initialized with session {self._session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"State manager initialization failed: {e}")
            return False
    
    async def _recover_state(self):
        """Recover state from previous session"""
        try:
            # Try cache first for recent state
            cached_state = await self.cache.get(DataType.OPERATIONAL, "current_state")
            
            if cached_state:
                self._current_state = OperationalState.from_dict(cached_state)
                self.logger.info("Recovered state from cache")
            else:
                # Fall back to database
                db_state = await self.db.get_latest_operational_state()
                if db_state:
                    self._current_state = db_state
                    self.logger.info("Recovered state from database")
                else:
                    # Initialize with default state
                    self._current_state = OperationalState(
                        state=SystemState.STARTING.value,
                        mode=OperationMode.AUTOMATIC.value,
                        battery_level=0.0,
                        current_task=None,
                        progress=0.0,
                        estimated_completion=None,
                        metadata={"session_id": self._session_id}
                    )
                    self.logger.info("Initialized with default state")
            
            # Try to recover session data
            recovery_data = await self.cache.get(DataType.OPERATIONAL, "recovery_data")
            if recovery_data:
                self._recovery_data = recovery_data
                self.logger.info("Recovered session data")
                
        except Exception as e:
            self.logger.error(f"State recovery failed: {e}")
            # Initialize with safe default state
            self._current_state = OperationalState(
                state=SystemState.ERROR.value,
                mode=OperationMode.SAFETY.value,
                battery_level=0.0,
                metadata={"recovery_error": str(e), "session_id": self._session_id}
            )
    
    async def get_current_state(self) -> OperationalState:
        """Get current operational state"""
        async with self._state_lock:
            if self._current_state is None:
                await self._recover_state()
            return self._current_state
    
    async def update_state(self, new_state: str = None, mode: str = None,
                          battery_level: float = None, current_task: str = None,
                          progress: float = None, estimated_completion: datetime = None,
                          metadata: Dict[str, Any] = None) -> bool:
        """Update operational state"""
        async with self._state_lock:
            try:
                if self._current_state is None:
                    await self._recover_state()
                
                old_state = self._current_state.state
                
                # Create updated state
                updated_state = OperationalState(
                    state=new_state or self._current_state.state,
                    mode=mode or self._current_state.mode,
                    battery_level=battery_level if battery_level is not None else self._current_state.battery_level,
                    current_task=current_task if current_task is not None else self._current_state.current_task,
                    progress=progress if progress is not None else self._current_state.progress,
                    estimated_completion=estimated_completion if estimated_completion is not None else self._current_state.estimated_completion,
                    last_update=datetime.now(),
                    metadata={**(self._current_state.metadata or {}), **(metadata or {})}
                )
                
                # Validate state transition
                if new_state and not self._is_valid_transition(old_state, new_state):
                    self.logger.warning(f"Invalid state transition: {old_state} -> {new_state}")
                    return False
                
                # Update current state
                self._current_state = updated_state
                
                # Add to history
                self._add_to_history(old_state, new_state or old_state)
                
                # Cache immediately for quick access
                await self.cache.set(DataType.OPERATIONAL, "current_state", updated_state.to_dict(), ttl=30)
                
                self.logger.debug(f"State updated: {old_state} -> {updated_state.state}")
                return True
                
            except Exception as e:
                self.logger.error(f"State update failed: {e}")
                return False
    
    def _is_valid_transition(self, from_state: str, to_state: str) -> bool:
        """Validate state transition"""
        try:
            from_enum = SystemState(from_state)
            to_enum = SystemState(to_state)
            
            return to_enum in self._valid_transitions.get(from_enum, [])
        except ValueError:
            # Unknown states - allow transition but log warning
            self.logger.warning(f"Unknown state in transition: {from_state} -> {to_state}")
            return True
    
    def _add_to_history(self, from_state: str, to_state: str):
        """Add state transition to history"""
        transition = {
            "timestamp": datetime.now().isoformat(),
            "from_state": from_state,
            "to_state": to_state,
            "session_id": self._session_id
        }
        
        self._state_history.append(transition)
        
        # Trim history if too long
        if len(self._state_history) > self._max_history:
            self._state_history = self._state_history[-self._max_history:]
    
    async def set_recovery_data(self, key: str, value: Any):
        """Set recovery data for session persistence"""
        self._recovery_data[key] = value
        
        # Persist to cache immediately
        await self.cache.set(DataType.OPERATIONAL, "recovery_data", self._recovery_data, ttl=3600)
    
    async def get_recovery_data(self, key: str, default: Any = None) -> Any:
        """Get recovery data"""
        return self._recovery_data.get(key, default)
    
    async def clear_recovery_data(self, key: str = None):
        """Clear recovery data"""
        if key:
            self._recovery_data.pop(key, None)
        else:
            self._recovery_data.clear()
        
        await self.cache.set(DataType.OPERATIONAL, "recovery_data", self._recovery_data, ttl=3600)
    
    async def emergency_stop(self, reason: str = "Emergency stop triggered"):
        """Trigger emergency stop state"""
        await self.update_state(
            new_state=SystemState.EMERGENCY_STOP.value,
            mode=OperationMode.SAFETY.value,
            current_task="EMERGENCY_STOP",
            metadata={"emergency_reason": reason, "emergency_time": datetime.now().isoformat()}
        )
        
        # Store emergency data for recovery
        await self.set_recovery_data("emergency_stop", {
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "previous_state": self._state_history[-1] if self._state_history else None
        })
        
        self.logger.critical(f"Emergency stop activated: {reason}")
    
    async def can_resume_operation(self) -> bool:
        """Check if system can resume normal operation"""
        current = await self.get_current_state()
        
        # Check if in a resumable state
        resumable_states = [SystemState.IDLE.value, SystemState.CHARGING.value]
        if current.state not in resumable_states:
            return False
        
        # Check battery level
        if current.battery_level < 0.2:  # 20% minimum
            return False
        
        # Check for unresolved errors
        if current.metadata.get("unresolved_errors"):
            return False
        
        return True
    
    async def get_state_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get state transition history"""
        return self._state_history[-limit:] if self._state_history else []
    
    async def get_session_info(self) -> Dict[str, Any]:
        """Get current session information"""
        current = await self.get_current_state()
        
        session_start = None
        if self._state_history:
            session_start = self._state_history[0]["timestamp"]
        
        return {
            "session_id": self._session_id,
            "session_start": session_start,
            "current_state": current.to_dict(),
            "state_transitions": len(self._state_history),
            "recovery_data_keys": list(self._recovery_data.keys()),
            "uptime_seconds": (datetime.now() - current.last_update).total_seconds() if current else 0
        }
    
    async def _persistence_loop(self):
        """Background task to persist state regularly"""
        while True:
            try:
                await asyncio.sleep(self._persist_interval)
                
                if self._current_state:
                    # Store to database
                    await self.db.store_operational_state(self._current_state)
                    
                    # Update cache with longer TTL
                    await self.cache.set(DataType.OPERATIONAL, "current_state", 
                                       self._current_state.to_dict(), ttl=300)
                    
                    # Persist state history
                    if self._state_history:
                        await self.cache.set(DataType.OPERATIONAL, "state_history", 
                                           self._state_history, ttl=3600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"State persistence error: {e}")
    
    async def create_checkpoint(self, name: str) -> bool:
        """Create a state checkpoint for recovery"""
        try:
            checkpoint_data = {
                "name": name,
                "timestamp": datetime.now().isoformat(),
                "state": self._current_state.to_dict() if self._current_state else None,
                "recovery_data": self._recovery_data.copy(),
                "state_history": self._state_history[-10:],  # Last 10 transitions
                "session_id": self._session_id
            }
            
            checkpoint_key = f"checkpoint_{name}"
            await self.cache.set(DataType.OPERATIONAL, checkpoint_key, checkpoint_data, ttl=86400)  # 24 hours
            
            self.logger.info(f"Checkpoint '{name}' created")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create checkpoint '{name}': {e}")
            return False
    
    async def restore_checkpoint(self, name: str) -> bool:
        """Restore from a checkpoint"""
        try:
            checkpoint_key = f"checkpoint_{name}"
            checkpoint_data = await self.cache.get(DataType.OPERATIONAL, checkpoint_key)
            
            if not checkpoint_data:
                self.logger.error(f"Checkpoint '{name}' not found")
                return False
            
            # Restore state
            if checkpoint_data.get("state"):
                self._current_state = OperationalState.from_dict(checkpoint_data["state"])
            
            # Restore recovery data
            self._recovery_data = checkpoint_data.get("recovery_data", {})
            
            # Add restoration to history
            self._add_to_history("CHECKPOINT_RESTORE", self._current_state.state if self._current_state else "UNKNOWN")
            
            self.logger.info(f"Restored from checkpoint '{name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to restore checkpoint '{name}': {e}")
            return False
    
    async def shutdown(self):
        """Graceful shutdown of state manager"""
        try:
            # Update state to shutting down
            await self.update_state(new_state=SystemState.SHUTTING_DOWN.value)
            
            # Cancel persistence task
            if self._persist_task:
                self._persist_task.cancel()
                try:
                    await self._persist_task
                except asyncio.CancelledError:
                    pass
            
            # Final state persistence
            if self._current_state:
                await self.db.store_operational_state(self._current_state)
                await self.cache.set(DataType.OPERATIONAL, "current_state", 
                                   self._current_state.to_dict(), ttl=3600)
            
            # Store final session data
            await self.cache.set(DataType.OPERATIONAL, "recovery_data", 
                               self._recovery_data, ttl=86400)
            
            self.logger.info("State manager shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during state manager shutdown: {e}")
