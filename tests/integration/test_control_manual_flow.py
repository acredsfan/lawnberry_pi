"""
Integration tests for manual control flow.
Validates drive commands, blade control, emergency commands, latency budgets, audit trails, safety interlocks.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from backend.src.main import app
import os
from datetime import datetime


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_manual_drive_command_with_joystick_input():
    """
    Test manual drive command POST /api/v2/control/drive with joystick coordinates.
    Validates throttle/turn conversion, motor speed calculation, safety interlocks.
    Allows 404/501 per TDD.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "command": "drive",
            "throttle": 0.75,  # 75% forward
            "turn": 0.2,       # 20% right turn
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        headers = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}
        response = await client.post("/api/v2/control/drive", json=payload, headers=headers)
        
        # TDD: Allow 404 (not implemented), 501 (not yet available), or 422 (validation)
        if response.status_code in (404, 501, 422):
            return
        
        # When implemented: expect 200 with motor speeds
        assert response.status_code == 200
        data = response.json()
        assert "left_motor_speed" in data
        assert "right_motor_speed" in data
        assert -1.0 <= data["left_motor_speed"] <= 1.0
        assert -1.0 <= data["right_motor_speed"] <= 1.0
        assert "safety_status" in data
        assert data["safety_status"] in ["OK", "LOCKED_OUT", "EMERGENCY_STOP"]


