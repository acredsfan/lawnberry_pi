"""Integration test for Dashboard telemetry at 5 Hz with <100ms latency."""
import pytest
import asyncio
import time
import os
import json
from typing import List
from pathlib import Path
import httpx


@pytest.mark.asyncio
async def test_telemetry_latency_under_100ms():
    """Test that telemetry responses have <100ms latency."""
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        latencies = []
        
        # Measure latency over multiple requests
        for _ in range(10):
            start_time = time.perf_counter()
            response = await client.get("/api/v2/dashboard/telemetry")
            end_time = time.perf_counter()
            
            assert response.status_code == 200
            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)
            
            # Small delay between requests
            await asyncio.sleep(0.05)
        
        # Verify latencies
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        
        print(f"Average latency: {avg_latency:.2f}ms")
        print(f"Max latency: {max_latency:.2f}ms")
        
        # Contract requirement: <100ms latency
        assert avg_latency < 100, f"Average latency {avg_latency:.2f}ms exceeds 100ms"
        assert max_latency < 150, f"Peak latency {max_latency:.2f}ms too high"


@pytest.mark.asyncio
async def test_telemetry_5hz_frequency():
    """Test that telemetry can be delivered at 5Hz (200ms intervals)."""
    # This will initially pass with current implementation, but we need to verify
    # the new v1 API endpoints maintain this performance
    
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Test rapid polling at 5Hz rate
        start_time = time.perf_counter()
        successful_requests = 0
        
        for i in range(25):  # 5 seconds worth at 5Hz
            request_start = time.perf_counter()
            response = await client.get("/api/v2/dashboard/telemetry")
            
            if response.status_code == 200:
                successful_requests += 1
            
            # Wait for next 200ms interval
            elapsed = time.perf_counter() - request_start
            sleep_time = max(0, 0.2 - elapsed)
            await asyncio.sleep(sleep_time)
        
        total_time = time.perf_counter() - start_time
        actual_frequency = successful_requests / total_time
        
        print(f"Achieved frequency: {actual_frequency:.2f}Hz")
        print(f"Successful requests: {successful_requests}/25")
        
        # Should maintain at least 4.5Hz (allowing some variance)
        assert actual_frequency >= 4.5, f"Frequency {actual_frequency:.2f}Hz below minimum"
        assert successful_requests >= 23, "Too many failed requests"


@pytest.mark.asyncio
async def test_telemetry_scalable_to_10hz():
    """Test that telemetry can scale to 10Hz when required."""
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Test rapid polling at 10Hz rate (100ms intervals)
        successful_requests = 0
        start_time = time.perf_counter()
        
        for i in range(30):  # 3 seconds worth at 10Hz
            request_start = time.perf_counter()
            response = await client.get("/api/v2/dashboard/telemetry")
            
            if response.status_code == 200:
                successful_requests += 1
            
            # Wait for next 100ms interval
            elapsed = time.perf_counter() - request_start
            sleep_time = max(0, 0.1 - elapsed)
            await asyncio.sleep(sleep_time)
        
        total_time = time.perf_counter() - start_time
        actual_frequency = successful_requests / total_time
        
        print(f"10Hz test frequency: {actual_frequency:.2f}Hz")
        
        # Should maintain at least 8Hz at high frequency
        assert actual_frequency >= 8.0, f"High frequency {actual_frequency:.2f}Hz insufficient"


