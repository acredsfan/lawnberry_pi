import importlib
from pathlib import Path


def test_settings_service_uses_lawn_settings_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LAWN_SETTINGS_DIR", str(tmp_path))

    import backend.src.services.settings_service as settings_service_module

    reloaded = importlib.reload(settings_service_module)
    service = reloaded.SettingsService(persistence=object())
    assert service.config_dir == Path(str(tmp_path))
