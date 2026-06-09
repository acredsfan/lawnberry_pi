import importlib
from pathlib import Path


def test_settings_router_uses_lawn_data_dir_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))

    import backend.src.api.routers.settings as settings_router

    reloaded = importlib.reload(settings_router)
    assert reloaded.DATA_DIR == Path(str(tmp_path))
    assert reloaded.SETTINGS_FILE == Path(str(tmp_path)) / "settings.json"
    assert reloaded.UI_SETTINGS_FILE == Path(str(tmp_path)) / "ui_settings.json"
