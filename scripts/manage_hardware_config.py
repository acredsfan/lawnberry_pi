#!/usr/bin/env python3
"""Manage LawnBerry runtime hardware configuration without exposing values."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.src.core.config_loader import ConfigLoader  # noqa: E402
from backend.src.hardware.platform_profile import (  # noqa: E402
    PlatformKind,
    detect_platform_profile,
)

REDACTED = "[REDACTED]"
SENSITIVE_NAME_RE = re.compile(
    r"(encryption[_-]?key|device[_-]?key|api[_-]?key|password|token|credential[s]?)",
    re.IGNORECASE,
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"((?:encryption[_-]?key|device[_-]?key|api[_-]?key|password|token|credential[s]?)"
    r"\s*[:=]\s*)[^\s,;]+",
    re.IGNORECASE,
)

PROFILE_TEMPLATES = {
    "pi5": "hardware.pi5.example.yaml",
    "pi4": "hardware.pi4.example.yaml",
}
LEGACY_CONFIG_RELATIVE = Path("config") / "hardware.local.yaml"


def _redact_text(value: str) -> str:
    return SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{REDACTED}", value)


def _validation_error_summary(exc: Exception) -> str:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        parts: list[str] = []
        for err in errors():
            loc = ".".join(str(part) for part in err.get("loc", ())) or "configuration"
            msg = str(err.get("msg", "invalid"))
            parts.append(f"{loc}: {msg}")
        if parts:
            return _redact_text("; ".join(parts))
    return _redact_text(str(exc))


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a mapping")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def _chmod_owner_only(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        _chmod_owner_only(tmp_path)
        os.replace(tmp_path, path)
        _chmod_owner_only(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _atomic_copy_bytes(source: Path, dest: Path) -> None:
    data = source.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", dir=dest.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _chmod_owner_only(tmp_path)
        os.replace(tmp_path, dest)
        _chmod_owner_only(dest)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _backup_path(backup_dir: Path, source: Path, stamp: str) -> Path:
    candidate = backup_dir / f"{source.name}.{stamp}.bak"
    counter = 1
    while candidate.exists():
        candidate = backup_dir / f"{source.name}.{stamp}.{counter}.bak"
        counter += 1
    return candidate


def _legacy_path(root: Path) -> Path:
    return root / LEGACY_CONFIG_RELATIVE


def _fail_if_legacy_exists(root: Path, command: str) -> bool:
    legacy = _legacy_path(root)
    if not legacy.exists():
        return False
    print(
        "[hardware-config] Legacy config/hardware.local.yaml exists; "
        f"`{command}` refuses to ignore it. Run "
        "`uv run python scripts/manage_hardware_config.py migrate-legacy --profile auto` "
        "or remove the legacy file after verifying it is obsolete.",
        file=sys.stderr,
    )
    return True


def _copy_backup(source: Path, backup_dir: Path, stamp: str) -> Path:
    _secure_dir(backup_dir)
    dest = _backup_path(backup_dir, source, stamp)
    shutil.copy2(source, dest)
    _chmod_owner_only(dest)
    return dest


def _move_to_backup(source: Path, backup_dir: Path, stamp: str) -> Path:
    _secure_dir(backup_dir)
    dest = _backup_path(backup_dir, source, stamp)
    os.replace(source, dest)
    _chmod_owner_only(dest)
    return dest


def _restore_after_migration_failure(
    *,
    hardware: Path,
    legacy: Path,
    hardware_existed: bool,
    hardware_backup: Path | None,
    legacy_backup: Path | None,
) -> list[str]:
    errors: list[str] = []
    try:
        if hardware_existed:
            if hardware_backup and hardware_backup.exists():
                _atomic_copy_bytes(hardware_backup, hardware)
            elif not hardware.exists():
                errors.append("missing hardware backup")
        elif hardware.exists():
            hardware.unlink()
    except Exception as exc:
        errors.append(f"hardware restore failed: {_validation_error_summary(exc)}")

    try:
        if legacy_backup and legacy_backup.exists():
            _atomic_copy_bytes(legacy_backup, legacy)
        elif not legacy.exists():
            errors.append("missing legacy backup")
    except Exception as exc:
        errors.append(f"legacy restore failed: {_validation_error_summary(exc)}")

    return errors


def _profile_template(root: Path, profile: str, model_path: Path | None) -> tuple[str, Path]:
    selected = profile
    if profile == "auto":
        detected = detect_platform_profile(model_path=model_path or Path("/proc/device-tree/model"))
        if detected.kind is PlatformKind.RPI5:
            selected = "pi5"
        elif detected.kind is PlatformKind.RPI4B:
            selected = "pi4"
        else:
            raise RuntimeError(
                "Unable to auto-detect a supported Raspberry Pi profile; "
                "pass --profile pi5 or --profile pi4."
            )
    template_name = PROFILE_TEMPLATES[selected]
    template = root / "config" / template_name
    if not template.exists():
        raise FileNotFoundError(f"Template not found: {template}")
    return selected, template


def _validate_file(root: Path, hardware_path: Path) -> None:
    ConfigLoader(
        config_dir=str(root / "config"),
        hardware_path=str(hardware_path),
        hardware_local_path=str(root / "config" / ".hardware.local.disabled"),
    ).load()


def _validate_data(root: Path, data: dict[str, Any]) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".hardware-validate.", suffix=".yaml", dir=root / "config")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
        _validate_file(root, tmp_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def cmd_ensure(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if _fail_if_legacy_exists(root, "ensure"):
        return 1
    config_dir = root / "config"
    hardware = config_dir / "hardware.yaml"
    profile, template = _profile_template(root, args.profile, args.model_path)

    if hardware.exists():
        before = hardware.read_bytes()
        try:
            _validate_file(root, hardware)
        except Exception as exc:
            print(f"[hardware-config] validation failed: {_validation_error_summary(exc)}", file=sys.stderr)
            return 1
        after = hardware.read_bytes()
        if before != after:
            print("[hardware-config] existing hardware.yaml changed unexpectedly", file=sys.stderr)
            return 1
        _chmod_owner_only(hardware)
        print(
            "[hardware-config] preserved existing config/hardware.yaml "
            f"(profile={profile}, bytes={len(after)})"
        )
        return 0

    _atomic_copy_bytes(template, hardware)
    try:
        _validate_file(root, hardware)
    except Exception as exc:
        hardware.unlink(missing_ok=True)
        print(f"[hardware-config] template validation failed: {_validation_error_summary(exc)}", file=sys.stderr)
        return 1
    print(
        "[hardware-config] created config/hardware.yaml "
        f"from config/{template.name}; review wiring before SIM_MODE=0"
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if _fail_if_legacy_exists(root, "validate"):
        return 1
    hardware = root / "config" / "hardware.yaml"
    try:
        _validate_file(root, hardware)
    except Exception as exc:
        print(f"[hardware-config] validation failed: {_validation_error_summary(exc)}", file=sys.stderr)
        return 1
    print(f"[hardware-config] validated {hardware.relative_to(root)}")
    return 0


def cmd_migrate_legacy(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    config_dir = root / "config"
    hardware = config_dir / "hardware.yaml"
    legacy = _legacy_path(root)
    backup_dir = args.backup_dir.resolve() if args.backup_dir else root / "backups" / "hardware-config"

    if not legacy.exists():
        print("[hardware-config] no legacy config/hardware.local.yaml found")
        if hardware.exists():
            return cmd_validate(args)
        return cmd_ensure(args)

    profile, template = _profile_template(root, args.profile, args.model_path)
    try:
        base = _load_yaml(hardware) if hardware.exists() else _load_yaml(template)
        local = _load_yaml(legacy)
        merged = _deep_merge(base, local)
        _validate_data(root, merged)
    except Exception as exc:
        print(f"[hardware-config] migration validation failed: {_validation_error_summary(exc)}", file=sys.stderr)
        return 1

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backups: list[Path] = []
    hardware_existed = hardware.exists()
    hardware_backup: Path | None = None
    legacy_backup: Path | None = None
    try:
        if hardware_existed:
            hardware_backup = _copy_backup(hardware, backup_dir, stamp)
            backups.append(hardware_backup)
        legacy_backup = _move_to_backup(legacy, backup_dir, stamp)
        backups.append(legacy_backup)
        _atomic_write_yaml(hardware, merged)
        _validate_file(root, hardware)
    except Exception as exc:
        print(
            f"[hardware-config] migration failed after backups began: {_validation_error_summary(exc)}",
            file=sys.stderr,
        )
        restore_errors = _restore_after_migration_failure(
            hardware=hardware,
            legacy=legacy,
            hardware_existed=hardware_existed,
            hardware_backup=hardware_backup,
            legacy_backup=legacy_backup,
        )
        if restore_errors:
            print(
                "[hardware-config] rollback failed: " + "; ".join(restore_errors),
                file=sys.stderr,
            )
        else:
            print("[hardware-config] restored original files after failed migration", file=sys.stderr)
        return 1

    print(
        "[hardware-config] migrated legacy hardware.local.yaml into config/hardware.yaml "
        f"(profile={profile}, backups={len(backups)}, backup_dir={backup_dir})"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    ensure = sub.add_parser("ensure", help="Create config/hardware.yaml only if absent")
    ensure.add_argument(
        "--profile",
        choices=("auto", "pi5", "pi4"),
        default="auto",
        help="Hardware profile template to use",
    )
    ensure.add_argument("--model-path", type=Path, default=None, help="Platform model path")
    ensure.add_argument("--backup-dir", type=Path, default=None, help=argparse.SUPPRESS)
    ensure.add_argument("--update", action="store_true", help="Accepted for setup compatibility; never overwrites")
    ensure.set_defaults(func=cmd_ensure)

    validate = sub.add_parser("validate", help="Validate config/hardware.yaml")
    validate.add_argument("--profile", choices=("auto", "pi5", "pi4"), default="auto", help=argparse.SUPPRESS)
    validate.add_argument("--model-path", type=Path, default=None, help=argparse.SUPPRESS)
    validate.add_argument("--backup-dir", type=Path, default=None, help=argparse.SUPPRESS)
    validate.set_defaults(func=cmd_validate)

    migrate = sub.add_parser("migrate-legacy", help="One-time migration from hardware.local.yaml")
    migrate.add_argument(
        "--profile",
        choices=("auto", "pi5", "pi4"),
        default="auto",
        help="Hardware profile template to use",
    )
    migrate.add_argument("--model-path", type=Path, default=None, help="Platform model path")
    migrate.add_argument("--backup-dir", type=Path, default=None, help="Legacy migration backup dir")
    migrate.set_defaults(func=cmd_migrate_legacy)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"[hardware-config] failed: {_validation_error_summary(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
