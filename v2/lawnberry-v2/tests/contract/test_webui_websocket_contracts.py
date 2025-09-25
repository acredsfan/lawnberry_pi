"""Contract validation tests for WebUI WebSocket topics."""
import pytest
from pathlib import Path
from typing import Dict, Any
import yaml


class TestWebUIWebSocketContracts:
    """Test WebSocket contract compliance per T004 requirements."""
    
    @pytest.fixture
    def contract_spec(self) -> Dict[str, Any]:
        """Load WebUI WebSocket contract specification."""
        contract_path = Path("/home/pi/lawnberry/specs/002-update-spec-to/contracts/webui-websocket.yaml")
        if not contract_path.exists():
            pytest.skip("WebSocket contract specification not found")
        
        with open(contract_path, 'r') as f:
            return yaml.safe_load(f)
    
    def test_telemetry_topic_present(self, contract_spec: Dict[str, Any]):
        """Test telemetry/updates topic is documented with proper cadence."""
        channels = contract_spec.get("channels", {})
        
        telemetry_topic = "telemetry/updates"
        assert telemetry_topic in channels, f"Topic {telemetry_topic} missing from contract"
        
        topic_spec = channels[telemetry_topic]
        
        # Check for message schema
        assert "subscribe" in topic_spec, "Telemetry topic missing subscribe operation"
        subscribe_spec = topic_spec["subscribe"]
        assert "message" in subscribe_spec, "Telemetry topic missing message schema"
        
        # Check for cadence configuration
        message_spec = subscribe_spec["message"]
        if "bindings" in message_spec:
            bindings = message_spec["bindings"]
            # Should document 5Hz default cadence
            assert "cadence_hz" in str(bindings).lower() or "5" in str(bindings), "Missing cadence configuration"
    
    def test_manual_feedback_topic_present(self, contract_spec: Dict[str, Any]):
        """Test manual/feedback topic is documented."""
        channels = contract_spec.get("channels", {})
        
        feedback_topic = "manual/feedback"
        assert feedback_topic in channels, f"Topic {feedback_topic} missing from contract"
        
        topic_spec = channels[feedback_topic]
        assert "subscribe" in topic_spec, "Manual feedback topic missing subscribe operation"
    
    def test_map_updates_topic_present(self, contract_spec: Dict[str, Any]):
        """Test map/updates topic is documented."""
        channels = contract_spec.get("channels", {})
        
        map_topic = "map/updates"
        assert map_topic in channels, f"Topic {map_topic} missing from contract"
    
    def test_mow_job_events_topic_present(self, contract_spec: Dict[str, Any]):
        """Test mow job events topic is documented."""
        channels = contract_spec.get("channels", {})
        
        # Look for pattern or specific job events topic
        job_topics = [ch for ch in channels.keys() if "mow/jobs" in ch and "events" in ch]
        assert job_topics, "No mow job events topics found in contract"
    
    def test_ai_training_progress_topic_present(self, contract_spec: Dict[str, Any]):
        """Test AI training progress topic is documented."""
        channels = contract_spec.get("channels", {})
        
        ai_topic = "ai/training/progress"
        assert ai_topic in channels, f"Topic {ai_topic} missing from contract"
    
    def test_settings_cadence_topic_present(self, contract_spec: Dict[str, Any]):
        """Test settings/cadence topic is documented."""
        channels = contract_spec.get("channels", {})
        
        settings_topic = "settings/cadence"
        assert settings_topic in channels, f"Topic {settings_topic} missing from contract"
    
    def test_heartbeat_intervals_documented(self, contract_spec: Dict[str, Any]):
        """Test that heartbeat intervals are documented for critical topics."""
        channels = contract_spec.get("channels", {})
        
        critical_topics = ["telemetry/updates", "manual/feedback"]
        
        for topic in critical_topics:
            if topic in channels:
                topic_spec = channels[topic]
                # Look for heartbeat configuration
                spec_str = str(topic_spec).lower()
                assert "heartbeat" in spec_str or "interval" in spec_str, f"Missing heartbeat config for {topic}"
    
    def test_cadence_range_documented(self, contract_spec: Dict[str, Any]):
        """Test that telemetry cadence defaults and ranges are documented."""
        channels = contract_spec.get("channels", {})
        
        telemetry_topic = "telemetry/updates"
        if telemetry_topic in channels:
            topic_spec = channels[telemetry_topic]
            spec_str = str(topic_spec).lower()
            
            # Should document 5Hz default, 10Hz max, 1Hz min
            cadence_keywords = ["5", "10", "1", "hz", "cadence"]
            found_keywords = sum(1 for keyword in cadence_keywords if keyword in spec_str)
            assert found_keywords >= 3, f"Insufficient cadence configuration documentation for {telemetry_topic}"
    
    def test_topic_coverage_complete(self, contract_spec: Dict[str, Any]):
        """Test that all five required WebSocket channels are covered."""
        channels = contract_spec.get("channels", {})
        
        required_topics = [
            "telemetry/updates",
            "manual/feedback", 
            "map/updates",
            "ai/training/progress",
            "settings/cadence"
        ]
        
        for topic in required_topics:
            assert topic in channels or any(topic in ch for ch in channels.keys()), \
                f"Required topic {topic} not found in channels"