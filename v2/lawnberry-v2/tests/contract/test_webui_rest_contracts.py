"""Contract validation tests for WebUI REST endpoints."""
import pytest
from pathlib import Path
from typing import Dict, Any
import yaml


class TestWebUIRestContracts:
    """Test REST contract compliance per T003 requirements."""
    
    @pytest.fixture
    def contract_spec(self) -> Dict[str, Any]:
        """Load WebUI OpenAPI contract specification."""
        contract_path = Path("/home/pi/lawnberry/specs/002-update-spec-to/contracts/webui-openapi.yaml")
        if not contract_path.exists():
            pytest.skip("Contract specification not found")
        
        with open(contract_path, 'r') as f:
            return yaml.safe_load(f)
    
    def test_dashboard_endpoints_present(self, contract_spec: Dict[str, Any]):
        """Test that dashboard endpoints are documented in contract."""
        paths = contract_spec.get("paths", {})
        
        # Required dashboard endpoints
        required_endpoints = [
            "/api/v1/dashboard/state",
            "/api/v1/dashboard/alerts"
        ]
        
        for endpoint in required_endpoints:
            assert endpoint in paths, f"Dashboard endpoint {endpoint} missing from contract"
            assert "get" in paths[endpoint], f"GET method missing for {endpoint}"
    
    def test_map_endpoints_present(self, contract_spec: Dict[str, Any]):
        """Test that map setup endpoints are documented."""
        paths = contract_spec.get("paths", {})
        
        required_endpoints = [
            "/api/v1/map/zones",
            "/api/v1/map/boundaries"
        ]
        
        for endpoint in required_endpoints:
            assert endpoint in paths, f"Map endpoint {endpoint} missing from contract"
    
    def test_manual_control_endpoints_present(self, contract_spec: Dict[str, Any]):
        """Test that manual control endpoints are documented."""
        paths = contract_spec.get("paths", {})
        
        required_endpoints = [
            "/api/v1/manual/command"
        ]
        
        for endpoint in required_endpoints:
            assert endpoint in paths, f"Manual control endpoint {endpoint} missing from contract"
            assert "post" in paths[endpoint], f"POST method missing for {endpoint}"
    
    def test_mow_planning_endpoints_present(self, contract_spec: Dict[str, Any]):
        """Test that mow planning endpoints are documented."""
        paths = contract_spec.get("paths", {})
        
        required_endpoints = [
            "/api/v1/mow/jobs",
            "/api/v1/mow/jobs/{jobId}"
        ]
        
        for endpoint in required_endpoints:
            assert endpoint in paths, f"Mow planning endpoint {endpoint} missing from contract"
    
    def test_ai_training_endpoints_present(self, contract_spec: Dict[str, Any]):
        """Test that AI training endpoints are documented."""
        paths = contract_spec.get("paths", {})
        
        required_endpoints = [
            "/api/v1/ai/datasets",
            "/api/v1/ai/datasets/export"
        ]
        
        for endpoint in required_endpoints:
            assert endpoint in paths, f"AI training endpoint {endpoint} missing from contract"
    
    def test_settings_endpoints_present(self, contract_spec: Dict[str, Any]):
        """Test that settings endpoints are documented."""
        paths = contract_spec.get("paths", {})
        
        required_endpoints = [
            "/api/v1/settings/profile"
        ]
        
        for endpoint in required_endpoints:
            assert endpoint in paths, f"Settings endpoint {endpoint} missing from contract"
    
    def test_docs_endpoints_present(self, contract_spec: Dict[str, Any]):
        """Test that docs hub endpoints are documented."""
        paths = contract_spec.get("paths", {})
        
        required_endpoints = [
            "/api/v1/docs/index"
        ]
        
        for endpoint in required_endpoints:
            assert endpoint in paths, f"Docs hub endpoint {endpoint} missing from contract"
    
    def test_response_schemas_present(self, contract_spec: Dict[str, Any]):
        """Test that all endpoints have required response schemas."""
        paths = contract_spec.get("paths", {})
        
        for path, methods in paths.items():
            for method, spec in methods.items():
                responses = spec.get("responses", {})
                assert "200" in responses, f"Missing 200 response for {method.upper()} {path}"
                
                response_200 = responses["200"]
                assert "content" in response_200, f"Missing content in 200 response for {method.upper()} {path}"
    
    def test_auth_requirements_documented(self, contract_spec: Dict[str, Any]):
        """Test that authentication requirements are documented."""
        paths = contract_spec.get("paths", {})
        
        # Manual control and sensitive endpoints should require auth
        auth_required_paths = [
            "/api/v1/manual/command",
            "/api/v1/settings/profile",
            "/api/v1/ai/datasets/export"
        ]
        
        for path in auth_required_paths:
            if path in paths:
                for method, spec in paths[path].items():
                    security = spec.get("security", [])
                    assert security, f"Authentication missing for {method.upper()} {path}"