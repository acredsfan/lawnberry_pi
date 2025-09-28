"""
Performance tests for telemetry pipeline
Tests WebSocket telemetry performance, latency, and throughput
"""

import pytest
import asyncio
import time
import json
import statistics
from typing import List, Dict, Any
from unittest.mock import Mock, patch, AsyncMock
import websockets
from websockets.exceptions import ConnectionClosed

from backend.src.api.rest import websocket_hub
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
        
        print(f"Telemetry generation - Avg: {avg_time:.2f}ms, Max: {max_time:.2f}ms, P95: {p95_time:.2f}ms")
        
        # Performance requirements
        assert avg_time < 5.0, f"Average telemetry generation time {avg_time:.2f}ms exceeds 5ms threshold"
        assert max_time < 20.0, f"Maximum telemetry generation time {max_time:.2f}ms exceeds 20ms threshold"
        assert p95_time < 10.0, f"95th percentile telemetry generation time {p95_time:.2f}ms exceeds 10ms threshold"

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
        
        print(f"Broadcast performance - Avg: {avg_time:.2f}ms, Max: {max_time:.2f}ms for {len(connected_clients)} clients")
        
        # Performance requirements (should scale with client count)
        expected_max_time = len(connected_clients) * 2.0  # 2ms per client
        assert avg_time < expected_max_time, f"Broadcast time {avg_time:.2f}ms exceeds expected {expected_max_time:.2f}ms"

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
        assert avg_filtering_time < 5.0, f"Subscription filtering time {avg_filtering_time:.2f}ms exceeds 5ms threshold"

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
        
        print(f"Telemetry loop - Avg: {avg_loop_time:.2f}ms, Max: {max_loop_time:.2f}ms")
        print(f"Total messages sent: {total_messages}")
        
        # Performance requirements for 10 Hz operation
        max_allowed_time = (1000 / mock_websocket_hub.telemetry_cadence_hz) * 0.5  # 50% of cycle time
        assert avg_loop_time < max_allowed_time, f"Telemetry loop time {avg_loop_time:.2f}ms exceeds {max_allowed_time:.2f}ms"

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
        expected_iterations = int(2.0 * mock_websocket_hub.telemetry_cadence_hz * 0.9)  # 90% tolerance
        error_rate = error_count / max(iteration_count, 1)
        
        print(f"High-frequency test - Iterations: {iteration_count}, Errors: {error_count}, Rate: {iteration_count/2.0:.1f} Hz")
        
        assert iteration_count >= expected_iterations, f"Insufficient iterations {iteration_count} < {expected_iterations}"
        assert error_rate < 0.01, f"Error rate {error_rate:.3f} exceeds 1% threshold"

    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, mock_websocket_hub):
        """Test memory usage stability during continuous operation."""
        import gc
        import psutil
        import os
        
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
        
        print(f"Memory usage - Initial: {initial_memory:.1f}MB, Final: {final_memory:.1f}MB, Increase: {memory_increase:.1f}MB")
        
        # Memory requirements (should not grow significantly)
        assert memory_increase < 50.0, f"Memory increase {memory_increase:.1f}MB exceeds 50MB threshold"

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
        print(f"Connection - Avg: {avg_connection_time:.2f}ms, Max: {max_connection_time:.2f}ms")
        print(f"Broadcast time: {broadcast_time:.2f}ms")
        
        # Scalability requirements
        assert avg_connection_time < 10.0, f"Average connection time {avg_connection_time:.2f}ms exceeds 10ms"
        assert broadcast_time < client_count * 1.0, f"Broadcast time {broadcast_time:.2f}ms doesn't scale well"

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
        
        print(f"Cleanup performance - Avg: {avg_cleanup_time:.2f}ms, Max: {max_cleanup_time:.2f}ms")
        
        # Cleanup should be fast
        assert avg_cleanup_time < 5.0, f"Average cleanup time {avg_cleanup_time:.2f}ms exceeds 5ms"
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
        
        print(f"Error handling performance - Avg: {avg_error_time:.2f}ms with {len(bad_clients)} failing clients")
        
        # Error handling shouldn't significantly impact performance
        assert avg_error_time < 50.0, f"Error handling time {avg_error_time:.2f}ms exceeds 50ms threshold"


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
            
            print(f"End-to-end latency - Avg: {avg_latency:.2f}ms, Max: {max_latency:.2f}ms")
            
            # Latency requirements
            assert avg_latency < 100.0, f"Average latency {avg_latency:.2f}ms exceeds 100ms threshold"
            assert max_latency < 200.0, f"Maximum latency {max_latency:.2f}ms exceeds 200ms threshold"


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
        
        print(f"Maximum throughput: {throughput:.0f} messages/second with {client_count} clients")
        
        # Throughput requirements
        expected_min_throughput = client_count * 100  # 100 messages/second per client minimum  
        assert throughput >= expected_min_throughput, f"Throughput {throughput:.0f} msg/s below minimum {expected_min_throughput}"


if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "-s"])