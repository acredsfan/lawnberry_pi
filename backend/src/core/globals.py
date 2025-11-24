from typing import Any
from datetime import datetime, timezone
from ..models.auth_security_config import AuthSecurityConfig

# Global shared state
# These were previously in backend/src/api/rest.py

# Blade/global safety state
_blade_state = {"active": False}
_safety_state = {"emergency_stop_active": False}
# Short-lived emergency TTL to block immediate subsequent commands without cross-test leakage
_emergency_until: float = 0.0
# Per-client emergency flags (scoped by Authorization or X-Client-Id)
_client_emergency: dict[str, float] = {}
# Legacy control flow state for integration tests
_legacy_motors_active = False

# Simple in-memory overrides for debug injections (SIM_MODE-friendly)
_debug_overrides: dict[str, Any] = {}

# Manual control unlock sessions
_manual_control_sessions: dict[str, dict[str, Any]] = {}

# Security settings (auth levels, MFA options)
_security_settings = AuthSecurityConfig()
_security_last_modified: datetime = datetime.now(timezone.utc)
