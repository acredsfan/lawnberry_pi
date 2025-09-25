"""Integration test for WebUI pages contract matrix."""
import pytest
from pathlib import Path
import re
from typing import Dict, Set


class TestWebUIPagesContractMatrix:
    """Test WebUI pages contract matrix per T005 requirements."""
    
    @pytest.fixture
    def spec_content(self) -> str:
        """Load the specification content."""
        spec_path = Path("/home/pi/lawnberry/specs/002-update-spec-to/spec.md")
        if not spec_path.exists():
            pytest.skip("Specification file not found")
        
        with open(spec_path, 'r') as f:
            return f.read()
    
    def test_dashboard_page_has_contracts(self, spec_content: str):
        """Test Dashboard page references required REST endpoints and WebSocket topics."""
        # Look for Dashboard section
        dashboard_section = self._extract_page_section(spec_content, "Dashboard")
        
        # Should reference REST endpoints
        rest_patterns = [
            r"/api/dashboard/state",
            r"/api/dashboard/alerts"
        ]
        
        for pattern in rest_patterns:
            assert re.search(pattern, dashboard_section, re.IGNORECASE), \
                f"Dashboard section missing REST endpoint reference: {pattern}"
        
        # Should reference WebSocket topic
        ws_pattern = r"telemetry/updates"
        assert re.search(ws_pattern, dashboard_section, re.IGNORECASE), \
            f"Dashboard section missing WebSocket topic: {ws_pattern}"
    
    def test_map_setup_page_has_contracts(self, spec_content: str):
        """Test Map Setup page references required contracts."""
        map_section = self._extract_page_section(spec_content, "Map Setup")
        
        rest_patterns = [r"/api/map/zones"]
        ws_patterns = [r"map/updates"]
        
        for pattern in rest_patterns:
            assert re.search(pattern, map_section, re.IGNORECASE), \
                f"Map Setup section missing REST endpoint: {pattern}"
        
        for pattern in ws_patterns:
            assert re.search(pattern, map_section, re.IGNORECASE), \
                f"Map Setup section missing WebSocket topic: {pattern}"
    
    def test_manual_control_page_has_contracts(self, spec_content: str):
        """Test Manual Control page references required contracts."""
        manual_section = self._extract_page_section(spec_content, "Manual Control")
        
        rest_patterns = [r"/api/manual/command"]
        ws_patterns = [r"manual/feedback"]
        
        for pattern in rest_patterns:
            assert re.search(pattern, manual_section, re.IGNORECASE), \
                f"Manual Control section missing REST endpoint: {pattern}"
        
        for pattern in ws_patterns:
            assert re.search(pattern, manual_section, re.IGNORECASE), \
                f"Manual Control section missing WebSocket topic: {pattern}"
    
    def test_mow_planning_page_has_contracts(self, spec_content: str):
        """Test Mow Planning page references required contracts."""
        mow_section = self._extract_page_section(spec_content, "Mow Planning")
        
        rest_patterns = [r"/api/mow/jobs"]
        ws_patterns = [r"mow/jobs/.*events"]
        
        for pattern in rest_patterns:
            assert re.search(pattern, mow_section, re.IGNORECASE), \
                f"Mow Planning section missing REST endpoint: {pattern}"
        
        for pattern in ws_patterns:
            assert re.search(pattern, mow_section, re.IGNORECASE), \
                f"Mow Planning section missing WebSocket topic: {pattern}"
    
    def test_ai_training_page_has_contracts(self, spec_content: str):
        """Test AI Training page references required contracts."""
        ai_section = self._extract_page_section(spec_content, "AI Training")
        
        rest_patterns = [r"/api/ai/datasets", r"/api/ai/datasets/export"]
        ws_patterns = [r"ai/training/progress"]
        
        for pattern in rest_patterns:
            assert re.search(pattern, ai_section, re.IGNORECASE), \
                f"AI Training section missing REST endpoint: {pattern}"
        
        for pattern in ws_patterns:
            assert re.search(pattern, ai_section, re.IGNORECASE), \
                f"AI Training section missing WebSocket topic: {pattern}"
    
    def test_settings_page_has_contracts(self, spec_content: str):
        """Test Settings page references required contracts."""
        settings_section = self._extract_page_section(spec_content, "Settings")
        
        rest_patterns = [r"/api/settings/profile"]
        ws_patterns = [r"settings/cadence"]
        
        for pattern in rest_patterns:
            assert re.search(pattern, settings_section, re.IGNORECASE), \
                f"Settings section missing REST endpoint: {pattern}"
        
        for pattern in ws_patterns:
            assert re.search(pattern, settings_section, re.IGNORECASE), \
                f"Settings section missing WebSocket topic: {pattern}"
    
    def test_docs_hub_page_has_contracts(self, spec_content: str):
        """Test Docs Hub page references required contracts."""
        docs_section = self._extract_page_section(spec_content, "Docs Hub")
        
        rest_patterns = [r"/api/docs/index"]
        
        for pattern in rest_patterns:
            assert re.search(pattern, docs_section, re.IGNORECASE), \
                f"Docs Hub section missing REST endpoint: {pattern}"
    
    def test_all_pages_documented(self, spec_content: str):
        """Test that all seven mandated pages are documented."""
        required_pages = [
            "Dashboard",
            "Map Setup", 
            "Manual Control",
            "Mow Planning",
            "AI Training",
            "Settings",
            "Docs Hub"
        ]
        
        for page in required_pages:
            assert self._page_section_exists(spec_content, page), \
                f"Required page {page} not found in specification"
    
    def _extract_page_section(self, content: str, page_name: str) -> str:
        """Extract content for a specific page section."""
        # Look for page header patterns
        patterns = [
            rf"#{1,4}\s*{re.escape(page_name)}.*?(?=#{1,4}\s|\Z)",
            rf"## {re.escape(page_name)}.*?(?=##|\Z)",
            rf"### {re.escape(page_name)}.*?(?=###|\Z)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(0)
        
        return ""
    
    def _page_section_exists(self, content: str, page_name: str) -> bool:
        """Check if a page section exists in the content."""
        section = self._extract_page_section(content, page_name)
        return len(section) > 0