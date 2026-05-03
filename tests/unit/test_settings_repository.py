# tests/unit/test_settings_repository.py
"""Unit tests for SettingsRepository.

Run: SIM_MODE=1 uv run pytest tests/unit/test_settings_repository.py -v
"""
from __future__ import annotations

import pytest
from pathlib import Path
from backend.src.repositories.settings_repository import SettingsRepository


@pytest.fixture
def repo(tmp_path: Path) -> SettingsRepository:
    return SettingsRepository(db_path=tmp_path / "settings.db")


def test_load_settings_empty(repo: SettingsRepository) -> None:
    """Loading before any save returns None."""
    assert repo.load() is None


def test_save_and_load_settings(repo: SettingsRepository) -> None:
    settings = {"theme": "dark", "units": "metric", "map_provider": "osm", "version": 1}
    repo.save(settings)
    loaded = repo.load()
    assert loaded is not None
    assert loaded["theme"] == "dark"
    assert loaded["version"] == 1


def test_save_overwrites(repo: SettingsRepository) -> None:
    repo.save({"theme": "light", "version": 1})
    repo.save({"theme": "dark", "version": 2})
    loaded = repo.load()
    assert loaded["theme"] == "dark"
    assert loaded["version"] == 2


def test_patch_setting(repo: SettingsRepository) -> None:
    repo.save({"theme": "light", "units": "metric", "version": 1})
    repo.patch({"theme": "dark"})
    loaded = repo.load()
    assert loaded["theme"] == "dark"
    assert loaded["units"] == "metric"  # unchanged


def test_patch_setting_missing_base(repo: SettingsRepository) -> None:
    """Patching when no settings exist creates a new record."""
    repo.patch({"theme": "retro"})
    loaded = repo.load()
    assert loaded["theme"] == "retro"


def test_load_ui_settings_empty(repo: SettingsRepository) -> None:
    assert repo.load_ui_settings() is None


def test_save_and_load_ui_settings(repo: SettingsRepository) -> None:
    ui = {"maps": {"provider": "google", "zoom": 14}, "dashboard": {"refresh_hz": 5}}
    repo.save_ui_settings(ui)
    loaded = repo.load_ui_settings()
    assert loaded is not None
    assert loaded["maps"]["provider"] == "google"
