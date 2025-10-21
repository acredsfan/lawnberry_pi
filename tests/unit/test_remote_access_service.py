from pathlib import Path

import pytest

from backend.src.models.remote_access_config import CloudflareConfig, NgrokConfig, RemoteAccessConfig
from backend.src.services.remote_access_service import RemoteAccessError, RemoteAccessService


@pytest.fixture()
def temp_paths(tmp_path: Path):
    config_path = tmp_path / "remote_access.json"
    status_path = tmp_path / "remote_access_status.json"
    return config_path, status_path


def test_cloudflare_validation_requires_tunnel(temp_paths):
    config_path, status_path = temp_paths
    service = RemoteAccessService(config_path=config_path, status_path=status_path)
    cfg = RemoteAccessConfig(provider="cloudflare", enabled=True)
    with pytest.raises(RemoteAccessError):
        service.configure(cfg, persist=False)

@pytest.mark.asyncio
async def test_ngrok_fallback_when_cloudflare_start_fails(monkeypatch, temp_paths):
    config_path, status_path = temp_paths
    service = RemoteAccessService(config_path=config_path, status_path=status_path)
    creds = config_path.parent / "cf.json"
    creds.write_text("{}")
    cfg = RemoteAccessConfig(
        provider="cloudflare",
        enabled=True,
        cloudflare=CloudflareConfig(tunnel_name="lawnberry", credentials_file=str(creds)),
        ngrok=NgrokConfig(authtoken="unit-test-token"),
    )
    service.configure(cfg, persist=False)

    calls = {"ngrok": 0}

    async def fail_cloudflare(self, *_args, **_kwargs):
        raise RemoteAccessError("boom")

    async def fake_ngrok(self, *_args, fallback: bool, **_kwargs):
        calls["ngrok"] += 1
        assert fallback is True
        self._status.provider = "ngrok"
        self._status.active = True
        self._status.health = "starting"
        self._status.message = "fallback"
        self._status.fallback_provider = "ngrok"

    monkeypatch.setattr(RemoteAccessService, "_start_cloudflare", fail_cloudflare, raising=False)
    monkeypatch.setattr(RemoteAccessService, "_start_ngrok", fake_ngrok, raising=False)

    await service.enable()
    assert calls["ngrok"] == 1
    status = RemoteAccessService.load_status_from_disk(status_path)
    assert status.provider == "ngrok"
    assert status.fallback_provider == "ngrok"
    assert status.enabled is True


@pytest.mark.asyncio
async def test_disable_updates_status_on_disk(temp_paths):
    config_path, status_path = temp_paths
    service = RemoteAccessService(config_path=config_path, status_path=status_path)
    cfg = RemoteAccessConfig(provider="ngrok", enabled=True, ngrok=NgrokConfig(authtoken="token"))
    service.configure(cfg, persist=False)

    # Mark status as active before disabling to ensure fields flip correctly
    service.get_status().active = True
    await service.disable()
    persisted = RemoteAccessService.load_status_from_disk(status_path)
    assert persisted.active is False
    assert persisted.health == "stopped"
    assert persisted.url is None
