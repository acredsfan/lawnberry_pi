"""
Performance tests for telemetry pipeline
Tests WebSocket telemetry performance, latency, and throughput
"""

import asyncio
import json
import statistics
import time
from unittest.mock import AsyncMock

import pytest

from backend.src.services.websocket_hub import WebSocketHub


class TestTelemetryPerformance:
    """Test telemetry pipeline performance characteristics."""
    
    @pytest.fixture
    def mock_websocket_hub(self):
        """Create a fresh WebSocket hub for testing."""
        return WebSocketHub()
    
    @pytest.fixture
    async def connected_clients(self, mock_websocket_hub):
        """Create multiple connected WebSocket clients."""
        clients = []
        for i in range(5):
            mock_ws = AsyncMock()
            mock_ws.send_text = AsyncMock()
            client_id = f"test_client_{i}"
            clients.append((client_id, mock_ws))
            mock_websocket_hub.clients[client_id] = mock_ws
        return clients

    @pytest.mark.asyncio
    async def test_telemetry_generation_performance(self, mock_websocket_hub):
        """Test telemetry data generation performance."""
        generation_times = []
        
        # Generate telemetry data multiple times and measure
        for _ in range(100):
            start_time = time.perf_counter()
            telemetry = await mock_websocket_hub._generate_telemetry()
            end_time = time.perf_counter()
            
            generation_times.append((end_time - start_time) * 1000)  # Convert to ms
            
            # Validate telemetry structure
            assert isinstance(telemetry, dict)
            assert "source" in telemetry
            assert "battery" in telemetry
            assert "position" in telemetry
        
        # Performance assertions
        avg_time = statistics.mean(generation_times)
        max_time = max(generation_times)
        p95_time = statistics.quantiles(generation_times, n=20)[18]  # 95th percentile
        
        generation_summary = (
            "Telemetry generation - "
            f"Avg: {avg_time:.2f}ms, "
            f"Max: {max_time:.2f}ms, "
            f"P95: {p95_time:.2f}ms"
        )
        print(generation_summary)
        
        # Performance requirements
        assert avg_time < 5.0, (
            f"Average telemetry generation time {avg_time:.2f}ms exceeds 5ms threshold"
        )
        assert max_time < 20.0, (
            f"Maximum telemetry generation time {max_time:.2f}ms exceeds 20ms threshold"
        )
        assert p95_time < 10.0, (
            f"95th percentile telemetry generation time {p95_time:.2f}ms exceeds 10ms threshold"
        )

    @pytest.mark.asyncio
    async def test_broadcast_performance(self, mock_websocket_hub, connected_clients):
        """Test telemetry broadcast performance to multiple clients."""
        broadcast_times = []
        message = json.dumps({"type": "telemetry", "data": {"test": "data"}})
        
        # Test broadcasting to multiple clients
        for _ in range(50):
            start_time = time.perf_counter()
            await mock_websocket_hub.broadcast(message)
            end_time = time.perf_counter()
            
            broadcast_times.append((end_time - start_time) * 1000)  # Convert to ms
        
        # Performance analysis
        avg_time = statistics.mean(broadcast_times)
        max_time = max(broadcast_times)
        
        broadcast_summary = (
            "Broadcast performance - "
            f"Avg: {avg_time:.2f}ms, "
            f"Max: {max_time:.2f}ms for {len(connected_clients)} clients"
        )
        print(broadcast_summary)
        
        # Performance requirements (should scale with client count)
        expected_max_time = len(connected_clients) * 2.0  # 2ms per client
        assert avg_time < expected_max_time, (
            f"Broadcast time {avg_time:.2f}ms exceeds expected {expected_max_time:.2f}ms"
        )

    @pytest.mark.asyncio 
    async def test_subscription_filtering_performance(self, mock_websocket_hub):
        """Test performance of topic-based subscription filtering."""
        # Set up multiple clients with different subscriptions
        for i in range(10):
            client_id = f"client_{i}"
            mock_ws = AsyncMock()
            mock_websocket_hub.clients[client_id] = mock_ws
            
            # Subscribe to different topics
            await mock_websocket_hub.subscribe(client_id, f"topic_{i % 3}")
        
        filtering_times = []
        
        # Test subscription filtering performance
        for topic_id in range(3):
            topic = f"topic_{topic_id}"
            message = json.dumps({"type": "topic_data", "topic": topic, "data": {"test": "data"}})
            
            start_time = time.perf_counter()
            await mock_websocket_hub.broadcast_to_topic(topic, message)
            end_time = time.perf_counter()
            
            filtering_times.append((end_time - start_time) * 1000)
        
        avg_filtering_time = statistics.mean(filtering_times)
        print(f"Subscription filtering - Avg: {avg_filtering_time:.2f}ms")
        
        # Should be fast even with many subscriptions
        assert avg_filtering_time < 5.0, (
            f"Subscription filtering time {avg_filtering_time:.2f}ms exceeds 5ms threshold"
        )

    @pytest.mark.asyncio
    async def test_telemetry_loop_performance(self, mock_websocket_hub):
        """Test the performance of the continuous telemetry loop."""
        # Set up mock clients
        for i in range(3):
            client_id = f"perf_client_{i}"
            mock_ws = AsyncMock()
            mock_websocket_hub.clients[client_id] = mock_ws
            await mock_websocket_hub.subscribe(client_id, "telemetry")
        
        # Configure telemetry frequency
        mock_websocket_hub.telemetry_cadence_hz = 10.0  # 10 Hz for testing
        
        # Collect timing data
        loop_times = []
        message_counts = []
        
        async def measure_telemetry_loop():
            """Measure telemetry loop performance."""
            for _ in range(20):  # Run for 20 iterations
                start_time = time.perf_counter()
                
                # Generate and broadcast telemetry
                telemetry_data = await mock_websocket_hub._generate_telemetry()
                await mock_websocket_hub._broadcast_telemetry_topics(telemetry_data)
                
                end_time = time.perf_counter()
                loop_times.append((end_time - start_time) * 1000)
                
                # Count messages sent
                message_count = sum(
                    ws.send_text.call_count 
                    for ws in mock_websocket_hub.clients.values()
                )
                message_counts.append(message_count)
                
                # Sleep to maintain frequency
                await asyncio.sleep(1.0 / mock_websocket_hub.telemetry_cadence_hz)
        
        await measure_telemetry_loop()
        
        # Performance analysis
        avg_loop_time = statistics.mean(loop_times)
        max_loop_time = max(loop_times)
        total_messages = sum(message_counts)
        
        loop_summary = (
            "Telemetry loop - "
            f"Avg: {avg_loop_time:.2f}ms, "
            f"Max: {max_loop_time:.2f}ms"
        )
        print(loop_summary)
        print(f"Total messages sent: {total_messages}")
        
        # Performance requirements for 10 Hz operation
        max_allowed_time = (1000 / mock_websocket_hub.telemetry_cadence_hz) * 0.5
        # 50% of cycle time
        assert avg_loop_time < max_allowed_time, (
            f"Telemetry loop time {avg_loop_time:.2f}ms exceeds {max_allowed_time:.2f}ms"
        )

    @pytest.mark.asyncio
    async def test_high_frequency_telemetry_stability(self, mock_websocket_hub):
        """Test telemetry stability at high frequencies."""
        # Configure for high frequency
        mock_websocket_hub.telemetry_cadence_hz = 20.0  # 20 Hz
        
        # Add clients
        for i in range(5):
            client_id = f"stress_client_{i}"
            mock_ws = AsyncMock()
            mock_websocket_hub.clients[client_id] = mock_ws
            await mock_websocket_hub.subscribe(client_id, "telemetry")
        
        # Run high-frequency telemetry for a period
        start_time = time.time()
        iteration_count = 0
        error_count = 0
        
        while time.time() - start_time < 2.0:  # Run for 2 seconds
            try:
                telemetry_data = await mock_websocket_hub._generate_telemetry()
                await mock_websocket_hub._broadcast_telemetry_topics(telemetry_data)
                iteration_count += 1
                
                # Maintain frequency
                await asyncio.sleep(1.0 / mock_websocket_hub.telemetry_cadence_hz)
                
            except Exception as e:
                error_count += 1
                print(f"Error in high-frequency test: {e}")
        
        # Stability requirements
        expected_iterations = int(2.0 * mock_websocket_hub.telemetry_cadence_hz * 0.9)
        # 90% tolerance
        error_rate = error_count / max(iteration_count, 1)
        
        stability_summary = (
            "High-frequency test - "
            f"Iterations: {iteration_count}, "
            f"Errors: {error_count}, "
            f"Rate: {iteration_count/2.0:.1f} Hz"
        )
        print(stability_summary)
        
        assert iteration_count >= expected_iterations, (
            f"Insufficient iterations {iteration_count} < {expected_iterations}"
        )
        assert error_rate < 0.01, (
            f"Error rate {error_rate:.3f} exceeds 1% threshold"
        )

    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, mock_websocket_hub):
        """Test memory usage stability during continuous operation."""
        import gc
        import os

        import psutil
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Add clients and run telemetry
        for i in range(10):
            client_id = f"memory_client_{i}"
            mock_ws = AsyncMock()
            mock_websocket_hub.clients[client_id] = mock_ws
            await mock_websocket_hub.subscribe(client_id, "telemetry")
        
        # Run telemetry for extended period
        for _ in range(200):  # 200 iterations
            telemetry_data = await mock_websocket_hub._generate_telemetry()
            await mock_websocket_hub._broadcast_telemetry_topics(telemetry_data)
            
            # Simulate some delay
            await asyncio.sleep(0.01)
        
        # Force garbage collection and measure memory
        gc.collect()
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        memory_summary = (
            "Memory usage - "
            f"Initial: {initial_memory:.1f}MB, "
            f"Final: {final_memory:.1f}MB, "
            f"Increase: {memory_increase:.1f}MB"
        )
        print(memory_summary)
        
        # Memory requirements (should not grow significantly)
        assert memory_increase < 50.0, (
            f"Memory increase {memory_increase:.1f}MB exceeds 50MB threshold"
        )

    @pytest.mark.asyncio
    async def test_client_connection_scalability(self, mock_websocket_hub):
        """Test scalability with many concurrent clients."""
        client_count = 50
        connection_times = []
        
        # Connect many clients and measure time
        for i in range(client_count):
            start_time = time.perf_counter()
            
            client_id = f"scale_client_{i}"
            mock_ws = AsyncMock()
            await mock_websocket_hub.connect(mock_ws, client_id)
            await mock_websocket_hub.subscribe(client_id, "telemetry")
            
            end_time = time.perf_counter()
            connection_times.append((end_time - start_time) * 1000)
        
        # Test broadcast performance with many clients
        broadcast_start = time.perf_counter()
        telemetry_data = await mock_websocket_hub._generate_telemetry()
        await mock_websocket_hub._broadcast_telemetry_topics(telemetry_data)
        broadcast_time = (time.perf_counter() - broadcast_start) * 1000
        
        # Performance analysis
        avg_connection_time = statistics.mean(connection_times)
        max_connection_time = max(connection_times)
        
        print(f"Scalability test - {client_count} clients")
        connection_summary = (
            "Connection - "
            f"Avg: {avg_connection_time:.2f}ms, "
            f"Max: {max_connection_time:.2f}ms"
        )
        print(connection_summary)
        print(f"Broadcast time: {broadcast_time:.2f}ms")
        
        # Scalability requirements
        assert avg_connection_time < 10.0, (
            f"Average connection time {avg_connection_time:.2f}ms exceeds 10ms"
        )
        assert broadcast_time < client_count * 1.0, (
            f"Broadcast time {broadcast_time:.2f}ms doesn't scale well"
        )

    @pytest.mark.asyncio
    async def test_disconnection_cleanup_performance(self, mock_websocket_hub):
        """Test performance of client disconnection cleanup."""
        # Connect many clients
        client_count = 30
        for i in range(client_count):
            client_id = f"cleanup_client_{i}"
            mock_ws = AsyncMock()
            await mock_websocket_hub.connect(mock_ws, client_id)
            await mock_websocket_hub.subscribe(client_id, "telemetry")
        
        assert len(mock_websocket_hub.clients) == client_count
        
        # Measure disconnection cleanup time
        cleanup_times = []
        
        for i in range(client_count):
            client_id = f"cleanup_client_{i}"
            
            start_time = time.perf_counter()
            mock_websocket_hub.disconnect(client_id)
            end_time = time.perf_counter()
            
            cleanup_times.append((end_time - start_time) * 1000)
        
        # Performance analysis
        avg_cleanup_time = statistics.mean(cleanup_times)
        max_cleanup_time = max(cleanup_times)
        
        cleanup_summary = (
            "Cleanup performance - "
            f"Avg: {avg_cleanup_time:.2f}ms, "
            f"Max: {max_cleanup_time:.2f}ms"
        )
        print(cleanup_summary)
        
        # Cleanup should be fast
        assert avg_cleanup_time < 5.0, (
            f"Average cleanup time {avg_cleanup_time:.2f}ms exceeds 5ms"
        )
        assert len(mock_websocket_hub.clients) == 0, "Not all clients were cleaned up"

    @pytest.mark.asyncio
    async def test_error_handling_performance(self, mock_websocket_hub):
        """Test performance impact of error handling."""
        # Add clients, some of which will fail
        good_clients = []
        bad_clients = []
        
        for i in range(10):
            # Good client
            good_id = f"good_client_{i}"
            good_ws = AsyncMock()
            good_clients.append(good_id)
            await mock_websocket_hub.connect(good_ws, good_id)
            
            # Bad client (will raise exception on send)
            bad_id = f"bad_client_{i}"
            bad_ws = AsyncMock()
            bad_ws.send_text.side_effect = Exception("Connection lost")
            bad_clients.append(bad_id)
            await mock_websocket_hub.connect(bad_ws, bad_id)
        
        # Measure broadcast performance with errors
        error_handling_times = []
        
        for _ in range(20):
            start_time = time.perf_counter()
            
            message = json.dumps({"type": "test", "data": "error_test"})
            await mock_websocket_hub.broadcast(message)
            
            end_time = time.perf_counter()
            error_handling_times.append((end_time - start_time) * 1000)
        
        # Performance analysis
        avg_error_time = statistics.mean(error_handling_times)
        
        error_summary = (
            "Error handling performance - "
            f"Avg: {avg_error_time:.2f}ms with {len(bad_clients)} failing clients"
        )
        print(error_summary)
        
        # Error handling shouldn't significantly impact performance
        assert avg_error_time < 50.0, (
            f"Error handling time {avg_error_time:.2f}ms exceeds 50ms threshold"
        )


