from __future__ import annotations

import sys
from pathlib import Path

import pytest

WATCHDOG_SRC = Path("/opt/wifi-watchdog/src")


def _load_watchdog_modules(monkeypatch):
    if not WATCHDOG_SRC.exists():
        pytest.skip("/opt/wifi-watchdog source package is not installed on this host")
    monkeypatch.syspath_prepend(str(WATCHDOG_SRC))
    for name in list(sys.modules):
        if name == "watchdog" or name.startswith("watchdog."):
            sys.modules.pop(name)
    from watchdog import recovery_steps
    from watchdog.config import Config
    from watchdog.escalation import EscalationManager
    from watchdog.metrics import ClassificationResult, HealthState

    return Config, EscalationManager, ClassificationResult, HealthState, recovery_steps


def test_t9_disabled_wifi_watchdog_tiers_advance_without_stalling(
    tmp_path,
    monkeypatch,
):
    (
        Config,
        EscalationManager,
        ClassificationResult,
        HealthState,
        recovery_steps,
    ) = _load_watchdog_modules(monkeypatch)

    invoked: list[str] = []
    monkeypatch.setattr(recovery_steps, "refresh_dhcp", lambda cfg: invoked.append("refresh_dhcp") or True)
    monkeypatch.setattr(
        recovery_steps,
        "cycle_interface",
        lambda cfg: invoked.append("cycle_interface") or True,
    )
    monkeypatch.setattr(
        recovery_steps,
        "reset_usb_device",
        lambda cfg, tier: invoked.append("reset_usb_device") or True,
    )
    monkeypatch.setattr(
        recovery_steps,
        "reboot_system",
        lambda cfg: invoked.append("reboot") or True,
    )

    cfg = Config.from_dict(
        {
            "paths": {
                "state_dir": str(tmp_path),
                "action_history": str(tmp_path / "action_history.log"),
                "status_json": str(tmp_path / "status.json"),
            },
            "limits": {
                "max_reboots_per_day": 10,
                "min_uptime_before_reboot": 0,
                "min_seconds_between_reboots": 0,
            },
            "escalation": {
                "tiers": [
                    {"name": "refresh_dhcp", "enabled": False, "min_interval_seconds": 0},
                    {
                        "name": "cycle_interface",
                        "enabled": False,
                        "min_interval_seconds": 0,
                    },
                    {
                        "name": "reset_usb_device",
                        "enabled": True,
                        "min_interval_seconds": 0,
                    },
                    {"name": "reboot", "enabled": True, "min_interval_seconds": 0},
                ],
            },
        }
    )
    manager = EscalationManager(cfg)
    lost = ClassificationResult(
        state=HealthState.LOST,
        fail_ratio=1.0,
        consecutive_fail_packets=10,
        rssi=-90,
    )

    assert manager.maybe_escalate(lost) == "reset_usb_device"
    assert manager.maybe_escalate(lost) == "reboot"
    assert invoked == ["reset_usb_device", "reboot"]
