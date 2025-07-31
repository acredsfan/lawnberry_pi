"""
System State Machine - Manages overall system state transitions with persistence
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SystemState(Enum):
    """System states"""
    INITIALIZING = "initializing"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"
    ERROR = "error"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class StateTransition:
    """State transition record"""
    from_state: SystemState
    to_state: SystemState
    timestamp: datetime
    reason: Optional[str] = None
    user: Optional[str] = None


class SystemStateMachine:
    """
    System state machine with transition validation and persistence
    """
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        SystemState.INITIALIZING: [
            SystemState.STARTING,
            SystemState.ERROR,
            SystemState.EMERGENCY_STOP
        ],
        SystemState.STARTING: [
            SystemState.RUNNING,
            SystemState.ERROR,
            SystemState.EMERGENCY_STOP,
            SystemState.SHUTTING_DOWN
        ],
        SystemState.RUNNING: [
            SystemState.DEGRADED,
            SystemState.MAINTENANCE,
            SystemState.SHUTTING_DOWN,
            SystemState.ERROR,
            SystemState.EMERGENCY_STOP
        ],
        SystemState.DEGRADED: [
            SystemState.RUNNING,
            SystemState.MAINTENANCE,
            SystemState.SHUTTING_DOWN,
            SystemState.ERROR,
            SystemState.EMERGENCY_STOP
        ],
        SystemState.MAINTENANCE: [
            SystemState.RUNNING,
            SystemState.DEGRADED,
            SystemState.SHUTTING_DOWN,
            SystemState.ERROR,
            SystemState.EMERGENCY_STOP
        ],
        SystemState.ERROR: [
            SystemState.STARTING,
            SystemState.MAINTENANCE,
            SystemState.SHUTTING_DOWN,
            SystemState.EMERGENCY_STOP
        ],
        SystemState.SHUTTING_DOWN: [
            SystemState.STOPPED,
            SystemState.EMERGENCY_STOP
        ],
        SystemState.STOPPED: [
            SystemState.INITIALIZING,
            SystemState.STARTING
        ],
        SystemState.EMERGENCY_STOP: [
            SystemState.STOPPED,
            SystemState.MAINTENANCE
        ]
    }
    
    def __init__(self):
        self.current_state = SystemState.INITIALIZING
        self.previous_state: Optional[SystemState] = None
        self.state_history: List[StateTransition] = []
        self.state_callbacks: Dict[SystemState, List[Callable]] = {}
        self.transition_callbacks: List[Callable] = []
        
        # State persistence
        self.state_file = Path('/var/lib/lawnberry/system_state.json')
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # State-specific data
        self.state_data: Dict[str, any] = {}
        
        # Automatic transitions
        self.auto_transition_tasks: Dict[SystemState, asyncio.Task] = {}
    
    async def initialize(self):
        """Initialize state machine"""
        logger.info("Initializing System State Machine")
        
        # Load previous state if available
        await self._load_state()
        
        # Set initial state
        if self.current_state in [SystemState.SHUTTING_DOWN, SystemState.STOPPED]:
            # Normal case - system was shut down properly
            self.current_state = SystemState.INITIALIZING
        elif self.current_state in [SystemState.RUNNING, SystemState.DEGRADED]:
            # System crashed or was forcibly stopped
            logger.warning("System was not shut down properly - entering error state")
            self.current_state = SystemState.ERROR
            self.state_data['recovery_needed'] = True
        
        # Record initial state
        await self._record_transition(None, self.current_state, "System initialization")
        
        logger.info(f"State machine initialized in state: {self.current_state.value}")
    
    async def transition_to(self, new_state: SystemState, reason: str = None, user: str = None) -> bool:
        """Transition to a new state with validation"""
        if not self._is_valid_transition(self.current_state, new_state):
            logger.error(f"Invalid state transition: {self.current_state.value} -> {new_state.value}")
            return False
        
        logger.info(f"State transition: {self.current_state.value} -> {new_state.value}")
        if reason:
            logger.info(f"Transition reason: {reason}")
        
        # Cancel any auto-transition tasks for current state
        await self._cancel_auto_transitions()
        
        # Execute pre-transition callbacks
        await self._execute_pre_transition_callbacks(self.current_state, new_state)
        
        # Record transition
        await self._record_transition(self.current_state, new_state, reason, user)
        
        # Update states
        self.previous_state = self.current_state
        self.current_state = new_state
        
        # Execute post-transition callbacks
        await self._execute_post_transition_callbacks(self.previous_state, new_state)
        
        # Execute state entry callbacks
        await self._execute_state_callbacks(new_state)
        
        # Set up automatic transitions if needed
        await self._setup_auto_transitions(new_state)
        
        # Save state
        await self.save_state()
        
        logger.info(f"Successfully transitioned to state: {new_state.value}")
        return True
    
    def _is_valid_transition(self, from_state: SystemState, to_state: SystemState) -> bool:
        """Check if state transition is valid"""
        valid_next_states = self.VALID_TRANSITIONS.get(from_state, [])
        return to_state in valid_next_states
    
    async def _record_transition(self, from_state: Optional[SystemState], to_state: SystemState, 
                               reason: str = None, user: str = None):
        """Record state transition in history"""
        transition = StateTransition(
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.now(),
            reason=reason,
            user=user
        )
        
        self.state_history.append(transition)
        
        # Keep only recent history (last 1000 transitions)
        if len(self.state_history) > 1000:
            self.state_history = self.state_history[-500:]
    
    async def _execute_pre_transition_callbacks(self, from_state: SystemState, to_state: SystemState):
        """Execute callbacks before state transition"""
        for callback in self.transition_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback('pre_transition', from_state, to_state)
                else:
                    callback('pre_transition', from_state, to_state)
            except Exception as e:
                logger.error(f"Error in pre-transition callback: {e}")
    
    async def _execute_post_transition_callbacks(self, from_state: SystemState, to_state: SystemState):
        """Execute callbacks after state transition"""
        for callback in self.transition_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback('post_transition', from_state, to_state)
                else:
                    callback('post_transition', from_state, to_state)
            except Exception as e:
                logger.error(f"Error in post-transition callback: {e}")
    
    async def _execute_state_callbacks(self, state: SystemState):
        """Execute callbacks for entering a state"""
        callbacks = self.state_callbacks.get(state, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(state)
                else:
                    callback(state)
            except Exception as e:
                logger.error(f"Error in state callback for {state.value}: {e}")
    
    async def _setup_auto_transitions(self, state: SystemState):
        """Set up automatic transitions for certain states"""
        # Example: Auto-transition from ERROR to MAINTENANCE after 30 seconds
        if state == SystemState.ERROR:
            async def auto_transition():
                await asyncio.sleep(30.0)
                if self.current_state == SystemState.ERROR:
                    logger.info("Auto-transitioning from ERROR to MAINTENANCE")
                    await self.transition_to(SystemState.MAINTENANCE, "Automatic error recovery")
            
            self.auto_transition_tasks[state] = asyncio.create_task(auto_transition())
        
        # Example: Auto-transition from EMERGENCY_STOP to STOPPED after 5 seconds
        elif state == SystemState.EMERGENCY_STOP:
            async def auto_transition():
                await asyncio.sleep(5.0)
                if self.current_state == SystemState.EMERGENCY_STOP:
                    logger.info("Auto-transitioning from EMERGENCY_STOP to STOPPED")
                    await self.transition_to(SystemState.STOPPED, "Automatic emergency shutdown completion")
            
            self.auto_transition_tasks[state] = asyncio.create_task(auto_transition())
    
    async def _cancel_auto_transitions(self):
        """Cancel any pending automatic transitions"""
        for task in self.auto_transition_tasks.values():
            if not task.done():
                task.cancel()
        self.auto_transition_tasks.clear()
    
    def register_state_callback(self, state: SystemState, callback: Callable):
        """Register callback for state entry"""
        if state not in self.state_callbacks:
            self.state_callbacks[state] = []
        self.state_callbacks[state].append(callback)
    
    def register_transition_callback(self, callback: Callable):
        """Register callback for state transitions"""
        self.transition_callbacks.append(callback)
    
    def get_valid_transitions(self) -> List[SystemState]:
        """Get valid transitions from current state"""
        return self.VALID_TRANSITIONS.get(self.current_state, [])
    
    def can_transition_to(self, state: SystemState) -> bool:
        """Check if can transition to given state"""
        return state in self.get_valid_transitions()
    
    def get_state_history(self, limit: int = 100) -> List[StateTransition]:
        """Get recent state transition history"""
        return self.state_history[-limit:]
    
    def set_state_data(self, key: str, value: any):
        """Set state-specific data"""
        self.state_data[key] = value
    
    def get_state_data(self, key: str, default: any = None) -> any:
        """Get state-specific data"""
        return self.state_data.get(key, default)
    
    def clear_state_data(self, key: str = None):
        """Clear state-specific data"""
        if key:
            self.state_data.pop(key, None)
        else:
            self.state_data.clear()
    
    async def save_state(self):
        """Save current state to file"""
        try:
            state_info = {
                'current_state': self.current_state.value,
                'previous_state': self.previous_state.value if self.previous_state else None,
                'timestamp': datetime.now().isoformat(),
                'state_data': self.state_data,
                'recent_history': [
                    {
                        'from_state': t.from_state.value if t.from_state else None,
                        'to_state': t.to_state.value,
                        'timestamp': t.timestamp.isoformat(),
                        'reason': t.reason,
                        'user': t.user
                    }
                    for t in self.state_history[-10:]  # Save last 10 transitions
                ]
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state_info, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    async def _load_state(self):
        """Load previous state from file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state_info = json.load(f)
                
                # Restore current state
                self.current_state = SystemState(state_info['current_state'])
                
                if state_info.get('previous_state'):
                    self.previous_state = SystemState(state_info['previous_state'])
                
                # Restore state data
                self.state_data = state_info.get('state_data', {})
                
                # Restore recent history
                history = state_info.get('recent_history', [])
                for h in history:
                    transition = StateTransition(
                        from_state=SystemState(h['from_state']) if h['from_state'] else None,
                        to_state=SystemState(h['to_state']),
                        timestamp=datetime.fromisoformat(h['timestamp']),
                        reason=h.get('reason'),
                        user=h.get('user')
                    )
                    self.state_history.append(transition)
                
                logger.info(f"Loaded previous state: {self.current_state.value}")
                
        except Exception as e:
            logger.warning(f"Could not load previous state: {e}")
            # Use default initial state
            self.current_state = SystemState.INITIALIZING
    
    def get_state_summary(self) -> Dict[str, any]:
        """Get summary of current state"""
        return {
            'current_state': self.current_state.value,
            'previous_state': self.previous_state.value if self.previous_state else None,
            'valid_transitions': [s.value for s in self.get_valid_transitions()],
            'state_data': self.state_data.copy(),
            'last_transition': self.state_history[-1] if self.state_history else None
        }
    
    async def force_state(self, state: SystemState, reason: str = "Forced state change"):
        """Force transition to any state (emergency use only)"""
        logger.warning(f"FORCING state transition to {state.value}: {reason}")
        
        # Cancel auto-transitions
        await self._cancel_auto_transitions()
        
        # Record forced transition
        await self._record_transition(self.current_state, state, f"FORCED: {reason}")
        
        # Update state
        self.previous_state = self.current_state
        self.current_state = state
        
        # Execute callbacks
        await self._execute_state_callbacks(state)
        
        # Save state
        await self.save_state()
        
        logger.warning(f"State FORCED to: {state.value}")
    
    async def shutdown(self):
        """Shutdown state machine"""
        logger.info("Shutting down state machine")
        
        # Cancel any pending auto-transitions
        await self._cancel_auto_transitions()
        
        # Save final state
        await self.save_state()
        
        logger.info("State machine shut down")


# Example usage and state-specific behavior
async def example_state_machine_usage():
    """Example of how to use the state machine"""
    sm = SystemStateMachine()
    await sm.initialize()
    
    # Register state callbacks
    async def on_running(state):
        logger.info("System is now running - all services operational")
    
    async def on_error(state):
        logger.error("System entered error state - initiating recovery")
    
    sm.register_state_callback(SystemState.RUNNING, on_running)
    sm.register_state_callback(SystemState.ERROR, on_error)
    
    # Register transition callback
    async def on_transition(phase, from_state, to_state):
        if phase == 'pre_transition':
            logger.info(f"Preparing for transition: {from_state.value} -> {to_state.value}")
        elif phase == 'post_transition':
            logger.info(f"Completed transition: {from_state.value} -> {to_state.value}")
    
    sm.register_transition_callback(on_transition)
    
    # Example transitions
    await sm.transition_to(SystemState.STARTING, "System initialization complete")
    await sm.transition_to(SystemState.RUNNING, "All services started successfully")
    
    return sm
