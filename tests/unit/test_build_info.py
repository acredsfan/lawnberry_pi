from __future__ import annotations

import pytest

from backend.src.core import build_info


@pytest.fixture(autouse=True)
def clear_build_info_cache():
    build_info.get_build_info.cache_clear()
    yield
    build_info.get_build_info.cache_clear()


def test_build_info_prefers_valid_deployment_sha(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_BUILD_SHA", "A" * 40)
    monkeypatch.setattr(build_info, "_git_sha", lambda: "b" * 40)
    build_info.get_build_info.cache_clear()

    result = build_info.get_build_info()

    assert result["commit_sha"] == "a" * 40
    assert result["short_sha"] == "a" * 12
    assert result["source"] == "environment"


def test_build_info_reports_unavailable_instead_of_fabricating_sha(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_BUILD_SHA", "not-a-sha")
    monkeypatch.setattr(build_info, "_git_sha", lambda: None)
    build_info.get_build_info.cache_clear()

    result = build_info.get_build_info()

    assert result["commit_sha"] is None
    assert result["short_sha"] is None
    assert result["source"] == "unavailable"