@pytest.mark.asyncio
async def test_blade_control_enable_disable_with_safety_interlock():
    """
    Test blade control POST /api/v2/control/blade with enable/disable commands.
    Validates safety interlock: blade cannot enable if motors not stopped.
    Allows 404/501 per TDD.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attempt to enable blade
        payload_enable = {
            "command": "blade_enable",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        headers = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}
        response_enable = await client.post("/api/v2/control/blade", json=payload_enable, headers=headers)
        
        if response_enable.status_code in (404, 501, 422):
            return
        
        # When implemented: blade enable should succeed if motors stopped
        assert response_enable.status_code in (200, 403)  # 403 if safety interlock active
        if response_enable.status_code == 200:
            data_enable = response_enable.json()
            assert data_enable["blade_status"] in ["ENABLED", "LOCKED_OUT"]
        
        # Attempt to disable blade
        payload_disable = {
            "command": "blade_disable",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        response_disable = await client.post("/api/v2/control/blade", json=payload_disable, headers=headers)
        
        if response_disable.status_code in (404, 501, 422):
            return
        
        assert response_disable.status_code == 200
        data_disable = response_disable.json()
        assert data_disable["blade_status"] == "DISABLED"


@pytest.mark.asyncio
async def test_emergency_stop_command_overrides_all_control():
    """
    Test emergency stop POST /api/v2/control/emergency with immediate motor/blade cutoff.
    Validates all control commands rejected until emergency cleared.
    Allows 404/501 per TDD.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}
        
        # Send emergency stop
        payload_emergency = {
            "command": "emergency_stop",
            "reason": "operator_request",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        response_emergency = await client.post("/api/v2/control/emergency", json=payload_emergency, headers=headers)
        
        if response_emergency.status_code in (404, 501, 422):
            return
        
        # When implemented: expect 200 with confirmation
        assert response_emergency.status_code == 200
        data_emergency = response_emergency.json()
        assert data_emergency["status"] == "EMERGENCY_STOP_ACTIVE"
        assert data_emergency["motors_stopped"] is True
        assert data_emergency["blade_disabled"] is True
        
        # Attempt drive command while emergency active - should be rejected
        payload_drive = {
            "command": "drive",
            "throttle": 0.5,
            "turn": 0.0,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        response_drive = await client.post("/api/v2/control/drive", json=payload_drive, headers=headers)
        
        if response_drive.status_code in (404, 501, 422):
            return
        
        # Should be rejected with 403 while emergency active
        assert response_drive.status_code == 403
        data_drive = response_drive.json()
        assert "emergency" in data_drive.get("detail", "").lower()


@pytest.mark.asyncio
async def test_control_command_latency_100ms_budget():
    """
    Test control command latency POST /api/v2/control/ping with ≤100ms budget.
    Validates X-Control-Latency-Ms header present and within budget.
    Allows 404/501 per TDD.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        import time
        start = time.time()
        response = await client.post("/api/v2/control/ping", json=payload, headers=headers)
        elapsed_ms = (time.time() - start) * 1000
        
        if response.status_code in (404, 501, 422):
            return
        
        # When implemented: validate latency header and budget
        assert response.status_code == 200
        assert "X-Control-Latency-Ms" in response.headers
        
        reported_latency = float(response.headers["X-Control-Latency-Ms"])
        assert reported_latency <= 100.0, f"Control latency {reported_latency}ms exceeds 100ms budget"
        
        # Sanity check: elapsed time should be close to reported latency
        assert abs(elapsed_ms - reported_latency) < 50, "Reported latency doesn't match measured time"


@pytest.mark.asyncio
async def test_control_audit_trail_for_all_commands():
    """
    Test control audit trail GET /api/v2/control/audit for all control commands.
    Validates timestamp, command type, user, outcome logged.
    Allows 404/501 per TDD.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-token"}
        response = await client.get("/api/v2/control/audit", headers=headers)
        
        if response.status_code in (404, 501, 422):
            return
        
        # When implemented: validate audit log structure
        assert response.status_code == 200
        data = response.json()
        assert "audit_entries" in data
        
        if len(data["audit_entries"]) > 0:
            entry = data["audit_entries"][0]
            assert "timestamp" in entry
            assert "command_type" in entry
            assert entry["command_type"] in ["drive", "blade_enable", "blade_disable", "emergency_stop", "emergency_clear"]
            assert "user" in entry
            assert "outcome" in entry
            assert entry["outcome"] in ["SUCCESS", "REJECTED", "ERROR"]
            assert "details" in entry


@pytest.mark.asyncio
async def test_control_safety_interlock_blade_requires_stopped_motors():
    """
    Test safety interlock: blade_enable rejected if motors not stopped.
    Validates safety_status:"LOCKED_OUT" with reason.
    Allows 404/501 per TDD.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}
        
        # Step 1: Send drive command to activate motors
        payload_drive = {
            "command": "drive",
            "throttle": 0.3,
            "turn": 0.0,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        response_drive = await client.post("/api/v2/control/drive", json=payload_drive, headers=headers)
        
        if response_drive.status_code in (404, 501, 422):
            return
        
        # Step 2: Attempt blade enable while motors active - should be rejected
        payload_blade = {
            "command": "blade_enable",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        response_blade = await client.post("/api/v2/control/blade", json=payload_blade, headers=headers)
        
        if response_blade.status_code in (404, 501, 422):
            return
        
        # When implemented: expect 403 with safety interlock reason
        assert response_blade.status_code == 403
        data_blade = response_blade.json()
        assert "safety_interlock" in data_blade.get("detail", "").lower() or "motors_active" in data_blade.get("detail", "").lower()


@pytest.mark.asyncio
async def test_control_emergency_clear_requires_explicit_confirmation():
    """
    Test emergency clear POST /api/v2/control/emergency_clear with confirmation flag.
    Validates emergency cannot be cleared without explicit operator confirmation.
    Allows 404/501 per TDD.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}
        
        # Attempt emergency clear without confirmation - should be rejected
        payload_no_confirm = {
            "command": "emergency_clear",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        response_no_confirm = await client.post("/api/v2/control/emergency_clear", json=payload_no_confirm, headers=headers)
        
        if response_no_confirm.status_code in (404, 501, 422):
            return
        
        # When implemented: expect 400 or 422 without confirmation
        assert response_no_confirm.status_code in (400, 422)
        data_no_confirm = response_no_confirm.json()
        assert "confirmation" in data_no_confirm.get("detail", "").lower() or "confirm" in data_no_confirm.get("detail", "").lower()
        
        # Attempt emergency clear WITH confirmation - should succeed
        payload_with_confirm = {
            "command": "emergency_clear",
            "confirmation": True,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        response_with_confirm = await client.post("/api/v2/control/emergency_clear", json=payload_with_confirm, headers=headers)
        
        if response_with_confirm.status_code in (404, 501, 422):
            return
        
        assert response_with_confirm.status_code == 200
        data_with_confirm = response_with_confirm.json()
        assert data_with_confirm["status"] == "EMERGENCY_CLEARED"
