"""Contract tests for the deployed AI inference surface."""

from backend.src.main import app


def test_ai_openapi_advertises_only_implemented_runtime_capabilities() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v2/ai/status" in paths
    assert "/api/v2/ai/perception/latest" in paths
    assert "/api/v2/ai/results/recent" in paths
    assert "/api/v2/ai/inference" in paths
    assert "/api/v2/ai/inference/latest" in paths
    assert "/api/v2/ai/datasets" not in paths
    assert "/api/v2/ai/datasets/{dataset_id}/export" not in paths
