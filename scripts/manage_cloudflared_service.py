#!/usr/bin/env python3
"""Install and verify cloudflared without exposing its tunnel token in argv."""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIT_SOURCE = REPO_ROOT / "systemd/cloudflared.service"
UNIT_DESTINATION = Path("/etc/systemd/system/cloudflared.service")
TOKEN_PATH = Path("/etc/cloudflared/tunnel-token")
SERVICE_NAME = "cloudflared.service"
INLINE_TOKEN_RE = re.compile(r"--token(?:=|\s+)([^\s\"']+)")


class CloudflaredServiceError(RuntimeError):
    """Raised when a safe cloudflared installation cannot be completed."""


def _run(
    command: list[str],
    *,
    check: bool = True,
    timeout: float = 40,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def extract_inline_token(unit_text: str) -> str:
    """Extract a legacy inline token without returning surrounding unit content."""
    match = INLINE_TOKEN_RE.search(unit_text)
    if not match:
        raise CloudflaredServiceError("The installed unit does not contain a legacy inline token")
    return validate_tunnel_token(match.group(1))


def validate_tunnel_token(token: str) -> str:
    """Validate the opaque token shape while keeping its secret payload private."""
    token = token.strip()
    if len(token) < 80 or any(character.isspace() for character in token):
        raise CloudflaredServiceError("Invalid Cloudflare Tunnel token")

    encoded = token.split(".")[1] if token.count(".") == 2 else token
    encoded += "=" * (-len(encoded) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise CloudflaredServiceError("Invalid Cloudflare Tunnel token") from exc

    if not isinstance(payload, dict) or not {"a", "s", "t"}.issubset(payload):
        raise CloudflaredServiceError("Invalid Cloudflare Tunnel token")
    if not all(isinstance(payload[key], str) and payload[key] for key in ("a", "s", "t")):
        raise CloudflaredServiceError("Invalid Cloudflare Tunnel token")
    return token


def read_protected_token_file(path: Path) -> str:
    """Read a token only from a file inaccessible to group and other users."""
    source = path.expanduser()
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise CloudflaredServiceError("Unable to open the protected tunnel token source") from exc

    try:
        source_stat = os.fstat(descriptor)
        if not stat.S_ISREG(source_stat.st_mode):
            raise CloudflaredServiceError("Tunnel token source must be a regular file")
        if stat.S_IMODE(source_stat.st_mode) & 0o077:
            raise CloudflaredServiceError(
                "Tunnel token source must be owner-only (mode 0600 or stricter)"
            )
        resolved = Path(os.path.realpath(f"/proc/self/fd/{descriptor}"))
        if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
            raise CloudflaredServiceError(
                "Refusing to read a tunnel token from inside the repository"
            )
        content = os.read(descriptor, 16_385)
        if len(content) > 16_384:
            raise CloudflaredServiceError("Tunnel token source is unexpectedly large")
        try:
            token = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CloudflaredServiceError("Invalid Cloudflare Tunnel token") from exc
        return validate_tunnel_token(token)
    finally:
        os.close(descriptor)


def _installed_unit_text() -> str:
    result = _run(["systemctl", "cat", "--no-pager", SERVICE_NAME])
    return result.stdout


def _current_token() -> str | None:
    try:
        return extract_inline_token(_installed_unit_text())
    except (CloudflaredServiceError, subprocess.SubprocessError):
        pass
    try:
        return validate_tunnel_token(TOKEN_PATH.read_text(encoding="utf-8"))
    except (CloudflaredServiceError, OSError):
        return None


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, mode)
        os.chown(path, 0, 0)
    finally:
        temporary_path.unlink(missing_ok=True)


def _backup(path: Path, backup_directory: Path) -> Path | None:
    if not path.exists():
        return None
    backup = backup_directory / path.name
    shutil.copy2(path, backup)
    return backup


def _restore(path: Path, backup: Path | None) -> None:
    if backup is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, path)


def _main_pid() -> str:
    result = _run(
        ["systemctl", "show", SERVICE_NAME, "-p", "MainPID", "--value"],
        check=False,
        timeout=5,
    )
    return result.stdout.strip()


