import importlib
from pathlib import Path


def test_global_persistence_uses_db_path_env(monkeypatch, tmp_path):
    isolated_db = tmp_path / "isolated-test.db"
    monkeypatch.setenv("DB_PATH", str(isolated_db))

    import backend.src.core.persistence as persistence_module

    reloaded = importlib.reload(persistence_module)
    assert reloaded.persistence.db_path == Path(str(isolated_db))