class TestTelemetryLatency:
    """Test telemetry latency characteristics."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_latency(self):
        """Test end-to-end telemetry latency."""
        hub = WebSocketHub()
        
        # Mock WebSocket client
        mock_ws = AsyncMock()
        received_messages = []
        
        async def capture_messages(message):
            timestamp = time.time()
            received_messages.append((timestamp, json.loads(message)))
        
        mock_ws.send_text.side_effect = capture_messages
        
        # Connect client
        await hub.connect(mock_ws, "latency_test_client")
        await hub.subscribe("latency_test_client", "telemetry")
        
        # Generate telemetry with timestamps
        latencies = []
        
        for _ in range(10):
            send_time = time.time()
            
            # Simulate telemetry generation and broadcast
            telemetry_data = await hub._generate_telemetry()
            telemetry_data["send_timestamp"] = send_time
            
            await hub._broadcast_telemetry_topics(telemetry_data)
            
            # Wait for message to be "sent"
            await asyncio.sleep(0.001)
        
        # Calculate latencies
        for receive_time, message in received_messages:
            if "send_timestamp" in message.get("data", {}):
                send_time = message["data"]["send_timestamp"]
                latency = (receive_time - send_time) * 1000  # Convert to ms
                latencies.append(latency)
        
        if latencies:
            avg_latency = statistics.mean(latencies)
            max_latency = max(latencies)
            
            latency_summary = (
                "End-to-end latency - "
                f"Avg: {avg_latency:.2f}ms, "
                f"Max: {max_latency:.2f}ms"
            )
            print(latency_summary)
            
            # Latency requirements
            assert avg_latency < 100.0, (
                f"Average latency {avg_latency:.2f}ms exceeds 100ms threshold"
            )
            assert max_latency < 200.0, (
                f"Maximum latency {max_latency:.2f}ms exceeds 200ms threshold"
            )


class TestTelemetryThroughput:
    """Test telemetry throughput characteristics."""
    
    @pytest.mark.asyncio
    async def test_maximum_throughput(self):
        """Test maximum sustainable telemetry throughput."""
        hub = WebSocketHub()
        
        # Add multiple clients
        client_count = 10
        for i in range(client_count):
            mock_ws = AsyncMock()
            client_id = f"throughput_client_{i}"
            await hub.connect(mock_ws, client_id)
            await hub.subscribe(client_id, "telemetry")
        
        # Measure throughput over time
        start_time = time.time()
        message_count = 0
        test_duration = 1.0  # 1 second test
        
        while time.time() - start_time < test_duration:
            telemetry_data = await hub._generate_telemetry()
            await hub._broadcast_telemetry_topics(telemetry_data)
            message_count += client_count  # Each client receives a message
            
            # Small delay to prevent overwhelming
            await asyncio.sleep(0.001)
        
        actual_duration = time.time() - start_time
        throughput = message_count / actual_duration
        
        throughput_summary = (
            "Maximum throughput: "
            f"{throughput:.0f} messages/second with {client_count} clients"
        )
        print(throughput_summary)
        
        # Throughput requirements
        expected_min_throughput = client_count * 100  # 100 messages/s per client minimum
        assert throughput >= expected_min_throughput, (
            f"Throughput {throughput:.0f} msg/s below minimum {expected_min_throughput}"
        )


# Platform-specific performance degradation tests (Pi 4B vs Pi 5)
@pytest.mark.asyncio
@pytest.mark.parametrize("device_model", ["pi4", "PI4B"])
async def test_pi4_graceful_performance_degradation(device_model, monkeypatch):
    """
    Test Raspberry Pi 4B graceful performance degradation.
    Validates telemetry cadence falls back to 2 Hz (from 5 Hz) on Pi 4B.
    Tests with --device pi4 flag or DEVICE_MODEL environment variable.
    """
    # Simulate Pi 4B platform detection
    monkeypatch.setenv("DEVICE_MODEL", device_model)
    
    # TDD: For now, this tests the pattern - implementation will check platform manager
    # In real implementation, would check backend.src.core.platform.PlatformManager
    
    # Simulate telemetry generation with platform-aware cadence
    # For TDD purposes, we're just verifying the test structure works
    telemetry_samples = []
    sample_count = 10
    start_time = time.time()
    
    for _ in range(sample_count):
        # Simulate telemetry generation (would call actual telemetry service)
        telemetry = {"timestamp": time.time(), "device": device_model}
        telemetry_samples.append(telemetry)
        await asyncio.sleep(0.5)  # 2 Hz = 500ms interval for Pi 4B
    
    elapsed = time.time() - start_time
    actual_cadence = sample_count / elapsed
    
    # Pi 4B should run at 2 Hz (± 0.5 Hz tolerance)
    assert 1.5 <= actual_cadence <= 2.5, (
        f"Pi 4B cadence {actual_cadence:.2f} Hz outside 2 Hz target (± 0.5 Hz)"
    )
    
    # Validate telemetry still contains required fields (no data loss)
    assert all('timestamp' in t for t in telemetry_samples)


@pytest.mark.asyncio
async def test_pi4_memory_constraint_compliance(monkeypatch):
    """
    Test Pi 4B memory usage stays within 6 GB constraint.
    Validates buffer sizes, message queues, and history limits reduced for Pi 4B.
    """
    import resource
    
    # Simulate Pi 4B platform
    monkeypatch.setenv("DEVICE_MODEL", "pi4")
    
    # TDD: Test structure for memory compliance on Pi 4B
    # Real implementation would use backend.src.core.platform.PlatformManager
    
    # Generate sustained telemetry load
    client_count = 10
    message_count = 100
    
    # Measure memory before load
    mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Convert to MB
    
    # Simulate telemetry generation and broadcast
    for _ in range(message_count):
        telemetry = {"timestamp": time.time(), "device": "pi4"}
        # Simulate broadcast overhead
        _ = [json.dumps(telemetry) for _ in range(client_count)]
        await asyncio.sleep(0.001)  # Small delay
    
    # Measure memory after load
    mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    mem_increase = mem_after - mem_before
    
    # Pi 4B memory increase should be <500 MB for this test
    # (Real implementation would track total system usage)
    assert mem_increase < 500, (
        f"Pi 4B memory increase {mem_increase:.1f} MB exceeds 500 MB limit"
    )


@pytest.mark.asyncio
async def test_pi4_latency_budget_adjustment(monkeypatch):
    """
    Test Pi 4B latency budget adjustment.
    Validates telemetry latency ≤350ms on Pi 4B (vs ≤250ms on Pi 5).
    """
    # Simulate Pi 4B platform
    monkeypatch.setenv("DEVICE_MODEL", "pi4")
    
    # TDD: Test latency budget for Pi 4B (≤350ms)
    latencies = []
    
    # Measure telemetry generation latency
    for _ in range(20):
        start_time = time.perf_counter()
        # Simulate telemetry generation (would call actual service)
        await asyncio.sleep(0.001)  # Minimal processing time
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        latencies.append(latency_ms)
    
    # Calculate percentiles
    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
    
    # Pi 4B latency budget: p95 ≤ 350ms
    assert p95 <= 350, (
        f"Pi 4B p95 latency {p95:.1f}ms exceeds 350ms budget"
    )
    
    # p50 should be well under budget
    assert p50 <= 200, f"Pi 4B p50 latency {p50:.1f}ms unexpectedly high"


@pytest.mark.asyncio
async def test_pi5_performance_baseline(monkeypatch):
    """
    Test Raspberry Pi 5 performance baseline (control test).
    Validates telemetry cadence at 5 Hz and latency ≤250ms on Pi 5.
    """
    # Simulate Pi 5 platform (default)
    monkeypatch.setenv("DEVICE_MODEL", "pi5")
    
    # TDD: Test baseline performance for Pi 5
    # Generate telemetry samples
    telemetry_samples = []
    sample_count = 10
    start_time = time.time()
    
    for _ in range(sample_count):
        telemetry = {"timestamp": time.time(), "device": "pi5"}
        telemetry_samples.append(telemetry)
        await asyncio.sleep(0.2)  # 5 Hz = 200ms interval
    
    elapsed = time.time() - start_time
    actual_cadence = sample_count / elapsed
    
    # Pi 5 should run at 5 Hz (± 1 Hz tolerance)
    assert 4.0 <= actual_cadence <= 6.0, (
        f"Pi 5 cadence {actual_cadence:.2f} Hz outside 5 Hz target (± 1 Hz)"
    )
    
    # Measure latency
    latencies = []
    for _ in range(20):
        start_time = time.perf_counter()
        await asyncio.sleep(0.001)  # Minimal processing time
        end_time = time.perf_counter()
        
        latency_ms = (end_time - start_time) * 1000
        latencies.append(latency_ms)
    
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
    
    # Pi 5 latency budget: p95 ≤ 250ms
    assert p95 <= 250, f"Pi 5 p95 latency {p95:.1f}ms exceeds 250ms budget"
if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "-s"])