def _wait_until_active(previous_pid: str | None = None, timeout_seconds: float = 35) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        active = _run(
            ["systemctl", "is-active", "--quiet", SERVICE_NAME],
            check=False,
            timeout=5,
        )
        current_pid = _main_pid()
        new_process = current_pid.isdigit() and current_pid != "0" and current_pid != previous_pid
        if active.returncode == 0 and new_process:
            return
        time.sleep(0.5)
    raise CloudflaredServiceError("cloudflared did not become active")


def _argument_value(arguments: list[bytes], flag: bytes) -> bytes | None:
    for index, argument in enumerate(arguments):
        if argument == flag:
            return arguments[index + 1] if index + 1 < len(arguments) else None
        prefix = flag + b"="
        if argument.startswith(prefix):
            return argument[len(prefix) :]
    return None


def inspect_security_state() -> dict[str, bool | str]:
    """Inspect only non-secret properties of the installed service and process."""
    try:
        unit_text = _installed_unit_text()
    except subprocess.SubprocessError:
        unit_text = ""
    try:
        fragment_text = UNIT_DESTINATION.read_text(encoding="utf-8")
    except OSError:
        fragment_text = ""

    dropins_result = _run(
        ["systemctl", "show", SERVICE_NAME, "-p", "DropInPaths", "--value"],
        check=False,
        timeout=5,
    )
    environment_result = _run(
        ["systemctl", "show", SERVICE_NAME, "-p", "Environment", "--value"],
        check=False,
        timeout=5,
    )
    effective_environment = environment_result.stdout if environment_result.returncode == 0 else ""

    token_exists = TOKEN_PATH.is_file()
    token_mode = "missing"
    token_owner_root = False
    token_valid = False
    if token_exists:
        token_stat = TOKEN_PATH.stat()
        token_mode = f"{stat.S_IMODE(token_stat.st_mode):04o}"
        token_owner_root = token_stat.st_uid == 0 and token_stat.st_gid == 0
        try:
            validate_tunnel_token(TOKEN_PATH.read_text(encoding="utf-8"))
            token_valid = True
        except (CloudflaredServiceError, OSError):
            token_valid = False

    pid_result = _run(
        ["systemctl", "show", SERVICE_NAME, "-p", "MainPID", "--value"],
        check=False,
        timeout=5,
    )
    pid = pid_result.stdout.strip()
    arguments: list[bytes] = []
    process_environment: list[bytes] = []
    process_state_readable = False
    if pid.isdigit() and pid != "0":
        try:
            arguments = [item for item in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if item]
            process_environment = [
                item for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0") if item
            ]
            process_state_readable = True
        except OSError:
            arguments = []
            process_environment = []

    inline_token_in_argv = any(
        argument == b"--token" or argument.startswith(b"--token=") for argument in arguments
    )
    token_file_argument = _argument_value(arguments, b"--token-file")
    token_environment_in_process = any(
        variable.startswith(b"TUNNEL_TOKEN=") or variable.startswith(b"TUNNEL_TOKEN_FILE=")
        for variable in process_environment
    )
    active = _run(
        ["systemctl", "is-active", "--quiet", SERVICE_NAME],
        check=False,
        timeout=5,
    ).returncode == 0

    return {
        "service_active": active,
        "unit_uses_token_file": f"--token-file {TOKEN_PATH}" in fragment_text,
        "unit_contains_inline_token": bool(INLINE_TOKEN_RE.search(unit_text)),
        "unit_has_dropins": bool(dropins_result.stdout.strip()),
        "unit_environment_contains_token": bool(
            re.search(r"(?:^|\s)TUNNEL_TOKEN(?:_FILE)?=", effective_environment)
        ),
        "process_state_readable": process_state_readable,
        "argv_uses_expected_token_file": token_file_argument == os.fsencode(TOKEN_PATH),
        "argv_contains_inline_token": inline_token_in_argv,
        "process_environment_contains_token": token_environment_in_process,
        "token_file_exists": token_exists,
        "token_file_mode": token_mode,
        "token_file_owner_root": token_owner_root,
        "token_file_valid": token_valid,
    }