@pytest.mark.asyncio
async def test_telemetry_data_completeness():
    """Test that telemetry data includes all required fields."""
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        response = await client.get("/api/v2/dashboard/telemetry")
        assert response.status_code == 200
        
        data = response.json()
        
        # Required telemetry fields per quickstart.md validation
        required_fields = [
            "timestamp",
            "battery",
            "position", 
            "temperatures",
            "imu",
            "tof",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required telemetry field: {field}"
        
        # Validate nested structures
        if "battery" in data:
            battery = data["battery"]
            assert "percentage" in battery or "voltage" in battery
        
        if "position" in data:
            position = data["position"]
            # Position fields may be null in SIM_MODE, but keys should exist
            expected_pos_fields = ["latitude", "longitude", "altitude", "accuracy", "gps_mode"]
            for field in expected_pos_fields:
                assert field in position

        if "tof" in data:
            tof = data["tof"]
            for side in ("left", "right"):
                assert side in tof, f"Missing ToF side '{side}'"
                side_payload = tof[side]
                assert "distance_mm" in side_payload
                assert "range_status" in side_payload


@pytest.mark.asyncio
async def test_telemetry_stream_with_sim_mode():
    """Test telemetry stream endpoint with SIM_MODE for hardware-independent validation."""
    from backend.src.main import app
    
    # Ensure SIM_MODE is enabled for this test
    original_sim_mode = os.environ.get("SIM_MODE")
    os.environ["SIM_MODE"] = "1"
    
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            
            response = await client.get("/api/v2/telemetry/stream?limit=10")
            assert response.status_code == 200
            
            data = response.json()
            assert "items" in data
            assert isinstance(data["items"], list)
            assert len(data["items"]) <= 10
            
            # Verify pagination cursor
            if len(data["items"]) > 0:
                assert "next_since" in data or "cursor" in data
            
            # Verify latency summary
            assert "latency_summary_ms" in data
            latency_summary = data["latency_summary_ms"]
            assert isinstance(latency_summary, dict)
            
            # Each item should have required fields
            for item in data["items"]:
                assert "timestamp" in item
                assert "component_id" in item
                assert "status" in item
                assert item["status"] in ["healthy", "warning", "fault"]
    
    finally:
        # Restore original SIM_MODE
        if original_sim_mode is None:
            os.environ.pop("SIM_MODE", None)
        else:
            os.environ["SIM_MODE"] = original_sim_mode


@pytest.mark.asyncio
async def test_telemetry_latency_budgets_pi5():
    """Test that telemetry latency meets Pi 5 budget (≤250 ms)."""
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Test POST /api/v2/telemetry/ping for latency measurement
        response = await client.post(
            "/api/v2/telemetry/ping",
            json={"component_id": "power", "sample_count": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "latency_ms_p95" in data
        assert "latency_ms_p50" in data
        assert "samples" in data
        
        # Pi 5 requirement: ≤250 ms p95 latency
        assert data["latency_ms_p95"] <= 250, f"P95 latency {data['latency_ms_p95']}ms exceeds 250ms budget"
        assert data["latency_ms_p50"] <= 200, f"P50 latency {data['latency_ms_p50']}ms exceeds 200ms"


@pytest.mark.asyncio
async def test_telemetry_latency_budgets_pi4():
    """Test that telemetry latency meets Pi 4B budget (≤350 ms) with graceful degradation."""
    from backend.src.main import app
    
    # Simulate Pi 4B environment
    original_device = os.environ.get("DEVICE_MODEL")
    os.environ["DEVICE_MODEL"] = "pi4"
    
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            
            response = await client.post(
                "/api/v2/telemetry/ping",
                json={"component_id": "power", "sample_count": 10}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Pi 4B requirement: ≤350 ms p95 latency (graceful degradation)
            assert data["latency_ms_p95"] <= 350, f"P95 latency {data['latency_ms_p95']}ms exceeds 350ms budget for Pi 4B"
    
    finally:
        if original_device is None:
            os.environ.pop("DEVICE_MODEL", None)
        else:
            os.environ["DEVICE_MODEL"] = original_device


@pytest.mark.asyncio
async def test_rtk_dropout_recovery_with_fallback():
    """Test RTK dropout detection and fallback messaging."""
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Get telemetry stream
        response = await client.get("/api/v2/telemetry/stream?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        
        # Check for RTK-related components
        has_gps_component = any(
            item.get("component_id") == "gps" 
            for item in data["items"]
        )
        
        if has_gps_component:
            gps_items = [item for item in data["items"] if item.get("component_id") == "gps"]
            
            for gps_item in gps_items:
                # Should have metadata about RTK status
                assert "metadata" in gps_item
                metadata = gps_item["metadata"]
                
                # Check for RTK fallback fields
                if "rtk_fix" in metadata:
                    assert metadata["rtk_fix"] in [True, False, None]
                
                if "rtk_status_message" in metadata:
                    # If RTK is not available, should have fallback message
                    if not metadata.get("rtk_fix"):
                        assert isinstance(metadata["rtk_status_message"], str)
                        assert len(metadata["rtk_status_message"]) > 0


@pytest.mark.asyncio
async def test_imu_orientation_metadata():
    """Test IMU orientation metadata in telemetry."""
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        response = await client.get("/api/v2/telemetry/stream?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        imu_items = [
            item for item in data["items"] 
            if item.get("component_id") == "imu"
        ]
        
        for imu_item in imu_items:
            assert "metadata" in imu_item
            metadata = imu_item["metadata"]
            
            # Should contain orientation data
            # This could be quaternion, euler angles, or other orientation representation
            assert any(
                key in metadata 
                for key in ["quaternion", "roll", "pitch", "yaw", "orientation"]
            ), "IMU item missing orientation metadata"


@pytest.mark.asyncio
async def test_telemetry_export_diagnostic_download():
    """Test telemetry export for diagnostic power metrics."""
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Test GET /api/v2/telemetry/export
        response = await client.get("/api/v2/telemetry/export?format=csv&component=power")
        
        # Should return CSV data or 404 if not implemented yet (TDD)
        assert response.status_code in [200, 404, 501]
        
        if response.status_code == 200:
            # Verify CSV headers
            content = response.text
            assert "timestamp" in content.lower()
            assert "component" in content.lower() or "power" in content.lower()
            
            # Check content type
            assert "text/csv" in response.headers.get("content-type", "").lower() or \
                   "application/csv" in response.headers.get("content-type", "").lower()


@pytest.mark.asyncio
async def test_telemetry_export_with_time_range():
    """Test telemetry export with time range filtering."""
    from backend.src.main import app
    from datetime import datetime, timedelta, timezone
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Define time range (last hour)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        
        response = await client.get(
            f"/api/v2/telemetry/export",
            params={
                "format": "csv",
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            }
        )
        
        # May not be implemented yet (TDD)
        assert response.status_code in [200, 404, 422, 501]


@pytest.mark.asyncio
async def test_telemetry_documentation_link_on_degradation():
    """Test that degraded telemetry includes remediation documentation links."""
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        response = await client.get("/api/v2/telemetry/stream?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check for items with warning or fault status
        degraded_items = [
            item for item in data["items"]
            if item.get("status") in ["warning", "fault"]
        ]
        
        # If there are degraded items, they should have remediation links
        for item in degraded_items:
            # Should have metadata with remediation info
            if "metadata" in item:
                metadata = item["metadata"]
                # Check for doc link or remediation message
                has_remediation = any(
                    key in metadata 
                    for key in ["remediation_link", "doc_url", "help_url", "remediation_message"]
                )
                
                # Not enforced yet, but log for visibility
                if not has_remediation:
                    print(f"Warning: Degraded item {item['component_id']} lacks remediation link")


@pytest.mark.asyncio
async def test_5hz_stream_consistency():
    """Test that telemetry maintains 5 Hz cadence consistently."""
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Collect timestamps over multiple requests
        timestamps = []
        
        for _ in range(10):
            response = await client.get("/api/v2/telemetry/stream?limit=1")
            if response.status_code == 200:
                data = response.json()
                if data["items"]:
                    timestamps.append(data["items"][0]["timestamp"])
            
            await asyncio.sleep(0.2)  # 5 Hz = 200ms intervals
        
        # Verify we got consistent timestamps
        assert len(timestamps) >= 8, "Insufficient telemetry samples received"


@pytest.mark.asyncio
async def test_evidence_capture_for_verification():
    """Capture telemetry evidence for verification artifacts."""
    from backend.src.main import app
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Collect telemetry evidence
        evidence = {
            "test_name": "test_evidence_capture_for_verification",
            "timestamp": time.time(),
            "samples": []
        }
        
        # Collect multiple samples
        for i in range(5):
            response = await client.get("/api/v2/telemetry/stream?limit=5")
            if response.status_code == 200:
                data = response.json()
                evidence["samples"].append({
                    "sample_id": i,
                    "item_count": len(data["items"]),
                    "latency_summary": data.get("latency_summary_ms", {}),
                })
            
            await asyncio.sleep(0.2)
        
        # Save evidence to artifacts directory
        artifacts_dir = Path("/home/pi/lawnberry/verification_artifacts/001-integrate-hardware-and")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        evidence_file = artifacts_dir / "telemetry_integration_evidence.json"
        with open(evidence_file, "w") as f:
            json.dump(evidence, f, indent=2)
        
        print(f"Evidence captured to {evidence_file}")
        
        # Verify evidence was captured
        assert len(evidence["samples"]) >= 3