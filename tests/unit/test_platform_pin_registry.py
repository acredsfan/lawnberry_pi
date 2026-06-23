from backend.src.hardware.pin_registry import build_pin_allocation_report
from backend.src.hardware.platform_profile import PlatformKind, PlatformProfile
from backend.src.models.hardware_config import HardwareConfig


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

