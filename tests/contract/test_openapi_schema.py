"""Contract tests for OpenAPI schema generation and correctness.

These tests ensure that:
1. The OpenAPI schema can be regenerated and matches the committed snapshot
2. All canonical v2 paths exist in the schema
3. All v1 paths are marked as deprecated
"""
import json
import os
from pathlib import Path

import pytest

# Set SIM_MODE before importing the app
os.environ.setdefault("SIM_MODE", "1")
os.environ.setdefault("LAWNBERRY_SKIP_HW_INIT", "1")

from backend.src.main import app


@pytest.fixture
def committed_schema():
    """Load the committed OpenAPI schema from disk."""
    schema_path = Path(__file__).parent.parent.parent / "openapi.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def generated_schema():
    """Generate the OpenAPI schema at test time."""
    return app.openapi()


def test_schema_matches_committed_snapshot(committed_schema, generated_schema):
    """Verify that the regenerated schema matches the committed openapi.json.

    This catches cases where:
    - New routes were added but openapi.json wasn't regenerated
    - Routes were removed or renamed
    - Schemas changed significantly
    """
    # Normalize both schemas to JSON strings for comparison (consistent key ordering)
    committed_json = json.dumps(committed_schema, indent=2, sort_keys=True)
    generated_json = json.dumps(generated_schema, indent=2, sort_keys=True)

    assert committed_json == generated_json, (
        "Committed openapi.json does not match regenerated schema. "
        "Run: uv run python scripts/generate_openapi.py openapi.json"
    )


def test_schema_has_canonical_paths(generated_schema):
    """Verify that all canonical v2 paths exist in the schema.

    Canonical paths are the main API routes that should always be present.
    """
    paths = generated_schema.get("paths", {})
    canonical_paths = {
        # Control
        "/api/v2/control/drive",
        "/api/v2/control/blade",
        "/api/v2/control/emergency",
        "/api/v2/control/emergency_clear",
        "/api/v2/control/status",
        # Maps & Planning
        "/api/v2/map/zones",
        "/api/v2/map/locations",
        "/api/v2/map/configuration",
        "/api/v2/map/provider-fallback",
        "/api/v2/planning/jobs",
        "/api/v2/planning/jobs/{job_id}",
        # Settings
        "/api/v2/settings",
        "/api/v2/settings/safety",
        "/api/v2/settings/security",
        "/api/v2/settings/maps",
        # Missions
        "/api/v2/missions/create",
        "/api/v2/missions/list",
        "/api/v2/missions/{mission_id}/status",
        "/api/v2/missions/{mission_id}/pause",
        "/api/v2/missions/{mission_id}/resume",
        "/api/v2/missions/{mission_id}/abort",
        "/api/v2/missions/{mission_id}/start",
        # Telemetry
        "/api/v2/telemetry/stream",
        "/api/v2/telemetry/export",
        "/api/v2/telemetry/ping",
        "/api/v2/dashboard/telemetry",
        "/api/v2/dashboard/status",
    }

    missing_paths = canonical_paths - set(paths.keys())
    assert not missing_paths, f"Missing canonical paths: {missing_paths}"


def test_v1_paths_are_deprecated(generated_schema):
    """Verify that all v1 paths are marked with deprecated: true in OpenAPI.

    This ensures deprecated endpoints are clearly documented as such.
    """
    paths = generated_schema.get("paths", {})
    v1_paths = {path: spec for path, spec in paths.items() if "/api/v1" in path}

    assert len(v1_paths) > 0, "No v1 paths found in schema (expected deprecated routes)"

    for path, path_spec in v1_paths.items():
        # Check each method (get, post, put, delete, patch)
        for method in ["get", "post", "put", "delete", "patch"]:
            operation = path_spec.get(method)
            if operation is None:
                continue

            # The operation should have deprecated: true flag
            deprecated = operation.get("deprecated", False)
            assert deprecated is True, (
                f"Path {path} {method.upper()} is missing deprecated: true flag. "
                f"Operation keys: {list(operation.keys())}"
            )
