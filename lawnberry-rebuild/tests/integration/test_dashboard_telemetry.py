"""Integration test for Dashboard telemetry at 5 Hz with <100ms latency."""
import pytest
import asyncio
import time
from typing import List
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
            "imu"
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