def security_state_is_safe(state: dict[str, bool | str]) -> bool:
    """Return whether the credential boundary is fully enforced."""
    expected = {
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
    return all(state.get(key) == value for key, value in expected.items())


def print_security_state(state: dict[str, bool | str]) -> None:
    """Print a redacted, machine-readable security report."""
    for key in sorted(state):
        value = state[key]
        if isinstance(value, bool):
            value = str(value).lower()
        print(f"{key}={value}")
    print(f"credential_boundary_safe={str(security_state_is_safe(state)).lower()}")


def _restore_previous_service(
    unit_backup: Path | None,
    token_backup: Path | None,
    *,
    previously_active: bool,
) -> None:
    _restore(UNIT_DESTINATION, unit_backup)
    _restore(TOKEN_PATH, token_backup)
    _run(["systemctl", "daemon-reload"])
    if previously_active:
        failed_pid = _main_pid()
        _run(["systemctl", "restart", "--no-block", SERVICE_NAME])
        _wait_until_active(failed_pid)
    else:
        _run(["systemctl", "stop", SERVICE_NAME])


def install_service(token: str) -> tuple[bool, dict[str, bool | str]]:
    """Install a token-file unit atomically and roll back on any failed gate."""
    if os.geteuid() != 0:
        raise CloudflaredServiceError("Installation must run as root")
    token = validate_tunnel_token(token)
    unit_content = UNIT_SOURCE.read_bytes()
    unit_text = unit_content.decode("utf-8")
    if INLINE_TOKEN_RE.search(unit_text) or f"--token-file {TOKEN_PATH}" not in unit_text:
        raise CloudflaredServiceError("Tracked cloudflared unit violates the token-file invariant")

    verification = _run(["systemd-analyze", "verify", str(UNIT_SOURCE)], check=False)
    if verification.returncode != 0:
        raise CloudflaredServiceError("Tracked cloudflared unit failed systemd verification")

    previous_token = _current_token()
    token_changed = previous_token != token
    previous_pid = _main_pid()
    previously_active = _run(
        ["systemctl", "is-active", "--quiet", SERVICE_NAME],
        check=False,
        timeout=5,
    ).returncode == 0
    Path("/etc/cloudflared").mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod("/etc/cloudflared", 0o700)
    os.chown("/etc/cloudflared", 0, 0)

    with tempfile.TemporaryDirectory(prefix="lawnberry-cloudflared-", dir="/run") as raw_backup:
        backup_directory = Path(raw_backup)
        unit_backup = _backup(UNIT_DESTINATION, backup_directory)
        token_backup = _backup(TOKEN_PATH, backup_directory)
        try:
            _atomic_write(TOKEN_PATH, f"{token}\n".encode(), 0o600)
            _atomic_write(UNIT_DESTINATION, unit_content, 0o644)
            _run(["systemctl", "daemon-reload"])
            _run(["systemctl", "restart", "--no-block", SERVICE_NAME])
            _wait_until_active(previous_pid)
            state = inspect_security_state()
            if not security_state_is_safe(state):
                raise CloudflaredServiceError("Installed service failed the credential boundary check")
            return token_changed, state
        except Exception as exc:
            try:
                _restore_previous_service(
                    unit_backup,
                    token_backup,
                    previously_active=previously_active,
                )
            except Exception as rollback_exc:
                raise CloudflaredServiceError(
                    "Secure installation failed and rollback could not restore service health"
                ) from rollback_exc
            raise CloudflaredServiceError(
                "Secure installation failed; the previous service configuration and state were restored"
            ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install or verify cloudflared without exposing the tunnel token in argv."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--migrate-existing",
        action="store_true",
        help="Move the legacy inline token into the protected token file.",
    )
    action.add_argument(
        "--token-file",
        type=Path,
        help="Install a replacement token from an owner-only file outside the repository.",
    )
    action.add_argument(
        "--prompt-token",
        action="store_true",
        help="Prompt without echo for a replacement token.",
    )
    action.add_argument(
        "--check",
        action="store_true",
        help="Verify the installed unit, token permissions, and live process arguments.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.check:
            if os.geteuid() != 0:
                raise CloudflaredServiceError("Verification must run as root")
            state = inspect_security_state()
            print_security_state(state)
            return 0 if security_state_is_safe(state) else 1

        if args.migrate_existing:
            token = extract_inline_token(_installed_unit_text())
        elif args.token_file:
            token = read_protected_token_file(args.token_file)
        else:
            token = validate_tunnel_token(getpass.getpass("New Cloudflare Tunnel token: "))

        token_changed, state = install_service(token)
        print_security_state(state)
        print(f"credential_changed={str(token_changed).lower()}")
        if args.migrate_existing:
            print("cloudflare_rotation_required=true")
        return 0
    except (CloudflaredServiceError, OSError, subprocess.SubprocessError) as exc:
        print(f"cloudflared_service_error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
