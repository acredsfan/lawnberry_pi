from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.src.core.config_loader import ConfigLoader
from backend.src.hardware.pin_registry import build_pin_allocation_report
from backend.src.hardware.platform_profile import PlatformKind, PlatformProfile
from backend.src.models.hardware_config import HardwareConfig

ROOT = Path(__file__).resolve().parents[2]


def _hardware(blade_in1: int, blade_in2: int, *, right_irq: int | None = None) -> HardwareConfig:
    return HardwareConfig.model_validate(
        {
            "imu_type": "bno085-uart",
            "blade_controller": "ibt-4",
            "blade": {
                "controller": "ibt-4",
                "allow_autonomous": True,
                "pins": {"in1": blade_in1, "in2": blade_in2},
            },
            "tof_config": {
                "left_shutdown_gpio": 22,
                "right_shutdown_gpio": 23,
                "right_interrupt_gpio": right_irq,
            },
        }
    )


def test_pi5_uart4_and_legacy_blade_pins_are_accepted():
    profile = PlatformProfile(PlatformKind.RPI5, "Raspberry Pi 5", (12, 13), True)
    report = build_pin_allocation_report(_hardware(24, 25), profile)
    assert report.ok


def test_pi4_uart4_conflicts_with_legacy_blade_gpio24():
    profile = PlatformProfile(PlatformKind.RPI4B, "Raspberry Pi 4 Model B", (24, 21), True)
    report = build_pin_allocation_report(_hardware(24, 25), profile)
    assert not report.ok
    assert report.conflicts[0].reason_code == "HARDWARE_PIN_CONFLICT"
    assert report.conflicts[0].gpio == 24


def test_pi4_rewired_blade_gpio26_27_is_accepted():
    profile = PlatformProfile(PlatformKind.RPI4B, "Raspberry Pi 4 Model B", (24, 21), True)
    report = build_pin_allocation_report(_hardware(26, 27), profile)
    assert report.ok


def test_pi5_tof_right_irq_gpio12_conflicts_with_uart4():
    profile = PlatformProfile(PlatformKind.RPI5, "Raspberry Pi 5", (12, 13), True)
    report = build_pin_allocation_report(_hardware(24, 25, right_irq=12), profile)
    assert not report.ok
    assert report.conflicts[0].gpio == 12


def _load_example(name: str) -> HardwareConfig:
    path = ROOT / "config" / name
    loader = ConfigLoader(
        config_dir=str(ROOT / "config"),
        hardware_path=str(path),
        hardware_local_path=str(ROOT / "config" / ".hardware.local.disabled"),
    )
    hardware, _limits = loader.load()
    return hardware


def _key_shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _key_shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_key_shape(value[0])] if value else []
    return "<scalar>"


def test_platform_examples_validate_and_are_conflict_free():
    pi5 = _load_example("hardware.pi5.example.yaml")
    pi4 = _load_example("hardware.pi4.example.yaml")

    assert build_pin_allocation_report(
        pi5,
        PlatformProfile(PlatformKind.RPI5, "Raspberry Pi 5", (12, 13), True),
    ).ok
    assert build_pin_allocation_report(
        pi4,
        PlatformProfile(PlatformKind.RPI4B, "Raspberry Pi 4 Model B", (24, 21), True),
    ).ok
    assert pi5.blade.allow_autonomous is False
    assert pi4.blade.allow_autonomous is False


def test_platform_examples_have_same_schema_except_platform_pins():
    pi5_path = ROOT / "config" / "hardware.pi5.example.yaml"
    pi4_path = ROOT / "config" / "hardware.pi4.example.yaml"
    pi5_raw = yaml.safe_load(pi5_path.read_text(encoding="utf-8"))
    pi4_raw = yaml.safe_load(pi4_path.read_text(encoding="utf-8"))

    assert _key_shape(pi5_raw) == _key_shape(pi4_raw)

    pi5_raw["blade"]["pins"] = {"in1": 0, "in2": 0}
    pi4_raw["blade"]["pins"] = {"in1": 0, "in2": 0}
    assert pi5_raw == pi4_raw


@pytest.mark.parametrize("name", ["hardware.pi5.example.yaml", "hardware.pi4.example.yaml"])
def test_platform_examples_do_not_contain_live_victron_secrets(name: str):
    raw = yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8"))
    victron = raw["victron"]

    assert victron["enabled"] is False
    assert victron["device_id"] is None
    assert victron["device_key"] is None
    assert victron["encryption_key"] is None
