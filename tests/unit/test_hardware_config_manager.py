from __future__ import annotations

import stat
from pathlib import Path

import yaml

from backend.src.core.config_loader import ConfigLoader
from scripts import manage_hardware_config

ROOT = Path(__file__).resolve().parents[2]


def _stage_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    config = root / "config"
    config.mkdir(parents=True)
    for name in ("hardware.pi5.example.yaml", "hardware.pi4.example.yaml", "limits.yaml"):
        (config / name).write_bytes((ROOT / "config" / name).read_bytes())
    return root


def _validate(root: Path) -> None:
    ConfigLoader(
        config_dir=str(root / "config"),
        hardware_path=str(root / "config" / "hardware.yaml"),
        hardware_local_path=str(root / "config" / ".hardware.local.disabled"),
    ).load()


def test_ensure_auto_pi5_creates_secure_valid_config(tmp_path: Path):
    root = _stage_root(tmp_path)
    model = tmp_path / "model"
    model.write_text("Raspberry Pi 5 Model B Rev 1.0", encoding="utf-8")

    rc = manage_hardware_config.main(
        ["--root", str(root), "ensure", "--profile", "auto", "--model-path", str(model)]
    )

    hardware = root / "config" / "hardware.yaml"
    assert rc == 0
    assert hardware.exists()
    assert stat.S_IMODE(hardware.stat().st_mode) == 0o600
    _validate(root)
    data = yaml.safe_load(hardware.read_text(encoding="utf-8"))
    assert data["blade"]["pins"] == {"in1": 24, "in2": 25}


def test_ensure_auto_pi4_selects_pi4_template(tmp_path: Path):
    root = _stage_root(tmp_path)
    model = tmp_path / "model"
    model.write_text("Raspberry Pi 4 Model B Rev 1.5", encoding="utf-8")

    rc = manage_hardware_config.main(
        ["--root", str(root), "ensure", "--profile", "auto", "--model-path", str(model)]
    )

    data = yaml.safe_load((root / "config" / "hardware.yaml").read_text(encoding="utf-8"))
    assert rc == 0
    assert data["blade"]["pins"] == {"in1": 26, "in2": 27}


def test_ensure_unknown_auto_requires_explicit_profile(tmp_path: Path):
    root = _stage_root(tmp_path)
    model = tmp_path / "model"
    model.write_text("Generic Linux", encoding="utf-8")

    rc = manage_hardware_config.main(
        ["--root", str(root), "ensure", "--profile", "auto", "--model-path", str(model)]
    )

    assert rc == 1
    assert not (root / "config" / "hardware.yaml").exists()


def test_ensure_preserves_existing_hardware_byte_for_byte(tmp_path: Path):
    root = _stage_root(tmp_path)
    hardware = root / "config" / "hardware.yaml"
    hardware.write_bytes((root / "config" / "hardware.pi5.example.yaml").read_bytes())
    before = hardware.read_bytes()

    rc = manage_hardware_config.main(["--root", str(root), "ensure", "--profile", "pi4", "--update"])

    assert rc == 0
    assert hardware.read_bytes() == before


def test_migrate_legacy_merges_once_backs_up_and_redacts_output(tmp_path: Path, capsys):
    root = _stage_root(tmp_path)
    hardware = root / "config" / "hardware.yaml"
    legacy = root / "config" / "hardware.local.yaml"
    backup_dir = tmp_path / "runtime-backups"
    hardware.write_bytes((root / "config" / "hardware.pi5.example.yaml").read_bytes())
    legacy.write_text(
        "victron:\n  enabled: true\n  encryption_key: unit-test-secret\n",
        encoding="utf-8",
    )

    rc = manage_hardware_config.main(
        [
            "--root",
            str(root),
            "migrate-legacy",
            "--profile",
            "pi5",
            "--backup-dir",
            str(backup_dir),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 0
    assert not legacy.exists()
    assert len(list(backup_dir.glob("hardware.yaml.*.bak"))) == 1
    assert len(list(backup_dir.glob("hardware.local.yaml.*.bak"))) == 1
    assert "unit-test-secret" not in captured.out
    assert "unit-test-secret" not in captured.err
    _validate(root)
    merged = yaml.safe_load(hardware.read_text(encoding="utf-8"))
    assert merged["victron"]["enabled"] is True
    assert merged["victron"]["encryption_key"] == "unit-test-secret"
    assert stat.S_IMODE(hardware.stat().st_mode) == 0o600


def test_migrate_legacy_failure_leaves_originals_unchanged(tmp_path: Path, capsys):
    root = _stage_root(tmp_path)
    hardware = root / "config" / "hardware.yaml"
    legacy = root / "config" / "hardware.local.yaml"
    hardware.write_bytes((root / "config" / "hardware.pi5.example.yaml").read_bytes())
    legacy.write_text("victron:\n  unexpected_secret_field: unit-test-secret\n", encoding="utf-8")
    before_hardware = hardware.read_bytes()
    before_legacy = legacy.read_bytes()

    rc = manage_hardware_config.main(
        ["--root", str(root), "migrate-legacy", "--profile", "pi5"]
    )
    captured = capsys.readouterr()

    assert rc == 1
    assert hardware.read_bytes() == before_hardware
    assert legacy.read_bytes() == before_legacy
    assert "unit-test-secret" not in captured.out
    assert "unit-test-secret" not in captured.err
