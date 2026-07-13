import base64
import json
import os
from pathlib import Path

import pytest

from scripts.manage_cloudflared_service import (
    CloudflaredServiceError,
    _restore_previous_service,
    extract_inline_token,
    read_protected_token_file,
    security_state_is_safe,
    validate_tunnel_token,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _token() -> str:
    payload = {
        "a": "a" * 32,
        "s": base64.b64encode(b"unit-test-tunnel-secret-value").decode(),
        "t": "12345678-1234-1234-1234-123456789abc",
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def test_tracked_cloudflared_unit_uses_protected_token_file() -> None:
    unit = (REPO_ROOT / "systemd/cloudflared.service").read_text()

    assert "--token-file /etc/cloudflared/tunnel-token" in unit
    assert "--token " not in unit
    assert "TUNNEL_TOKEN=" not in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit


def test_extract_inline_token_for_one_time_migration() -> None:
    token = _token()
    unit = f"ExecStart=/usr/bin/cloudflared tunnel run --token {token}\n"

    assert extract_inline_token(unit) == token


def test_validate_tunnel_token_rejects_unstructured_secret() -> None:
    with pytest.raises(CloudflaredServiceError, match="Invalid Cloudflare Tunnel token"):
        validate_tunnel_token("not-a-cloudflare-token")


def test_read_protected_token_file_requires_owner_only_permissions(tmp_path: Path) -> None:
    source = tmp_path / "tunnel-token"
    source.write_text(_token())
    source.chmod(0o644)

    with pytest.raises(CloudflaredServiceError, match="owner-only"):
        read_protected_token_file(source)

    source.chmod(0o600)
    assert read_protected_token_file(source) == _token()


def test_read_protected_token_file_rejects_symlinks_and_non_regular_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tunnel-token"
    source.write_text(_token())
    source.chmod(0o600)
    symlink = tmp_path / "tunnel-token-link"
    symlink.symlink_to(source)

    with pytest.raises(CloudflaredServiceError, match="Unable to open"):
        read_protected_token_file(symlink)

    fifo = tmp_path / "tunnel-token-fifo"
    os.mkfifo(fifo, mode=0o600)
    with pytest.raises(CloudflaredServiceError, match="regular file"):
        read_protected_token_file(fifo)


def test_security_state_rejects_effective_token_overrides() -> None:
    state: dict[str, bool | str] = {
        "service_active": True,
        "unit_uses_token_file": True,
        "unit_contains_inline_token": False,
        "unit_has_dropins": False,
        "unit_environment_contains_token": False,
        "process_state_readable": True,
        "argv_uses_expected_token_file": True,
        "argv_contains_inline_token": False,
        "process_environment_contains_token": False,
        "token_file_exists": True,
        "token_file_mode": "0600",
        "token_file_owner_root": True,
        "token_file_valid": True,
    }
    assert security_state_is_safe(state)

    for key in (
        "unit_has_dropins",
        "unit_environment_contains_token",
        "process_environment_contains_token",
    ):
        bypass = state | {key: True}
        assert not security_state_is_safe(bypass)
    assert not security_state_is_safe(state | {"argv_uses_expected_token_file": False})


def test_rollback_requires_restored_service_health(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str | list[str]] = []

    monkeypatch.setattr(
        "scripts.manage_cloudflared_service._restore",
        lambda *_args: calls.append("restore"),
    )
    monkeypatch.setattr(
        "scripts.manage_cloudflared_service._run",
        lambda command, **_kwargs: calls.append(command),
    )
    monkeypatch.setattr(
        "scripts.manage_cloudflared_service._wait_until_active",
        lambda previous_pid=None: calls.append(["active", previous_pid]),
    )
    monkeypatch.setattr("scripts.manage_cloudflared_service._main_pid", lambda: "99")

    _restore_previous_service(None, None, previously_active=True)

    assert calls == [
        "restore",
        "restore",
        ["systemctl", "daemon-reload"],
        ["systemctl", "restart", "--no-block", "cloudflared.service"],
        ["active", "99"],
    ]
